from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = PROJECT_ROOT / "app" / "services" / "reminder_service.py"


class FakeColumn:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other):  # noqa: D401 - simple fake predicate object
        return (self.name, "==", other)


class FakeSelectStatement:
    def __init__(self, model) -> None:
        self.model = model
        self.conditions = []

    def where(self, *conditions):
        self.conditions.extend(conditions)
        return self


def fake_select(model):
    return FakeSelectStatement(model)


class FakeReminderModel:
    event_id = FakeColumn("event_id")
    status = FakeColumn("status")
    user_id = FakeColumn("user_id")


class FakeScalarResult:
    def __init__(self, reminders: list[SimpleNamespace]) -> None:
        self._reminders = reminders

    def all(self):
        return list(self._reminders)


class FakeReminderRepository:
    def __init__(self, session) -> None:
        self.session = session
        self.reminders: dict[str, SimpleNamespace] = getattr(session, "reminders", {})
        self.calls: list[tuple[str, dict]] = []
        session.repository = self

    async def create(self, data: dict) -> SimpleNamespace:
        self.calls.append(("create", dict(data)))
        reminder = SimpleNamespace(**data)
        self.reminders[reminder.id] = reminder
        return reminder

    async def get_by_id(self, reminder_id: str):
        self.calls.append(("get_by_id", {"reminder_id": reminder_id}))
        return self.reminders.get(reminder_id)

    async def update(self, reminder: SimpleNamespace, data: dict):
        self.calls.append(("update", dict(data)))
        for field, value in data.items():
            setattr(reminder, field, value)
        self.reminders[reminder.id] = reminder
        return reminder

    async def list(self, user_id: str, status: str | None = None, limit: int = 100, offset: int = 0):
        self.calls.append(
            (
                "list",
                {
                    "user_id": user_id,
                    "status": status,
                    "limit": limit,
                    "offset": offset,
                },
            )
        )
        reminders = [
            reminder
            for reminder in self.reminders.values()
            if reminder.user_id == user_id and (status is None or reminder.status == status)
        ]
        return reminders[offset : offset + limit]

    async def list_due_pending(self, now: datetime, limit: int = 100):
        self.calls.append(("list_due_pending", {"now": now, "limit": limit}))
        reminders = [
            reminder
            for reminder in self.reminders.values()
            if reminder.status == "pending" and reminder.remind_time <= now
        ]
        return reminders[:limit]

    async def update_status(self, reminder: SimpleNamespace, status: str, error_message: str | None = None):
        self.calls.append(
            (
                "update_status",
                {
                    "reminder_id": reminder.id,
                    "status": status,
                    "error_message": error_message,
                },
            )
        )
        reminder.status = status
        reminder.error_message = error_message if status == "failed" else None
        self.reminders[reminder.id] = reminder
        return reminder


def install_import_stubs() -> dict[str, ModuleType | None]:
    originals = {
        name: sys.modules.get(name)
        for name in [
            "sqlalchemy",
            "sqlalchemy.ext",
            "sqlalchemy.ext.asyncio",
            "app.core",
            "app.core.config",
            "app.models",
            "app.models.reminder",
            "app.repositories",
            "app.repositories.reminder_repository",
            "app.schemas",
            "app.schemas.reminder",
        ]
    }

    sqlalchemy_module = ModuleType("sqlalchemy")
    sqlalchemy_module.select = fake_select
    sqlalchemy_ext_module = ModuleType("sqlalchemy.ext")
    sqlalchemy_asyncio_module = ModuleType("sqlalchemy.ext.asyncio")
    sqlalchemy_asyncio_module.AsyncSession = object
    app_core_module = ModuleType("app.core")
    app_core_config_module = ModuleType("app.core.config")
    app_core_config_module.get_settings = lambda: SimpleNamespace(timezone="Asia/Shanghai")
    app_models_module = ModuleType("app.models")
    app_models_reminder_module = ModuleType("app.models.reminder")
    app_models_reminder_module.Reminder = FakeReminderModel
    app_repositories_module = ModuleType("app.repositories")
    app_repositories_reminder_module = ModuleType("app.repositories.reminder_repository")
    app_repositories_reminder_module.ReminderRepository = FakeReminderRepository
    app_schemas_module = ModuleType("app.schemas")
    app_schemas_reminder_module = ModuleType("app.schemas.reminder")
    app_schemas_reminder_module.ReminderCreate = object
    app_schemas_reminder_module.ReminderUpdate = object

    sys.modules["sqlalchemy"] = sqlalchemy_module
    sys.modules["sqlalchemy.ext"] = sqlalchemy_ext_module
    sys.modules["sqlalchemy.ext.asyncio"] = sqlalchemy_asyncio_module
    sys.modules["app.core"] = app_core_module
    sys.modules["app.core.config"] = app_core_config_module
    sys.modules["app.models"] = app_models_module
    sys.modules["app.models.reminder"] = app_models_reminder_module
    sys.modules["app.repositories"] = app_repositories_module
    sys.modules["app.repositories.reminder_repository"] = app_repositories_reminder_module
    sys.modules["app.schemas"] = app_schemas_module
    sys.modules["app.schemas.reminder"] = app_schemas_reminder_module

    return originals


def restore_import_stubs(originals: dict[str, ModuleType | None]) -> None:
    for name, module in originals.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


original_modules = install_import_stubs()
spec = importlib.util.spec_from_file_location("reminder_service_under_test", SERVICE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load ReminderService from {SERVICE_PATH}")
reminder_service_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reminder_service_module
spec.loader.exec_module(reminder_service_module)
restore_import_stubs(original_modules)

ReminderService = reminder_service_module.ReminderService


class FakeReminderInput:
    def __init__(self, **data) -> None:
        self.data = dict(data)
        for key, value in data.items():
            setattr(self, key, value)

    def model_dump(self, **kwargs) -> dict:
        exclude = set(kwargs.get("exclude", set()))
        exclude_unset = kwargs.get("exclude_unset", False)
        payload = dict(self.data)
        for key in exclude:
            payload.pop(key, None)
        if exclude_unset:
            payload = {key: value for key, value in payload.items() if value is not None}
        return payload


class FakeSession:
    def __init__(self) -> None:
        self.reminders: dict[str, SimpleNamespace] = {}
        self.scalars_calls: list[FakeSelectStatement] = []
        self.flushed = 0
        self.repository = None

    async def scalars(self, statement):
        self.scalars_calls.append(statement)
        pending = [
            reminder
            for reminder in self.reminders.values()
            if reminder.status == "pending"
        ]
        return FakeScalarResult(pending)

    async def flush(self):
        self.flushed += 1


class ReminderServiceTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = FakeSession()
        self.service = ReminderService(self.session)

    async def test_create_reminder_sets_pending_and_aware_timezone(self) -> None:
        reminder = await self.service.create_reminder(
            FakeReminderInput(
                id=None,
                event_id="event-1",
                user_id="u001",
                remind_time=datetime(2099, 5, 31, 15, 0, 0),
                offset_minutes=0,
                channel="app_voice",
                allow_past_time_for_test=False,
            )
        )

        self.assertIsInstance(reminder.id, str)
        self.assertEqual(reminder.status, "pending")
        self.assertEqual(reminder.remind_time.isoformat(), "2099-05-31T15:00:00+08:00")
        self.assertEqual(self.session.repository.calls[-1][0], "create")

    async def test_create_reminder_allows_past_time_for_tests(self) -> None:
        reminder = await self.service.create_reminder(
            FakeReminderInput(
                id=None,
                event_id="event-1",
                user_id="u001",
                remind_time=datetime(2000, 1, 1, 8, 0, 0),
                offset_minutes=0,
                channel="app_voice",
                allow_past_time_for_test=True,
            )
        )

        self.assertEqual(reminder.remind_time.isoformat(), "2000-01-01T08:00:00+08:00")

    async def test_create_reminder_rejects_past_time_by_default(self) -> None:
        with self.assertRaises(ValueError):
            await self.service.create_reminder(
                FakeReminderInput(
                    id=None,
                    event_id="event-1",
                    user_id="u001",
                    remind_time=datetime(2000, 1, 1, 8, 0, 0),
                    offset_minutes=0,
                    channel="app_voice",
                    allow_past_time_for_test=False,
                )
            )

    async def test_update_cancel_mark_and_list_due_reminders(self) -> None:
        reminder = SimpleNamespace(
            id="reminder-1",
            event_id="event-1",
            user_id="u001",
            remind_time=datetime(2099, 5, 31, 15, 0, 0, tzinfo=timezone(timedelta(hours=8))),
            offset_minutes=15,
            channel="app_voice",
            status="pending",
            error_message=None,
        )
        self.session.reminders[reminder.id] = reminder

        updated = await self.service.update_reminder(
            "reminder-1",
            FakeReminderInput(
                remind_time=datetime(2099, 5, 31, 16, 0, 0),
                offset_minutes=30,
            ),
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated.offset_minutes, 30)
        self.assertEqual(updated.remind_time.isoformat(), "2099-05-31T16:00:00+08:00")

        due = await self.service.list_due_pending_reminders(
            now=datetime(2099, 5, 31, 17, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(due, [reminder])

        sent = await self.service.mark_sent("reminder-1")
        self.assertEqual(sent.status, "sent")
        self.assertIsNone(sent.error_message)

        failed_reminder = SimpleNamespace(
            id="reminder-2",
            event_id="event-1",
            user_id="u001",
            remind_time=datetime(2099, 5, 31, 18, 0, 0, tzinfo=timezone(timedelta(hours=8))),
            offset_minutes=0,
            channel="app_voice",
            status="pending",
            error_message=None,
        )
        self.session.reminders[failed_reminder.id] = failed_reminder

        failed = await self.service.mark_failed("reminder-2", error_message="network error")
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error_message, "network error")

        cancelled = await self.service.cancel_reminder("reminder-2")
        self.assertEqual(cancelled.status, "failed")

    async def test_cancel_event_reminders_marks_matching_pending_reminders(self) -> None:
        reminder_1 = SimpleNamespace(
            id="reminder-1",
            event_id="event-1",
            user_id="u001",
            remind_time=datetime(2026, 5, 31, 15, 0, 0, tzinfo=timezone(timedelta(hours=8))),
            offset_minutes=15,
            channel="app_voice",
            status="pending",
            error_message=None,
        )
        reminder_2 = SimpleNamespace(
            id="reminder-2",
            event_id="event-1",
            user_id="u001",
            remind_time=datetime(2026, 5, 31, 16, 0, 0, tzinfo=timezone(timedelta(hours=8))),
            offset_minutes=0,
            channel="app_voice",
            status="pending",
            error_message=None,
        )
        reminder_3 = SimpleNamespace(
            id="reminder-3",
            event_id="event-2",
            user_id="u001",
            remind_time=datetime(2026, 5, 31, 16, 0, 0, tzinfo=timezone(timedelta(hours=8))),
            offset_minutes=0,
            channel="app_voice",
            status="sent",
            error_message=None,
        )
        self.session.reminders.update(
            {
                reminder_1.id: reminder_1,
                reminder_2.id: reminder_2,
                reminder_3.id: reminder_3,
            }
        )

        cancelled = await self.service.cancel_event_reminders(event_id="event-1", user_id="u001")

        self.assertEqual([reminder.id for reminder in cancelled], ["reminder-1", "reminder-2"])
        self.assertEqual(reminder_1.status, "cancelled")
        self.assertEqual(reminder_2.status, "cancelled")
        self.assertEqual(reminder_3.status, "sent")
        self.assertEqual(self.session.flushed, 1)


if __name__ == "__main__":
    unittest.main()
