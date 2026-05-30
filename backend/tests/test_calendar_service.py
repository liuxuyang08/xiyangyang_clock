from __future__ import annotations

from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = PROJECT_ROOT / "app" / "services" / "calendar_service.py"


class FakeEventRepository:
    def __init__(self, session) -> None:
        self.session = session
        self.events: dict[str, SimpleNamespace] = getattr(session, "events", {})
        self.calls: list[tuple[str, dict]] = []
        session.repository = self

    async def create(self, data: dict) -> SimpleNamespace:
        self.calls.append(("create", dict(data)))
        event = SimpleNamespace(**data, deleted_at=data.get("deleted_at"))
        self.events[event.id] = event
        return event

    async def get_by_id(self, event_id: str) -> SimpleNamespace | None:
        self.calls.append(("get_by_id", {"event_id": event_id}))
        return self.events.get(event_id)

    async def update(self, event: SimpleNamespace, data: dict) -> SimpleNamespace:
        self.calls.append(("update", dict(data)))
        for field, value in data.items():
            setattr(event, field, value)
        return event

    async def list_by_time_range(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        status: str | None = "active",
    ) -> list[SimpleNamespace]:
        self.calls.append(
            (
                "list_by_time_range",
                {
                    "user_id": user_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "status": status,
                },
            )
        )
        return [
            event
            for event in self.events.values()
            if event.user_id == user_id
            and event.status == status
            and event.deleted_at is None
            and start_time <= event.start_time < end_time
        ]

    async def soft_delete(self, event: SimpleNamespace, deleted_at: datetime) -> SimpleNamespace:
        self.calls.append(("soft_delete", {"event_id": event.id, "deleted_at": deleted_at}))
        event.status = "deleted"
        event.deleted_at = deleted_at
        return event

    async def search_candidates(
        self,
        user_id: str,
        keyword: str,
        limit: int = 10,
        status: str | None = "active",
    ) -> list[SimpleNamespace]:
        self.calls.append(
            (
                "search_candidates",
                {
                    "user_id": user_id,
                    "keyword": keyword,
                    "limit": limit,
                    "status": status,
                },
            )
        )
        return [
            event
            for event in self.events.values()
            if event.user_id == user_id
            and event.status == status
            and event.deleted_at is None
            and keyword in event.title
        ][:limit]


def install_import_stubs() -> dict[str, ModuleType | None]:
    originals = {
        name: sys.modules.get(name)
        for name in [
            "sqlalchemy",
            "sqlalchemy.ext",
            "sqlalchemy.ext.asyncio",
            "app.models",
            "app.models.event",
            "app.repositories",
            "app.repositories.event_repository",
            "app.schemas",
            "app.schemas.event",
        ]
    }

    sqlalchemy_module = ModuleType("sqlalchemy")
    sqlalchemy_ext_module = ModuleType("sqlalchemy.ext")
    sqlalchemy_asyncio_module = ModuleType("sqlalchemy.ext.asyncio")
    sqlalchemy_asyncio_module.AsyncSession = object

    app_models_module = ModuleType("app.models")
    app_models_event_module = ModuleType("app.models.event")
    app_models_event_module.Event = SimpleNamespace
    app_repositories_module = ModuleType("app.repositories")
    app_event_repository_module = ModuleType("app.repositories.event_repository")
    app_event_repository_module.EventRepository = FakeEventRepository
    app_schemas_module = ModuleType("app.schemas")
    app_event_schema_module = ModuleType("app.schemas.event")
    app_event_schema_module.EventCreate = object
    app_event_schema_module.EventUpdate = object

    sys.modules["sqlalchemy"] = sqlalchemy_module
    sys.modules["sqlalchemy.ext"] = sqlalchemy_ext_module
    sys.modules["sqlalchemy.ext.asyncio"] = sqlalchemy_asyncio_module
    sys.modules["app.models"] = app_models_module
    sys.modules["app.models.event"] = app_models_event_module
    sys.modules["app.repositories"] = app_repositories_module
    sys.modules["app.repositories.event_repository"] = app_event_repository_module
    sys.modules["app.schemas"] = app_schemas_module
    sys.modules["app.schemas.event"] = app_event_schema_module

    return originals


def restore_import_stubs(originals: dict[str, ModuleType | None]) -> None:
    for name, module in originals.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


original_modules = install_import_stubs()
spec = importlib.util.spec_from_file_location("calendar_service_under_test", SERVICE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load CalendarService from {SERVICE_PATH}")
calendar_service_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = calendar_service_module
spec.loader.exec_module(calendar_service_module)
restore_import_stubs(original_modules)

CalendarService = calendar_service_module.CalendarService


class FakeModelInput:
    def __init__(self, **data) -> None:
        self.data = dict(data)

    def model_dump(self, **kwargs) -> dict:
        exclude_unset = kwargs.get("exclude_unset", False)
        if exclude_unset:
            return {key: value for key, value in self.data.items() if value is not None}
        return dict(self.data)


class CalendarServiceTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.session = SimpleNamespace(events={})
        self.service = CalendarService(self.session)

    async def test_create_event_generates_id_and_active_status(self) -> None:
        start_time = datetime(2026, 5, 31, 15, 0, 0)

        event = await self.service.create_event(
            FakeModelInput(
                id=None,
                user_id="u001",
                title="交项目文档",
                start_time=start_time,
                status=None,
            )
        )

        self.assertIsInstance(event.id, str)
        self.assertTrue(event.id)
        self.assertEqual(event.user_id, "u001")
        self.assertEqual(event.title, "交项目文档")
        self.assertEqual(event.start_time, start_time)
        self.assertEqual(event.status, "active")
        self.assertIn(event.id, self.session.events)

    async def test_list_events_by_range_filters_active_events(self) -> None:
        active = SimpleNamespace(
            id="event-1",
            user_id="u001",
            title="今天项目讨论",
            start_time=datetime(2026, 5, 30, 10, 0, 0),
            status="active",
            deleted_at=None,
        )
        deleted = SimpleNamespace(
            id="event-2",
            user_id="u001",
            title="已删除会议",
            start_time=datetime(2026, 5, 30, 11, 0, 0),
            status="deleted",
            deleted_at=datetime(2026, 5, 30, 9, 0, 0),
        )
        self.session.events.update({active.id: active, deleted.id: deleted})

        events = await self.service.list_events_by_range(
            user_id="u001",
            start_time=datetime(2026, 5, 30, 0, 0, 0),
            end_time=datetime(2026, 5, 31, 0, 0, 0),
        )

        self.assertEqual(events, [active])
        self.assertEqual(self.session.repository.calls[-1][0], "list_by_time_range")
        self.assertEqual(self.session.repository.calls[-1][1]["status"], "active")

    async def test_get_update_soft_delete_and_search_candidates(self) -> None:
        event = SimpleNamespace(
            id="event-1",
            user_id="u001",
            title="明天的会议",
            start_time=datetime(2026, 5, 31, 10, 0, 0),
            end_time=None,
            location=None,
            status="active",
            deleted_at=None,
        )
        deleted = SimpleNamespace(
            id="event-2",
            user_id="u001",
            title="旧会议",
            start_time=datetime(2026, 5, 31, 9, 0, 0),
            end_time=None,
            location=None,
            status="deleted",
            deleted_at=datetime(2026, 5, 30, 9, 0, 0),
        )
        self.session.events.update({event.id: event, deleted.id: deleted})

        self.assertIs(await self.service.get_event("event-1"), event)
        self.assertIsNone(await self.service.get_event("event-2"))

        updated = await self.service.update_event(
            "event-1",
            FakeModelInput(
                title=None,
                start_time=datetime(2026, 6, 4, 14, 0, 0),
                location="会议室",
                deleted_at=datetime(2026, 5, 30, 9, 0, 0),
            ),
        )

        self.assertIs(updated, event)
        self.assertEqual(event.start_time, datetime(2026, 6, 4, 14, 0, 0))
        self.assertEqual(event.location, "会议室")
        self.assertIsNone(event.deleted_at)
        self.assertIsNotNone(getattr(event, "updated_at", None))

        candidates = await self.service.search_candidate_events(
            user_id="u001",
            keyword="会议",
            limit=10,
        )
        self.assertEqual(candidates, [event])
        self.assertEqual(self.session.repository.calls[-1][1]["status"], "active")

        deleted_event = await self.service.soft_delete_event("event-1")
        self.assertIs(deleted_event, event)
        self.assertEqual(event.status, "deleted")
        self.assertIsNotNone(event.deleted_at)
        self.assertIsNone(await self.service.soft_delete_event("missing"))


if __name__ == "__main__":
    unittest.main()
