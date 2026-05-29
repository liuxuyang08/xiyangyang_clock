from app.api.events import router as events_router
from app.api.reminders import router as reminders_router

__all__ = [
    "events_router",
    "reminders_router",
]
