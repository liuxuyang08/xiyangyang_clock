from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = PROJECT_ROOT / "app" / "services" / "voice_command_log_service.py"

spec = importlib.util.spec_from_file_location("voice_command_log_service", SERVICE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load VoiceCommandLogService from {SERVICE_PATH}")
voice_command_log_service_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = voice_command_log_service_module
spec.loader.exec_module(voice_command_log_service_module)
VoiceCommandLogService = voice_command_log_service_module.VoiceCommandLogService


class FakeVoiceCommandRepository:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.store: dict[str, SimpleNamespace] = {}

    async def create(self, data: dict) -> SimpleNamespace:
        if self.fail:
            raise RuntimeError("log storage unavailable")

        voice_command = SimpleNamespace(**data)
        self.store[voice_command.id] = voice_command
        return voice_command

    async def get_by_id(self, voice_command_id: str) -> SimpleNamespace | None:
        if self.fail:
            raise RuntimeError("log storage unavailable")

        return self.store.get(voice_command_id)

    async def update(self, voice_command: SimpleNamespace, data: dict) -> SimpleNamespace:
        if self.fail:
            raise RuntimeError("log storage unavailable")

        for field, value in data.items():
            setattr(voice_command, field, value)
        self.store[voice_command.id] = voice_command
        return voice_command


class VoiceCommandLogServiceTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logging.disable(logging.CRITICAL)
        self.repository = FakeVoiceCommandRepository()
        self.service = VoiceCommandLogService(voice_command_repository=self.repository)

    def tearDown(self) -> None:
        logging.disable(logging.NOTSET)

    async def test_record_received_creates_record_with_required_fields(self) -> None:
        record = await self.service.record_received(
            user_id="user-1",
            session_id="session-1",
            raw_text="create meeting tomorrow",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record.user_id, "user-1")
        self.assertEqual(record.session_id, "session-1")
        self.assertEqual(record.raw_text, "create meeting tomorrow")
        self.assertIsNone(record.intent)
        self.assertIsNone(record.confidence)
        self.assertEqual(record.entities, {})
        self.assertEqual(record.status, "received")
        self.assertIsNone(record.error_message)

    async def test_record_parsed_updates_existing_record(self) -> None:
        received = await self.service.record_received(
            user_id="user-1",
            session_id="session-1",
            raw_text="create meeting tomorrow",
        )

        parsed = await self.service.record_parsed(
            user_id="user-1",
            session_id="session-1",
            raw_text="create meeting tomorrow",
            intent="create_event",
            confidence=0.91,
            entities={"title": "meeting"},
            voice_command_id=received.id,
        )

        self.assertEqual(parsed.id, received.id)
        self.assertEqual(parsed.intent, "create_event")
        self.assertEqual(parsed.confidence, 0.91)
        self.assertEqual(parsed.entities, {"title": "meeting"})
        self.assertEqual(parsed.status, "parsed")
        self.assertIsNone(parsed.error_message)

    async def test_record_success_and_failed_set_terminal_status(self) -> None:
        success = await self.service.record_success(
            user_id="user-1",
            session_id="session-1",
            raw_text="show my calendar",
            intent="query_event",
            confidence=0.84,
            entities={"range": "today"},
        )
        failed = await self.service.record_failed(
            user_id="user-1",
            session_id="session-2",
            raw_text="delete a meeting",
            error_message=RuntimeError("missing confirmation"),
            intent="delete_event",
            confidence=0.7,
            entities={"target_event": "meeting"},
        )

        self.assertEqual(success.status, "success")
        self.assertIsNone(success.error_message)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.error_message, "missing confirmation")

    async def test_logging_failure_returns_none(self) -> None:
        service = VoiceCommandLogService(
            voice_command_repository=FakeVoiceCommandRepository(fail=True)
        )

        record = await service.record_received(
            user_id="user-1",
            session_id="session-1",
            raw_text="create meeting tomorrow",
        )

        self.assertIsNone(record)


if __name__ == "__main__":
    unittest.main()
