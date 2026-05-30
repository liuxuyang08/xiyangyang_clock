from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VOICE_API_PATH = PROJECT_ROOT / "app" / "api" / "voice.py"


class FakeAPIRouter:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def post(self, *args, **kwargs):
        def decorator(func):
            return func

        return decorator


class FakeBaseModel:
    def __init__(self, **data) -> None:
        for field, value in data.items():
            setattr(self, field, value)


class FakeConfigDict(dict):
    pass


def fake_field(default=None, default_factory=None, **kwargs):
    if default_factory is not None:
        return default_factory()
    return default


def install_import_stubs() -> dict[str, ModuleType | None]:
    originals = {
        name: sys.modules.get(name)
        for name in [
            "fastapi",
            "pydantic",
            "sqlalchemy",
            "sqlalchemy.ext",
            "sqlalchemy.ext.asyncio",
            "app.db",
            "app.db.session",
            "app.schemas",
            "app.schemas.common",
            "app.schemas.event",
            "app.schemas.reminder",
            "app.schemas.voice",
            "app.services",
            "app.services.calendar_service",
            "app.services.conflict_service",
            "app.services.dialog_service",
            "app.services.nlu_service",
            "app.services.reminder_service",
            "app.services.time_parser",
            "app.services.voice_command_log_service",
        ]
    }

    fastapi_module = ModuleType("fastapi")
    fastapi_module.APIRouter = FakeAPIRouter
    fastapi_module.Depends = lambda dependency=None: dependency
    sys.modules["fastapi"] = fastapi_module

    pydantic_module = ModuleType("pydantic")
    pydantic_module.BaseModel = FakeBaseModel
    pydantic_module.ConfigDict = FakeConfigDict
    pydantic_module.Field = fake_field
    sys.modules["pydantic"] = pydantic_module

    sqlalchemy_module = ModuleType("sqlalchemy")
    sqlalchemy_ext_module = ModuleType("sqlalchemy.ext")
    sqlalchemy_asyncio_module = ModuleType("sqlalchemy.ext.asyncio")
    sqlalchemy_asyncio_module.AsyncSession = object
    sys.modules["sqlalchemy"] = sqlalchemy_module
    sys.modules["sqlalchemy.ext"] = sqlalchemy_ext_module
    sys.modules["sqlalchemy.ext.asyncio"] = sqlalchemy_asyncio_module

    app_db_module = ModuleType("app.db")
    app_db_session_module = ModuleType("app.db.session")
    app_db_session_module.get_db_session = lambda: None
    app_db_session_module.SessionLocal = None
    sys.modules["app.db"] = app_db_module
    sys.modules["app.db.session"] = app_db_session_module

    app_services_module = ModuleType("app.services")
    calendar_service_module = ModuleType("app.services.calendar_service")
    conflict_service_module = ModuleType("app.services.conflict_service")
    dialog_service_module = ModuleType("app.services.dialog_service")
    nlu_service_module = ModuleType("app.services.nlu_service")
    reminder_service_module = ModuleType("app.services.reminder_service")
    time_parser_module = ModuleType("app.services.time_parser")
    voice_command_log_service_module = ModuleType("app.services.voice_command_log_service")
    calendar_service_module.CalendarService = object
    conflict_service_module.ConflictService = object
    dialog_service_module.DialogService = object
    nlu_service_module.NLUResult = object
    nlu_service_module.NLUService = object
    reminder_service_module.ReminderService = object
    time_parser_module.TimeParser = object
    voice_command_log_service_module.VoiceCommandLogService = object
    sys.modules["app.services"] = app_services_module
    sys.modules["app.services.calendar_service"] = calendar_service_module
    sys.modules["app.services.conflict_service"] = conflict_service_module
    sys.modules["app.services.dialog_service"] = dialog_service_module
    sys.modules["app.services.nlu_service"] = nlu_service_module
    sys.modules["app.services.reminder_service"] = reminder_service_module
    sys.modules["app.services.time_parser"] = time_parser_module
    sys.modules["app.services.voice_command_log_service"] = voice_command_log_service_module

    return originals


def restore_import_stubs(originals: dict[str, ModuleType | None]) -> None:
    for name, module in originals.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


original_modules = install_import_stubs()
spec = importlib.util.spec_from_file_location("voice_api", VOICE_API_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load voice api from {VOICE_API_PATH}")
voice_api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = voice_api
spec.loader.exec_module(voice_api)
restore_import_stubs(original_modules)


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeDialogService:
    def __init__(self, current_state=None) -> None:
        self.current_state = current_state
        self.created_state = None
        self.completed = False
        self.cancelled = False

    async def get_current_state(self, user_id: str, session_id: str, text: str | None = None):
        return self.current_state

    async def create_pending_state(self, **kwargs):
        self.created_state = SimpleNamespace(id="state-1", **kwargs)
        return self.created_state

    async def complete_state(self, user_id: str, session_id: str):
        self.completed = True
        return SimpleNamespace(
            id=getattr(self.current_state, "id", "state-1"),
            user_id=user_id,
            session_id=session_id,
            status="completed",
        )

    async def cancel_state(self, user_id: str, session_id: str):
        self.cancelled = True
        return SimpleNamespace(
            id=getattr(self.current_state, "id", "state-1"),
            user_id=user_id,
            session_id=session_id,
            status="cancelled",
        )


class FakeNLUService:
    def __init__(self, result) -> None:
        self.result = result
        self.context = None

    def parse(self, text: str, base_time: datetime, timezone: str, conversation_context=None):
        self.context = conversation_context
        return self.result


class FakeTimeParser:
    def __init__(self, result=None) -> None:
        self.result = result
        self.calls = []

    def parse(self, text: str, base_time: datetime, timezone: str):
        self.calls.append((text, base_time, timezone))
        return self.result


class FakeCalendarService:
    def __init__(self, events=None) -> None:
        self.created_event = None
        self.events = list(events or [])
        self.queried_range = None
        self.searched_candidates = None
        self.soft_deleted_event_id = None
        self.updated_event_id = None
        self.updated_event_payload = None

    async def create_event(self, event_in):
        self.created_event = event_in
        return SimpleNamespace(
            id="event-1",
            user_id=event_in.user_id,
            title=event_in.title,
            description=getattr(event_in, "description", None),
            start_time=event_in.start_time,
            end_time=getattr(event_in, "end_time", None),
            location=getattr(event_in, "location", None),
            participants=getattr(event_in, "participants", []),
            priority=getattr(event_in, "priority", "normal"),
            status="active",
            source=getattr(event_in, "source", "voice"),
            is_all_day=getattr(event_in, "is_all_day", False),
            recurrence_rule=getattr(event_in, "recurrence_rule", None),
            created_at=datetime(2026, 5, 29, 16, 0, 0),
            updated_at=datetime(2026, 5, 29, 16, 0, 0),
            deleted_at=None,
        )

    async def list_events_by_range(self, user_id: str, start_time: datetime, end_time: datetime):
        self.queried_range = {
            "user_id": user_id,
            "start_time": start_time,
            "end_time": end_time,
        }
        return list(self.events)

    async def search_candidate_events(self, user_id: str, keyword: str, limit: int = 10):
        self.searched_candidates = {
            "user_id": user_id,
            "keyword": keyword,
            "limit": limit,
        }
        if not keyword:
            return list(self.events)[:limit]
        return [
            event
            for event in self.events
            if keyword.lower() in event.title.lower()
        ][:limit]

    async def soft_delete_event(self, event_id: str):
        self.soft_deleted_event_id = event_id
        for event in self.events:
            if event.id == event_id:
                event.status = "deleted"
                event.deleted_at = datetime(2026, 5, 30, 9, 0, 0)
                return event
        return None

    async def get_event(self, event_id: str):
        for event in self.events:
            if event.id == event_id and event.status == "active" and event.deleted_at is None:
                return event
        return None

    async def update_event(self, event_id: str, event_in):
        self.updated_event_id = event_id
        self.updated_event_payload = event_in
        event = await self.get_event(event_id)
        if event is None:
            return None

        for field in (
            "title",
            "description",
            "start_time",
            "end_time",
            "location",
            "participants",
            "priority",
            "is_all_day",
            "recurrence_rule",
        ):
            if hasattr(event_in, field):
                value = getattr(event_in, field)
                if value is not None:
                    setattr(event, field, value)
        event.updated_at = datetime(2026, 5, 30, 9, 30, 0)
        return event


class FakeConflictService:
    def __init__(self, conflicts=None) -> None:
        self.conflicts = list(conflicts or [])
        self.calls = []

    async def list_conflicting_events(self, user_id: str, start_time: datetime, end_time: datetime):
        self.calls.append(
            {
                "method": "list_conflicting_events",
                "user_id": user_id,
                "start_time": start_time,
                "end_time": end_time,
            }
        )
        return list(self.conflicts)

    async def list_conflicting_events_excluding_current(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        current_event_id: str,
    ):
        self.calls.append(
            {
                "method": "list_conflicting_events_excluding_current",
                "user_id": user_id,
                "start_time": start_time,
                "end_time": end_time,
                "current_event_id": current_event_id,
            }
        )
        return [
            conflict
            for conflict in self.conflicts
            if getattr(conflict, "id", None) != current_event_id
        ]


class FakeReminderService:
    def __init__(self) -> None:
        self.created_reminder = None
        self.cancelled_event_id = None
        self.cancelled_user_id = None

    async def create_reminder(self, reminder_in):
        self.created_reminder = reminder_in
        return SimpleNamespace(
            id="reminder-1",
            event_id=reminder_in.event_id,
            user_id=reminder_in.user_id,
            remind_time=reminder_in.remind_time,
            offset_minutes=reminder_in.offset_minutes,
            channel=reminder_in.channel,
            status="pending",
            created_at=datetime(2026, 5, 29, 16, 0, 0),
        )

    async def cancel_event_reminders(self, event_id: str, user_id: str | None = None):
        self.cancelled_event_id = event_id
        self.cancelled_user_id = user_id
        return [
            SimpleNamespace(
                id="reminder-1",
                event_id=event_id,
                user_id=user_id,
                remind_time=datetime(2026, 5, 30, 9, 30, 0),
                offset_minutes=30,
                channel="app_voice",
                status="cancelled",
                created_at=datetime(2026, 5, 29, 16, 0, 0),
            )
        ]


class FakeVoiceCommandLogService:
    def __init__(self) -> None:
        self.calls = []

    async def record_received(self, **kwargs):
        self.calls.append(("received", kwargs))
        return SimpleNamespace(id="voice-1")

    async def record_parsed(self, **kwargs):
        self.calls.append(("parsed", kwargs))
        return SimpleNamespace(id=kwargs.get("voice_command_id") or "voice-1")

    async def record_success(self, **kwargs):
        self.calls.append(("success", kwargs))
        return SimpleNamespace(id=kwargs.get("voice_command_id") or "voice-1")

    async def record_failed(self, **kwargs):
        self.calls.append(("failed", kwargs))
        return SimpleNamespace(id=kwargs.get("voice_command_id") or "voice-1")


def fake_event(event_id: str, title: str, start_time: datetime):
    return SimpleNamespace(
        id=event_id,
        user_id="user-1",
        title=title,
        description=None,
        start_time=start_time,
        end_time=None,
        location=None,
        participants=[],
        priority="normal",
        status="active",
        source="voice",
        is_all_day=False,
        recurrence_rule=None,
        created_at=datetime(2026, 5, 29, 16, 0, 0),
        updated_at=datetime(2026, 5, 29, 16, 0, 0),
        deleted_at=None,
    )


def pending_delete_state(
    *,
    status: str,
    candidates: list[dict],
    slots: dict | None = None,
):
    return SimpleNamespace(
        id="state-delete-1",
        user_id="user-1",
        session_id="session-1",
        pending_intent="delete_event",
        slots=dict(slots or {}),
        missing_slots=[],
        candidate_events=list(candidates),
        status=status,
        expires_at=None,
        updated_at=datetime(2026, 5, 30, 8, 0, 0),
    )


def pending_update_state(
    *,
    status: str,
    candidates: list[dict],
    slots: dict | None = None,
):
    return SimpleNamespace(
        id="state-update-1",
        user_id="user-1",
        session_id="session-1",
        pending_intent="update_event",
        slots=dict(slots or {}),
        missing_slots=[],
        candidate_events=list(candidates),
        status=status,
        expires_at=None,
        updated_at=datetime(2026, 5, 30, 8, 0, 0),
    )


def pending_conflict_state(
    *,
    pending_intent: str,
    slots: dict,
    conflicts: list[dict],
    candidates: list[dict] | None = None,
):
    state_slots = {
        **slots,
        "conflict_confirmation": {
            "operation": pending_intent,
            "conflicts": conflicts,
            "time_parse": {},
        },
    }
    return SimpleNamespace(
        id="state-conflict-1",
        user_id="user-1",
        session_id="session-1",
        pending_intent=pending_intent,
        slots=state_slots,
        missing_slots=[],
        candidate_events=list(candidates or []),
        status="need_confirm",
        expires_at=None,
        updated_at=datetime(2026, 5, 30, 8, 0, 0),
    )


class VoiceApiTestCase(unittest.IsolatedAsyncioTestCase):
    def request_payload(self) -> SimpleNamespace:
        return SimpleNamespace(
            user_id="user-1",
            session_id="session-1",
            text="schedule meeting tomorrow at three",
            timezone="Asia/Shanghai",
            client_time=datetime(2026, 5, 29, 15, 0, 0),
        )

    async def test_create_event_creates_event_and_reminder(self) -> None:
        session = FakeSession()
        log_service = FakeVoiceCommandLogService()
        calendar_service = FakeCalendarService()
        reminder_service = FakeReminderService()
        nlu_result = SimpleNamespace(
            intent="create_event",
            confidence=0.91,
            slots={
                "title": "meeting",
                "date_text": "tomorrow",
                "time_text": "3pm",
                "reminder_offset_minutes": 30,
            },
            missing_slots=[],
        )
        time_result = SimpleNamespace(
            raw_text="tomorrow3pm",
            success=True,
            datetime=datetime(2026, 5, 30, 15, 0, 0),
            start_datetime=None,
            end_datetime=None,
            ambiguous=False,
            need_followup=False,
            is_past=False,
            missing_slots=[],
            reason=None,
        )

        response = await voice_api.handle_voice_command(
            self.request_payload(),
            session=session,
            dialog_service=FakeDialogService(),
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=reminder_service,
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(time_result),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "event_created")
        self.assertFalse(response.need_user_reply)
        self.assertIn("meeting", response.reply)
        self.assertEqual(response.data["event"]["id"], "event-1")
        self.assertEqual(response.data["event"]["title"], "meeting")
        self.assertEqual(response.data["reminder"]["id"], "reminder-1")
        self.assertEqual(response.data["reminder"]["offset_minutes"], 30)
        self.assertEqual(calendar_service.created_event.source, "voice")
        self.assertEqual(reminder_service.created_reminder.event_id, "event-1")
        self.assertEqual([call[0] for call in log_service.calls], ["received", "parsed", "success"])
        self.assertEqual(log_service.calls[-1][1]["entities"]["event"]["id"], "event-1")
        self.assertEqual(log_service.calls[-1][1]["entities"]["reminder"]["id"], "reminder-1")
        self.assertTrue(session.committed)

    async def test_create_event_conflict_saves_pending_confirm_without_creating(self) -> None:
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService()
        reminder_service = FakeReminderService()
        conflict_event = fake_event("conflict-1", "project meeting", datetime(2026, 5, 30, 15, 0, 0))
        conflict_event.end_time = datetime(2026, 5, 30, 16, 0, 0)
        conflict_service = FakeConflictService(conflicts=[conflict_event])
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="create_event",
            confidence=0.91,
            slots={
                "title": "write report",
                "start_time": datetime(2026, 5, 30, 15, 0, 0).isoformat(),
            },
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            self.request_payload(),
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=conflict_service,
            reminder_service=reminder_service,
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "create_event_conflict_need_confirm")
        self.assertTrue(response.need_user_reply)
        self.assertIn("project meeting", response.reply)
        self.assertEqual(response.data["conflicts"][0]["id"], "conflict-1")
        self.assertEqual(conflict_service.calls[0]["method"], "list_conflicting_events")
        self.assertEqual(conflict_service.calls[0]["end_time"], datetime(2026, 5, 30, 16, 0, 0))
        self.assertEqual(dialog_service.created_state.pending_intent, "create_event")
        self.assertEqual(dialog_service.created_state.status, "need_confirm")
        self.assertEqual(dialog_service.created_state.slots["conflict_confirmation"]["operation"], "create_event")
        self.assertIsNone(calendar_service.created_event)
        self.assertIsNone(reminder_service.created_reminder)
        self.assertTrue(session.committed)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "create_event_conflict_detected")

    async def test_pending_create_conflict_confirm_continues_create_and_clears_state(self) -> None:
        payload = self.request_payload()
        payload.text = "确认"
        conflicts = [
            {
                "id": "conflict-1",
                "title": "project meeting",
                "start_time": "2026-05-30T15:00:00",
                "end_time": "2026-05-30T16:00:00",
            }
        ]
        state = pending_conflict_state(
            pending_intent="create_event",
            slots={
                "title": "write report",
                "start_time": datetime(2026, 5, 30, 15, 0, 0).isoformat(),
                "reminder_offset_minutes": 15,
            },
            conflicts=conflicts,
        )
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService()
        reminder_service = FakeReminderService()
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="confirm",
            confidence=0.95,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=reminder_service,
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "event_created")
        self.assertFalse(response.need_user_reply)
        self.assertEqual(response.data["event"]["title"], "write report")
        self.assertEqual(response.data["conflicts"], conflicts)
        self.assertEqual(calendar_service.created_event.title, "write report")
        self.assertEqual(reminder_service.created_reminder.offset_minutes, 15)
        self.assertTrue(dialog_service.completed)
        self.assertTrue(session.committed)
        self.assertEqual(log_service.calls[-1][1]["intent"], "create_event")
        self.assertEqual(log_service.calls[-1][1]["entities"]["conflicts"], conflicts)

    async def test_pending_create_conflict_deny_clears_state_without_creating(self) -> None:
        payload = self.request_payload()
        payload.text = "取消"
        conflicts = [
            {
                "id": "conflict-1",
                "title": "project meeting",
                "start_time": "2026-05-30T15:00:00",
                "end_time": "2026-05-30T16:00:00",
            }
        ]
        state = pending_conflict_state(
            pending_intent="create_event",
            slots={
                "title": "write report",
                "start_time": datetime(2026, 5, 30, 15, 0, 0).isoformat(),
            },
            conflicts=conflicts,
        )
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService()
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="deny",
            confidence=0.9,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "create_event_cancelled")
        self.assertEqual(response.data["conflicts"], conflicts)
        self.assertTrue(dialog_service.cancelled)
        self.assertTrue(session.committed)
        self.assertIsNone(calendar_service.created_event)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "create_event_conflict_cancelled")

    async def test_query_event_defaults_to_today_and_returns_sorted_voice_reply(self) -> None:
        session = FakeSession()
        log_service = FakeVoiceCommandLogService()
        calendar_service = FakeCalendarService(
            events=[
                fake_event("event-2", "submit document", datetime(2026, 5, 29, 15, 0, 0)),
                fake_event("event-1", "project discussion", datetime(2026, 5, 29, 10, 0, 0)),
                fake_event("event-3", "workout", datetime(2026, 5, 29, 19, 0, 0)),
            ]
        )
        reminder_service = FakeReminderService()
        nlu_result = SimpleNamespace(
            intent="query_event",
            confidence=0.86,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            self.request_payload(),
            session=session,
            dialog_service=FakeDialogService(),
            calendar_service=calendar_service,
            reminder_service=reminder_service,
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "events_queried")
        self.assertFalse(response.need_user_reply)
        self.assertEqual(response.data["query_range"]["label"], "今天")
        self.assertEqual(calendar_service.queried_range["start_time"].hour, 0)
        self.assertEqual(calendar_service.queried_range["end_time"].date().isoformat(), "2026-05-30")
        self.assertEqual([event["id"] for event in response.data["events"]], ["event-1", "event-2", "event-3"])
        self.assertIn("今天你有 3 个安排", response.reply)
        self.assertLess(response.reply.index("project discussion"), response.reply.index("submit document"))
        self.assertLess(response.reply.index("submit document"), response.reply.index("workout"))
        self.assertIsNone(calendar_service.created_event)
        self.assertIsNone(reminder_service.created_reminder)
        self.assertFalse(session.committed)
        self.assertEqual([call[0] for call in log_service.calls], ["received", "parsed", "success"])
        self.assertEqual(log_service.calls[-1][1]["entities"]["event_count"], 3)

    async def test_query_event_recent_uses_future_seven_days(self) -> None:
        payload = self.request_payload()
        payload.text = "最近有什么安排"
        calendar_service = FakeCalendarService()
        nlu_result = SimpleNamespace(
            intent="query_event",
            confidence=0.86,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=FakeSession(),
            dialog_service=FakeDialogService(),
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=FakeVoiceCommandLogService(),
        )

        self.assertEqual(response.action, "events_queried")
        self.assertEqual(response.reply, "暂无安排。")
        self.assertEqual(response.data["query_range"]["label"], "最近7天")
        self.assertEqual(calendar_service.queried_range["start_time"], payload.client_time.replace(tzinfo=calendar_service.queried_range["start_time"].tzinfo))
        self.assertEqual(
            calendar_service.queried_range["end_time"],
            calendar_service.queried_range["start_time"] + voice_api.timedelta(days=7),
        )

    async def test_query_event_afternoon_uses_today_noon_to_six(self) -> None:
        payload = self.request_payload()
        payload.text = "我下午有什么安排"
        calendar_service = FakeCalendarService()
        nlu_result = SimpleNamespace(
            intent="query_event",
            confidence=0.86,
            slots={"time_text": "下午"},
            missing_slots=["specific_time"],
        )
        time_result = SimpleNamespace(
            raw_text="下午",
            success=False,
            datetime=None,
            start_datetime=None,
            end_datetime=None,
            ambiguous=False,
            need_followup=True,
            is_past=False,
            missing_slots=["specific_time"],
            reason="fuzzy_time_expression",
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=FakeSession(),
            dialog_service=FakeDialogService(),
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(time_result),
            voice_command_log_service=FakeVoiceCommandLogService(),
        )

        self.assertEqual(response.action, "events_queried")
        self.assertEqual(response.data["query_range"]["label"], "今天下午")
        self.assertEqual(calendar_service.queried_range["start_time"].hour, 12)
        self.assertEqual(calendar_service.queried_range["end_time"].hour, 18)

    async def test_delete_event_no_candidates_returns_not_found(self) -> None:
        payload = self.request_payload()
        payload.text = "删除健身"
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService(events=[])
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="delete_event",
            confidence=0.84,
            slots={"target_event": "fitness"},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=FakeSession(),
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "delete_event_not_found")
        self.assertFalse(response.need_user_reply)
        self.assertEqual(response.data["candidate_events"], [])
        self.assertEqual(calendar_service.searched_candidates["keyword"], "fitness")
        self.assertIsNone(dialog_service.created_state)
        self.assertIsNone(calendar_service.created_event)
        self.assertEqual(log_service.calls[-1][1]["entities"]["candidate_count"], 0)

    async def test_delete_event_single_candidate_saves_pending_confirm(self) -> None:
        payload = self.request_payload()
        payload.text = "删除明天的会议"
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService(
            events=[
                fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0)),
                fake_event("event-2", "meeting", datetime(2026, 5, 31, 10, 0, 0)),
            ]
        )
        nlu_result = SimpleNamespace(
            intent="delete_event",
            confidence=0.84,
            slots={"target_event": "meeting", "date_text": "tomorrow"},
            missing_slots=[],
        )
        time_result = SimpleNamespace(
            raw_text="tomorrow",
            success=True,
            datetime=datetime(2026, 5, 30, 0, 0, 0),
            start_datetime=None,
            end_datetime=None,
            ambiguous=False,
            need_followup=False,
            is_past=False,
            missing_slots=[],
            reason=None,
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(time_result),
            voice_command_log_service=FakeVoiceCommandLogService(),
        )

        self.assertEqual(response.action, "delete_event_need_confirm")
        self.assertTrue(response.need_user_reply)
        self.assertIn("event-1", [candidate["id"] for candidate in response.data["candidate_events"]])
        self.assertEqual(len(response.data["candidate_events"]), 1)
        self.assertEqual(dialog_service.created_state.status, "need_confirm")
        self.assertEqual(dialog_service.created_state.pending_intent, "delete_event")
        self.assertEqual(dialog_service.created_state.candidate_events[0]["id"], "event-1")
        self.assertEqual(dialog_service.created_state.slots["delete_target_event_id"], "event-1")
        self.assertTrue(session.committed)
        self.assertIsNone(calendar_service.created_event)

    async def test_delete_event_multiple_candidates_saves_candidate_events(self) -> None:
        payload = self.request_payload()
        payload.text = "删除会议"
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService(
            events=[
                fake_event("event-2", "meeting", datetime(2026, 5, 30, 15, 0, 0)),
                fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0)),
            ]
        )
        nlu_result = SimpleNamespace(
            intent="delete_event",
            confidence=0.84,
            slots={"target_event": "meeting"},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=FakeVoiceCommandLogService(),
        )

        self.assertEqual(response.action, "delete_event_need_select")
        self.assertTrue(response.need_user_reply)
        self.assertEqual([candidate["id"] for candidate in response.data["candidate_events"]], ["event-1", "event-2"])
        self.assertEqual(set(response.data["candidate_events"][0].keys()), {"id", "title", "start_time"})
        self.assertEqual(dialog_service.created_state.status, "need_select")
        self.assertEqual(dialog_service.created_state.candidate_events, response.data["candidate_events"])
        self.assertTrue(session.committed)
        self.assertIsNone(calendar_service.created_event)

    async def test_update_event_no_candidates_returns_not_found_without_updating(self) -> None:
        payload = self.request_payload()
        payload.text = "把会议改到下午三点"
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService(events=[])
        log_service = FakeVoiceCommandLogService()
        new_start = datetime(2026, 5, 30, 15, 0, 0).isoformat()
        nlu_result = SimpleNamespace(
            intent="update_event",
            confidence=0.88,
            slots={
                "target_event": "meeting",
                "start_time": new_start,
            },
            missing_slots=["target_event", "start_time"],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=FakeSession(),
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "update_event_not_found")
        self.assertFalse(response.need_user_reply)
        self.assertEqual(response.data["candidate_events"], [])
        self.assertEqual(response.data["updates"]["start_time"], new_start)
        self.assertEqual(calendar_service.searched_candidates["keyword"], "meeting")
        self.assertIsNone(dialog_service.created_state)
        self.assertIsNone(calendar_service.updated_event_id)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "update_event_draft_prepared")
        self.assertEqual(log_service.calls[-1][1]["entities"]["candidate_count"], 0)

    async def test_update_event_single_candidate_saves_pending_confirm_without_updating(self) -> None:
        payload = self.request_payload()
        payload.text = "把明天上午的会议改到下午三点"
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService(
            events=[
                fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0)),
                fake_event("event-2", "meeting", datetime(2026, 5, 31, 10, 0, 0)),
            ]
        )
        log_service = FakeVoiceCommandLogService()
        new_start = datetime(2026, 5, 30, 15, 0, 0).isoformat()
        nlu_result = SimpleNamespace(
            intent="update_event",
            confidence=0.88,
            slots={
                "target_event": "meeting",
                "target_start_time": datetime(2026, 5, 30, 0, 0, 0).isoformat(),
                "start_time": new_start,
                "reminder_offset_minutes": 15,
            },
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "update_event_need_confirm")
        self.assertTrue(response.need_user_reply)
        self.assertIn("meeting", response.reply)
        self.assertEqual([candidate["id"] for candidate in response.data["candidate_events"]], ["event-1"])
        self.assertEqual(response.data["updates"]["start_time"], new_start)
        self.assertEqual(response.data["updates"]["reminder_offset_minutes"], 15)
        self.assertEqual(dialog_service.created_state.status, "need_confirm")
        self.assertEqual(dialog_service.created_state.pending_intent, "update_event")
        self.assertEqual(dialog_service.created_state.slots["update_target_event_id"], "event-1")
        self.assertEqual(dialog_service.created_state.slots["update_draft"]["start_time"], new_start)
        self.assertEqual(dialog_service.created_state.slots["update_draft"]["reminder_offset_minutes"], 15)
        self.assertEqual(dialog_service.created_state.candidate_events[0]["id"], "event-1")
        self.assertTrue(session.committed)
        self.assertIsNone(calendar_service.updated_event_id)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "update_event_draft_prepared")

    async def test_update_event_multiple_candidates_saves_candidate_events_without_updating(self) -> None:
        payload = self.request_payload()
        payload.text = "把会议改到下午三点"
        session = FakeSession()
        dialog_service = FakeDialogService()
        calendar_service = FakeCalendarService(
            events=[
                fake_event("event-2", "meeting", datetime(2026, 5, 30, 15, 0, 0)),
                fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0)),
            ]
        )
        new_start = datetime(2026, 5, 31, 15, 0, 0).isoformat()
        nlu_result = SimpleNamespace(
            intent="update_event",
            confidence=0.88,
            slots={
                "target_event": "meeting",
                "start_time": new_start,
                "location": "conference room",
            },
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=FakeVoiceCommandLogService(),
        )

        self.assertEqual(response.action, "update_event_need_select")
        self.assertTrue(response.need_user_reply)
        self.assertEqual([candidate["id"] for candidate in response.data["candidate_events"]], ["event-1", "event-2"])
        self.assertEqual(set(response.data["candidate_events"][0].keys()), {"id", "title", "start_time"})
        self.assertEqual(response.data["updates"]["start_time"], new_start)
        self.assertEqual(response.data["updates"]["location"], "conference room")
        self.assertEqual(dialog_service.created_state.status, "need_select")
        self.assertEqual(dialog_service.created_state.pending_intent, "update_event")
        self.assertEqual(dialog_service.created_state.candidate_events, response.data["candidate_events"])
        self.assertEqual(dialog_service.created_state.slots["update_draft"]["location"], "conference room")
        self.assertTrue(session.committed)
        self.assertIsNone(calendar_service.updated_event_id)

    async def test_pending_update_confirm_updates_event_rebuilds_reminder_and_clears_state(self) -> None:
        payload = self.request_payload()
        payload.text = "确认"
        new_start = datetime(2026, 5, 30, 15, 0, 0)
        event = fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0))
        candidate = {"id": "event-1", "title": "meeting", "start_time": event.start_time.isoformat()}
        state = pending_update_state(
            status="need_confirm",
            candidates=[candidate],
            slots={
                "update_target_event_id": "event-1",
                "update_draft": {
                    "start_time": new_start.isoformat(),
                    "location": "conference room",
                    "reminder_offset_minutes": 30,
                },
            },
        )
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService(events=[event])
        reminder_service = FakeReminderService()
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="confirm",
            confidence=0.95,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=FakeConflictService(),
            reminder_service=reminder_service,
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "event_updated")
        self.assertFalse(response.need_user_reply)
        self.assertEqual(calendar_service.updated_event_id, "event-1")
        self.assertEqual(calendar_service.updated_event_payload.start_time, new_start)
        self.assertEqual(calendar_service.updated_event_payload.location, "conference room")
        self.assertEqual(response.data["event"]["id"], "event-1")
        self.assertEqual(response.data["event"]["location"], "conference room")
        self.assertEqual(reminder_service.cancelled_event_id, "event-1")
        self.assertEqual(reminder_service.cancelled_user_id, "user-1")
        self.assertEqual(reminder_service.created_reminder.event_id, "event-1")
        self.assertEqual(reminder_service.created_reminder.offset_minutes, 30)
        self.assertEqual(reminder_service.created_reminder.remind_time, datetime(2026, 5, 30, 14, 30, 0))
        self.assertTrue(dialog_service.completed)
        self.assertTrue(session.committed)
        self.assertEqual(log_service.calls[-1][1]["intent"], "update_event")
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "update_event_confirmed")
        self.assertEqual(log_service.calls[-1][1]["entities"]["event"]["id"], "event-1")

    async def test_pending_update_confirm_conflict_saves_confirm_without_updating(self) -> None:
        payload = self.request_payload()
        payload.text = "确认"
        new_start = datetime(2026, 5, 30, 15, 0, 0)
        event = fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0))
        conflict_event = fake_event("conflict-1", "project meeting", datetime(2026, 5, 30, 15, 0, 0))
        conflict_event.end_time = datetime(2026, 5, 30, 16, 0, 0)
        candidate = {"id": "event-1", "title": "meeting", "start_time": event.start_time.isoformat()}
        state = pending_update_state(
            status="need_confirm",
            candidates=[candidate],
            slots={
                "update_target_event_id": "event-1",
                "update_draft": {"start_time": new_start.isoformat()},
            },
        )
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService(events=[event])
        conflict_service = FakeConflictService(conflicts=[conflict_event])
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="confirm",
            confidence=0.95,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            conflict_service=conflict_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "update_event_conflict_need_confirm")
        self.assertTrue(response.need_user_reply)
        self.assertEqual(response.data["conflicts"][0]["id"], "conflict-1")
        self.assertEqual(conflict_service.calls[0]["method"], "list_conflicting_events_excluding_current")
        self.assertEqual(conflict_service.calls[0]["current_event_id"], "event-1")
        self.assertEqual(dialog_service.created_state.pending_intent, "update_event")
        self.assertEqual(dialog_service.created_state.status, "need_confirm")
        self.assertEqual(dialog_service.created_state.slots["conflict_confirmation"]["operation"], "update_event")
        self.assertIsNone(calendar_service.updated_event_id)
        self.assertTrue(session.committed)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "update_event_conflict_detected")

    async def test_pending_update_conflict_confirm_continues_update_and_clears_state(self) -> None:
        payload = self.request_payload()
        payload.text = "确认"
        new_start = datetime(2026, 5, 30, 15, 0, 0)
        event = fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0))
        candidate = {"id": "event-1", "title": "meeting", "start_time": event.start_time.isoformat()}
        conflicts = [
            {
                "id": "conflict-1",
                "title": "project meeting",
                "start_time": "2026-05-30T15:00:00",
                "end_time": "2026-05-30T16:00:00",
            }
        ]
        state = pending_conflict_state(
            pending_intent="update_event",
            slots={
                "update_target_event_id": "event-1",
                "update_draft": {
                    "start_time": new_start.isoformat(),
                    "location": "conference room",
                },
            },
            conflicts=conflicts,
            candidates=[candidate],
        )
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService(events=[event])
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="confirm",
            confidence=0.95,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "event_updated")
        self.assertFalse(response.need_user_reply)
        self.assertEqual(calendar_service.updated_event_id, "event-1")
        self.assertEqual(response.data["event"]["start_time"], str(new_start))
        self.assertEqual(response.data["event"]["location"], "conference room")
        self.assertEqual(response.data["conflicts"], conflicts)
        self.assertTrue(dialog_service.completed)
        self.assertTrue(session.committed)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "update_event_confirmed")
        self.assertEqual(log_service.calls[-1][1]["entities"]["conflicts"], conflicts)

    async def test_pending_update_deny_clears_state_without_updating(self) -> None:
        payload = self.request_payload()
        payload.text = "取消"
        event = fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0))
        candidate = {"id": "event-1", "title": "meeting", "start_time": event.start_time.isoformat()}
        state = pending_update_state(
            status="need_confirm",
            candidates=[candidate],
            slots={
                "update_target_event_id": "event-1",
                "update_draft": {"start_time": datetime(2026, 5, 30, 15, 0, 0).isoformat()},
            },
        )
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService(events=[event])
        reminder_service = FakeReminderService()
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="deny",
            confidence=0.9,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=reminder_service,
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "update_event_cancelled")
        self.assertEqual(response.reply, "已取消修改。")
        self.assertTrue(dialog_service.cancelled)
        self.assertTrue(session.committed)
        self.assertIsNone(calendar_service.updated_event_id)
        self.assertIsNone(reminder_service.created_reminder)
        self.assertIsNone(reminder_service.cancelled_event_id)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "update_event_cancelled")

    async def test_pending_update_confirm_missing_target_clears_state_without_updating(self) -> None:
        payload = self.request_payload()
        payload.text = "确认"
        deleted_event = fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0))
        deleted_event.status = "deleted"
        deleted_event.deleted_at = datetime(2026, 5, 30, 9, 0, 0)
        candidate = {"id": "event-1", "title": "meeting", "start_time": deleted_event.start_time.isoformat()}
        state = pending_update_state(
            status="need_confirm",
            candidates=[candidate],
            slots={
                "update_target_event_id": "event-1",
                "update_draft": {"start_time": datetime(2026, 5, 30, 15, 0, 0).isoformat()},
            },
        )
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService(events=[deleted_event])
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="confirm",
            confidence=0.95,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "update_event_not_found")
        self.assertFalse(response.need_user_reply)
        self.assertIsNone(response.data["event"])
        self.assertTrue(dialog_service.cancelled)
        self.assertTrue(session.committed)
        self.assertIsNone(calendar_service.updated_event_id)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "update_event_target_missing")

    async def test_pending_delete_confirm_soft_deletes_and_clears_state(self) -> None:
        payload = self.request_payload()
        payload.text = "确认"
        event = fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0))
        candidate = {"id": "event-1", "title": "meeting", "start_time": event.start_time.isoformat()}
        state = pending_delete_state(
            status="need_confirm",
            candidates=[candidate],
            slots={"delete_target_event_id": "event-1"},
        )
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService(events=[event])
        reminder_service = FakeReminderService()
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="confirm",
            confidence=0.95,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=reminder_service,
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "event_deleted")
        self.assertFalse(response.need_user_reply)
        self.assertEqual(calendar_service.soft_deleted_event_id, "event-1")
        self.assertEqual(reminder_service.cancelled_event_id, "event-1")
        self.assertEqual(reminder_service.cancelled_user_id, "user-1")
        self.assertTrue(dialog_service.completed)
        self.assertTrue(session.committed)
        self.assertEqual(response.data["undo"]["event_id"], "event-1")
        self.assertEqual(response.data["cancelled_reminders"][0]["status"], "cancelled")
        self.assertEqual(log_service.calls[-1][0], "success")
        self.assertEqual(log_service.calls[-1][1]["intent"], "delete_event")
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "delete_event_confirmed")
        self.assertEqual(log_service.calls[-1][1]["entities"]["undo"]["event_id"], "event-1")

    async def test_pending_delete_deny_clears_state_without_deleting(self) -> None:
        payload = self.request_payload()
        payload.text = "取消"
        candidate = {"id": "event-1", "title": "meeting", "start_time": "2026-05-30T10:00:00"}
        state = pending_delete_state(
            status="need_confirm",
            candidates=[candidate],
            slots={"delete_target_event_id": "event-1"},
        )
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService(events=[fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0))])
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="deny",
            confidence=0.9,
            slots={},
            missing_slots=[],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "delete_event_cancelled")
        self.assertEqual(response.reply, "已取消删除。")
        self.assertTrue(dialog_service.cancelled)
        self.assertTrue(session.committed)
        self.assertIsNone(calendar_service.soft_deleted_event_id)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "delete_event_cancelled")

    async def test_pending_delete_selection_enters_confirm_without_deleting(self) -> None:
        payload = self.request_payload()
        payload.text = "第二个"
        candidates = [
            {"id": "event-1", "title": "meeting", "start_time": "2026-05-30T10:00:00"},
            {"id": "event-2", "title": "meeting", "start_time": "2026-05-30T15:00:00"},
        ]
        state = pending_delete_state(status="need_select", candidates=candidates, slots={"target_event": "meeting"})
        session = FakeSession()
        dialog_service = FakeDialogService(current_state=state)
        calendar_service = FakeCalendarService(events=[
            fake_event("event-1", "meeting", datetime(2026, 5, 30, 10, 0, 0)),
            fake_event("event-2", "meeting", datetime(2026, 5, 30, 15, 0, 0)),
        ])
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="unknown",
            confidence=0.2,
            slots={},
            missing_slots=["intent"],
        )

        response = await voice_api.handle_voice_command(
            payload,
            session=session,
            dialog_service=dialog_service,
            calendar_service=calendar_service,
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "delete_event_need_confirm")
        self.assertTrue(response.need_user_reply)
        self.assertEqual(response.data["candidate_events"][0]["id"], "event-2")
        self.assertEqual(dialog_service.created_state.status, "need_confirm")
        self.assertEqual(dialog_service.created_state.slots["delete_target_event_id"], "event-2")
        self.assertEqual(dialog_service.created_state.candidate_events[0]["id"], "event-2")
        self.assertTrue(session.committed)
        self.assertIsNone(calendar_service.soft_deleted_event_id)
        self.assertEqual(log_service.calls[-1][1]["entities"]["operation"], "delete_event_candidate_selected")

    async def test_missing_slots_save_conversation_state_and_return_followup(self) -> None:
        session = FakeSession()
        dialog_service = FakeDialogService()
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="create_event",
            confidence=0.8,
            slots={"title": "meeting"},
            missing_slots=["start_time"],
        )

        response = await voice_api.handle_voice_command(
            self.request_payload(),
            session=session,
            dialog_service=dialog_service,
            calendar_service=FakeCalendarService(),
            reminder_service=FakeReminderService(),
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "need_more_info")
        self.assertTrue(response.need_user_reply)
        self.assertIn("具体时间", response.reply)
        self.assertTrue(session.committed)
        self.assertEqual(dialog_service.created_state.pending_intent, "create_event")
        self.assertEqual(dialog_service.created_state.missing_slots, ["start_time"])
        self.assertEqual([call[0] for call in log_service.calls], ["received", "parsed"])


if __name__ == "__main__":
    unittest.main()
