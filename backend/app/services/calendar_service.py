from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from app.repositories.event_repository import EventRepository
from app.schemas.event import EventCreate, EventUpdate


class CalendarService:
    def __init__(self, session: AsyncSession) -> None:
        self.event_repository = EventRepository(session)

    async def create_event(self, event_in: EventCreate) -> Event:
        data = event_in.model_dump()
        data["id"] = data["id"] or str(uuid4())
        data["status"] = data.get("status") or "active"

        return await self.event_repository.create(data)

    async def list_events_by_range(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Event]:
        return await self.event_repository.list_by_time_range(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            status="active",
        )

    async def get_event(self, event_id: str) -> Event | None:
        event = await self.event_repository.get_by_id(event_id)
        if event is None or event.status != "active" or event.deleted_at is not None:
            return None

        return event

    async def update_event(self, event_id: str, event_in: EventUpdate) -> Event | None:
        event = await self.get_event(event_id)
        if event is None:
            return None

        data = event_in.model_dump(exclude_unset=True)
        data.pop("deleted_at", None)
        data["updated_at"] = datetime.now(timezone.utc)

        return await self.event_repository.update(event, data)

    async def soft_delete_event(self, event_id: str) -> Event | None:
        event = await self.get_event(event_id)
        if event is None:
            return None

        return await self.event_repository.soft_delete(
            event=event,
            deleted_at=datetime.now(timezone.utc),
        )

    async def search_candidate_events(
        self,
        user_id: str,
        keyword: str,
        limit: int = 10,
    ) -> list[Event]:
        return await self.event_repository.search_candidates(
            user_id=user_id,
            keyword=keyword,
            limit=limit,
            status="active",
        )
