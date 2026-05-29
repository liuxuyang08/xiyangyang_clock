from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event


class EventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: dict[str, Any]) -> Event:
        event = Event(**data)
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, event_id: str) -> Event | None:
        return await self.session.get(Event, event_id)

    async def update(self, event: Event, data: dict[str, Any]) -> Event:
        for field, value in data.items():
            setattr(event, field, value)

        await self.session.flush()
        return event

    async def list(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0,
        status: str | None = "active",
    ) -> list[Event]:
        statement = (
            select(Event)
            .where(Event.user_id == user_id, Event.deleted_at.is_(None))
            .order_by(Event.start_time.asc())
            .offset(offset)
            .limit(limit)
        )

        if status is not None:
            statement = statement.where(Event.status == status)

        result = await self.session.scalars(statement)
        return list(result.all())

    async def list_by_time_range(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        status: str | None = "active",
    ) -> list[Event]:
        statement = (
            select(Event)
            .where(
                Event.user_id == user_id,
                Event.deleted_at.is_(None),
                Event.start_time >= start_time,
                Event.start_time < end_time,
            )
            .order_by(Event.start_time.asc())
        )

        if status is not None:
            statement = statement.where(Event.status == status)

        result = await self.session.scalars(statement)
        return list(result.all())

    async def search_candidates(
        self,
        user_id: str,
        keyword: str,
        limit: int = 10,
        status: str | None = "active",
    ) -> list[Event]:
        pattern = f"%{keyword}%"
        statement = (
            select(Event)
            .where(
                Event.user_id == user_id,
                Event.deleted_at.is_(None),
                or_(
                    Event.title.ilike(pattern),
                    Event.description.ilike(pattern),
                    Event.location.ilike(pattern),
                ),
            )
            .order_by(Event.start_time.asc())
            .limit(limit)
        )

        if status is not None:
            statement = statement.where(Event.status == status)

        result = await self.session.scalars(statement)
        return list(result.all())

    async def soft_delete(self, event: Event, deleted_at: datetime) -> Event:
        event.status = "deleted"
        event.deleted_at = deleted_at
        await self.session.flush()
        return event
