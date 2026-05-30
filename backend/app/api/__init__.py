from app.api.events import router as events_router
from app.api.reminders import router as reminders_router
from app.api.voice import router as voice_router
from app.api.ws import router as ws_router

__all__ = [
    "events_router",
    "reminders_router",
    "voice_router",
    "ws_router",
]
