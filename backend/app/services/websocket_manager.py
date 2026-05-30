from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.redis import get_redis_client


logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        heartbeat_ttl_seconds: int | None = None,
    ) -> None:
        settings = get_settings()
        self.redis_client = get_redis_client() if redis_client is None else redis_client
        self.heartbeat_ttl_seconds = heartbeat_ttl_seconds or settings.ws_heartbeat_interval * 3
        self._connections: dict[str, dict[str, set[Any]]] = defaultdict(lambda: defaultdict(set))

    @property
    def connections(self) -> dict[str, dict[str, set[Any]]]:
        return self._connections

    async def connect(self, websocket: Any, user_id: str, session_id: str) -> None:
        await websocket.accept()
        self._connections[user_id][session_id].add(websocket)
        await self._write_online_state(user_id)

    async def disconnect(self, websocket: Any, user_id: str, session_id: str) -> None:
        user_sessions = self._connections.get(user_id)
        if user_sessions is None:
            await self._write_online_state(user_id)
            return

        session_connections = user_sessions.get(session_id)
        if session_connections is not None:
            session_connections.discard(websocket)
            if not session_connections:
                user_sessions.pop(session_id, None)

        if not user_sessions:
            self._connections.pop(user_id, None)

        await self._write_online_state(user_id)

    async def send_to_user(
        self,
        user_id: str,
        session_id: str,
        message: dict[str, Any],
    ) -> int:
        connections = list(self._connections.get(user_id, {}).get(session_id, set()))
        return await self._send_to_connections(
            connections=connections,
            message=message,
            user_id=user_id,
            session_id=session_id,
        )

    async def broadcast_to_user_sessions(
        self,
        user_id: str,
        message: dict[str, Any],
    ) -> int:
        sent_count = 0
        user_sessions = self._connections.get(user_id, {})
        for session_id, connections in list(user_sessions.items()):
            sent_count += await self._send_to_connections(
                connections=list(connections),
                message=message,
                user_id=user_id,
                session_id=session_id,
            )
        return sent_count

    async def heartbeat(self, user_id: str, session_id: str) -> dict[str, Any]:
        now = _utc_now_iso()
        await self._write_online_state(user_id)
        return {
            "type": "heartbeat_ack",
            "user_id": user_id,
            "session_id": session_id,
            "server_time": now,
        }

    def is_user_online(self, user_id: str) -> bool:
        return bool(self._connections.get(user_id))

    def session_count(self, user_id: str) -> int:
        return len(self._connections.get(user_id, {}))

    async def _send_to_connections(
        self,
        *,
        connections: list[Any],
        message: dict[str, Any],
        user_id: str,
        session_id: str,
    ) -> int:
        sent_count = 0
        stale_connections: list[Any] = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
                sent_count += 1
            except Exception:
                logger.exception(
                    "Failed to send websocket message",
                    extra={"user_id": user_id, "session_id": session_id},
                )
                stale_connections.append(websocket)

        for websocket in stale_connections:
            await self.disconnect(websocket, user_id=user_id, session_id=session_id)

        return sent_count

    async def _write_online_state(self, user_id: str) -> None:
        if self.redis_client is None:
            return

        key = self._online_key(user_id)
        sessions = sorted(self._connections.get(user_id, {}).keys())
        try:
            if sessions:
                payload = json.dumps(
                    {
                        "user_id": user_id,
                        "sessions": sessions,
                        "session_count": len(sessions),
                        "updated_at": _utc_now_iso(),
                    },
                    ensure_ascii=False,
                )
                await self.redis_client.setex(key, self.heartbeat_ttl_seconds, payload)
            else:
                await self.redis_client.delete(key)
        except Exception:
            logger.exception(
                "Failed to update websocket online state",
                extra={"user_id": user_id},
            )

    @staticmethod
    def _online_key(user_id: str) -> str:
        return f"voice:ws:online:{user_id}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


websocket_manager = WebSocketManager()

