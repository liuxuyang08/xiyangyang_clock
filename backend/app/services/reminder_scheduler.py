from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.event import Event
from app.models.reminder import Reminder
from app.services.reminder_service import ReminderService
from app.services.websocket_manager import websocket_manager


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ReminderMessage:
    reminder_id: str
    event_id: str
    user_id: str
    remind_time: datetime
    title: str | None
    event_start_time: datetime | None
    text: str


@dataclass(slots=True)
class ReminderScanResult:
    scanned: int = 0
    sent: int = 0
    failed: int = 0
    messages: list[ReminderMessage] = field(default_factory=list)
    skipped_reason: str | None = None


class ReminderDispatcher(Protocol):
    async def send(self, message: ReminderMessage) -> None:
        ...


class LoggingReminderDispatcher:
    async def send(self, message: ReminderMessage) -> None:
        logger.info(
            "Reminder triggered",
            extra={
                "reminder_id": message.reminder_id,
                "event_id": message.event_id,
                "user_id": message.user_id,
                "message": message.text,
            },
        )


class WebSocketReminderDispatcher:
    def __init__(self, manager: Any | None = None) -> None:
        self.manager = manager or websocket_manager

    async def send(self, message: ReminderMessage) -> None:
        payload = {
            "type": "reminder_triggered",
            "user_id": message.user_id,
            "data": {
                "event_id": message.event_id,
                "title": message.title,
                "start_time": (
                    message.event_start_time.isoformat()
                    if message.event_start_time is not None
                    else None
                ),
            },
        }
        sent_count = await self.manager.broadcast_to_user_sessions(message.user_id, payload)
        if sent_count <= 0:
            raise RuntimeError("no websocket connections for user")


class ReminderScheduler:
    def __init__(
        self,
        *,
        session_factory: Any = None,
        service_factory: Any = None,
        dispatcher: ReminderDispatcher | None = None,
        scan_interval: int | None = None,
        batch_limit: int = 100,
    ) -> None:
        settings = get_settings()
        self.session_factory = SessionLocal if session_factory is None else session_factory
        self.service_factory = service_factory or ReminderService
        self.dispatcher = dispatcher or WebSocketReminderDispatcher()
        self.scan_interval = scan_interval or settings.reminder_scan_interval
        self.batch_limit = batch_limit
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.session_factory is None:
            logger.warning("Reminder scheduler is disabled because database is not configured")
            return
        if self.is_running:
            return

        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="reminder-scheduler")

    async def stop(self) -> None:
        if self._task is None:
            return

        if self._stop_event is not None:
            self._stop_event.set()

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            self._stop_event = None

    async def _run_loop(self) -> None:
        if self._stop_event is None:
            return

        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("Reminder scheduler scan failed")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.scan_interval,
                )
            except asyncio.TimeoutError:
                continue

    async def run_once(self, now: datetime | None = None) -> ReminderScanResult:
        if self.session_factory is None:
            return ReminderScanResult(skipped_reason="database_not_configured")

        async with self.session_factory() as session:
            service = self.service_factory(session)
            reminders = await service.list_due_pending_reminders(
                now=now or datetime.now(timezone.utc),
                limit=self.batch_limit,
            )
            result = ReminderScanResult(scanned=len(reminders))

            for reminder in reminders:
                message = await self._build_message(session=session, reminder=reminder)
                result.messages.append(message)
                try:
                    await self.dispatcher.send(message)
                    await service.mark_sent(message.reminder_id)
                    await self._commit(session)
                    result.sent += 1
                except Exception as exc:
                    await self._rollback(session)
                    await self._mark_failed(
                        session=session,
                        service=service,
                        reminder_id=message.reminder_id,
                        error=exc,
                    )
                    result.failed += 1

            return result

    async def _build_message(self, *, session: Any, reminder: Reminder) -> ReminderMessage:
        event = await self._load_event(session=session, event_id=reminder.event_id)
        title = getattr(event, "title", None)
        event_start_time = getattr(event, "start_time", None)
        if title:
            text = f"提醒：{title}"
        else:
            text = f"提醒时间到了，日程 {reminder.event_id}"

        return ReminderMessage(
            reminder_id=reminder.id,
            event_id=reminder.event_id,
            user_id=reminder.user_id,
            remind_time=reminder.remind_time,
            title=title,
            event_start_time=event_start_time,
            text=text,
        )

    async def _load_event(self, *, session: Any, event_id: str) -> Event | None:
        get = getattr(session, "get", None)
        if get is None:
            return None
        try:
            return await get(Event, event_id)
        except Exception:
            logger.exception("Failed to load event for reminder message")
            return None

    async def _mark_failed(
        self,
        *,
        session: Any,
        service: ReminderService,
        reminder_id: str,
        error: Exception,
    ) -> None:
        error_message = str(error)
        try:
            await service.mark_failed(reminder_id, error_message=error_message)
            await self._commit(session)
        except Exception:
            await self._rollback(session)
            logger.exception(
                "Failed to mark reminder as failed",
                extra={"reminder_id": reminder_id, "error_message": error_message},
            )

    async def _commit(self, session: Any) -> None:
        commit = getattr(session, "commit", None)
        if commit is not None:
            await commit()

    async def _rollback(self, session: Any) -> None:
        rollback = getattr(session, "rollback", None)
        if rollback is not None:
            await rollback()
