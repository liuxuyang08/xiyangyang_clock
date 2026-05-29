from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import ApiResponse
from app.schemas.reminder import ReminderCreate, ReminderRead, ReminderUpdate
from app.services.reminder_service import ReminderService


router = APIRouter(prefix="/api/reminders", tags=["reminders"])


async def get_reminder_service(
    session: AsyncSession = Depends(get_db_session),
) -> ReminderService:
    return ReminderService(session)


def _to_reminder_read(reminder) -> ReminderRead:
    return ReminderRead.model_validate(reminder)


@router.get("", response_model=ApiResponse[list[ReminderRead]])
async def list_reminders(
    user_id: str = Query(...),
    status: str | None = Query(default=None),
    service: ReminderService = Depends(get_reminder_service),
) -> ApiResponse[list[ReminderRead]]:
    reminders = await service.list_reminders(user_id=user_id, status=status)
    return ApiResponse(
        success=True,
        data=[_to_reminder_read(reminder) for reminder in reminders],
    )


@router.post("", response_model=ApiResponse[ReminderRead], status_code=status.HTTP_201_CREATED)
async def create_reminder(
    payload: ReminderCreate,
    service: ReminderService = Depends(get_reminder_service),
) -> ApiResponse[ReminderRead]:
    try:
        reminder = await service.create_reminder(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ApiResponse(success=True, data=_to_reminder_read(reminder))


@router.patch("/{reminder_id}", response_model=ApiResponse[ReminderRead])
async def update_reminder(
    reminder_id: str,
    payload: ReminderUpdate,
    service: ReminderService = Depends(get_reminder_service),
) -> ApiResponse[ReminderRead]:
    try:
        reminder = await service.update_reminder(reminder_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    return ApiResponse(success=True, data=_to_reminder_read(reminder))


@router.delete("/{reminder_id}", response_model=ApiResponse[ReminderRead])
async def delete_reminder(
    reminder_id: str,
    service: ReminderService = Depends(get_reminder_service),
) -> ApiResponse[ReminderRead]:
    reminder = await service.cancel_reminder(reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    return ApiResponse(success=True, data=_to_reminder_read(reminder))

