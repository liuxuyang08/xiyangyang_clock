from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

from test_voice_api import (
    FakeCalendarService,
    FakeConflictService,
    FakeDialogService,
    FakeReminderService,
    FakeSession,
    FakeVoiceCommandLogService,
    fake_event,
    voice_api,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NLU_SERVICE_PATH = PROJECT_ROOT / "app" / "services" / "nlu_service.py"
TIME_PARSER_PATH = PROJECT_ROOT / "app" / "services" / "time_parser.py"


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {module_name} from {path}")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


NLUService = load_module("voice_api_basic_nlu_service", NLU_SERVICE_PATH).NLUService
TimeParser = load_module("voice_api_basic_time_parser", TIME_PARSER_PATH).TimeParser


class VoiceApiBasicScenariosTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.base_time = datetime(2026, 5, 30, 12, 0, 0)
        self.timezone = "Asia/Shanghai"
        self.nlu_service = NLUService(enable_llm=False)
        self.time_parser = TimeParser()

    def request_payload(self, text: str, session_id: str = "session-1") -> SimpleNamespace:
        return SimpleNamespace(
            user_id="u001",
            session_id=session_id,
            text=text,
            timezone=self.timezone,
            client_time=self.base_time,
        )

    async def test_create_event_from_voice_command(self) -> None:
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService()
        reminder_service = FakeReminderService()
        log_service = FakeVoiceCommandLogService()

        response = await voice_api.handle_voice_command(
            self.request_payload("明天下午三点提醒我交项目文档"),
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=reminder_service,
            nlu_service=self.nlu_service,
            time_parser=self.time_parser,
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "event_created")
        self.assertFalse(response.need_user_reply)
        self.assertIn("交项目文档", response.reply)
        self.assertEqual(response.data["event"]["title"], "交项目文档")
        self.assertEqual(response.data["reminder"]["offset_minutes"], 0)
        self.assertEqual([call[0] for call in log_service.calls], ["received", "parsed", "success"])
        self.assertTrue(session.committed)

    async def test_query_event_defaults_to_today(self) -> None:
        events = [
            fake_event("event-1", "项目讨论", datetime(2026, 5, 30, 10, 0, 0)),
            fake_event("event-2", "提交文档", datetime(2026, 5, 30, 15, 0, 0)),
            fake_event("event-3", "健身", datetime(2026, 5, 30, 19, 0, 0)),
        ]
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService(events=events)
        log_service = FakeVoiceCommandLogService()

        response = await voice_api.handle_voice_command(
            self.request_payload("我今天有什么安排", session_id="session-query"),
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=FakeReminderService(),
            nlu_service=self.nlu_service,
            time_parser=self.time_parser,
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "events_queried")
        self.assertEqual(response.data["event_count"], 3)
        self.assertIn("3 个安排", response.reply)
        self.assertIn("项目讨论", response.reply)
        self.assertIn("提交文档", response.reply)
        self.assertIn("健身", response.reply)

    async def test_delete_event_requires_confirmation_before_soft_delete(self) -> None:
        event = fake_event("event-1", "会议", datetime(2026, 5, 31, 10, 0, 0))
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService(events=[event])
        reminder_service = FakeReminderService()
        log_service = FakeVoiceCommandLogService()

        first_response = await voice_api.handle_voice_command(
            self.request_payload("删除明天的会议", session_id="session-delete"),
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=reminder_service,
            nlu_service=self.nlu_service,
            time_parser=self.time_parser,
            voice_command_log_service=log_service,
        )

        self.assertEqual(first_response.action, "delete_event_need_confirm")
        self.assertTrue(first_response.need_user_reply)
        self.assertIn("请确认是否删除", first_response.reply)
        self.assertIsNotNone(dialog_service.created_state)
        self.assertEqual(dialog_service.created_state.status, "need_confirm")
        self.assertEqual(dialog_service.created_state.pending_intent, "delete_event")

        dialog_service.current_state = dialog_service.created_state
        confirm_response = await voice_api.handle_voice_command(
            self.request_payload("确认", session_id="session-delete"),
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=reminder_service,
            nlu_service=self.nlu_service,
            time_parser=self.time_parser,
            voice_command_log_service=log_service,
        )

        self.assertEqual(confirm_response.action, "event_deleted")
        self.assertFalse(confirm_response.need_user_reply)
        self.assertEqual(calendar_service.soft_deleted_event_id, "event-1")
        self.assertEqual(reminder_service.cancelled_event_id, "event-1")
        self.assertEqual(confirm_response.data["event"]["status"], "deleted")
        self.assertTrue(dialog_service.completed)

    async def test_update_event_requires_selection_and_confirmation(self) -> None:
        event = fake_event("event-1", "会", datetime(2026, 6, 3, 10, 0, 0))
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService(events=[event])
        reminder_service = FakeReminderService()
        log_service = FakeVoiceCommandLogService()

        first_response = await voice_api.handle_voice_command(
            self.request_payload("把下周三的会改到周四下午两点", session_id="session-update"),
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=reminder_service,
            nlu_service=self.nlu_service,
            time_parser=self.time_parser,
            voice_command_log_service=log_service,
        )

        self.assertEqual(first_response.action, "update_event_need_confirm")
        self.assertTrue(first_response.need_user_reply)
        self.assertIn("是否将它改到周四下午两点", first_response.reply)
        self.assertIsNotNone(dialog_service.created_state)
        self.assertEqual(dialog_service.created_state.status, "need_confirm")

        dialog_service.current_state = dialog_service.created_state
        confirm_response = await voice_api.handle_voice_command(
            self.request_payload("确认", session_id="session-update"),
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=reminder_service,
            nlu_service=self.nlu_service,
            time_parser=self.time_parser,
            voice_command_log_service=log_service,
        )

        self.assertEqual(confirm_response.action, "event_updated")
        self.assertFalse(confirm_response.need_user_reply)
        self.assertEqual(calendar_service.updated_event_id, "event-1")
        self.assertEqual(
            calendar_service.updated_event_payload.start_time.isoformat(),
            "2026-06-04T14:00:00+08:00",
        )
        self.assertEqual(confirm_response.data["event"]["location"], None)
        self.assertTrue(dialog_service.completed)

    async def test_missing_time_triggers_followup(self) -> None:
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService()
        reminder_service = FakeReminderService()
        log_service = FakeVoiceCommandLogService()

        response = await voice_api.handle_voice_command(
            self.request_payload("提醒我交项目文档", session_id="session-followup"),
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=reminder_service,
            nlu_service=self.nlu_service,
            time_parser=self.time_parser,
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "need_more_info")
        self.assertTrue(response.need_user_reply)
        self.assertIn("具体时间", response.reply)
        self.assertIn("start_time", response.data["missing_slots"])
        self.assertEqual(dialog_service.created_state.pending_intent, "create_event")
        self.assertTrue(session.committed)


if __name__ == "__main__":
    unittest.main()
