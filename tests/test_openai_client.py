import asyncio
import importlib.util
import json
from pathlib import Path
import runpy
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_client(base_url, debug=False):
    config = ModuleType("app.config")
    config.IS_DEBUG = debug
    config.OPENAI_API_KEY = "test-api-key"
    config.OPENAI_BASE_URL = base_url
    config.OPENAI_MODEL = "custom-model"
    spec = importlib.util.spec_from_file_location("client_under_test", ROOT / "app/openai_client.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"app.config": config}):
        spec.loader.exec_module(module)
    return module


class ConfigTests(unittest.TestCase):
    def load_config(self, **overrides):
        env = {
            "ENV_MODE": "production",
            "SECRET_KEY": "test",
            "DATABASE_URL": "test",
            **{key: "test" for key in (
                "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_ACCOUNT_ID",
                "R2_BUCKET_NAME", "R2_ENDPOINT", "R2_PUBLIC_DOMAIN",
            )},
            **overrides,
        }
        with patch.dict("os.environ", env, clear=True), patch("dotenv.load_dotenv"):
            return runpy.run_path(str(ROOT / "app/config.py"))

    def test_custom_settings_without_groq_key(self):
        config = self.load_config(
            OPENAI_API_KEY="custom-key",
            OPENAI_BASE_URL="https://compatible.example/v1",
            OPENAI_MODEL="custom-model",
        )
        self.assertEqual(config["OPENAI_API_KEY"], "custom-key")
        self.assertEqual(config["OPENAI_BASE_URL"], "https://compatible.example/v1")
        self.assertEqual(config["OPENAI_MODEL"], "custom-model")

    def test_defaults(self):
        config = self.load_config(OPENAI_API_KEY="test-key")
        self.assertEqual(config["OPENAI_BASE_URL"], "https://api.openai.com/v1")
        self.assertEqual(config["OPENAI_MODEL"], "gpt-4o-mini")

    def test_production_requires_api_key(self):
        with self.assertRaisesRegex(Exception, "OPENAI_API_KEY"):
            self.load_config()

    def test_debug_does_not_require_api_key(self):
        config = self.load_config(ENV_MODE="develop")
        self.assertEqual(config["OPENAI_API_KEY"], "")


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.status = 200
        test = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                test.requests.append((self.path, self.headers["Authorization"], body))
                self.send_response(test.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if test.status == 200:
                    payload = {
                        "id": "test-completion", "object": "chat.completion", "created": 0,
                        "model": "custom-model",
                        "choices": [{"index": 0, "finish_reason": "stop", "message": {
                            "role": "assistant", "content": "Hello from compatible API!",
                        }}],
                    }
                else:
                    payload = {"error": {"message": "Test error", "type": "test_error"}}
                self.wfile.write(json.dumps(payload).encode())

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.module = load_client(f"http://127.0.0.1:{self.server.server_port}/custom/v1")
        self.client = self.module.ai_client
        # 错误分支无需等待 SDK 自动重试。
        self.client.client.max_retries = 0

    async def asyncTearDown(self):
        await self.client.client.close()
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()
        self.thread.join()

    async def test_custom_endpoint_key_model_and_messages(self):
        history = [{"role": "assistant", "content": "Previous reply"}]
        reply = await self.client.chat_endpoint("Hi", "fr", "Test persona", history)
        self.assertEqual(reply, "Hello from compatible API!")
        path, authorization, body = self.requests[0]
        self.assertEqual(path, "/custom/v1/chat/completions")
        self.assertEqual(authorization, "Bearer test-api-key")
        self.assertEqual(body["model"], "custom-model")
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertIn("Test persona", body["messages"][0]["content"])
        self.assertIn("français", body["messages"][0]["content"])
        self.assertEqual(body["messages"][1:], history + [{"role": "user", "content": "Hi"}])
        self.assertEqual(len(history), 1)
        self.assertFalse(body["stream"])

    async def test_api_errors_return_none(self):
        for status in (429, 401, 500):
            with self.subTest(status=status):
                self.status = status
                reply = await self.client.chat_endpoint("Hi", "en", "Persona", [])
                self.assertIsNone(reply)

    async def test_connection_error_returns_none(self):
        with patch.object(self.client.client.chat.completions, "create", new=AsyncMock(side_effect=OSError("offline"))):
            self.assertIsNone(await self.client.chat_endpoint("Hi", "en", "Persona", []))

    async def test_debug_skips_sdk_and_requests(self):
        with patch("openai.AsyncOpenAI") as sdk:
            module = load_client("https://unused.example/v1", debug=True)
            reply = await module.ai_client.chat_endpoint("Hi", "en", "Persona", [])
        sdk.assert_not_called()
        self.assertIn(reply, module.DEBUG_MESSAGES)
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
