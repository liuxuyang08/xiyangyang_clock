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
            "app.schemas.voice",
            "app.services",
            "app.services.dialog_service",
            "app.services.nlu_service",
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
    dialog_service_module = ModuleType("app.services.dialog_service")
    nlu_service_module = ModuleType("app.services.nlu_service")
    time_parser_module = ModuleType("app.services.time_parser")
    voice_command_log_service_module = ModuleType("app.services.voice_command_log_service")
    dialog_service_module.DialogService = object
    nlu_service_module.NLUResult = object
    nlu_service_module.NLUService = object
    time_parser_module.TimeParser = object
    voice_command_log_service_module.VoiceCommandLogService = object
    sys.modules["app.services"] = app_services_module
    sys.modules["app.services.dialog_service"] = dialog_service_module
    sys.modules["app.services.nlu_service"] = nlu_service_module
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

    async def get_current_state(self, user_id: str, session_id: str, text: str | None = None):
        return self.current_state

    async def create_pending_state(self, **kwargs):
        self.created_state = SimpleNamespace(id="state-1", **kwargs)
        return self.created_state


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


class VoiceApiTestCase(unittest.IsolatedAsyncioTestCase):
    def request_payload(self) -> SimpleNamespace:
        return SimpleNamespace(
            user_id="user-1",
            session_id="session-1",
            text="schedule meeting tomorrow at three",
            timezone="Asia/Shanghai",
            client_time=datetime(2026, 5, 29, 15, 0, 0),
        )

    async def test_complete_command_returns_placeholder_without_business_execution(self) -> None:
        session = FakeSession()
        log_service = FakeVoiceCommandLogService()
        nlu_result = SimpleNamespace(
            intent="create_event",
            confidence=0.91,
            slots={"title": "meeting", "date_text": "tomorrow", "time_text": "3pm"},
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
            nlu_service=FakeNLUService(nlu_result),
            time_parser=FakeTimeParser(time_result),
            voice_command_log_service=log_service,
        )

        self.assertEqual(response.action, "voice_command_recognized")
        self.assertFalse(response.need_user_reply)
        self.assertEqual(response.data["business_execution"], "pending")
        self.assertEqual(response.data["slots"]["start_time"], "2026-05-30T15:00:00")
        self.assertEqual([call[0] for call in log_service.calls], ["received", "parsed", "success"])
        self.assertFalse(session.committed)

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
