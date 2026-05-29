from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.event import EventCreate, EventRead, EventUpdate
from app.services.calendar_service import CalendarService


router = APIRouter(prefix="/api/events", tags=["events"])


async def get_calendar_service(
    session: AsyncSession = Depends(get_db_session),
) -> CalendarService:
    return CalendarService(session)


def _to_event_read(event) -> EventRead:
    return EventRead.model_validate(event)


@router.get("", response_model=ApiResponse[list[EventRead]])
async def list_events(
    user_id: str = Query(...),
    start: datetime = Query(...),
    end: datetime = Query(...),
    service: CalendarService = Depends(get_calendar_service),
) -> ApiResponse[list[EventRead]]:
    events = await service.list_events_by_range(
        user_id=user_id,
        start_time=start,
        end_time=end,
    )
    return ApiResponse(
        success=True,
        data=[_to_event_read(event) for event in events],
    )


@router.post("", response_model=ApiResponse[EventRead], status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate,
    service: CalendarService = Depends(get_calendar_service),
) -> ApiResponse[EventRead]:
    event = await service.create_event(payload)
    return ApiResponse(success=True, data=_to_event_read(event))


@router.get("/{event_id}", response_model=ApiResponse[EventRead])
async def get_event(
    event_id: str,
    service: CalendarService = Depends(get_calendar_service),
) -> ApiResponse[EventRead]:
    event = await service.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return ApiResponse(success=True, data=_to_event_read(event))


@router.patch("/{event_id}", response_model=ApiResponse[EventRead])
async def update_event(
    event_id: str,
    payload: EventUpdate,
    service: CalendarService = Depends(get_calendar_service),
) -> ApiResponse[EventRead]:
    event = await service.update_event(event_id, payload)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return ApiResponse(success=True, data=_to_event_read(event))


@router.delete("/{event_id}", response_model=ApiResponse[EventRead])
async def delete_event(
    event_id: str,
    service: CalendarService = Depends(get_calendar_service),
) -> ApiResponse[EventRead]:
    event = await service.soft_delete_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    return ApiResponse(success=True, data=_to_event_read(event))

