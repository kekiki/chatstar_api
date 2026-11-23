import io
import json
import logging
import os
import re
import unittest
from argparse import Namespace
from contextlib import contextmanager
from unittest.mock import patch
from zoneinfo import ZoneInfo

import anyio
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from app.logging_config import AppLogFormatter, RequestLoggingMiddleware, configure_logging, log_event, log_validation_error, request_id_var
from scripts.filter_logs import format_record, matches, read_records


@contextmanager
def configured_logs(level="INFO"):
    names = (None, "uvicorn", "uvicorn.error", "uvicorn.asgi", "uvicorn.access", "httpx", "httpx2", "httpcore",
             "urllib3", "openai", "boto3", "botocore", "sqlalchemy")
    snapshots = [(logger, logger.handlers[:], logger.level, logger.propagate) for logger in map(logging.getLogger, names)]
    stream = io.StringIO()
    try:
        with patch.dict(os.environ, {"LOG_FORMAT": "json", "LOG_LEVEL": level}), patch("sys.stdout", stream):
            configure_logging()
        yield stream
    finally:
        for logger, handlers, old_level, propagate in snapshots:
            logger.handlers[:] = handlers
            logger.setLevel(old_level)
            logger.propagate = propagate


def records(stream):
    return [json.loads(line) for line in stream.getvalue().splitlines()]


class RequestLoggingTests(unittest.TestCase):
    def setUp(self):
        api = FastAPI()
        api.add_exception_handler(RequestValidationError, log_validation_error)

        class Purchase(BaseModel):
            purchaseToken: str

        @api.post("/verify")
        async def verify(purchase: Purchase):
            return {"ok": True}

        @api.get("/health")
        async def health():
            return {"ok": True}

        @api.get("/items/{item_id}")
        async def item(item_id: int):
            log_event(logging.getLogger("app.tests"), logging.INFO, "item.read", user_id=item_id, secret="never-log-extra")
            return {"item": item_id}

        @api.get("/fail")
        async def fail():
            raise ValueError("raw-error-with-email@example.com")

        @api.websocket("/ws")
        async def ws(websocket: WebSocket):
            await websocket.accept()
            await websocket.close(code=1000)

        self.app = RequestLoggingMiddleware(api)
        self.client = self.enterContext(TestClient(self.app, raise_server_exceptions=False))

    def test_access_log_uses_route_template_and_correlates_business_event(self):
        with configured_logs() as stream:
            response = self.client.get("/items/42?secret=do-not-log", headers={"x-request-id": "untrusted-request-id"})
            self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        request_id = response.headers["x-request-id"]
        self.assertRegex(request_id, r"^[a-f0-9]{32}$")
        event, access = records(stream)
        self.assertEqual(event["event"], "item.read")
        self.assertEqual(access["event"], "http.request")
        self.assertEqual(access["route"], "/items/{item_id}")
        self.assertEqual(access["status"], 200)
        self.assertGreaterEqual(access["duration_ms"], 0)
        self.assertEqual({access["request_id"], event["request_id"]}, {request_id})
        self.assertIsNone(request_id_var.get())
        for private in ("do-not-log", "never-log-extra", "untrusted-request-id", "/items/42"):
            self.assertNotIn(private, stream.getvalue())

    def test_unhandled_error_keeps_request_id_and_safe_stack(self):
        with configured_logs() as stream:
            response = self.client.get("/fail")
        self.assertEqual(response.status_code, 500)
        event, = records(stream)
        self.assertEqual(event["status"], 500)
        self.assertEqual(event["request_id"], response.headers["x-request-id"])
        self.assertEqual(event["error_type"], "ValueError")
        self.assertEqual(event["level"], "ERROR")
        self.assertTrue(any(frame.endswith(":fail") for frame in event["stack"]))
        self.assertNotIn("raw-error-with-email", stream.getvalue())

    def test_http_client_errors_are_warnings_and_unmatched_paths_are_not_logged(self):
        with configured_logs() as stream:
            self.assertEqual(self.client.get("/items/not-an-int").status_code, 422)
            self.assertEqual(self.client.get("/private/unique-user-input?foo=bar").status_code, 404)
        validation, invalid, missing = records(stream)
        self.assertEqual(validation["request_id"], invalid["request_id"])
        self.assertEqual((invalid["status"], invalid["level"]), (422, "WARNING"))
        self.assertEqual((missing["status"], missing["route"]), (404, "<unmatched>"))
        self.assertNotIn("unique-user-input", stream.getvalue())
        self.assertNotIn("not-an-int", stream.getvalue())

    def test_validation_reports_missing_fields_without_payload(self):
        with configured_logs() as stream:
            response = self.client.post("/verify", json={"untrusted": "secret-payload-value"})
        validation, access = records(stream)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(validation["missing_fields"], ["body.purchaseToken"])
        self.assertEqual(validation["request_id"], access["request_id"])
        self.assertNotIn("secret-payload-value", stream.getvalue())
        self.assertNotIn("untrusted", stream.getvalue())

    def test_websocket_and_server_access_logs_do_not_expose_query_credentials(self):
        with configured_logs() as stream:
            logging.getLogger("uvicorn.access").info("POST /api/google/rtdn?secret=legacy-secret")
            logging.getLogger("uvicorn.error").error("Traceback (most recent call last):\nValueError: legacy-raw-lifespan-error")
            logging.getLogger("uvicorn.error").info('%s - "WebSocket %s" [accepted]', "client", "/ws?token=legacy-token")
            with self.client.websocket_connect("/ws?token=private-ws-token"):
                pass
        event, = records(stream)
        self.assertEqual((event["event"], event["route"], event["accepted"], event["close_code"]),
                         ("websocket.connection", "/ws", True, 1000))
        self.assertNotIn("legacy-", stream.getvalue())
        self.assertNotIn("private-ws-token", stream.getvalue())

    def test_concurrent_requests_keep_their_own_request_ids(self):
        import httpx

        api = FastAPI()

        @api.get("/parallel/{item_id}")
        async def parallel(item_id: int):
            await anyio.sleep(0)
            log_event(logging.getLogger("app.tests"), logging.INFO, "parallel", user_id=item_id)
            return {"item_id": item_id}

        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=RequestLoggingMiddleware(api)), base_url="http://test") as client:
                results = {}

                async def fetch(item_id):
                    response = await client.get(f"/parallel/{item_id}")
                    results[item_id] = response.headers["x-request-id"]

                async with anyio.create_task_group() as group:
                    for item_id in range(5):
                        group.start_soon(fetch, item_id)
                return results

        with configured_logs() as stream:
            results = anyio.run(run)
        events = {row["user_id"]: row["request_id"] for row in records(stream) if row["event"] == "parallel"}
        self.assertEqual(events, results)
        self.assertEqual(len(set(events.values())), 5)


class FormatterAndCLITests(unittest.TestCase):
    def test_plain_message_scrubbing_and_console_output(self):
        formatter = AppLogFormatter(as_json=False)
        record = logging.LogRecord("test", logging.WARNING, "", 1,
                                   'POST /api/google/rtdn?secret=abc123 Bearer xyz987 https://host/tokens/purchase789\nnext', (), None)
        output = formatter.format(record)
        for secret in ("abc123", "xyz987", "purchase789"):
            self.assertNotIn(secret, output)
        self.assertNotIn("\n", output)
        self.assertTrue(re.match(r"\d{4}-\d{2}-\d{2}T.*Z WARNING", output))

    def test_cli_handles_pretty_printed_fly_records_and_filters_both_order_ids(self):
        record = {"event": "refund.processed", "level": "INFO", "timestamp": "2026-11-23T09:00:00.000Z",
                  "order_no": "O1", "google_order_id": "GPA.test", "diamonds_revoked": 100}
        legacy = {"level": "warning", "message": "POST /api/google/rtdn?secret=legacy-value", "timestamp": record["timestamp"]}
        fly = json.dumps({"message": json.dumps(record), "instance": "123"}, indent=4)
        result = list(read_records(io.StringIO(f'{fly}\n{json.dumps(legacy, indent=4)}\n{json.dumps(record)}\n')))
        self.assertEqual(result[0], record)
        self.assertEqual(result[2], record)
        self.assertNotIn("legacy-value", result[1]["message"])
        for order in ("O1", "GPA.test"):
            args = Namespace(level="INFO", event=["refund"], route=None, request_id=None, order=order)
            self.assertEqual([row for row in result if matches(row, args)], [record, record])
            args.level = "WARNING"
            self.assertEqual([row for row in result if matches(row, args)], [])
        self.assertIn("17:00:00.000+08:00", format_record(record, ZoneInfo("Asia/Shanghai")))


if __name__ == "__main__":
    unittest.main()
