from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_state import ConversationState


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: dict[str, Any]) -> ConversationState:
        conversation = ConversationState(**data)
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get_by_id(self, conversation_id: str) -> ConversationState | None:
        return await self.session.get(ConversationState, conversation_id)

    async def update(
        self,
        conversation: ConversationState,
        data: dict[str, Any],
    ) -> ConversationState:
        for field, value in data.items():
            setattr(conversation, field, value)

        await self.session.flush()
        return conversation

    async def list(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ConversationState]:
        statement = (
            select(ConversationState)
            .where(ConversationState.user_id == user_id)
            .order_by(ConversationState.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_by_session(
        self,
        user_id: str,
        session_id: str,
    ) -> ConversationState | None:
        statement = select(ConversationState).where(
            ConversationState.user_id == user_id,
            ConversationState.session_id == session_id,
        )
        result = await self.session.scalars(statement)
        return result.first()
