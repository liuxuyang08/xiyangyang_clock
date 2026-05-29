from datetime import datetime

from app.schemas.common import SchemaModel


class ReminderBase(SchemaModel):
    event_id: str
    user_id: str
    remind_time: datetime
    offset_minutes: int = 0
    channel: str = "app_voice"
    status: str = "pending"


class ReminderCreate(ReminderBase):
    id: str | None = None


class ReminderUpdate(SchemaModel):
    remind_time: datetime | None = None
    offset_minutes: int | None = None
    channel: str | None = None
    status: str | None = None


class ReminderRead(ReminderBase):
    id: str
    created_at: datetime

