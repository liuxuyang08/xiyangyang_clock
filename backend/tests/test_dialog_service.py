from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIALOG_SERVICE_PATH = PROJECT_ROOT / "app" / "services" / "dialog_service.py"

spec = importlib.util.spec_from_file_location("dialog_service", DIALOG_SERVICE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load DialogService from {DIALOG_SERVICE_PATH}")
dialog_service_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dialog_service_module
spec.loader.exec_module(dialog_service_module)
DialogService = dialog_service_module.DialogService


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value
        self.ttl[key] = ttl

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)
            self.ttl.pop(key, None)


class FakeConversationRepository:
    def __init__(self) -> None:
        self.by_session: dict[tuple[str, str], SimpleNamespace] = {}

    async def get_by_session(self, user_id: str, session_id: str):
        return self.by_session.get((user_id, session_id))

    async def create(self, data: dict):
        conversation = SimpleNamespace(**data)
        self.by_session[(conversation.user_id, conversation.session_id)] = conversation
        return conversation

    async def update(self, conversation, data: dict):
        for field, value in data.items():
            setattr(conversation, field, value)
        self.by_session[(conversation.user_id, conversation.session_id)] = conversation
        return conversation


class DialogServiceTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.redis = FakeRedis()
        self.repository = FakeConversationRepository()
        self.service = DialogService(
            conversation_repository=self.repository,
            redis_client=self.redis,
            state_ttl_seconds=1800,
            confirm_ttl_seconds=900,
        )
        self.user_id = "user-1"
        self.session_id = "session-1"

    async def test_create_pending_state_writes_redis_and_database(self) -> None:
        state = await self.service.create_pending_state(
            user_id=self.user_id,
            session_id=self.session_id,
            pending_intent="create_event",
            slots={"title": "开会"},
            missing_slots=["start_time"],
        )

        self.assertEqual(state.status, "need_more_info")
        self.assertIn("voice:session:session-1", self.redis.store)
        self.assertIn("voice:user:user-1:state", self.redis.store)
        self.assertEqual(self.redis.ttl["voice:session:session-1"], 1800)
        self.assertEqual(
            self.repository.by_session[(self.user_id, self.session_id)].pending_intent,
            "create_event",
        )

    async def test_update_state_slots_merges_slots(self) -> None:
        await self.service.create_pending_state(
            user_id=self.user_id,
            session_id=self.session_id,
            pending_intent="create_event",
            slots={"title": "开会"},
            missing_slots=["start_time"],
        )

        state = await self.service.update_state_slots(
            user_id=self.user_id,
            session_id=self.session_id,
            slots={"start_time": "2026-05-30T15:00:00+08:00"},
            missing_slots=[],
        )

        self.assertIsNotNone(state)
        self.assertEqual(state.status, "pending")
        self.assertEqual(state.slots["title"], "开会")
        self.assertEqual(state.slots["start_time"], "2026-05-30T15:00:00+08:00")

    async def test_set_candidates_and_need_confirm_sets_expected_keys(self) -> None:
        await self.service.create_pending_state(
            user_id=self.user_id,
            session_id=self.session_id,
            pending_intent="delete_event",
            slots={"target_event": "会议"},
        )

        selected = await self.service.set_candidates(
            user_id=self.user_id,
            session_id=self.session_id,
            candidate_events=[{"id": "event-1", "title": "会议"}],
        )
        confirmed = await self.service.set_need_confirm(
            user_id=self.user_id,
            session_id=self.session_id,
        )

        self.assertIsNotNone(selected)
        self.assertEqual(selected.status, "need_select")
        self.assertIsNotNone(confirmed)
        self.assertEqual(confirmed.status, "need_confirm")
        self.assertIn("voice:user:user-1:pending_confirm", self.redis.store)
        self.assertEqual(self.redis.ttl["voice:user:user-1:pending_confirm"], 900)

    async def test_short_confirm_prefers_pending_confirm_context(self) -> None:
        await self.service.create_pending_state(
            user_id=self.user_id,
            session_id=self.session_id,
            pending_intent="delete_event",
            slots={"target_event": "会议"},
        )
        await self.service.set_need_confirm(
            user_id=self.user_id,
            session_id=self.session_id,
        )

        # Simulate stale session context. A short reply must prefer pending_confirm.
        stale_payload = json.dumps(
            {
                "id": "stale",
                "user_id": self.user_id,
                "session_id": self.session_id,
                "pending_intent": "create_event",
                "slots": {"title": "过期上下文"},
                "missing_slots": [],
                "candidate_events": [],
                "status": "pending",
                "expires_at": None,
                "updated_at": "2026-05-29T00:00:00+00:00",
            },
            ensure_ascii=False,
        )
        self.redis.store["voice:session:session-1"] = stale_payload

        state = await self.service.get_current_state(
            user_id=self.user_id,
            session_id=self.session_id,
            text="确认",
        )

        self.assertIsNotNone(state)
        self.assertEqual(state.status, "need_confirm")
        self.assertEqual(state.pending_intent, "delete_event")

    async def test_short_cancel_prefers_pending_confirm_context(self) -> None:
        await self.service.create_pending_state(
            user_id=self.user_id,
            session_id=self.session_id,
            pending_intent="delete_event",
            slots={"target_event": "会议"},
        )
        await self.service.set_need_confirm(
            user_id=self.user_id,
            session_id=self.session_id,
        )

        stale_payload = json.dumps(
            {
                "id": "stale",
                "user_id": self.user_id,
                "session_id": self.session_id,
                "pending_intent": "create_event",
                "slots": {"title": "交项目文档"},
                "missing_slots": ["start_time"],
                "candidate_events": [],
                "status": "need_more_info",
                "expires_at": None,
                "updated_at": "2026-05-29T00:00:00+00:00",
            },
            ensure_ascii=False,
        )
        self.redis.store["voice:session:session-1"] = stale_payload

        state = await self.service.get_current_state(
            user_id=self.user_id,
            session_id=self.session_id,
            text="取消",
        )

        self.assertIsNotNone(state)
        self.assertEqual(state.status, "need_confirm")
        self.assertEqual(state.pending_intent, "delete_event")

    async def test_cancel_state_marks_database_and_clears_redis(self) -> None:
        await self.service.create_pending_state(
            user_id=self.user_id,
            session_id=self.session_id,
            pending_intent="create_event",
        )
        state = await self.service.cancel_state(
            user_id=self.user_id,
            session_id=self.session_id,
        )

        self.assertIsNotNone(state)
        self.assertEqual(state.status, "cancelled")
        self.assertEqual(
            self.repository.by_session[(self.user_id, self.session_id)].status,
            "cancelled",
        )
        self.assertNotIn("voice:session:session-1", self.redis.store)
        self.assertNotIn("voice:user:user-1:state", self.redis.store)


if __name__ == "__main__":
    unittest.main()
