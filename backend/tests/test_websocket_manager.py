from __future__ import annotations

import importlib.util
import json
import logging
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = PROJECT_ROOT / "app" / "services" / "websocket_manager.py"


def install_import_stubs() -> dict[str, ModuleType | None]:
    originals = {
        name: sys.modules.get(name)
        for name in [
            "app",
            "app.core",
            "app.core.config",
            "app.core.redis",
        ]
    }

    app_module = ModuleType("app")
    app_core_module = ModuleType("app.core")
    app_core_config_module = ModuleType("app.core.config")
    app_core_redis_module = ModuleType("app.core.redis")
    app_core_config_module.get_settings = lambda: SimpleNamespace(ws_heartbeat_interval=30)
    app_core_redis_module.get_redis_client = lambda: None

    sys.modules["app"] = app_module
    sys.modules["app.core"] = app_core_module
    sys.modules["app.core.config"] = app_core_config_module
    sys.modules["app.core.redis"] = app_core_redis_module

    return originals


def restore_import_stubs(originals: dict[str, ModuleType | None]) -> None:
    for name, module in originals.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


original_modules = install_import_stubs()
spec = importlib.util.spec_from_file_location("websocket_manager", MANAGER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load websocket manager from {MANAGER_PATH}")
websocket_manager_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = websocket_manager_module
spec.loader.exec_module(websocket_manager_module)
restore_import_stubs(original_modules)

WebSocketManager = websocket_manager_module.WebSocketManager


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}
        self.deleted: list[str] = []

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value
        self.ttl[key] = ttl

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)
        self.ttl.pop(key, None)
        self.deleted.append(key)


class FakeWebSocket:
    def __init__(self, fail_send: bool = False) -> None:
        self.accepted = False
        self.sent: list[dict] = []
        self.fail_send = fail_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict) -> None:
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append(message)


class WebSocketManagerTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)

    def tearDown(self) -> None:
        logging.disable(logging.NOTSET)

    async def test_connect_records_session_and_online_state(self) -> None:
        redis = FakeRedis()
        manager = WebSocketManager(redis_client=redis, heartbeat_ttl_seconds=90)
        websocket = FakeWebSocket()

        await manager.connect(websocket, user_id="user-1", session_id="session-1")

        self.assertTrue(websocket.accepted)
        self.assertTrue(manager.is_user_online("user-1"))
        self.assertEqual(manager.session_count("user-1"), 1)
        payload = json.loads(redis.store["voice:ws:online:user-1"])
        self.assertEqual(payload["user_id"], "user-1")
        self.assertEqual(payload["sessions"], ["session-1"])
        self.assertEqual(redis.ttl["voice:ws:online:user-1"], 90)

    async def test_disconnect_removes_empty_user_and_online_state(self) -> None:
        redis = FakeRedis()
        manager = WebSocketManager(redis_client=redis, heartbeat_ttl_seconds=90)
        websocket = FakeWebSocket()

        await manager.connect(websocket, user_id="user-1", session_id="session-1")
        await manager.disconnect(websocket, user_id="user-1", session_id="session-1")

        self.assertFalse(manager.is_user_online("user-1"))
        self.assertNotIn("voice:ws:online:user-1", redis.store)
        self.assertEqual(redis.deleted, ["voice:ws:online:user-1"])

    async def test_send_to_user_targets_single_session(self) -> None:
        manager = WebSocketManager(redis_client=FakeRedis(), heartbeat_ttl_seconds=90)
        first = FakeWebSocket()
        second = FakeWebSocket()
        await manager.connect(first, user_id="user-1", session_id="session-1")
        await manager.connect(second, user_id="user-1", session_id="session-2")

        sent_count = await manager.send_to_user(
            "user-1",
            "session-1",
            {"type": "notice", "text": "hello"},
        )

        self.assertEqual(sent_count, 1)
        self.assertEqual(first.sent, [{"type": "notice", "text": "hello"}])
        self.assertEqual(second.sent, [])

    async def test_broadcast_to_user_sessions_sends_all_sessions(self) -> None:
        manager = WebSocketManager(redis_client=FakeRedis(), heartbeat_ttl_seconds=90)
        first = FakeWebSocket()
        second = FakeWebSocket()
        await manager.connect(first, user_id="user-1", session_id="session-1")
        await manager.connect(second, user_id="user-1", session_id="session-2")

        sent_count = await manager.broadcast_to_user_sessions(
            "user-1",
            {"type": "notice"},
        )

        self.assertEqual(sent_count, 2)
        self.assertEqual(first.sent, [{"type": "notice"}])
        self.assertEqual(second.sent, [{"type": "notice"}])

    async def test_heartbeat_refreshes_online_state_and_returns_ack(self) -> None:
        redis = FakeRedis()
        manager = WebSocketManager(redis_client=redis, heartbeat_ttl_seconds=90)
        websocket = FakeWebSocket()
        await manager.connect(websocket, user_id="user-1", session_id="session-1")

        response = await manager.heartbeat(user_id="user-1", session_id="session-1")

        self.assertEqual(response["type"], "heartbeat_ack")
        self.assertEqual(response["user_id"], "user-1")
        self.assertEqual(response["session_id"], "session-1")
        payload = json.loads(redis.store["voice:ws:online:user-1"])
        self.assertEqual(payload["sessions"], ["session-1"])

    async def test_failed_send_disconnects_stale_connection(self) -> None:
        redis = FakeRedis()
        manager = WebSocketManager(redis_client=redis, heartbeat_ttl_seconds=90)
        websocket = FakeWebSocket(fail_send=True)
        await manager.connect(websocket, user_id="user-1", session_id="session-1")

        sent_count = await manager.send_to_user(
            "user-1",
            "session-1",
            {"type": "notice"},
        )

        self.assertEqual(sent_count, 0)
        self.assertFalse(manager.is_user_online("user-1"))
        self.assertNotIn("voice:ws:online:user-1", redis.store)


if __name__ == "__main__":
    unittest.main()
