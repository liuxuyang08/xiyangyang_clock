from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.repositories.event_repository import EventRepository


@dataclass(slots=True)
class ConflictEventSummary:
    id: str
    title: str
    start_time: datetime
    end_time: datetime | None


class ConflictService:
    def __init__(self, session: AsyncSession) -> None:
        self.event_repository = EventRepository(session)

    @staticmethod
    def is_conflict(
        new_start: datetime,
        new_end: datetime,
        existing_start: datetime,
        existing_end: datetime,
    ) -> bool:
        return new_start < existing_end and new_end > existing_start

    @staticmethod
    def _build_summary(event: Event) -> ConflictEventSummary:
        return ConflictEventSummary(
            id=event.id,
            title=event.title,
            start_time=event.start_time,
            end_time=event.end_time,
        )

    async def list_conflicting_events(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[ConflictEventSummary]:
        statement = (
            select(Event)
            .where(
                Event.user_id == user_id,
                Event.status == "active",
                Event.deleted_at.is_(None),
                Event.start_time < end_time,
                Event.end_time.is_not(None),
                Event.end_time > start_time,
            )
            .order_by(Event.start_time.asc())
        )
        result = await self.event_repository.session.scalars(statement)
        events = list(result.all())

        return [
            self._build_summary(event)
            for event in events
            if event.end_time is not None
            and self.is_conflict(
                new_start=start_time,
                new_end=end_time,
                existing_start=event.start_time,
                existing_end=event.end_time,
            )
        ]

    async def list_conflicting_events_excluding_current(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        current_event_id: str,
    ) -> list[ConflictEventSummary]:
        conflicts = await self.list_conflicting_events(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
        )
        return [item for item in conflicts if item.id != current_event_id]
