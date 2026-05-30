from __future__ import annotations

from datetime import datetime
import importlib.util
from types import SimpleNamespace
import sys
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NLU_SERVICE_PATH = PROJECT_ROOT / "app" / "services" / "nlu_service.py"

spec = importlib.util.spec_from_file_location("nlu_service", NLU_SERVICE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load NLUService from {NLU_SERVICE_PATH}")
nlu_service_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = nlu_service_module
spec.loader.exec_module(nlu_service_module)
NLUService = nlu_service_module.NLUService


class NLUServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = NLUService(enable_llm=False)
        self.base_time = datetime(2026, 5, 29, 15, 0, 0)
        self.timezone = "Asia/Shanghai"

    def parse(self, text: str):
        return self.service.parse(
            text,
            base_time=self.base_time,
            timezone=self.timezone,
        )

    def test_requested_voice_scenarios_use_rule_parse(self) -> None:
        base_time = datetime.fromisoformat("2026-05-30T12:00:00+08:00")

        create_result = self.service.parse(
            "明天下午三点提醒我交项目文档",
            base_time=base_time,
            timezone=self.timezone,
        )
        query_result = self.service.parse(
            "我今天有什么安排",
            base_time=base_time,
            timezone=self.timezone,
        )
        delete_result = self.service.parse(
            "删除明天的会议",
            base_time=base_time,
            timezone=self.timezone,
        )
        update_result = self.service.parse(
            "把下周三的会改到周四下午两点",
            base_time=base_time,
            timezone=self.timezone,
        )
        missing_time_result = self.service.parse(
            "提醒我交项目文档",
            base_time=base_time,
            timezone=self.timezone,
        )

        self.assertEqual(create_result.intent, "create_reminder")
        self.assertEqual(create_result.slots["title"], "交项目文档")
        self.assertEqual(create_result.slots["date_text"], "明天")
        self.assertEqual(create_result.slots["time_text"], "下午三点")
        self.assertEqual(create_result.slots["start_time"], "2026-05-31T15:00:00+08:00")
        self.assertEqual(create_result.missing_slots, [])

        self.assertEqual(query_result.intent, "query_event")
        self.assertEqual(query_result.slots["date_text"], "今天")
        self.assertEqual(query_result.slots["start_time"], "2026-05-30T00:00:00+08:00")

        self.assertEqual(delete_result.intent, "delete_event")
        self.assertEqual(delete_result.slots["target_event"], "会议")
        self.assertEqual(delete_result.slots["date_text"], "明天")

        self.assertEqual(update_result.intent, "update_event")
        self.assertEqual(update_result.slots["target_event"], "会")
        self.assertEqual(update_result.slots["date_text"], "周四")
        self.assertEqual(update_result.slots["time_text"], "下午两点")
        self.assertEqual(update_result.slots["start_time"], "2026-06-04T14:00:00+08:00")

        self.assertEqual(missing_time_result.intent, "create_reminder")
        self.assertEqual(missing_time_result.slots["title"], "交项目文档")
        self.assertEqual(missing_time_result.missing_slots, ["start_time"])

    def test_extract_reminder_slots(self) -> None:
        result = self.parse("明天下午三点提醒我交项目文档")

        self.assertEqual(result.intent, "create_reminder")
        self.assertEqual(result.slots["title"], "交项目文档")
        self.assertEqual(result.slots["date_text"], "明天")
        self.assertEqual(result.slots["time_text"], "下午三点")
        self.assertEqual(result.slots["start_time"], "2026-05-30T15:00:00+08:00")
        self.assertEqual(result.missing_slots, [])

    def test_extract_event_people_location_slots(self) -> None:
        result = self.parse("下周三上午十点和王老师在图书馆开会")

        self.assertEqual(result.intent, "create_event")
        self.assertEqual(result.slots["title"], "开会")
        self.assertEqual(result.slots["date_text"], "下周三")
        self.assertEqual(result.slots["time_text"], "上午十点")
        self.assertEqual(result.slots["start_time"], "2026-06-03T10:00:00+08:00")
        self.assertEqual(result.slots["location"], "图书馆")
        self.assertEqual(result.slots["participants"], ["王老师"])
        self.assertEqual(result.missing_slots, [])

    def test_extract_recurrence_slots(self) -> None:
        result = self.parse("每周一上午九点提醒我开例会")

        self.assertEqual(result.intent, "create_reminder")
        self.assertEqual(result.slots["title"], "开例会")
        self.assertEqual(result.slots["recurrence_text"], "每周一上午九点")
        self.assertEqual(result.slots["date_text"], "周一")
        self.assertEqual(result.slots["time_text"], "上午九点")
        self.assertEqual(result.slots["start_time"], "2026-06-01T09:00:00+08:00")
        self.assertEqual(result.missing_slots, [])

    def test_extract_update_slots(self) -> None:
        result = self.parse("把明天上午的会议改到下午三点")

        self.assertEqual(result.intent, "update_event")
        self.assertEqual(result.slots["target_event"], "会议")
        self.assertEqual(result.slots["date_text"], "明天")
        self.assertEqual(result.slots["time_text"], "下午三点")
        self.assertEqual(result.slots["start_time"], "2026-05-30T15:00:00+08:00")
        self.assertEqual(result.missing_slots, [])

    def test_extract_delete_slots(self) -> None:
        result = self.parse("删除明天的健身")

        self.assertEqual(result.intent, "delete_event")
        self.assertEqual(result.slots["target_event"], "健身")
        self.assertEqual(result.slots["date_text"], "明天")
        self.assertEqual(result.slots["start_time"], "2026-05-30T00:00:00+08:00")
        self.assertEqual(result.missing_slots, [])

    def test_missing_required_slots(self) -> None:
        result = self.parse("提醒我")

        self.assertEqual(result.intent, "create_reminder")
        self.assertEqual(result.missing_slots, ["title", "start_time"])

    def test_simple_intents(self) -> None:
        self.assertEqual(self.parse("确认").intent, "confirm")
        self.assertEqual(self.parse("不用了").intent, "deny")
        self.assertEqual(self.parse("撤销上一步").intent, "undo")
        self.assertEqual(self.parse("你能做什么").intent, "help")

    def test_unknown_has_missing_intent(self) -> None:
        result = self.parse("随便说一句")

        self.assertEqual(result.intent, "unknown")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.missing_slots, ["intent"])

    def test_uses_llm_structured_parse_when_available(self) -> None:
        class FakeLLMParseService:
            def parse(self, *args, **kwargs):
                return SimpleNamespace(
                    raw_text="补一句上下文",
                    intent="update_event",
                    confidence=0.92,
                    slots={
                        "target_event": "会议",
                        "date_text": "明天",
                        "time_text": "下午三点",
                        "start_time": "2026-05-30T15:00:00+08:00",
                    },
                    missing_slots=[],
                )

        service = NLUService(llm_parse_service=FakeLLMParseService())
        result = service.parse(
            "补一句上下文",
            base_time=self.base_time,
            timezone=self.timezone,
            conversation_context={"pending_intent": "update_event"},
        )

        self.assertEqual(result.intent, "update_event")
        self.assertEqual(result.confidence, 0.92)
        self.assertEqual(result.slots["target_event"], "会议")

    def test_falls_back_when_llm_parse_fails(self) -> None:
        class FailingLLMParseService:
            def parse(self, *args, **kwargs):
                raise RuntimeError("llm unavailable")

        service = NLUService(llm_parse_service=FailingLLMParseService())
        result = service.parse(
            "明天下午三点提醒我交项目文档",
            base_time=self.base_time,
            timezone=self.timezone,
        )

        self.assertEqual(result.intent, "create_reminder")
        self.assertEqual(result.slots["title"], "交项目文档")


if __name__ == "__main__":
    unittest.main()
