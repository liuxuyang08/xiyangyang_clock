from datetime import datetime
from typing import Any

from app.schemas.common import SchemaModel


class ConversationStateRead(SchemaModel):
    id: str
    user_id: str
    session_id: str
    pending_intent: str | None = None
    slots: dict[str, Any]
    missing_slots: list[str]
    candidate_events: list[dict[str, Any]]
    status: str
    expires_at: datetime | None = None
    updated_at: datetime

