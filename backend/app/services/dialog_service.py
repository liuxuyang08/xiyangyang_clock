from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
from typing import Any
from uuid import uuid4

try:  # pragma: no cover - optional in isolated unit tests
    from app.core.redis import get_redis_client
except Exception:  # pragma: no cover - Redis/config dependencies may be absent in tests
    get_redis_client = None

try:  # pragma: no cover - optional in isolated unit tests
    from app.repositories.conversation_repository import ConversationRepository
except Exception:  # pragma: no cover - SQLAlchemy may be absent in stripped test envs
    ConversationRepository = None


SESSION_STATE_TTL_SECONDS = 30 * 60
PENDING_CONFIRM_TTL_SECONDS = 15 * 60

TERMINAL_STATUSES = {"completed", "cancelled", "expired"}
CONFIRM_SHORT_TEXTS = {"确认", "是的", "对", "对的", "可以", "好的", "没错", "确定"}
CANCEL_SHORT_TEXTS = {"取消", "不要了", "不用了", "算了", "不是", "不对"}


@dataclass(slots=True)
class DialogStateData:
    id: str
    user_id: str
    session_id: str
    pending_intent: str | None = None
    slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    candidate_events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
    expires_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        now = now or datetime.now(timezone.utc)
        return self._ensure_aware(self.expires_at) <= now

    def to_cache_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["expires_at"] = self.expires_at.isoformat() if self.expires_at else None
        payload["updated_at"] = self.updated_at.isoformat()
        return payload

    @staticmethod
    def _ensure_aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class DialogService:
    def __init__(
        self,
        session: Any | None = None,
        conversation_repository: Any | None = None,
        redis_client: Any | None = None,
        state_ttl_seconds: int = SESSION_STATE_TTL_SECONDS,
        confirm_ttl_seconds: int = PENDING_CONFIRM_TTL_SECONDS,
    ) -> None:
        self.conversation_repository = conversation_repository
        if self.conversation_repository is None and session is not None and ConversationRepository is not None:
            self.conversation_repository = ConversationRepository(session)

        if redis_client is not None:
            self.redis_client = redis_client
        elif get_redis_client is not None:
            self.redis_client = get_redis_client()
        else:
            self.redis_client = None

        self.state_ttl_seconds = state_ttl_seconds
        self.confirm_ttl_seconds = confirm_ttl_seconds

    async def get_current_state(
        self,
        user_id: str,
        session_id: str,
        text: str | None = None,
    ) -> DialogStateData | None:
        state = await self._load_current_state(
            user_id=user_id,
            session_id=session_id,
            text=text,
            include_terminal=False,
        )
        if state is None:
            return None

        if state.is_expired():
            await self._mark_state(state, "expired", clear_redis=True)
            return None

        return state

    async def create_pending_state(
        self,
        user_id: str,
        session_id: str,
        pending_intent: str | None,
        slots: dict[str, Any] | None = None,
        missing_slots: list[str] | None = None,
        candidate_events: list[dict[str, Any]] | None = None,
        status: str | None = None,
        ttl_seconds: int | None = None,
    ) -> DialogStateData:
        ttl = ttl_seconds or self.state_ttl_seconds
        now = datetime.now(timezone.utc)
        normalized_missing_slots = list(missing_slots or [])
        state = DialogStateData(
            id=str(uuid4()),
            user_id=user_id,
            session_id=session_id,
            pending_intent=pending_intent,
            slots=dict(slots or {}),
            missing_slots=normalized_missing_slots,
            candidate_events=list(candidate_events or []),
            status=status or ("need_more_info" if normalized_missing_slots else "pending"),
            expires_at=now + timedelta(seconds=ttl),
            updated_at=now,
        )

        state = await self._save_persistent_state(state)
        await self._cache_state(state, ttl_seconds=ttl)
        return state

    async def update_state_slots(
        self,
        user_id: str,
        session_id: str,
        slots: dict[str, Any],
        missing_slots: list[str] | None = None,
        ttl_seconds: int | None = None,
    ) -> DialogStateData | None:
        state = await self.get_current_state(user_id=user_id, session_id=session_id)
        if state is None:
            return None

        ttl = ttl_seconds or self.state_ttl_seconds
        state.slots.update(slots)
        if missing_slots is not None:
            state.missing_slots = list(missing_slots)
            state.status = "need_more_info" if state.missing_slots else "pending"
        state.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        state = await self._touch_and_save(state)
        await self._cache_state(state, ttl_seconds=ttl)
        return state

    async def set_candidates(
        self,
        user_id: str,
        session_id: str,
        candidate_events: list[dict[str, Any]],
        ttl_seconds: int | None = None,
    ) -> DialogStateData | None:
        state = await self.get_current_state(user_id=user_id, session_id=session_id)
        if state is None:
            return None

        ttl = ttl_seconds or self.state_ttl_seconds
        state.candidate_events = list(candidate_events)
        state.status = "need_select"
        state.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        state = await self._touch_and_save(state)
        await self._cache_state(state, ttl_seconds=ttl)
        return state

    async def set_need_confirm(
        self,
        user_id: str,
        session_id: str,
        ttl_seconds: int | None = None,
    ) -> DialogStateData | None:
        state = await self.get_current_state(user_id=user_id, session_id=session_id)
        if state is None:
            return None

        ttl = ttl_seconds or self.confirm_ttl_seconds
        state.status = "need_confirm"
        state.expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)

        state = await self._touch_and_save(state)
        await self._cache_state(
            state,
            ttl_seconds=ttl,
            include_pending_confirm=True,
        )
        return state

    async def complete_state(
        self,
        user_id: str,
        session_id: str,
    ) -> DialogStateData | None:
        state = await self.get_current_state(
            user_id=user_id,
            session_id=session_id,
        )
        if state is None:
            return None
        return await self._mark_state(state, "completed", clear_redis=True)

    async def cancel_state(
        self,
        user_id: str,
        session_id: str,
    ) -> DialogStateData | None:
        state = await self.get_current_state(
            user_id=user_id,
            session_id=session_id,
            text="取消",
        )
        if state is None:
            return None
        return await self._mark_state(state, "cancelled", clear_redis=True)

    async def expire_state(
        self,
        user_id: str,
        session_id: str,
    ) -> DialogStateData | None:
        state = await self._load_current_state(
            user_id=user_id,
            session_id=session_id,
            include_terminal=False,
        )
        if state is None:
            return None
        return await self._mark_state(state, "expired", clear_redis=True)

    def is_contextual_short_reply(self, text: str) -> bool:
        normalized_text = text.strip()
        return normalized_text in CONFIRM_SHORT_TEXTS or normalized_text in CANCEL_SHORT_TEXTS

    async def _load_current_state(
        self,
        user_id: str,
        session_id: str,
        text: str | None = None,
        include_terminal: bool = False,
    ) -> DialogStateData | None:
        for key in self._state_lookup_keys(user_id=user_id, session_id=session_id, text=text):
            cached_state = await self._load_cached_state(key)
            if cached_state is not None and (
                include_terminal or cached_state.status not in TERMINAL_STATUSES
            ):
                return cached_state

        persistent_state = await self._load_persistent_state(
            user_id=user_id,
            session_id=session_id,
        )
        if persistent_state is None:
            return None

        if not include_terminal and persistent_state.status in TERMINAL_STATUSES:
            return None

        return persistent_state

    def _state_lookup_keys(
        self,
        user_id: str,
        session_id: str,
        text: str | None = None,
    ) -> list[str]:
        session_key = self._session_key(session_id)
        user_state_key = self._user_state_key(user_id)
        pending_confirm_key = self._pending_confirm_key(user_id)

        if text is not None and self.is_contextual_short_reply(text):
            return [pending_confirm_key, user_state_key, session_key]

        return [session_key, user_state_key, pending_confirm_key]

    async def _load_cached_state(self, key: str) -> DialogStateData | None:
        client = self.redis_client
        if client is None:
            return None

        try:
            payload = await client.get(key)
        except Exception:
            return None

        if not payload:
            return None

        try:
            data = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return None

        if not isinstance(data, dict):
            return None

        return self._state_from_mapping(data)

    async def _load_persistent_state(
        self,
        user_id: str,
        session_id: str,
    ) -> DialogStateData | None:
        repository = self.conversation_repository
        if repository is None:
            return None

        try:
            conversation = await repository.get_by_session(
                user_id=user_id,
                session_id=session_id,
            )
        except Exception:
            return None

        if conversation is None:
            return None

        return self._state_from_model(conversation)

    async def _save_persistent_state(self, state: DialogStateData) -> DialogStateData:
        repository = self.conversation_repository
        if repository is None:
            return state

        existing = await repository.get_by_session(
            user_id=state.user_id,
            session_id=state.session_id,
        )
        data = self._state_to_model_data(state)

        if existing is None:
            saved = await repository.create({"id": state.id, **data})
            return self._state_from_model(saved)

        state.id = existing.id
        saved = await repository.update(existing, data)
        return self._state_from_model(saved)

    async def _touch_and_save(self, state: DialogStateData) -> DialogStateData:
        state.updated_at = datetime.now(timezone.utc)
        return await self._save_persistent_state(state)

    async def _cache_state(
        self,
        state: DialogStateData,
        ttl_seconds: int,
        include_pending_confirm: bool = False,
    ) -> None:
        client = self.redis_client
        if client is None:
            return

        payload = json.dumps(state.to_cache_dict(), ensure_ascii=False, default=str)
        keys = [
            self._session_key(state.session_id),
            self._user_state_key(state.user_id),
        ]

        try:
            for key in keys:
                await client.setex(key, ttl_seconds, payload)

            if include_pending_confirm or state.status == "need_confirm":
                await client.setex(
                    self._pending_confirm_key(state.user_id),
                    min(ttl_seconds, self.confirm_ttl_seconds),
                    payload,
                )
            else:
                await client.delete(self._pending_confirm_key(state.user_id))
        except Exception:
            return

    async def _delete_cached_state(self, user_id: str, session_id: str) -> None:
        client = self.redis_client
        if client is None:
            return

        try:
            await client.delete(
                self._session_key(session_id),
                self._user_state_key(user_id),
                self._pending_confirm_key(user_id),
            )
        except Exception:
            return

    async def _mark_state(
        self,
        state: DialogStateData,
        status: str,
        clear_redis: bool,
    ) -> DialogStateData:
        state.status = status
        state.updated_at = datetime.now(timezone.utc)
        state.expires_at = state.updated_at
        state = await self._save_persistent_state(state)

        if clear_redis:
            await self._delete_cached_state(
                user_id=state.user_id,
                session_id=state.session_id,
            )

        return state

    def _state_from_mapping(self, data: dict[str, Any]) -> DialogStateData:
        return DialogStateData(
            id=str(data.get("id") or uuid4()),
            user_id=str(data.get("user_id", "")),
            session_id=str(data.get("session_id", "")),
            pending_intent=data.get("pending_intent"),
            slots=dict(data.get("slots") or {}),
            missing_slots=list(data.get("missing_slots") or []),
            candidate_events=list(data.get("candidate_events") or []),
            status=str(data.get("status") or "pending"),
            expires_at=self._parse_datetime(data.get("expires_at")),
            updated_at=self._parse_datetime(data.get("updated_at")) or datetime.now(timezone.utc),
        )

    def _state_from_model(self, model: Any) -> DialogStateData:
        return DialogStateData(
            id=str(model.id),
            user_id=str(model.user_id),
            session_id=str(model.session_id),
            pending_intent=model.pending_intent,
            slots=dict(model.slots or {}),
            missing_slots=list(model.missing_slots or []),
            candidate_events=list(model.candidate_events or []),
            status=str(model.status or "pending"),
            expires_at=self._ensure_aware_datetime(model.expires_at),
            updated_at=self._ensure_aware_datetime(model.updated_at) or datetime.now(timezone.utc),
        )

    def _state_to_model_data(self, state: DialogStateData) -> dict[str, Any]:
        return {
            "user_id": state.user_id,
            "session_id": state.session_id,
            "pending_intent": state.pending_intent,
            "slots": state.slots,
            "missing_slots": state.missing_slots,
            "candidate_events": state.candidate_events,
            "status": state.status,
            "expires_at": state.expires_at,
            "updated_at": state.updated_at,
        }

    def _parse_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return self._ensure_aware_datetime(value)
        if not isinstance(value, str):
            return None

        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return self._ensure_aware_datetime(parsed)

    def _ensure_aware_datetime(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _session_key(self, session_id: str) -> str:
        return f"voice:session:{session_id}"

    def _user_state_key(self, user_id: str) -> str:
        return f"voice:user:{user_id}:state"

    def _pending_confirm_key(self, user_id: str) -> str:
        return f"voice:user:{user_id}:pending_confirm"
