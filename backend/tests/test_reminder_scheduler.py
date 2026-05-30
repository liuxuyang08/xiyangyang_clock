from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import logging
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEDULER_PATH = PROJECT_ROOT / "app" / "services" / "reminder_scheduler.py"


class ImportedWebSocketManager:
    def __init__(self) -> None:
        self.sent_count = 1
        self.messages = []

    async def broadcast_to_user_sessions(self, user_id: str, message: dict):
        self.messages.append((user_id, message))
        return self.sent_count


def install_import_stubs() -> dict[str, ModuleType | None]:
    originals = {
        name: sys.modules.get(name)
        for name in [
            "app",
            "app.core",
            "app.core.config",
            "app.db",
            "app.db.session",
            "app.models",
            "app.models.event",
            "app.models.reminder",
            "app.services",
            "app.services.reminder_service",
            "app.services.websocket_manager",
        ]
    }

    app_module = ModuleType("app")
    app_core_module = ModuleType("app.core")
    app_core_config_module = ModuleType("app.core.config")
    app_core_config_module.get_settings = lambda: SimpleNamespace(
        reminder_scan_interval=60,
        timezone="Asia/Shanghai",
    )
    app_db_module = ModuleType("app.db")
    app_db_session_module = ModuleType("app.db.session")
    app_db_session_module.SessionLocal = None
    app_models_module = ModuleType("app.models")
    app_models_event_module = ModuleType("app.models.event")
    app_models_reminder_module = ModuleType("app.models.reminder")
    app_services_module = ModuleType("app.services")
    app_services_reminder_module = ModuleType("app.services.reminder_service")
    app_services_websocket_module = ModuleType("app.services.websocket_manager")
    app_models_event_module.Event = object
    app_models_reminder_module.Reminder = object
    app_services_reminder_module.ReminderService = object
    app_services_websocket_module.websocket_manager = ImportedWebSocketManager()

    sys.modules["app"] = app_module
    sys.modules["app.core"] = app_core_module
    sys.modules["app.core.config"] = app_core_config_module
    sys.modules["app.db"] = app_db_module
    sys.modules["app.db.session"] = app_db_session_module
    sys.modules["app.models"] = app_models_module
    sys.modules["app.models.event"] = app_models_event_module
    sys.modules["app.models.reminder"] = app_models_reminder_module
    sys.modules["app.services"] = app_services_module
    sys.modules["app.services.reminder_service"] = app_services_reminder_module
    sys.modules["app.services.websocket_manager"] = app_services_websocket_module

    return originals


def restore_import_stubs(originals: dict[str, ModuleType | None]) -> None:
    for name, module in originals.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


original_modules = install_import_stubs()
spec = importlib.util.spec_from_file_location("reminder_scheduler", SCHEDULER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load reminder scheduler from {SCHEDULER_PATH}")
reminder_scheduler_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reminder_scheduler_module
spec.loader.exec_module(reminder_scheduler_module)
restore_import_stubs(original_modules)

ReminderScheduler = reminder_scheduler_module.ReminderScheduler
ReminderMessage = reminder_scheduler_module.ReminderMessage
WebSocketReminderDispatcher = reminder_scheduler_module.WebSocketReminderDispatcher


class FakeSession:
    def __init__(self, events: dict[str, SimpleNamespace] | None = None) -> None:
        self.events = events or {}
        self.committed = 0
        self.rolled_back = 0

    async def get(self, model, item_id: str):
        return self.events.get(item_id)

    async def commit(self) -> None:
        self.committed += 1

    async def rollback(self) -> None:
        self.rolled_back += 1


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self) -> FakeSessionContext:
        return FakeSessionContext(self.session)


class FakeReminderService:
    def __init__(self, reminders: list[SimpleNamespace]) -> None:
        self.reminders = reminders
        self.sent_ids: list[str] = []
        self.failed: list[tuple[str, str | None]] = []

    async def list_due_pending_reminders(self, now=None, limit: int = 100):
        return [
            reminder
            for reminder in self.reminders
            if reminder.status == "pending" and reminder.remind_time <= now
        ][:limit]

    async def mark_sent(self, reminder_id: str):
        self.sent_ids.append(reminder_id)
        for reminder in self.reminders:
            if reminder.id == reminder_id:
                reminder.status = "sent"
                reminder.error_message = None
                return reminder
        return None

    async def mark_failed(self, reminder_id: str, error_message: str | None = None):
        self.failed.append((reminder_id, error_message))
        for reminder in self.reminders:
            if reminder.id == reminder_id:
                reminder.status = "failed"
                reminder.error_message = error_message
                return reminder
        return None


class CapturingDispatcher:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages = []

    async def send(self, message) -> None:
        self.messages.append(message)
        if self.fail:
            raise RuntimeError("dispatch failed")


class FakeWebSocketManager:
    def __init__(self, sent_count: int = 1) -> None:
        self.sent_count = sent_count
        self.messages = []

    async def broadcast_to_user_sessions(self, user_id: str, message: dict):
        self.messages.append((user_id, message))
        return self.sent_count


class ReminderSchedulerTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)

    def tearDown(self) -> None:
        logging.disable(logging.NOTSET)

    async def test_run_once_sends_due_reminder_and_marks_sent(self) -> None:
        now = datetime(2026, 5, 30, 9, 0, tzinfo=timezone.utc)
        reminder = SimpleNamespace(
            id="reminder-1",
            event_id="event-1",
            user_id="user-1",
            remind_time=now,
            status="pending",
            error_message=None,
        )
        event = SimpleNamespace(
            id="event-1",
            title="project meeting",
            start_time=datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
        )
        session = FakeSession(events={"event-1": event})
        service = FakeReminderService([reminder])
        dispatcher = CapturingDispatcher()
        scheduler = ReminderScheduler(
            session_factory=FakeSessionFactory(session),
            service_factory=lambda session: service,
            dispatcher=dispatcher,
            scan_interval=60,
        )

        result = await scheduler.run_once(now=now)

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.sent, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(service.sent_ids, ["reminder-1"])
        self.assertEqual(reminder.status, "sent")
        self.assertEqual(session.committed, 1)
        self.assertEqual(session.rolled_back, 0)
        self.assertEqual(dispatcher.messages[0].text, "提醒：project meeting")
        self.assertEqual(result.messages[0].title, "project meeting")

    async def test_websocket_dispatcher_sends_reminder_triggered_payload(self) -> None:
        manager = FakeWebSocketManager(sent_count=2)
        dispatcher = WebSocketReminderDispatcher(manager=manager)
        start_time = datetime(
            2026,
            5,
            30,
            15,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        )
        message = ReminderMessage(
            reminder_id="reminder-1",
            event_id="e001",
            user_id="u001",
            remind_time=datetime(2026, 5, 30, 14, 50, tzinfo=timezone.utc),
            title="项目会议",
            event_start_time=start_time,
            text="提醒：项目会议",
        )

        await dispatcher.send(message)

        self.assertEqual(
            manager.messages,
            [
                (
                    "u001",
                    {
                        "type": "reminder_triggered",
                        "user_id": "u001",
                        "data": {
                            "event_id": "e001",
                            "title": "项目会议",
                            "start_time": "2026-05-30T15:00:00+08:00",
                        },
                    },
                )
            ],
        )

    async def test_run_once_marks_failed_when_websocket_push_has_no_connections(self) -> None:
        now = datetime(2026, 5, 30, 9, 0, tzinfo=timezone.utc)
        reminder = SimpleNamespace(
            id="reminder-1",
            event_id="event-1",
            user_id="user-1",
            remind_time=now,
            status="pending",
            error_message=None,
        )
        session = FakeSession()
        service = FakeReminderService([reminder])
        dispatcher = WebSocketReminderDispatcher(manager=FakeWebSocketManager(sent_count=0))
        scheduler = ReminderScheduler(
            session_factory=FakeSessionFactory(session),
            service_factory=lambda session: service,
            dispatcher=dispatcher,
            scan_interval=60,
        )

        result = await scheduler.run_once(now=now)

        self.assertEqual(result.sent, 0)
        self.assertEqual(result.failed, 1)
        self.assertEqual(service.failed, [("reminder-1", "no websocket connections for user")])
        self.assertEqual(reminder.status, "failed")
        self.assertEqual(reminder.error_message, "no websocket connections for user")

    async def test_run_once_marks_failed_with_error_message_when_dispatch_fails(self) -> None:
        now = datetime(2026, 5, 30, 9, 0, tzinfo=timezone.utc)
        reminder = SimpleNamespace(
            id="reminder-1",
            event_id="event-1",
            user_id="user-1",
            remind_time=now,
            status="pending",
            error_message=None,
        )
        session = FakeSession()
        service = FakeReminderService([reminder])
        dispatcher = CapturingDispatcher(fail=True)
        scheduler = ReminderScheduler(
            session_factory=FakeSessionFactory(session),
            service_factory=lambda session: service,
            dispatcher=dispatcher,
            scan_interval=60,
        )

        result = await scheduler.run_once(now=now)

        self.assertEqual(result.scanned, 1)
        self.assertEqual(result.sent, 0)
        self.assertEqual(result.failed, 1)
        self.assertEqual(service.failed, [("reminder-1", "dispatch failed")])
        self.assertEqual(reminder.status, "failed")
        self.assertEqual(reminder.error_message, "dispatch failed")
        self.assertEqual(session.rolled_back, 1)
        self.assertEqual(session.committed, 1)

    async def test_start_is_noop_without_database_session_factory(self) -> None:
        scheduler = ReminderScheduler(session_factory=None, scan_interval=60)

        await scheduler.start()
        result = await scheduler.run_once()

        self.assertFalse(scheduler.is_running)
        self.assertEqual(result.skipped_reason, "database_not_configured")


if __name__ == "__main__":
    unittest.main()
