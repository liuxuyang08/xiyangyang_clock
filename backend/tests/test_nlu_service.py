from __future__ import annotations

import importlib.util
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
        self.service = NLUService()

    def test_create_event(self) -> None:
        result = self.service.parse("添加明天下午三点开会")

        self.assertEqual(result.intent, "create_event")
        self.assertGreaterEqual(result.confidence, 0.8)
        self.assertEqual(result.slots["time_text"], "明天下午三点")
        self.assertEqual(result.slots["title"], "开会")
        self.assertEqual(result.missing_slots, [])

    def test_query_event(self) -> None:
        result = self.service.parse("今天有什么安排")

        self.assertEqual(result.intent, "query_event")
        self.assertIn("time_text", result.slots)
        self.assertEqual(result.missing_slots, [])

    def test_update_event(self) -> None:
        result = self.service.parse("把开会改到明天上午十点")

        self.assertEqual(result.intent, "update_event")
        self.assertEqual(result.slots["time_text"], "明天上午十点")
        self.assertIn("开会", result.slots["target_text"])

    def test_delete_event(self) -> None:
        result = self.service.parse("删除明天的开会")

        self.assertEqual(result.intent, "delete_event")
        self.assertIn("开会", result.slots["target_text"])

    def test_create_reminder(self) -> None:
        result = self.service.parse("提醒我一小时后喝水")

        self.assertEqual(result.intent, "create_reminder")
        self.assertEqual(result.slots["time_text"], "一小时后")
        self.assertEqual(result.slots["title"], "喝水")

    def test_cancel_reminder(self) -> None:
        result = self.service.parse("取消提醒喝水")

        self.assertEqual(result.intent, "cancel_reminder")
        self.assertEqual(result.slots["target_text"], "喝水")

    def test_confirm(self) -> None:
        for text in ["确认", "是的", "对"]:
            with self.subTest(text=text):
                self.assertEqual(self.service.parse(text).intent, "confirm")

    def test_deny(self) -> None:
        for text in ["不用了", "取消", "不是"]:
            with self.subTest(text=text):
                self.assertEqual(self.service.parse(text).intent, "deny")

    def test_undo(self) -> None:
        result = self.service.parse("撤销上一步")

        self.assertEqual(result.intent, "undo")

    def test_help(self) -> None:
        result = self.service.parse("你能做什么")

        self.assertEqual(result.intent, "help")

    def test_unknown_has_missing_intent(self) -> None:
        result = self.service.parse("随便说一句")

        self.assertEqual(result.intent, "unknown")
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.missing_slots, ["intent"])


if __name__ == "__main__":
    unittest.main()
