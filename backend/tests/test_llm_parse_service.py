from __future__ import annotations

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LLM_PARSE_SERVICE_PATH = PROJECT_ROOT / "app" / "services" / "llm_parse_service.py"

spec = importlib.util.spec_from_file_location("llm_parse_service", LLM_PARSE_SERVICE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load LLMParseService from {LLM_PARSE_SERVICE_PATH}")
llm_parse_service_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = llm_parse_service_module
spec.loader.exec_module(llm_parse_service_module)
LLMParseService = llm_parse_service_module.LLMParseService


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.request_body: dict | None = None
        self.request_headers: dict | None = None
        self.request_url: str | None = None

    def post(self, *args, **kwargs) -> FakeResponse:
        self.request_url = args[0] if args else kwargs.get("url")
        self.request_headers = kwargs.get("headers")
        self.request_body = kwargs.get("json")
        return FakeResponse(self.payload)


class LLMParseServiceTestCase(unittest.TestCase):
    def test_returns_none_without_api_key(self) -> None:
        service = LLMParseService(api_key="")

        result = service.parse("明天下午三点开会")

        self.assertIsNone(result)

    def test_parses_structured_response(self) -> None:
        content = json.dumps(
            {
                "intent": "create_event",
                "confidence": 0.91,
                "slots": {
                    "title": "开会",
                    "date_text": "明天",
                    "time_text": "下午三点",
                    "start_time": "2026-05-30T15:00:00+08:00",
                },
                "missing_slots": [],
            },
            ensure_ascii=False,
        )
        fake_client = FakeClient(
            {
                "choices": [
                    {
                        "message": {
                            "content": content,
                        },
                    },
                ],
            }
        )
        service = LLMParseService(api_key="test-key", client=fake_client)

        result = service.parse(
            "明天下午三点开会",
            conversation_context={"pending_intent": "create_event"},
            base_time=datetime(2026, 5, 29, 15, 0, 0),
            timezone="Asia/Shanghai",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.intent, "create_event")
        self.assertEqual(result.confidence, 0.91)
        self.assertEqual(result.slots["title"], "开会")
        self.assertEqual(result.missing_slots, [])
        self.assertIsNotNone(fake_client.request_body)
        self.assertEqual(fake_client.request_body["response_format"], {"type": "json_object"})

    def test_uses_custom_api_base_url(self) -> None:
        content = json.dumps(
            {
                "intent": "help",
                "confidence": 0.8,
                "slots": {},
                "missing_slots": [],
            },
            ensure_ascii=False,
        )
        fake_client = FakeClient(
            {
                "choices": [
                    {
                        "message": {
                            "content": content,
                        },
                    },
                ],
            }
        )
        service = LLMParseService(
            api_key="proxy-key",
            api_base_url="https://proxy.example.com/v1/",
            client=fake_client,
        )

        result = service.parse("甯姪")

        self.assertIsNotNone(result)
        self.assertEqual(
            fake_client.request_url,
            "https://proxy.example.com/v1/chat/completions",
        )
        self.assertIsNotNone(fake_client.request_headers)
        self.assertEqual(fake_client.request_headers["Authorization"], "Bearer proxy-key")


if __name__ == "__main__":
    unittest.main()
