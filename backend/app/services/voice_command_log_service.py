from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

try:  # pragma: no cover - optional when this file is loaded in isolation
    from app.db.session import SessionLocal
except Exception:  # pragma: no cover
    SessionLocal = None

try:  # pragma: no cover - optional when this file is loaded in isolation
    from app.repositories.voice_command_repository import VoiceCommandRepository
except Exception:  # pragma: no cover
    VoiceCommandRepository = None


logger = logging.getLogger(__name__)


class VoiceCommandLogService:
    STATUS_RECEIVED = "received"
    STATUS_PARSED = "parsed"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"

    def __init__(
        self,
        voice_command_repository: Any | None = None,
        session_factory: Any | None = None,
    ) -> None:
        self.voice_command_repository = voice_command_repository
        self.session_factory = session_factory if session_factory is not None else SessionLocal

    async def record_received(
        self,
        user_id: str,
        session_id: str,
        raw_text: str,
        *,
        voice_command_id: str | None = None,
    ) -> Any | None:
        return await self._record(
            user_id=user_id,
            session_id=session_id,
            raw_text=raw_text,
            status=self.STATUS_RECEIVED,
            intent=None,
            confidence=None,
            entities=None,
            error_message=None,
            voice_command_id=voice_command_id,
        )

    async def record_parsed(
        self,
        user_id: str,
        session_id: str,
        raw_text: str,
        *,
        intent: str | None,
        confidence: float | None,
        entities: Mapping[str, Any] | None = None,
        voice_command_id: str | None = None,
    ) -> Any | None:
        return await self._record(
            user_id=user_id,
            session_id=session_id,
            raw_text=raw_text,
            status=self.STATUS_PARSED,
            intent=intent,
            confidence=confidence,
            entities=entities,
            error_message=None,
            voice_command_id=voice_command_id,
        )

    async def record_success(
        self,
        user_id: str,
        session_id: str,
        raw_text: str,
        *,
        intent: str | None = None,
        confidence: float | None = None,
        entities: Mapping[str, Any] | None = None,
        voice_command_id: str | None = None,
    ) -> Any | None:
        return await self._record(
            user_id=user_id,
            session_id=session_id,
            raw_text=raw_text,
            status=self.STATUS_SUCCESS,
            intent=intent,
            confidence=confidence,
            entities=entities,
            error_message=None,
            voice_command_id=voice_command_id,
        )

    async def record_failed(
        self,
        user_id: str,
        session_id: str,
        raw_text: str,
        error_message: str | BaseException | None,
        *,
        intent: str | None = None,
        confidence: float | None = None,
        entities: Mapping[str, Any] | None = None,
        voice_command_id: str | None = None,
    ) -> Any | None:
        return await self._record(
            user_id=user_id,
            session_id=session_id,
            raw_text=raw_text,
            status=self.STATUS_FAILED,
            intent=intent,
            confidence=confidence,
            entities=entities,
            error_message=str(error_message) if error_message is not None else None,
            voice_command_id=voice_command_id,
        )

    async def _record(
        self,
        *,
        user_id: str,
        session_id: str,
        raw_text: str,
        status: str,
        intent: str | None,
        confidence: float | None,
        entities: Mapping[str, Any] | None,
        error_message: str | None,
        voice_command_id: str | None,
    ) -> Any | None:
        try:
            data = {
                "user_id": user_id,
                "session_id": session_id,
                "raw_text": raw_text,
                "intent": intent,
                "confidence": self._normalize_confidence(confidence),
                "entities": self._normalize_entities(entities),
                "status": status,
                "error_message": error_message,
            }

            return await self._write(data=data, voice_command_id=voice_command_id)
        except Exception:
            logger.warning("Failed to record voice command log", exc_info=True)
            return None

    async def _write(
        self,
        *,
        data: dict[str, Any],
        voice_command_id: str | None,
    ) -> Any | None:
        repository = self.voice_command_repository
        if repository is not None:
            return await self._upsert(repository, data=data, voice_command_id=voice_command_id)

        if self.session_factory is None or VoiceCommandRepository is None:
            return None

        async with self.session_factory() as session:
            repository = VoiceCommandRepository(session)
            try:
                voice_command = await self._upsert(
                    repository,
                    data=data,
                    voice_command_id=voice_command_id,
                )
                await session.commit()
                return voice_command
            except Exception:
                await session.rollback()
                raise

    async def _upsert(
        self,
        repository: Any,
        *,
        data: dict[str, Any],
        voice_command_id: str | None,
    ) -> Any:
        if voice_command_id is not None:
            existing = await repository.get_by_id(voice_command_id)
            if existing is not None:
                return await repository.update(existing, data)

        return await repository.create({"id": voice_command_id or str(uuid4()), **data})

    def _normalize_entities(self, entities: Mapping[str, Any] | None) -> dict[str, Any]:
        if entities is None:
            return {}

        payload = dict(entities)
        return json.loads(json.dumps(payload, ensure_ascii=False, default=str))

    def _normalize_confidence(self, confidence: float | None) -> float | None:
        if confidence is None:
            return None

        try:
            return float(confidence)
        except (TypeError, ValueError):
            return None
