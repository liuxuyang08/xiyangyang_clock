from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.voice_command import VoiceCommand


class VoiceCommandRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: dict[str, Any]) -> VoiceCommand:
        voice_command = VoiceCommand(**data)
        self.session.add(voice_command)
        await self.session.flush()
        return voice_command

    async def get_by_id(self, voice_command_id: str) -> VoiceCommand | None:
        return await self.session.get(VoiceCommand, voice_command_id)

    async def update(
        self,
        voice_command: VoiceCommand,
        data: dict[str, Any],
    ) -> VoiceCommand:
        for field, value in data.items():
            setattr(voice_command, field, value)

        await self.session.flush()
        return voice_command

    async def list(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[VoiceCommand]:
        statement = (
            select(VoiceCommand)
            .where(VoiceCommand.user_id == user_id)
            .order_by(VoiceCommand.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def search(
        self,
        user_id: str,
        status: str | None = None,
        intent: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[VoiceCommand]:
        statement = select(VoiceCommand).where(VoiceCommand.user_id == user_id)

        if status is not None:
            statement = statement.where(VoiceCommand.status == status)

        if intent is not None:
            statement = statement.where(VoiceCommand.intent == intent)

        statement = (
            statement.order_by(VoiceCommand.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())
