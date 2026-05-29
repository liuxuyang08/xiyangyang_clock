from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import SchemaModel


class EventBase(SchemaModel):
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    location: str | None = None
    participants: list[str] = Field(default_factory=list)
    priority: str = "normal"
    status: str = "active"
    source: str = "manual"
    is_all_day: bool = False
    recurrence_rule: dict[str, Any] | None = None


class EventCreate(EventBase):
    id: str | None = None
    user_id: str


class EventUpdate(SchemaModel):
    title: str | None = None
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = None
    participants: list[str] | None = None
    priority: str | None = None
    status: str | None = None
    source: str | None = None
    is_all_day: bool | None = None
    recurrence_rule: dict[str, Any] | None = None
    deleted_at: datetime | None = None


class EventRead(EventBase):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
