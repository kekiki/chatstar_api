"""Single-line application logs with request correlation and safe diagnostics."""
import json
import logging
import os
import re
import sys
from collections import deque
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from traceback import walk_tb
from uuid import uuid4

from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
request_logger = logging.getLogger("app.request")

# Structured events accept diagnostic metadata, not headers, credentials or payloads.
EVENT_FIELDS = frozenset({
    "accepted", "amount", "asset_type", "call_id", "call_type", "close_code", "diamonds_granted", "diamonds_revoked",
    "duration_ms", "environment", "error_count", "error_type", "error_types", "gift_id", "google_order_id",
    "google_status", "login_method", "method", "missing_fields", "notification_type", "operation", "order_no",
    "order_status", "outcome", "package_name", "product_id", "provider_status", "purchase_state", "reason",
    "refund_type", "refunded", "route", "sku", "status", "transaction_type", "user_id", "voided_checked",
})
LEVELS = {name: getattr(logging, name) for name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")}
_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"})
_URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s\"'<>]+")
_QUERY = re.compile(r"(/[^\s\"'<>?]*)\?[^\s\"'<>]*")
_TOKEN_PATH = re.compile(r"(?i)(/tokens/)[^\s/\"'<>]+")
_CREDENTIAL = re.compile(
    r"(?i)\b(?:authorization|bearer|x-rtdn-secret|x-cron-secret|secret|(?:purchase|access|refresh|firebase|id)[_-]?token|"
    r"token|password|(?:api|private)[_-]?key)\b[\"']?(?:\s*[:=]\s*|\s+)(?:bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def redact(text: str) -> str:
    """Defense in depth for plain messages from the server and libraries."""
    text = _URL.sub("[url]", text)
    text = _QUERY.sub(r"\1?[redacted]", text)
    text = _TOKEN_PATH.sub(r"\1[redacted]", text)
    return _JWT.sub("[redacted]", _CREDENTIAL.sub("[redacted]", text))


def log_event(logger: logging.Logger, level: int, event: str, *, exc_info: bool = False, **fields) -> None:
    if logger.isEnabledFor(level):
        # Keep raw exception text out of fallback/default Python handlers, too.
        logger.log(level, event, extra={"event_fields": fields, "event_exception": sys.exc_info() if exc_info else None},
                   stacklevel=2)


class AppLogFormatter(logging.Formatter):
    def __init__(self, *, as_json: bool):
        super().__init__()
        self.as_json = as_json

    def format(self, record: logging.LogRecord) -> str:
        fields = {}
        for key, value in getattr(record, "event_fields", {}).items():
            if key not in EVENT_FIELDS or value is None:
                continue
            if isinstance(value, str):
                fields[key] = redact(value)[:256]
            elif isinstance(value, (bool, int, float)):
                fields[key] = value
            elif key in {"error_types", "missing_fields"} and isinstance(value, list):
                fields[key] = [redact(item)[:64] for item in value[:16] if isinstance(item, str)]
        data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
        }
        request_id = request_id_var.get()
        if request_id:
            data["request_id"] = request_id
        if hasattr(record, "event_fields"):
            data["event"] = record.getMessage()
        else:
            data["event"] = "log"
            data["message"] = redact(record.getMessage())[:2048]
        data.update(fields)
        exception = getattr(record, "event_exception", None) or record.exc_info
        if exception and exception[0]:
            error_class, _, tb = exception
            data["error_type"] = error_class.__name__
            # Error messages, SQL parameters, source lines and locals can contain secrets.
            data["stack"] = [
                f"{os.path.basename(frame.f_code.co_filename)}:{line}:{frame.f_code.co_name}"
                for frame, line in deque(walk_tb(tb), maxlen=12)
            ]
        if self.as_json:
            return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        timestamp, level, event = (data.pop(key) for key in ("timestamp", "level", "event"))
        details = " ".join(f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in data.items())
        return f"{timestamp} {level:<8} {event} {details}"


class _ServerNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.error":
            msg = str(record.msg)
            if ' - "WebSocket ' in msg or msg in {"connection open", "connection closed"}:
                # Our ASGI middleware replaces protocol logs that can include query credentials.
                return False
            if msg.lstrip().startswith(("Traceback (most recent call last):", "+ Exception Group Traceback")):
                # The server can echo a preformatted lifespan failure after app.startup_failed.
                return False
            if msg.startswith("Exception in ASGI application") and record.exc_info:
                return not getattr(record.exc_info[1], "_chatstar_request_logged", False)
        return True


def configure_logging() -> None:
    """Use stdout (collected by Fly) instead of adding log files on the instance."""
    level = LEVELS.get(os.getenv("LOG_LEVEL", "INFO").strip().upper(), logging.INFO)
    as_json = os.getenv("LOG_FORMAT", "console").strip().lower() == "json"
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(AppLogFormatter(as_json=as_json))
    handler.addFilter(_ServerNoiseFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.asgi"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    for name in ("httpx", "httpx2", "httpcore", "urllib3", "openai", "boto3", "botocore", "sqlalchemy"):
        logging.getLogger(name).setLevel(logging.WARNING)


async def log_validation_error(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # Top-level required schema fields are useful for a 422. Never log values,
    # arbitrary dict keys, or FastAPI/Pydantic's raw diagnostic payload.
    missing_fields = sorted({
        f"{source}.{field}"
        for error in errors if error["type"] == "missing" and len(error["loc"]) == 2
        for source, field in (error["loc"],)
        if source in ("body", "query", "header", "path", "cookie")
        and isinstance(field, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", field)
    })
    log_event(request_logger, logging.WARNING, "http.validation_failed",
              route=getattr(request.scope.get("route"), "path", None), error_count=len(errors),
              error_types=sorted({error["type"] for error in errors}), missing_fields=missing_fields or None)
    return await request_validation_exception_handler(request, exc)


class RequestLoggingMiddleware:
    """Outer ASGI layer so even framework-generated 500 responses get a request ID."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex
        context_token = request_id_var.set(request_id)
        start = perf_counter()
        http = scope["type"] == "http"
        status = None
        finished_at = None
        accepted = False
        close_code = None
        failed = False

        async def wrapped_send(message: Message) -> None:
            nonlocal status, accepted, close_code, finished_at
            kind = message["type"]
            if kind == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["x-request-id"] = request_id
            elif kind == "websocket.accept":
                accepted = True
            elif kind == "websocket.close":
                close_code = message.get("code", 1000)
            elif kind == "websocket.http.response.start":
                status = message["status"]
            await send(message)
            if kind == "http.response.body" and not message.get("more_body", False):
                finished_at = perf_counter()

        async def wrapped_receive() -> Message:
            nonlocal close_code
            message = await receive()
            if message["type"] == "websocket.disconnect":
                close_code = message.get("code", 1000)
            return message

        def request_fields() -> dict:
            route = getattr(scope.get("route"), "path", None) or "<unmatched>"
            fields = {"route": route, "status": status, "duration_ms": round(((finished_at or perf_counter()) - start) * 1000, 2)}
            if http:
                method = scope.get("method")
                fields["method"] = method if method in _HTTP_METHODS else "OTHER"
            else:
                fields.update(accepted=accepted, close_code=close_code)
            return fields

        event = "http.request" if http else "websocket.connection"
        try:
            await self.app(scope, receive if http else wrapped_receive, wrapped_send)
        except Exception as exc:
            failed = True
            if request_logger.isEnabledFor(logging.ERROR):
                log_event(request_logger, logging.ERROR, event, exc_info=True, outcome="error", **request_fields())
                try:
                    exc._chatstar_request_logged = True
                except (AttributeError, TypeError):
                    pass
            raise
        finally:
            try:
                if not failed:
                    fields = request_fields()
                    if not (http and fields["route"] == "/health" and status is not None and 200 <= status < 300):
                        if status is not None and status >= 500:
                            level = logging.ERROR
                        elif (status is not None and status >= 400) or (not http and not accepted):
                            level = logging.WARNING
                        else:
                            level = logging.INFO
                        log_event(request_logger, level, event, **fields)
            finally:
                request_id_var.reset(context_token)
