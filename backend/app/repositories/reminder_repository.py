from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reminder import Reminder


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: dict[str, Any]) -> Reminder:
        reminder = Reminder(**data)
        self.session.add(reminder)
        await self.session.flush()
        return reminder

    async def get_by_id(self, reminder_id: str) -> Reminder | None:
        return await self.session.get(Reminder, reminder_id)

    async def update(self, reminder: Reminder, data: dict[str, Any]) -> Reminder:
        for field, value in data.items():
            setattr(reminder, field, value)

        await self.session.flush()
        return reminder

    async def list(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Reminder]:
        statement = (
            select(Reminder)
            .where(Reminder.user_id == user_id)
            .order_by(Reminder.remind_time.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def list_due_pending(
        self,
        now: datetime,
        limit: int = 100,
    ) -> list[Reminder]:
        statement = (
            select(Reminder)
            .where(
                Reminder.status == "pending",
                Reminder.remind_time <= now,
            )
            .order_by(Reminder.remind_time.asc())
            .limit(limit)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def update_status(self, reminder: Reminder, status: str) -> Reminder:
        reminder.status = status
        await self.session.flush()
        return reminder

