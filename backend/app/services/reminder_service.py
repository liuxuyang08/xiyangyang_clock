from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.reminder import Reminder
from app.repositories.reminder_repository import ReminderRepository
from app.schemas.reminder import ReminderCreate, ReminderUpdate


class ReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.reminder_repository = ReminderRepository(session)

    def _project_timezone(self) -> ZoneInfo:
        settings = get_settings()
        try:
            return ZoneInfo(settings.timezone)
        except Exception:
            return ZoneInfo("UTC")

    def _ensure_aware(self, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=self._project_timezone())
        return value

    async def create_reminder(
        self,
        reminder_in: ReminderCreate,
        allow_past_time_for_test: bool | None = None,
    ) -> Reminder:
        reminder_time = self._ensure_aware(reminder_in.remind_time)
        test_flag = (
            allow_past_time_for_test
            if allow_past_time_for_test is not None
            else reminder_in.allow_past_time_for_test
        )

        if not test_flag and reminder_time.astimezone(timezone.utc) < datetime.now(timezone.utc):
            raise ValueError(
                "remind_time cannot be earlier than the current time unless allow_past_time_for_test is enabled."
            )

        data = reminder_in.model_dump(exclude={"allow_past_time_for_test"})
        data["id"] = data.get("id") or str(uuid4())
        data["remind_time"] = reminder_time
        data["status"] = "pending"

        return await self.reminder_repository.create(data)

    async def list_reminders(
        self,
        user_id: str,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Reminder]:
        return await self.reminder_repository.list(
            user_id=user_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def update_reminder(
        self,
        reminder_id: str,
        reminder_in: ReminderUpdate,
    ) -> Reminder | None:
        reminder = await self.reminder_repository.get_by_id(reminder_id)
        if reminder is None:
            return None

        data = reminder_in.model_dump(exclude_unset=True)
        if "remind_time" in data and data["remind_time"] is not None:
            reminder_time = self._ensure_aware(data["remind_time"])
            if reminder_time.astimezone(timezone.utc) < datetime.now(timezone.utc):
                raise ValueError("remind_time cannot be earlier than the current time.")
            data["remind_time"] = reminder_time

        return await self.reminder_repository.update(reminder, data)

    async def cancel_reminder(self, reminder_id: str) -> Reminder | None:
        reminder = await self.reminder_repository.get_by_id(reminder_id)
        if reminder is None:
            return None

        if reminder.status != "pending":
            return reminder

        return await self.reminder_repository.update_status(reminder, "cancelled")

    async def cancel_event_reminders(
        self,
        event_id: str,
        user_id: str | None = None,
    ) -> list[Reminder]:
        statement = select(Reminder).where(
            Reminder.event_id == event_id,
            Reminder.status == "pending",
        )
        if user_id is not None:
            statement = statement.where(Reminder.user_id == user_id)

        result = await self.session.scalars(statement)
        reminders = list(result.all())

        for reminder in reminders:
            reminder.status = "cancelled"

        await self.session.flush()
        return reminders

    async def list_due_pending_reminders(
        self,
        now: datetime | None = None,
        limit: int = 100,
    ) -> list[Reminder]:
        if now is None:
            now = datetime.now(timezone.utc)
        else:
            now = self._ensure_aware(now)

        return await self.reminder_repository.list_due_pending(now=now, limit=limit)

    async def mark_sent(self, reminder_id: str) -> Reminder | None:
        reminder = await self.reminder_repository.get_by_id(reminder_id)
        if reminder is None or reminder.status != "pending":
            return reminder

        return await self.reminder_repository.update_status(reminder, "sent")

    async def mark_failed(
        self,
        reminder_id: str,
        error_message: str | None = None,
    ) -> Reminder | None:
        reminder = await self.reminder_repository.get_by_id(reminder_id)
        if reminder is None:
            return None

        if reminder.status in {"sent", "cancelled"}:
            return reminder

        return await self.reminder_repository.update_status(reminder, "failed")
