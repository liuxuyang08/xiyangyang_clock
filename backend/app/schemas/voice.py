from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import SchemaModel


class VoiceCommandRequest(BaseModel):
    user_id: str
    session_id: str
    text: str
    timezone: str = "Asia/Shanghai"
    client_time: datetime


class VoiceCommandResponse(BaseModel):
    action: str
    need_user_reply: bool
    reply: str
    data: dict[str, Any] = Field(default_factory=dict)


class VoiceCommandRead(SchemaModel):
    id: str
    user_id: str
    session_id: str
    raw_text: str
    intent: str | None = None
    confidence: float | None = None
    entities: dict[str, Any]
    status: str
    error_message: str | None = None
    created_at: datetime
