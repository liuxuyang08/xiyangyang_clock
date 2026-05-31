from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone as fixed_timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.schemas.event import EventCreate, EventUpdate
from app.schemas.reminder import ReminderCreate
from app.schemas.voice import VoiceCommandRequest, VoiceCommandResponse
from app.services.calendar_service import CalendarService
from app.services.conflict_service import ConflictService
from app.services.dialog_service import DialogService
from app.services.nlu_service import NLUResult, NLUService
from app.services.reminder_service import ReminderService
from app.services.time_parser import TimeParser
from app.services.voice_command_log_service import VoiceCommandLogService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

REQUIRED_SLOTS_BY_INTENT = {
    "create_event": ["title", "start_time"],
    "create_reminder": ["title", "start_time"],
    "query_event": [],
    "update_event": [],
    "delete_event": [],
    "cancel_reminder": ["target_event"],
    "unknown": ["intent"],
}

FOLLOWUP_REPLIES = {
    "intent": "请告诉我你想创建、查询、修改还是删除日程。",
    "title": "请补充日程标题。",
    "start_time": "请补充具体时间。",
    "time_text": "请补充具体时间。",
    "datetime": "请补充具体时间。",
    "specific_time": "请补充具体时间。",
    "date_text": "请补充日期。",
    "target_event": "请说明要操作哪一个日程。",
    "confirm_time": "这个时间已经过去了，请确认是否继续。",
    "confirm_range": "这个时间范围已经过去了，请确认是否继续。",
}

TIME_ASK_SLOTS = frozenset(
    {"start_time", "time_text", "datetime", "specific_time", "date_text"}
)

ASKABLE_SLOTS = frozenset(
    {
        "intent",
        "title",
        "start_time",
        "time_text",
        "datetime",
        "specific_time",
        "date_text",
        "target_event",
        "confirm_time",
        "confirm_range",
    }
)

EXPLICIT_DATE_MARKERS = ("今天", "明天", "后天", "本周", "下周")

EXPLICIT_DATE_PATTERNS = (
    re.compile(r"周[一二三四五六日天]"),
    re.compile(r"星期[一二三四五六日天]"),
    re.compile(r"\d{1,2}月\d{1,2}[日号]"),
    re.compile(r"\d{4}年"),
)


async def get_dialog_service(
    session: AsyncSession = Depends(get_db_session),
) -> DialogService:
    return DialogService(session)


async def get_calendar_service(
    session: AsyncSession = Depends(get_db_session),
) -> CalendarService:
    return CalendarService(session)


async def get_conflict_service(
    session: AsyncSession = Depends(get_db_session),
) -> ConflictService:
    return ConflictService(session)


async def get_reminder_service(
    session: AsyncSession = Depends(get_db_session),
) -> ReminderService:
    return ReminderService(session)


def get_nlu_service() -> NLUService:
    return NLUService()


def get_time_parser() -> TimeParser:
    return TimeParser()


def get_voice_command_log_service() -> VoiceCommandLogService:
    return VoiceCommandLogService()


@router.post("/command", response_model=VoiceCommandResponse)
async def handle_voice_command(
    payload: VoiceCommandRequest,
    session: AsyncSession = Depends(get_db_session),
    dialog_service: DialogService = Depends(get_dialog_service),
    calendar_service: CalendarService = Depends(get_calendar_service),
    conflict_service: ConflictService = Depends(get_conflict_service),
    reminder_service: ReminderService = Depends(get_reminder_service),
    nlu_service: NLUService = Depends(get_nlu_service),
    time_parser: TimeParser = Depends(get_time_parser),
    voice_command_log_service: VoiceCommandLogService = Depends(get_voice_command_log_service),
) -> VoiceCommandResponse:
    voice_command = await voice_command_log_service.record_received(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
    )
    voice_command_id = getattr(voice_command, "id", None)

    try:
        current_state = await dialog_service.get_current_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
            text=payload.text,
        )
        nlu_result = nlu_service.parse(
            payload.text,
            base_time=payload.client_time,
            timezone=payload.timezone,
            conversation_context=current_state,
        )

        intent = _resolve_intent(nlu_result, current_state)
        slots = _merge_slots(current_state, nlu_result)
        if intent == "create_reminder":
            intent = "create_event"
            slots.setdefault("reminder_offset_minutes", 0)
        time_parse_details = _normalize_time_slots(
            slots=slots,
            base_time=payload.client_time,
            timezone=payload.timezone,
            time_parser=time_parser,
        )
        future_shift_details = _apply_future_shift(
            slots=slots,
            raw_text=payload.text,
            base_time=payload.client_time,
        )
        missing_slots = _resolve_missing_slots(
            intent=intent,
            slots=slots,
            nlu_missing_slots=nlu_result.missing_slots,
            time_missing_slots=time_parse_details.get("missing_slots", []),
            base_time=payload.client_time,
        )
        entities = _jsonable(
            {
                "slots": slots,
                "missing_slots": missing_slots,
                "time_parse": time_parse_details,
                "future_shift": future_shift_details,
            }
        )

        parsed_voice_command = await voice_command_log_service.record_parsed(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent=intent,
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )
        voice_command_id = voice_command_id or getattr(parsed_voice_command, "id", None)

        if _is_pending_conflict_state(current_state):
            pending_conflict_response = await _handle_pending_conflict_confirmation(
                payload=payload,
                session=session,
                dialog_service=dialog_service,
                current_state=current_state,
                user_intent=nlu_result.intent,
                nlu_result=nlu_result,
                voice_command_id=voice_command_id,
                calendar_service=calendar_service,
                reminder_service=reminder_service,
                voice_command_log_service=voice_command_log_service,
            )
            if pending_conflict_response is not None:
                return pending_conflict_response

        if _is_pending_delete_state(current_state):
            pending_delete_response = await _handle_pending_delete_event(
                payload=payload,
                session=session,
                dialog_service=dialog_service,
                current_state=current_state,
                user_intent=nlu_result.intent,
                slots=slots,
                nlu_result=nlu_result,
                voice_command_id=voice_command_id,
                calendar_service=calendar_service,
                reminder_service=reminder_service,
                voice_command_log_service=voice_command_log_service,
            )
            if pending_delete_response is not None:
                return pending_delete_response

        if _is_pending_update_state(current_state):
            pending_update_response = await _handle_pending_update_event(
                payload=payload,
                session=session,
                dialog_service=dialog_service,
                current_state=current_state,
                user_intent=nlu_result.intent,
                slots=slots,
                nlu_result=nlu_result,
                voice_command_id=voice_command_id,
                calendar_service=calendar_service,
                conflict_service=conflict_service,
                reminder_service=reminder_service,
                voice_command_log_service=voice_command_log_service,
            )
            if pending_update_response is not None:
                return pending_update_response

        if missing_slots:
            state = await dialog_service.create_pending_state(
                user_id=payload.user_id,
                session_id=payload.session_id,
                pending_intent=intent,
                slots=slots,
                missing_slots=missing_slots,
                status="need_more_info",
            )
            await session.commit()

            return VoiceCommandResponse(
                action="need_more_info",
                need_user_reply=True,
                reply=_build_followup_reply(missing_slots),
                data={
                    "voice_command_id": voice_command_id,
                    "conversation_state_id": state.id,
                    "intent": intent,
                    "confidence": nlu_result.confidence,
                    "slots": _jsonable(slots),
                    "missing_slots": missing_slots,
                    "status": state.status,
                },
            )

        if intent == "create_event":
            return await _handle_create_event(
                payload=payload,
                session=session,
                dialog_service=dialog_service,
                intent=intent,
                slots=slots,
                nlu_result=nlu_result,
                time_parse_details=time_parse_details,
                voice_command_id=voice_command_id,
                calendar_service=calendar_service,
                conflict_service=conflict_service,
                reminder_service=reminder_service,
                voice_command_log_service=voice_command_log_service,
            )

        if intent == "query_event":
            return await _handle_query_event(
                payload=payload,
                intent=intent,
                slots=slots,
                nlu_result=nlu_result,
                time_parse_details=time_parse_details,
                voice_command_id=voice_command_id,
                calendar_service=calendar_service,
                voice_command_log_service=voice_command_log_service,
            )

        if intent == "update_event":
            return await _handle_update_event(
                payload=payload,
                session=session,
                dialog_service=dialog_service,
                intent=intent,
                slots=slots,
                nlu_result=nlu_result,
                time_parse_details=time_parse_details,
                voice_command_id=voice_command_id,
                calendar_service=calendar_service,
                voice_command_log_service=voice_command_log_service,
            )

        if intent == "delete_event":
            return await _handle_delete_event(
                payload=payload,
                session=session,
                dialog_service=dialog_service,
                intent=intent,
                slots=slots,
                nlu_result=nlu_result,
                time_parse_details=time_parse_details,
                voice_command_id=voice_command_id,
                calendar_service=calendar_service,
                voice_command_log_service=voice_command_log_service,
            )

        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent=intent,
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action="voice_command_recognized",
            need_user_reply=False,
            reply="已识别到操作，但业务执行将在下一步完成。",
            data={
                "voice_command_id": voice_command_id,
                "intent": intent,
                "confidence": nlu_result.confidence,
                "slots": _jsonable(slots),
                "missing_slots": [],
                "business_execution": "pending",
            },
        )
    except Exception as exc:
        await session.rollback()
        await voice_command_log_service.record_failed(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            error_message=exc,
            voice_command_id=voice_command_id,
        )
        logger.exception("Failed to handle voice command")
        return VoiceCommandResponse(
            action="voice_command_failed",
            need_user_reply=False,
            reply="语音命令处理失败，请稍后再试。",
            data={
                "voice_command_id": voice_command_id,
                "error_message": str(exc),
            },
        )


async def _handle_create_event(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    dialog_service: DialogService,
    intent: str,
    slots: dict[str, Any],
    nlu_result: NLUResult,
    time_parse_details: dict[str, Any],
    voice_command_id: str | None,
    calendar_service: CalendarService,
    conflict_service: ConflictService,
    reminder_service: ReminderService,
    voice_command_log_service: VoiceCommandLogService,
) -> VoiceCommandResponse:
    start_time = _parse_datetime_slot(slots["start_time"])
    end_time = _parse_optional_datetime_slot(slots.get("end_time"))
    conflict_end_time = _conflict_end_time(start_time=start_time, end_time=end_time)
    conflicts = await conflict_service.list_conflicting_events(
        user_id=payload.user_id,
        start_time=start_time,
        end_time=conflict_end_time,
    )
    conflict_data = _conflicts_to_data(conflicts)
    if conflict_data:
        return await _save_create_conflict_confirmation(
            payload=payload,
            session=session,
            dialog_service=dialog_service,
            intent=intent,
            slots=slots,
            nlu_result=nlu_result,
            time_parse_details=time_parse_details,
            voice_command_id=voice_command_id,
            conflicts=conflict_data,
            voice_command_log_service=voice_command_log_service,
        )

    return await _execute_create_event(
        payload=payload,
        session=session,
        slots=slots,
        nlu_result=nlu_result,
        time_parse_details=time_parse_details,
        voice_command_id=voice_command_id,
        calendar_service=calendar_service,
        reminder_service=reminder_service,
        voice_command_log_service=voice_command_log_service,
        conflicts=[],
    )


async def _execute_create_event(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    slots: dict[str, Any],
    nlu_result: NLUResult,
    time_parse_details: dict[str, Any],
    voice_command_id: str | None,
    calendar_service: CalendarService,
    reminder_service: ReminderService,
    voice_command_log_service: VoiceCommandLogService,
    conflicts: list[dict[str, Any]] | None = None,
    dialog_service: DialogService | None = None,
) -> VoiceCommandResponse:
    start_time = _parse_datetime_slot(slots["start_time"])
    end_time = _parse_optional_datetime_slot(slots.get("end_time"))
    event = await calendar_service.create_event(
        EventCreate(
            user_id=payload.user_id,
            title=str(slots["title"]),
            description=_optional_str(slots.get("description")),
            start_time=start_time,
            end_time=end_time,
            location=_optional_str(slots.get("location")),
            participants=_normalize_participants(slots.get("participants")),
            priority=str(slots.get("priority") or "normal"),
            source="voice",
            is_all_day=bool(slots.get("is_all_day") or False),
            recurrence_rule=_normalize_recurrence_rule(slots.get("recurrence_rule")),
        )
    )

    reminder = None
    if "reminder_offset_minutes" in slots and slots.get("reminder_offset_minutes") is not None:
        offset_minutes = _parse_int_slot(slots.get("reminder_offset_minutes"), default=0)
        reminder = await reminder_service.create_reminder(
            ReminderCreate(
                event_id=event.id,
                user_id=payload.user_id,
                remind_time=start_time - timedelta(minutes=offset_minutes),
                offset_minutes=offset_minutes,
                channel="app_voice",
        )
    )

    completed_state = None
    if dialog_service is not None:
        completed_state = await dialog_service.complete_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )

    await session.commit()

    event_data = _model_to_dict(event, EVENT_RESPONSE_FIELDS)
    reminder_data = _model_to_dict(reminder, REMINDER_RESPONSE_FIELDS) if reminder is not None else None
    entities = _jsonable(
        {
            "slots": slots,
            "missing_slots": [],
            "time_parse": time_parse_details,
            "event": event_data,
            "reminder": reminder_data,
            "conflicts": conflicts or [],
            "cleared_state_id": getattr(completed_state, "id", None),
        }
    )

    await voice_command_log_service.record_success(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
        intent="create_event",
        confidence=nlu_result.confidence,
        entities=entities,
        voice_command_id=voice_command_id,
    )

    return VoiceCommandResponse(
        action="event_created",
        need_user_reply=False,
        reply=_build_event_created_reply(
            slots=slots,
            event_data=event_data,
            reminder_data=reminder_data,
        ),
        data={
            "voice_command_id": voice_command_id,
            "conversation_state_id": getattr(completed_state, "id", None),
            "intent": "create_event",
            "confidence": nlu_result.confidence,
            "event": event_data,
            "reminder": reminder_data,
            "conflicts": conflicts or [],
        },
    )


async def _handle_query_event(
    *,
    payload: VoiceCommandRequest,
    intent: str,
    slots: dict[str, Any],
    nlu_result: NLUResult,
    time_parse_details: dict[str, Any],
    voice_command_id: str | None,
    calendar_service: CalendarService,
    voice_command_log_service: VoiceCommandLogService,
) -> VoiceCommandResponse:
    query_range = _resolve_query_range(payload=payload, slots=slots)
    events = await calendar_service.list_events_by_range(
        user_id=payload.user_id,
        start_time=query_range["start_time"],
        end_time=query_range["end_time"],
    )
    ordered_events = sorted(events, key=_event_sort_key)
    event_data = [_model_to_dict(event, EVENT_RESPONSE_FIELDS) for event in ordered_events]
    query_range_data = _query_range_to_data(query_range)
    entities = _jsonable(
        {
            "slots": slots,
            "missing_slots": [],
            "time_parse": time_parse_details,
            "query_range": query_range_data,
            "events": event_data,
            "event_count": len(event_data),
        }
    )

    await voice_command_log_service.record_success(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
        intent=intent,
        confidence=nlu_result.confidence,
        entities=entities,
        voice_command_id=voice_command_id,
    )

    return VoiceCommandResponse(
        action="events_queried",
        need_user_reply=False,
        reply=_build_query_events_reply(events=event_data, query_range=query_range),
        data={
            "voice_command_id": voice_command_id,
            "intent": intent,
            "confidence": nlu_result.confidence,
            "query_range": query_range_data,
            "events": event_data,
            "event_count": len(event_data),
        },
    )


async def _handle_delete_event(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    dialog_service: DialogService,
    intent: str,
    slots: dict[str, Any],
    nlu_result: NLUResult,
    time_parse_details: dict[str, Any],
    voice_command_id: str | None,
    calendar_service: CalendarService,
    voice_command_log_service: VoiceCommandLogService,
) -> VoiceCommandResponse:
    search_context = _resolve_delete_search_context(payload=payload, slots=slots)
    if not search_context["keyword"] and search_context["date_range"] is None:
        state = await dialog_service.create_pending_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
            pending_intent=intent,
            slots=slots,
            missing_slots=["target_event"],
            status="need_more_info",
        )
        await session.commit()
        return VoiceCommandResponse(
            action="need_more_info",
            need_user_reply=True,
            reply=_build_followup_reply(["target_event"]),
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": state.id,
                "intent": intent,
                "confidence": nlu_result.confidence,
                "slots": _jsonable(slots),
                "missing_slots": ["target_event"],
                "status": state.status,
            },
        )

    candidates = await calendar_service.search_candidate_events(
        user_id=payload.user_id,
        keyword=search_context["keyword"],
        limit=10,
    )
    matched_candidates = _filter_delete_candidates_by_date(
        candidates,
        date_range=search_context["date_range"],
    )
    candidate_events = [
        _candidate_event_to_dict(candidate)
        for candidate in sorted(matched_candidates, key=_event_sort_key)
    ]
    entities = _jsonable(
        {
            "slots": slots,
            "missing_slots": [],
            "time_parse": time_parse_details,
            "delete_search": _delete_search_context_to_data(search_context),
            "candidate_events": candidate_events,
            "candidate_count": len(candidate_events),
        }
    )

    if not candidate_events:
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent=intent,
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )
        return VoiceCommandResponse(
            action="delete_event_not_found",
            need_user_reply=False,
            reply="我没有找到相关日程。",
            data={
                "voice_command_id": voice_command_id,
                "intent": intent,
                "confidence": nlu_result.confidence,
                "keyword": search_context["keyword"],
                "date_range": _date_range_to_data(search_context["date_range"]),
                "candidate_events": [],
            },
        )

    if len(candidate_events) == 1:
        state = await dialog_service.create_pending_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
            pending_intent=intent,
            slots={
                **slots,
                "delete_target_event_id": candidate_events[0]["id"],
            },
            missing_slots=[],
            candidate_events=candidate_events,
            status="need_confirm",
        )
        await session.commit()
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent=intent,
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )
        return VoiceCommandResponse(
            action="delete_event_need_confirm",
            need_user_reply=True,
            reply=f"请确认是否删除{_format_candidate_for_reply(candidate_events[0])}？",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": state.id,
                "intent": intent,
                "confidence": nlu_result.confidence,
                "candidate_events": candidate_events,
                "status": state.status,
            },
        )

    state = await dialog_service.create_pending_state(
        user_id=payload.user_id,
        session_id=payload.session_id,
        pending_intent=intent,
        slots=slots,
        missing_slots=[],
        candidate_events=candidate_events,
        status="need_select",
    )
    await session.commit()
    await voice_command_log_service.record_success(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
        intent=intent,
        confidence=nlu_result.confidence,
        entities=entities,
        voice_command_id=voice_command_id,
    )
    return VoiceCommandResponse(
        action="delete_event_need_select",
        need_user_reply=True,
        reply=_build_delete_candidates_reply(candidate_events),
        data={
            "voice_command_id": voice_command_id,
            "conversation_state_id": state.id,
            "intent": intent,
            "confidence": nlu_result.confidence,
            "candidate_events": candidate_events,
            "status": state.status,
        },
    )


async def _handle_update_event(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    dialog_service: DialogService,
    intent: str,
    slots: dict[str, Any],
    nlu_result: NLUResult,
    time_parse_details: dict[str, Any],
    voice_command_id: str | None,
    calendar_service: CalendarService,
    voice_command_log_service: VoiceCommandLogService,
) -> VoiceCommandResponse:
    update_context = _resolve_update_context(payload=payload, slots=slots)
    update_draft = update_context["updates"]

    if not update_draft:
        state = await dialog_service.create_pending_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
            pending_intent=intent,
            slots=slots,
            missing_slots=["updates"],
            status="need_more_info",
        )
        await session.commit()
        return VoiceCommandResponse(
            action="need_more_info",
            need_user_reply=True,
            reply="请说明要修改成什么内容。",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": state.id,
                "intent": intent,
                "confidence": nlu_result.confidence,
                "slots": _jsonable(slots),
                "missing_slots": ["updates"],
                "status": state.status,
            },
        )

    if not update_context["keyword"] and update_context["target_range"] is None:
        state = await dialog_service.create_pending_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
            pending_intent=intent,
            slots={**slots, "update_draft": update_draft},
            missing_slots=["target_event"],
            status="need_more_info",
        )
        await session.commit()
        return VoiceCommandResponse(
            action="need_more_info",
            need_user_reply=True,
            reply=_build_followup_reply(["target_event"]),
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": state.id,
                "intent": intent,
                "confidence": nlu_result.confidence,
                "slots": _jsonable({**slots, "update_draft": update_draft}),
                "missing_slots": ["target_event"],
                "status": state.status,
            },
        )

    candidates = await calendar_service.search_candidate_events(
        user_id=payload.user_id,
        keyword=update_context["keyword"],
        limit=10,
    )
    matched_candidates = _filter_delete_candidates_by_date(
        candidates,
        date_range=update_context["target_range"],
    )
    candidate_events = [
        _candidate_event_to_dict(candidate)
        for candidate in sorted(matched_candidates, key=_event_sort_key)
    ]
    state_slots = {
        **slots,
        "update_draft": update_draft,
        "update_target": _update_target_context_to_data(update_context),
    }
    entities = _jsonable(
        {
            "operation": "update_event_draft_prepared",
            "slots": slots,
            "missing_slots": [],
            "time_parse": time_parse_details,
            "update_context": _update_target_context_to_data(update_context),
            "update_draft": update_draft,
            "candidate_events": candidate_events,
            "candidate_count": len(candidate_events),
        }
    )

    if not candidate_events:
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent=intent,
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )
        return VoiceCommandResponse(
            action="update_event_not_found",
            need_user_reply=False,
            reply="我没有找到相关日程。",
            data={
                "voice_command_id": voice_command_id,
                "intent": intent,
                "confidence": nlu_result.confidence,
                "keyword": update_context["keyword"],
                "target_range": _date_range_to_data(update_context["target_range"]),
                "updates": update_draft,
                "candidate_events": [],
            },
        )

    if len(candidate_events) == 1:
        selected_candidate = candidate_events[0]
        state = await dialog_service.create_pending_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
            pending_intent=intent,
            slots={
                **state_slots,
                "update_target_event_id": selected_candidate["id"],
            },
            missing_slots=[],
            candidate_events=candidate_events,
            status="need_confirm",
        )
        await session.commit()
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent=intent,
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )
        return VoiceCommandResponse(
            action="update_event_need_confirm",
            need_user_reply=True,
            reply=_build_update_confirm_reply(
                candidate=selected_candidate,
                updates=update_draft,
                slots=slots,
            ),
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": state.id,
                "intent": intent,
                "confidence": nlu_result.confidence,
                "update_target": _update_target_context_to_data(update_context),
                "updates": update_draft,
                "candidate_events": candidate_events,
                "status": state.status,
            },
        )

    state = await dialog_service.create_pending_state(
        user_id=payload.user_id,
        session_id=payload.session_id,
        pending_intent=intent,
        slots=state_slots,
        missing_slots=[],
        candidate_events=candidate_events,
        status="need_select",
    )
    await session.commit()
    await voice_command_log_service.record_success(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
        intent=intent,
        confidence=nlu_result.confidence,
        entities=entities,
        voice_command_id=voice_command_id,
    )
    return VoiceCommandResponse(
        action="update_event_need_select",
        need_user_reply=True,
        reply=_build_update_candidates_reply(candidate_events, update_draft),
        data={
            "voice_command_id": voice_command_id,
            "conversation_state_id": state.id,
            "intent": intent,
            "confidence": nlu_result.confidence,
            "update_target": _update_target_context_to_data(update_context),
            "updates": update_draft,
            "candidate_events": candidate_events,
            "status": state.status,
        },
    )


async def _handle_pending_conflict_confirmation(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    dialog_service: DialogService,
    current_state: Any,
    user_intent: str,
    nlu_result: NLUResult,
    voice_command_id: str | None,
    calendar_service: CalendarService,
    reminder_service: ReminderService,
    voice_command_log_service: VoiceCommandLogService,
) -> VoiceCommandResponse | None:
    conflict_context = _state_conflict_context(current_state)
    if conflict_context is None:
        return None

    operation = str(conflict_context.get("operation") or "")
    conflicts = list(conflict_context.get("conflicts") or [])

    if user_intent == "deny":
        state = await dialog_service.cancel_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )
        await session.commit()

        entities = _jsonable(
            {
                "operation": f"{operation}_conflict_cancelled",
                "conflicts": conflicts,
                "previous_state": _dialog_state_to_dict(current_state),
                "cleared_state_id": getattr(state, "id", None),
            }
        )
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent=operation,
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action=f"{operation}_cancelled",
            need_user_reply=False,
            reply="已取消创建。" if operation == "create_event" else "已取消修改。",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": getattr(state, "id", None),
                "intent": operation,
                "conflicts": conflicts,
                "status": getattr(state, "status", "cancelled"),
            },
        )

    if user_intent != "confirm":
        return VoiceCommandResponse(
            action=f"{operation}_conflict_need_confirm",
            need_user_reply=True,
            reply=_build_conflict_reply(conflicts=conflicts, operation=operation),
            data={
                "voice_command_id": voice_command_id,
                "intent": operation,
                "conflicts": conflicts,
                "status": getattr(current_state, "status", "need_confirm"),
            },
        )

    if operation == "create_event":
        return await _execute_create_event(
            payload=payload,
            session=session,
            slots=_state_slots(current_state),
            nlu_result=nlu_result,
            time_parse_details=dict(conflict_context.get("time_parse") or {}),
            voice_command_id=voice_command_id,
            calendar_service=calendar_service,
            reminder_service=reminder_service,
            voice_command_log_service=voice_command_log_service,
            conflicts=conflicts,
            dialog_service=dialog_service,
        )

    if operation == "update_event":
        return await _execute_update_event_from_state(
            payload=payload,
            session=session,
            dialog_service=dialog_service,
            current_state=current_state,
            nlu_result=nlu_result,
            voice_command_id=voice_command_id,
            calendar_service=calendar_service,
            reminder_service=reminder_service,
            voice_command_log_service=voice_command_log_service,
            conflicts=conflicts,
        )

    return None


async def _save_create_conflict_confirmation(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    dialog_service: DialogService,
    intent: str,
    slots: dict[str, Any],
    nlu_result: NLUResult,
    time_parse_details: dict[str, Any],
    voice_command_id: str | None,
    conflicts: list[dict[str, Any]],
    voice_command_log_service: VoiceCommandLogService,
) -> VoiceCommandResponse:
    state_slots = {
        **slots,
        "conflict_confirmation": {
            "operation": intent,
            "conflicts": conflicts,
            "time_parse": time_parse_details,
        },
    }
    state = await dialog_service.create_pending_state(
        user_id=payload.user_id,
        session_id=payload.session_id,
        pending_intent=intent,
        slots=state_slots,
        missing_slots=[],
        status="need_confirm",
    )
    await session.commit()

    entities = _jsonable(
        {
            "operation": "create_event_conflict_detected",
            "slots": slots,
            "time_parse": time_parse_details,
            "conflicts": conflicts,
            "conversation_state_id": state.id,
        }
    )
    await voice_command_log_service.record_success(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
        intent=intent,
        confidence=nlu_result.confidence,
        entities=entities,
        voice_command_id=voice_command_id,
    )

    return VoiceCommandResponse(
        action="create_event_conflict_need_confirm",
        need_user_reply=True,
        reply=_build_conflict_reply(conflicts=conflicts, operation="create_event"),
        data={
            "voice_command_id": voice_command_id,
            "conversation_state_id": state.id,
            "intent": intent,
            "confidence": nlu_result.confidence,
            "conflicts": conflicts,
            "status": state.status,
        },
    )


async def _save_update_conflict_confirmation(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    dialog_service: DialogService,
    current_state: Any,
    nlu_result: NLUResult,
    voice_command_id: str | None,
    conflicts: list[dict[str, Any]],
    voice_command_log_service: VoiceCommandLogService,
) -> VoiceCommandResponse:
    state_slots = {
        **_state_slots(current_state),
        "conflict_confirmation": {
            "operation": "update_event",
            "conflicts": conflicts,
        },
    }
    state = await dialog_service.create_pending_state(
        user_id=payload.user_id,
        session_id=payload.session_id,
        pending_intent="update_event",
        slots=state_slots,
        missing_slots=[],
        candidate_events=_state_candidate_events(current_state),
        status="need_confirm",
    )
    await session.commit()

    entities = _jsonable(
        {
            "operation": "update_event_conflict_detected",
            "update_draft": _update_draft_from_state(current_state),
            "conflicts": conflicts,
            "previous_state": _dialog_state_to_dict(current_state),
            "conversation_state_id": state.id,
        }
    )
    await voice_command_log_service.record_success(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
        intent="update_event",
        confidence=nlu_result.confidence,
        entities=entities,
        voice_command_id=voice_command_id,
    )

    return VoiceCommandResponse(
        action="update_event_conflict_need_confirm",
        need_user_reply=True,
        reply=_build_conflict_reply(conflicts=conflicts, operation="update_event"),
        data={
            "voice_command_id": voice_command_id,
            "conversation_state_id": state.id,
            "intent": "update_event",
            "updates": _update_draft_from_state(current_state),
            "conflicts": conflicts,
            "candidate_events": _state_candidate_events(current_state),
            "status": state.status,
        },
    )


async def _handle_pending_update_event(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    dialog_service: DialogService,
    current_state: Any,
    user_intent: str,
    slots: dict[str, Any],
    nlu_result: NLUResult,
    voice_command_id: str | None,
    calendar_service: CalendarService,
    conflict_service: ConflictService,
    reminder_service: ReminderService,
    voice_command_log_service: VoiceCommandLogService,
) -> VoiceCommandResponse | None:
    if user_intent == "deny":
        state = await dialog_service.cancel_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )
        await session.commit()

        entities = _jsonable(
            {
                "operation": "update_event_cancelled",
                "previous_state": _dialog_state_to_dict(current_state),
                "cleared_state_id": getattr(state, "id", None),
            }
        )
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent="update_event",
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action="update_event_cancelled",
            need_user_reply=False,
            reply="已取消修改。",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": getattr(state, "id", None),
                "intent": "update_event",
                "event": None,
                "status": getattr(state, "status", "cancelled"),
            },
        )

    state_status = str(getattr(current_state, "status", "") or "")
    candidate_events = _state_candidate_events(current_state)
    update_draft = _update_draft_from_state(current_state)

    if state_status == "need_select":
        selected_candidate = _select_candidate_from_reply(
            text=payload.text,
            slots=slots,
            candidate_events=candidate_events,
        )
        if selected_candidate is None:
            return VoiceCommandResponse(
                action="update_event_need_select",
                need_user_reply=True,
                reply=_build_update_candidates_reply(candidate_events, update_draft)
                if candidate_events
                else "请告诉我要修改哪一个日程。",
                data={
                    "voice_command_id": voice_command_id,
                    "intent": "update_event",
                    "updates": update_draft,
                    "candidate_events": candidate_events,
                    "status": state_status,
                },
            )

        confirm_state = await dialog_service.create_pending_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
            pending_intent="update_event",
            slots={
                **_state_slots(current_state),
                **slots,
                "update_target_event_id": selected_candidate["id"],
            },
            missing_slots=[],
            candidate_events=[selected_candidate],
            status="need_confirm",
        )
        await session.commit()

        entities = _jsonable(
            {
                "operation": "update_event_candidate_selected",
                "selected_candidate": selected_candidate,
                "update_draft": update_draft,
                "previous_state": _dialog_state_to_dict(current_state),
            }
        )
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent="update_event",
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action="update_event_need_confirm",
            need_user_reply=True,
            reply=_build_update_confirm_reply(
                candidate=selected_candidate,
                updates=update_draft,
                slots=_state_slots(confirm_state),
            ),
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": confirm_state.id,
                "intent": "update_event",
                "updates": update_draft,
                "candidate_events": [selected_candidate],
                "status": confirm_state.status,
            },
        )

    if user_intent != "confirm":
        selected_candidate = _update_target_candidate_from_state(current_state)
        return VoiceCommandResponse(
            action="update_event_need_confirm",
            need_user_reply=True,
            reply=_build_update_confirm_reply(
                candidate=selected_candidate or {},
                updates=update_draft,
                slots=_state_slots(current_state),
            )
            if selected_candidate is not None
            else "请确认是否修改该日程？",
            data={
                "voice_command_id": voice_command_id,
                "intent": "update_event",
                "updates": update_draft,
                "candidate_events": candidate_events,
                "status": state_status or "need_confirm",
            },
        )

    target_event_id = _update_target_event_id_from_state(current_state)
    if target_event_id is None:
        return VoiceCommandResponse(
            action="update_event_need_select",
            need_user_reply=True,
            reply="请先选择要修改哪一个日程。",
            data={
                "voice_command_id": voice_command_id,
                "intent": "update_event",
                "updates": update_draft,
                "candidate_events": candidate_events,
                "status": state_status,
            },
        )

    existing_event = await calendar_service.get_event(target_event_id)
    if existing_event is None:
        cleared_state = await dialog_service.cancel_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )
        await session.commit()

        entities = _jsonable(
            {
                "operation": "update_event_target_missing",
                "target_event_id": target_event_id,
                "update_draft": update_draft,
                "previous_state": _dialog_state_to_dict(current_state),
                "cleared_state_id": getattr(cleared_state, "id", None),
            }
        )
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent="update_event",
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action="update_event_not_found",
            need_user_reply=False,
            reply="我没有找到相关日程，修改已取消。",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": getattr(cleared_state, "id", None),
                "intent": "update_event",
                "event": None,
                "updates": update_draft,
                "status": getattr(cleared_state, "status", "cancelled"),
            },
        )

    conflict_range = _update_conflict_range(existing_event=existing_event, update_draft=update_draft)
    if conflict_range is not None:
        conflicts = await conflict_service.list_conflicting_events_excluding_current(
            user_id=payload.user_id,
            start_time=conflict_range["start_time"],
            end_time=conflict_range["end_time"],
            current_event_id=target_event_id,
        )
        conflict_data = _conflicts_to_data(conflicts)
        if conflict_data:
            return await _save_update_conflict_confirmation(
                payload=payload,
                session=session,
                dialog_service=dialog_service,
                current_state=current_state,
                nlu_result=nlu_result,
                voice_command_id=voice_command_id,
                conflicts=conflict_data,
                voice_command_log_service=voice_command_log_service,
            )

    event_update = _event_update_from_draft(update_draft)
    updated_event = await calendar_service.update_event(target_event_id, event_update)
    if updated_event is None:
        cleared_state = await dialog_service.cancel_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )
        await session.commit()

        entities = _jsonable(
            {
                "operation": "update_event_target_missing",
                "target_event_id": target_event_id,
                "update_draft": update_draft,
                "previous_state": _dialog_state_to_dict(current_state),
                "cleared_state_id": getattr(cleared_state, "id", None),
            }
        )
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent="update_event",
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action="update_event_not_found",
            need_user_reply=False,
            reply="我没有找到相关日程，修改已取消。",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": getattr(cleared_state, "id", None),
                "intent": "update_event",
                "event": None,
                "updates": update_draft,
                "status": getattr(cleared_state, "status", "cancelled"),
            },
        )

    reminder_result = await _rebuild_event_reminder_if_needed(
        event=updated_event,
        update_draft=update_draft,
        payload=payload,
        reminder_service=reminder_service,
    )
    completed_state = await dialog_service.complete_state(
        user_id=payload.user_id,
        session_id=payload.session_id,
    )
    await session.commit()
    await _refresh_models(session, updated_event, completed_state)

    event_data = _model_to_dict(updated_event, EVENT_RESPONSE_FIELDS)
    entities = _jsonable(
        {
            "operation": "update_event_confirmed",
            "target_event_id": target_event_id,
            "update_draft": update_draft,
            "event": event_data,
            "reminder": reminder_result,
            "cleared_state_id": getattr(completed_state, "id", None),
            "previous_state": _dialog_state_to_dict(current_state),
        }
    )
    await voice_command_log_service.record_success(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
        intent="update_event",
        confidence=nlu_result.confidence,
        entities=entities,
        voice_command_id=voice_command_id,
    )

    return VoiceCommandResponse(
        action="event_updated",
        need_user_reply=False,
        reply=_build_event_updated_reply(event_data=event_data, update_draft=update_draft),
        data={
            "voice_command_id": voice_command_id,
            "conversation_state_id": getattr(completed_state, "id", None),
            "intent": "update_event",
            "event": event_data,
            "updates": update_draft,
            "reminder": reminder_result,
        },
    )


async def _execute_update_event_from_state(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    dialog_service: DialogService,
    current_state: Any,
    nlu_result: NLUResult,
    voice_command_id: str | None,
    calendar_service: CalendarService,
    reminder_service: ReminderService,
    voice_command_log_service: VoiceCommandLogService,
    conflicts: list[dict[str, Any]] | None = None,
) -> VoiceCommandResponse:
    update_draft = _update_draft_from_state(current_state)
    target_event_id = _update_target_event_id_from_state(current_state)
    if target_event_id is None:
        return VoiceCommandResponse(
            action="update_event_need_select",
            need_user_reply=True,
            reply="请先选择要修改哪一个日程。",
            data={
                "voice_command_id": voice_command_id,
                "intent": "update_event",
                "updates": update_draft,
                "candidate_events": _state_candidate_events(current_state),
                "conflicts": conflicts or [],
                "status": getattr(current_state, "status", None),
            },
        )

    existing_event = await calendar_service.get_event(target_event_id)
    if existing_event is None:
        cleared_state = await dialog_service.cancel_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )
        await session.commit()

        entities = _jsonable(
            {
                "operation": "update_event_target_missing",
                "target_event_id": target_event_id,
                "update_draft": update_draft,
                "conflicts": conflicts or [],
                "previous_state": _dialog_state_to_dict(current_state),
                "cleared_state_id": getattr(cleared_state, "id", None),
            }
        )
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent="update_event",
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action="update_event_not_found",
            need_user_reply=False,
            reply="我没有找到相关日程，修改已取消。",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": getattr(cleared_state, "id", None),
                "intent": "update_event",
                "event": None,
                "updates": update_draft,
                "conflicts": conflicts or [],
                "status": getattr(cleared_state, "status", "cancelled"),
            },
        )

    event_update = _event_update_from_draft(update_draft)
    updated_event = await calendar_service.update_event(target_event_id, event_update)
    if updated_event is None:
        cleared_state = await dialog_service.cancel_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )
        await session.commit()

        entities = _jsonable(
            {
                "operation": "update_event_target_missing",
                "target_event_id": target_event_id,
                "update_draft": update_draft,
                "conflicts": conflicts or [],
                "previous_state": _dialog_state_to_dict(current_state),
                "cleared_state_id": getattr(cleared_state, "id", None),
            }
        )
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent="update_event",
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action="update_event_not_found",
            need_user_reply=False,
            reply="我没有找到相关日程，修改已取消。",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": getattr(cleared_state, "id", None),
                "intent": "update_event",
                "event": None,
                "updates": update_draft,
                "conflicts": conflicts or [],
                "status": getattr(cleared_state, "status", "cancelled"),
            },
        )

    reminder_result = await _rebuild_event_reminder_if_needed(
        event=updated_event,
        update_draft=update_draft,
        payload=payload,
        reminder_service=reminder_service,
    )
    completed_state = await dialog_service.complete_state(
        user_id=payload.user_id,
        session_id=payload.session_id,
    )
    await session.commit()
    await _refresh_models(session, updated_event, completed_state)

    event_data = _model_to_dict(updated_event, EVENT_RESPONSE_FIELDS)
    entities = _jsonable(
        {
            "operation": "update_event_confirmed",
            "target_event_id": target_event_id,
            "update_draft": update_draft,
            "event": event_data,
            "reminder": reminder_result,
            "conflicts": conflicts or [],
            "cleared_state_id": getattr(completed_state, "id", None),
            "previous_state": _dialog_state_to_dict(current_state),
        }
    )
    await voice_command_log_service.record_success(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
        intent="update_event",
        confidence=nlu_result.confidence,
        entities=entities,
        voice_command_id=voice_command_id,
    )

    return VoiceCommandResponse(
        action="event_updated",
        need_user_reply=False,
        reply=_build_event_updated_reply(event_data=event_data, update_draft=update_draft),
        data={
            "voice_command_id": voice_command_id,
            "conversation_state_id": getattr(completed_state, "id", None),
            "intent": "update_event",
            "event": event_data,
            "updates": update_draft,
            "reminder": reminder_result,
            "conflicts": conflicts or [],
        },
    )


async def _handle_pending_delete_event(
    *,
    payload: VoiceCommandRequest,
    session: AsyncSession,
    dialog_service: DialogService,
    current_state: Any,
    user_intent: str,
    slots: dict[str, Any],
    nlu_result: NLUResult,
    voice_command_id: str | None,
    calendar_service: CalendarService,
    reminder_service: ReminderService,
    voice_command_log_service: VoiceCommandLogService,
) -> VoiceCommandResponse | None:
    if user_intent == "deny":
        state = await dialog_service.cancel_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
        )
        await session.commit()

        entities = _jsonable(
            {
                "operation": "delete_event_cancelled",
                "previous_state": _dialog_state_to_dict(current_state),
                "cleared_state_id": getattr(state, "id", None),
            }
        )
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent="delete_event",
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action="delete_event_cancelled",
            need_user_reply=False,
            reply="已取消删除。",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": getattr(state, "id", None),
                "intent": "delete_event",
                "status": getattr(state, "status", "cancelled"),
            },
        )

    state_status = str(getattr(current_state, "status", "") or "")
    candidate_events = _state_candidate_events(current_state)

    if state_status == "need_select":
        selected_candidate = _select_candidate_from_reply(
            text=payload.text,
            slots=slots,
            candidate_events=candidate_events,
        )
        if selected_candidate is None:
            return VoiceCommandResponse(
                action="delete_event_need_select",
                need_user_reply=True,
                reply=_build_delete_candidates_reply(candidate_events)
                if candidate_events
                else "请告诉我要删除哪一个日程。",
                data={
                    "voice_command_id": voice_command_id,
                    "intent": "delete_event",
                    "candidate_events": candidate_events,
                    "status": state_status,
                },
            )

        confirm_state = await dialog_service.create_pending_state(
            user_id=payload.user_id,
            session_id=payload.session_id,
            pending_intent="delete_event",
            slots={
                **_state_slots(current_state),
                **slots,
                "delete_target_event_id": selected_candidate["id"],
            },
            missing_slots=[],
            candidate_events=[selected_candidate],
            status="need_confirm",
        )
        await session.commit()

        entities = _jsonable(
            {
                "operation": "delete_event_candidate_selected",
                "selected_candidate": selected_candidate,
                "previous_state": _dialog_state_to_dict(current_state),
            }
        )
        await voice_command_log_service.record_success(
            user_id=payload.user_id,
            session_id=payload.session_id,
            raw_text=payload.text,
            intent="delete_event",
            confidence=nlu_result.confidence,
            entities=entities,
            voice_command_id=voice_command_id,
        )

        return VoiceCommandResponse(
            action="delete_event_need_confirm",
            need_user_reply=True,
            reply=f"请确认是否删除{_format_candidate_for_reply(selected_candidate)}？",
            data={
                "voice_command_id": voice_command_id,
                "conversation_state_id": confirm_state.id,
                "intent": "delete_event",
                "candidate_events": [selected_candidate],
                "status": confirm_state.status,
            },
        )

    if user_intent != "confirm":
        selected_candidate = _delete_target_candidate_from_state(current_state)
        return VoiceCommandResponse(
            action="delete_event_need_confirm",
            need_user_reply=True,
            reply=f"请确认是否删除{_format_candidate_for_reply(selected_candidate)}？"
            if selected_candidate is not None
            else "请确认是否删除该日程？",
            data={
                "voice_command_id": voice_command_id,
                "intent": "delete_event",
                "candidate_events": candidate_events,
                "status": state_status or "need_confirm",
            },
        )

    target_event_id = _delete_target_event_id_from_state(current_state)
    if target_event_id is None:
        return VoiceCommandResponse(
            action="delete_event_need_select",
            need_user_reply=True,
            reply="请先选择要删除哪一个日程。",
            data={
                "voice_command_id": voice_command_id,
                "intent": "delete_event",
                "candidate_events": candidate_events,
                "status": state_status,
            },
        )

    deleted_event = await calendar_service.soft_delete_event(target_event_id)
    cancelled_reminders = await reminder_service.cancel_event_reminders(
        event_id=target_event_id,
        user_id=payload.user_id,
    )
    completed_state = await dialog_service.complete_state(
        user_id=payload.user_id,
        session_id=payload.session_id,
    )
    await session.commit()
    await _refresh_models(session, deleted_event, completed_state, *cancelled_reminders)

    deleted_event_data = _model_to_dict(deleted_event, EVENT_RESPONSE_FIELDS) if deleted_event is not None else None
    cancelled_reminder_data = [
        _model_to_dict(reminder, REMINDER_RESPONSE_FIELDS)
        for reminder in cancelled_reminders
    ]
    undo_data = {
        "type": "restore_deleted_event",
        "event_id": target_event_id,
        "event": deleted_event_data,
        "cancelled_reminders": cancelled_reminder_data,
    }
    entities = _jsonable(
        {
            "operation": "delete_event_confirmed",
            "deleted_event_id": target_event_id,
            "deleted_event": deleted_event_data,
            "cancelled_reminders": cancelled_reminder_data,
            "undo": undo_data,
            "cleared_state_id": getattr(completed_state, "id", None),
            "previous_state": _dialog_state_to_dict(current_state),
        }
    )
    await voice_command_log_service.record_success(
        user_id=payload.user_id,
        session_id=payload.session_id,
        raw_text=payload.text,
        intent="delete_event",
        confidence=nlu_result.confidence,
        entities=entities,
        voice_command_id=voice_command_id,
    )

    return VoiceCommandResponse(
        action="event_deleted",
        need_user_reply=False,
        reply=f"已删除{_deleted_event_reply_target(deleted_event_data, current_state)}。",
        data={
            "voice_command_id": voice_command_id,
            "conversation_state_id": getattr(completed_state, "id", None),
            "intent": "delete_event",
            "event": deleted_event_data,
            "cancelled_reminders": cancelled_reminder_data,
            "undo": _jsonable(undo_data),
        },
    )


def _resolve_intent(nlu_result: NLUResult, current_state: Any | None) -> str:
    pending_intent = getattr(current_state, "pending_intent", None)
    if pending_intent and nlu_result.intent == "unknown":
        return str(pending_intent)
    return nlu_result.intent


def _merge_slots(current_state: Any | None, nlu_result: NLUResult) -> dict[str, Any]:
    slots: dict[str, Any] = {}
    current_slots = getattr(current_state, "slots", None)
    if isinstance(current_slots, Mapping):
        slots.update(current_slots)
    slots.update(nlu_result.slots or {})
    return slots


def _normalize_time_slots(
    *,
    slots: dict[str, Any],
    base_time: datetime,
    timezone: str,
    time_parser: TimeParser,
) -> dict[str, Any]:
    expression = _build_time_expression(slots)
    if expression is None:
        return {}

    parsed = time_parser.parse(expression, base_time=base_time, timezone=timezone)
    result = {
        "raw_text": parsed.raw_text,
        "success": parsed.success,
        "ambiguous": parsed.ambiguous,
        "need_followup": parsed.need_followup,
        "is_past": parsed.is_past,
        "missing_slots": list(parsed.missing_slots),
        "reason": parsed.reason,
    }

    if parsed.success:
        new_start = parsed.start_datetime or parsed.datetime
        if new_start is not None:
            existing_start = _try_parse_datetime(slots.get("start_time"))
            if _should_replace_start_time(existing_start, new_start, base_time):
                slots["start_time"] = new_start.isoformat()

        if parsed.end_datetime is not None:
            slots["end_time"] = parsed.end_datetime.isoformat()

    return result


def _apply_future_shift(
    *,
    slots: dict[str, Any],
    raw_text: str,
    base_time: datetime,
) -> dict[str, Any]:
    start_value = _try_parse_datetime(slots.get("start_time"))
    if start_value is None:
        return {}

    base_aware = _ensure_aware(base_time)
    start_aware = _ensure_aware(start_value)
    if start_aware >= base_aware:
        return {"shifted": False, "is_past": False}

    if _has_explicit_date_marker(raw_text, slots):
        return {"shifted": False, "is_past": True, "reason": "explicit_date"}

    shifted_aware = start_aware
    while shifted_aware < base_aware:
        shifted_aware = shifted_aware + timedelta(days=1)

    delta = shifted_aware - start_aware
    if start_value.tzinfo is None or start_value.tzinfo.utcoffset(start_value) is None:
        shifted_value = (start_value + delta).replace(tzinfo=shifted_aware.tzinfo)
    else:
        shifted_value = start_value + delta
    slots["start_time"] = shifted_value.isoformat()

    end_value = _try_parse_datetime(slots.get("end_time"))
    if end_value is not None:
        shifted_end = end_value + delta
        slots["end_time"] = shifted_end.isoformat()

    return {
        "shifted": True,
        "is_past": False,
        "from": start_value.isoformat(),
        "to": shifted_value.isoformat(),
        "delta_days": delta.days,
    }


def _has_explicit_date_marker(text: str, slots: Mapping[str, Any]) -> bool:
    if slots.get("date_text"):
        return True
    if not text:
        return False
    if any(marker in text for marker in EXPLICIT_DATE_MARKERS):
        return True
    for pattern in EXPLICIT_DATE_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _try_parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _should_replace_start_time(
    existing: datetime | None,
    candidate: datetime,
    base_time: datetime,
) -> bool:
    if existing is None:
        return True

    base_aware = _ensure_aware(base_time)
    existing_aware = _ensure_aware(existing)
    candidate_aware = _ensure_aware(candidate)

    existing_is_future = existing_aware >= base_aware
    candidate_is_future = candidate_aware >= base_aware

    if existing_is_future and not candidate_is_future:
        return False
    if candidate_is_future and not existing_is_future:
        return True
    return True


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=fixed_timezone.utc)
    return value


def _build_time_expression(slots: Mapping[str, Any]) -> str | None:
    date_text = slots.get("date_text")
    time_text = slots.get("time_text")
    if date_text and time_text:
        return f"{date_text}{time_text}"
    if time_text:
        return str(time_text)
    if date_text:
        return str(date_text)
    return None


def _resolve_missing_slots(
    *,
    intent: str,
    slots: Mapping[str, Any],
    nlu_missing_slots: list[str],
    time_missing_slots: list[str],
    base_time: datetime | None = None,
) -> list[str]:
    if intent == "query_event":
        return []

    if intent == "update_event":
        return []

    if intent == "delete_event":
        has_delete_context = any(
            slots.get(field)
            for field in ("target_event", "date_text", "time_text", "start_time")
        )
        return [] if has_delete_context else ["target_event"]

    start_time_value = _try_parse_datetime(slots.get("start_time"))
    has_valid_start_time = start_time_value is not None

    missing_slots: list[str] = []
    for slot in [*nlu_missing_slots, *time_missing_slots]:
        if slot not in ASKABLE_SLOTS:
            continue
        if slot == "target_event" and intent not in {
            "delete_event",
            "update_event",
            "cancel_reminder",
        }:
            continue
        if slot == "intent" and intent != "unknown":
            continue
        if slot in TIME_ASK_SLOTS and has_valid_start_time:
            continue
        if slot == "confirm_time" and has_valid_start_time and base_time is not None:
            base_aware = _ensure_aware(base_time)
            start_aware = _ensure_aware(start_time_value)
            if start_aware >= base_aware:
                continue
        if slot != "intent" and slots.get(slot):
            continue
        if slot not in missing_slots:
            missing_slots.append(slot)

    for slot in REQUIRED_SLOTS_BY_INTENT.get(intent, []):
        if slot in TIME_ASK_SLOTS and has_valid_start_time:
            continue
        if not slots.get(slot) and slot not in missing_slots:
            missing_slots.append(slot)

    if (
        intent in {"create_event", "create_reminder"}
        and has_valid_start_time
        and base_time is not None
    ):
        base_aware = _ensure_aware(base_time)
        start_aware = _ensure_aware(start_time_value)
        if start_aware < base_aware and "confirm_time" not in missing_slots:
            missing_slots.append("confirm_time")

    return missing_slots


def _build_followup_reply(missing_slots: list[str]) -> str:
    replies: list[str] = []
    for slot in missing_slots:
        reply = FOLLOWUP_REPLIES.get(slot, f"请补充 {slot}。")
        if reply not in replies:
            replies.append(reply)
    return " ".join(replies)


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


EVENT_RESPONSE_FIELDS = [
    "id",
    "user_id",
    "title",
    "description",
    "start_time",
    "end_time",
    "location",
    "participants",
    "priority",
    "status",
    "source",
    "is_all_day",
    "recurrence_rule",
    "created_at",
    "updated_at",
    "deleted_at",
]

REMINDER_RESPONSE_FIELDS = [
    "id",
    "event_id",
    "user_id",
    "remind_time",
    "offset_minutes",
    "channel",
    "status",
    "created_at",
]


def _parse_datetime_slot(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError("start_time must be a datetime or ISO datetime string")


def _parse_optional_datetime_slot(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return _parse_datetime_slot(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_participants(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _normalize_recurrence_rule(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _parse_int_slot(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _model_to_dict(model: Any, fields: list[str]) -> dict[str, Any]:
    return _jsonable({field: getattr(model, field, None) for field in fields})


async def _refresh_models(session: AsyncSession, *models: Any) -> None:
    refresh = getattr(session, "refresh", None)
    if refresh is None:
        return

    for model in models:
        if model is not None and hasattr(model, "_sa_instance_state"):
            await refresh(model)


def _is_pending_delete_state(state: Any | None) -> bool:
    return state is not None and getattr(state, "pending_intent", None) == "delete_event"


def _is_pending_update_state(state: Any | None) -> bool:
    return state is not None and getattr(state, "pending_intent", None) == "update_event"


def _is_pending_conflict_state(state: Any | None) -> bool:
    return _state_conflict_context(state) is not None


def _state_slots(state: Any) -> dict[str, Any]:
    slots = getattr(state, "slots", None)
    return dict(slots) if isinstance(slots, Mapping) else {}


def _state_conflict_context(state: Any | None) -> dict[str, Any] | None:
    if state is None:
        return None
    conflict_context = _state_slots(state).get("conflict_confirmation")
    if not isinstance(conflict_context, Mapping):
        return None
    operation = conflict_context.get("operation")
    if operation not in {"create_event", "update_event"}:
        return None
    return _jsonable(dict(conflict_context))


def _state_candidate_events(state: Any) -> list[dict[str, Any]]:
    candidates = getattr(state, "candidate_events", None)
    if not isinstance(candidates, list):
        return []
    return [
        _jsonable(
            {
                "id": candidate.get("id") if isinstance(candidate, Mapping) else getattr(candidate, "id", None),
                "title": candidate.get("title") if isinstance(candidate, Mapping) else getattr(candidate, "title", None),
                "start_time": candidate.get("start_time") if isinstance(candidate, Mapping) else getattr(candidate, "start_time", None),
            }
        )
        for candidate in candidates
    ]


def _dialog_state_to_dict(state: Any | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return _jsonable(
        {
            "id": getattr(state, "id", None),
            "user_id": getattr(state, "user_id", None),
            "session_id": getattr(state, "session_id", None),
            "pending_intent": getattr(state, "pending_intent", None),
            "slots": _state_slots(state),
            "missing_slots": list(getattr(state, "missing_slots", []) or []),
            "candidate_events": _state_candidate_events(state),
            "status": getattr(state, "status", None),
            "expires_at": getattr(state, "expires_at", None),
            "updated_at": getattr(state, "updated_at", None),
        }
    )


def _delete_target_event_id_from_state(state: Any) -> str | None:
    slots = _state_slots(state)
    target_id = _optional_str(slots.get("delete_target_event_id"))
    if target_id is not None:
        return target_id

    candidate = _delete_target_candidate_from_state(state)
    if candidate is None:
        return None
    return _optional_str(candidate.get("id"))


def _delete_target_candidate_from_state(state: Any) -> dict[str, Any] | None:
    candidates = _state_candidate_events(state)
    if len(candidates) == 1:
        return candidates[0]

    target_id = _optional_str(_state_slots(state).get("delete_target_event_id"))
    if target_id is None:
        return None

    for candidate in candidates:
        if candidate.get("id") == target_id:
            return candidate
    return None


def _update_draft_from_state(state: Any) -> dict[str, Any]:
    slots = _state_slots(state)
    update_draft = slots.get("update_draft")
    if isinstance(update_draft, Mapping):
        return _jsonable(dict(update_draft))
    return _extract_update_draft(slots)


def _update_target_event_id_from_state(state: Any) -> str | None:
    slots = _state_slots(state)
    target_id = _optional_str(slots.get("update_target_event_id"))
    if target_id is not None:
        return target_id

    candidate = _update_target_candidate_from_state(state)
    if candidate is None:
        return None
    return _optional_str(candidate.get("id"))


def _update_target_candidate_from_state(state: Any) -> dict[str, Any] | None:
    candidates = _state_candidate_events(state)
    if len(candidates) == 1:
        return candidates[0]

    target_id = _optional_str(_state_slots(state).get("update_target_event_id"))
    if target_id is None:
        return None

    for candidate in candidates:
        if candidate.get("id") == target_id:
            return candidate
    return None


def _select_candidate_from_reply(
    *,
    text: str,
    slots: Mapping[str, Any],
    candidate_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidate_events:
        return None

    selected_id = _optional_str(slots.get("selected_event_id"))
    if selected_id is not None:
        for candidate in candidate_events:
            if candidate.get("id") == selected_id:
                return candidate

    index = _selection_index_from_text(text)
    if index is not None and 0 <= index < len(candidate_events):
        return candidate_events[index]

    target_text = _optional_str(slots.get("target_event")) or _optional_str(text)
    if target_text is None:
        return None

    for candidate in candidate_events:
        title = _optional_str(candidate.get("title"))
        if title and (target_text in title or title in target_text):
            return candidate
    return None


def _selection_index_from_text(text: str) -> int | None:
    normalized = text.strip().lower()
    for digit in ("1", "2", "3", "4", "5", "6", "7", "8", "9"):
        if digit in normalized:
            return int(digit) - 1

    selection_words = {
        "第一个": 0,
        "第1个": 0,
        "一": 0,
        "第一个": 0,
        "第二个": 1,
        "第2个": 1,
        "二": 1,
        "第三个": 2,
        "第3个": 2,
        "三": 2,
        "第四个": 3,
        "第4个": 3,
        "四": 3,
        "第五个": 4,
        "第5个": 4,
        "五": 4,
    }
    for word, index in selection_words.items():
        if word in normalized:
            return index
    return None


def _deleted_event_reply_target(
    event_data: Mapping[str, Any] | None,
    previous_state: Any,
) -> str:
    if event_data is not None:
        title = _optional_str(event_data.get("title"))
        if title is not None:
            return f"：{title}"

    candidate = _delete_target_candidate_from_state(previous_state)
    if candidate is not None:
        title = _optional_str(candidate.get("title"))
        if title is not None:
            return f"：{title}"
    return "该日程"


def _resolve_delete_search_context(
    *,
    payload: VoiceCommandRequest,
    slots: Mapping[str, Any],
) -> dict[str, Any]:
    keyword = _extract_delete_keyword(payload=payload, slots=slots)
    date_range = _resolve_delete_date_range(payload=payload, slots=slots)
    return {
        "keyword": keyword,
        "date_range": date_range,
        "target_event": slots.get("target_event"),
        "date_text": slots.get("date_text"),
        "time_text": slots.get("time_text"),
    }


def _extract_delete_keyword(
    *,
    payload: VoiceCommandRequest,
    slots: Mapping[str, Any],
) -> str:
    target_event = _optional_str(slots.get("target_event"))
    if target_event is not None:
        return target_event

    text = payload.text or ""
    for value in (slots.get("date_text"), slots.get("time_text")):
        if value:
            text = text.replace(str(value), "")

    for word in ("请", "帮我", "把", "删除", "取消", "不要", "日程", "安排", "的", "一下"):
        text = text.replace(word, "")

    return _optional_str(text) or ""


def _resolve_delete_date_range(
    *,
    payload: VoiceCommandRequest,
    slots: Mapping[str, Any],
) -> dict[str, datetime] | None:
    tz = _get_timezone(payload.timezone)
    base_time = _ensure_datetime_timezone(payload.client_time, tz)
    raw_text = payload.text or ""

    if _is_afternoon_query(raw_text=raw_text, slots=slots):
        query_date = _query_date_from_slots(slots=slots, base_time=base_time, timezone=tz)
        return {
            "start_time": datetime.combine(query_date, time(hour=12), tzinfo=tz),
            "end_time": datetime.combine(query_date, time(hour=18), tzinfo=tz),
        }

    start_time = _query_start_from_slots(slots=slots, timezone=tz)
    if start_time is None:
        return None

    end_time = _query_end_from_slots(slots=slots, timezone=tz)
    if end_time is None:
        day_start = datetime.combine(start_time.date(), time.min, tzinfo=tz)
        return {
            "start_time": day_start,
            "end_time": day_start + timedelta(days=1),
        }

    return {
        "start_time": start_time,
        "end_time": end_time,
    }


def _filter_delete_candidates_by_date(
    candidates: list[Any],
    *,
    date_range: Mapping[str, datetime] | None,
) -> list[Any]:
    if date_range is None:
        return candidates

    start_time = date_range["start_time"]
    end_time = date_range["end_time"]
    matched = []
    for candidate in candidates:
        candidate_start = getattr(candidate, "start_time", None)
        if isinstance(candidate_start, str):
            try:
                candidate_start = datetime.fromisoformat(candidate_start)
            except ValueError:
                candidate_start = None
        if not isinstance(candidate_start, datetime):
            continue
        if (
            candidate_start.tzinfo is None
            or candidate_start.tzinfo.utcoffset(candidate_start) is None
        ) and start_time.tzinfo is not None:
            candidate_start = candidate_start.replace(tzinfo=start_time.tzinfo)
        if start_time <= candidate_start < end_time:
            matched.append(candidate)
    return matched


def _candidate_event_to_dict(candidate: Any) -> dict[str, Any]:
    return _jsonable(
        {
            "id": getattr(candidate, "id", None),
            "title": getattr(candidate, "title", None),
            "start_time": getattr(candidate, "start_time", None),
        }
    )


def _delete_search_context_to_data(search_context: Mapping[str, Any]) -> dict[str, Any]:
    return _jsonable(
        {
            "keyword": search_context["keyword"],
            "date_range": _date_range_to_data(search_context["date_range"]),
            "target_event": search_context.get("target_event"),
            "date_text": search_context.get("date_text"),
            "time_text": search_context.get("time_text"),
        }
    )


def _resolve_update_context(
    *,
    payload: VoiceCommandRequest,
    slots: Mapping[str, Any],
) -> dict[str, Any]:
    target_text = _extract_update_target_text(payload.text or "")
    update_text = _extract_update_text(payload.text or "")
    target_date_text = (
        _optional_str(_first_slot_value(slots, "target_date_text", "old_date_text", "original_date_text"))
        or _extract_date_hint_from_text(target_text)
    )
    target_time_text = (
        _optional_str(_first_slot_value(slots, "target_time_text", "old_time_text", "original_time_text"))
        or _extract_time_period_from_text(target_text)
    )

    return {
        "keyword": _extract_update_keyword(
            payload=payload,
            slots=slots,
            target_text=target_text,
        ),
        "target_range": _resolve_update_target_range(
            payload=payload,
            slots=slots,
            target_text=target_text,
            target_date_text=target_date_text,
            target_time_text=target_time_text,
        ),
        "target_event": slots.get("target_event"),
        "target_text": target_text,
        "update_text": update_text,
        "target_date_text": target_date_text,
        "target_time_text": target_time_text,
        "updates": _extract_update_draft(slots),
    }


def _extract_update_target_text(text: str) -> str:
    match = _find_update_action_match(text)
    if match is None:
        return text
    return text[: match.start()]


def _extract_update_text(text: str) -> str:
    match = _find_update_action_match(text)
    if match is None:
        return ""
    return text[match.end() :]


def _find_update_action_match(text: str) -> re.Match[str] | None:
    return re.search(r"(改到|改成|修改为|换成|调整到|提前到|推迟到)", text)


def _extract_update_keyword(
    *,
    payload: VoiceCommandRequest,
    slots: Mapping[str, Any],
    target_text: str,
) -> str:
    target_event = _optional_str(slots.get("target_event"))
    if target_event is not None:
        return target_event

    keyword = target_text or payload.text or ""
    for value in (
        slots.get("target_date_text"),
        slots.get("target_time_text"),
        slots.get("old_date_text"),
        slots.get("old_time_text"),
        slots.get("original_date_text"),
        slots.get("original_time_text"),
    ):
        if value:
            keyword = keyword.replace(str(value), "")

    keyword = _remove_update_time_words(keyword)
    for word in (
        "请",
        "帮我",
        "把",
        "将",
        "给我",
        "我要",
        "一下",
        "这个",
        "那个",
        "一个",
        "的",
        "要",
        "日程",
        "安排",
        "提醒",
    ):
        keyword = keyword.replace(word, "")

    keyword = re.sub(r"[，。,.！？!?\s]", "", keyword)
    return _optional_str(keyword) or ""


def _remove_update_time_words(text: str) -> str:
    text = re.sub(r"(今天|明天|后天)", "", text)
    text = re.sub(
        r"(凌晨|早上|上午|中午|下午|晚上|今晚|夜里)"
        r"([零〇一二两三四五六七八九十\d]{1,3})?"
        r"(点|时)?(半|[零〇一二两三四五六七八九十\d]{1,3}分?)?",
        "",
        text,
    )
    return text


def _extract_update_draft(slots: Mapping[str, Any]) -> dict[str, Any]:
    aliases_by_field = {
        "title": ("new_title", "update_title", "title"),
        "start_time": ("new_start_time", "update_start_time", "start_time"),
        "end_time": ("new_end_time", "update_end_time", "end_time"),
        "location": ("new_location", "update_location", "location"),
        "description": ("new_description", "update_description", "description"),
        "participants": ("new_participants", "update_participants", "participants"),
        "priority": ("new_priority", "update_priority", "priority"),
        "is_all_day": ("new_is_all_day", "update_is_all_day", "is_all_day"),
        "recurrence_rule": ("new_recurrence_rule", "update_recurrence_rule", "recurrence_rule"),
        "reminder_offset_minutes": (
            "new_reminder_offset_minutes",
            "update_reminder_offset_minutes",
            "reminder_offset_minutes",
            "new_reminder_offset",
            "update_reminder_offset",
            "reminder_offset",
        ),
    }

    updates: dict[str, Any] = {}
    for field, aliases in aliases_by_field.items():
        value = _first_slot_value(slots, *aliases)
        if value is not None:
            updates[field] = value

    return _jsonable(updates)


def _resolve_update_target_range(
    *,
    payload: VoiceCommandRequest,
    slots: Mapping[str, Any],
    target_text: str,
    target_date_text: str | None,
    target_time_text: str | None,
) -> dict[str, datetime] | None:
    tz = _get_timezone(payload.timezone)
    base_time = _ensure_datetime_timezone(payload.client_time, tz)
    explicit_start = _datetime_from_slot_keys(
        slots,
        timezone=tz,
        keys=("target_start_time", "old_start_time", "original_start_time"),
    )
    explicit_end = _datetime_from_slot_keys(
        slots,
        timezone=tz,
        keys=("target_end_time", "old_end_time", "original_end_time"),
    )

    if explicit_start is not None:
        if explicit_end is not None:
            return {"start_time": explicit_start, "end_time": explicit_end}

        period_range = _period_range_for_text(
            target_time_text or target_text,
            target_date=explicit_start.date(),
            timezone=tz,
        )
        if period_range is not None:
            return period_range

        return _day_range(explicit_start.date(), tz)

    target_date = _date_from_text(target_date_text, base_time.date())
    if target_date is None and target_time_text:
        target_date = base_time.date()

    if target_date is not None:
        period_range = _period_range_for_text(
            target_time_text or target_text,
            target_date=target_date,
            timezone=tz,
        )
        if period_range is not None:
            return period_range
        return _day_range(target_date, tz)

    return None


def _datetime_from_slot_keys(
    slots: Mapping[str, Any],
    *,
    timezone: ZoneInfo | fixed_timezone,
    keys: tuple[str, ...],
) -> datetime | None:
    value = _first_slot_value(slots, *keys)
    if value is None:
        return None
    try:
        parsed = _parse_datetime_slot(value)
    except ValueError:
        return None
    return _ensure_datetime_timezone(parsed, timezone)


def _first_slot_value(slots: Mapping[str, Any], *keys: str) -> Any | None:
    for key in keys:
        value = slots.get(key)
        if value not in (None, ""):
            return value
    return None


def _date_from_text(value: Any, base_date: date) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value)
    if "今天" in text:
        return base_date
    if "明天" in text:
        return base_date + timedelta(days=1)
    if "后天" in text:
        return base_date + timedelta(days=2)
    weekday_match = re.search(r"(本周|下周)?(?:周|星期)([一二三四五六日天])", text)
    if weekday_match is not None:
        prefix, weekday_text = weekday_match.groups()
        weekday_index = {
            "一": 0,
            "二": 1,
            "三": 2,
            "四": 3,
            "五": 4,
            "六": 5,
            "日": 6,
            "天": 6,
        }[weekday_text]
        start_of_week = base_date - timedelta(days=base_date.weekday())
        if prefix == "下周":
            start_of_week += timedelta(days=7)
        elif prefix is None:
            days_until_target = (weekday_index - base_date.weekday()) % 7
            return base_date + timedelta(days=days_until_target)
        return start_of_week + timedelta(days=weekday_index)

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _extract_date_hint_from_text(text: str) -> str | None:
    for value in ("今天", "明天", "后天"):
        if value in text:
            return value
    match = re.search(r"(?:本周|下周)?(?:周|星期)[一二三四五六日天]", text)
    if match is not None:
        return match.group(0)
    return None


def _extract_time_period_from_text(text: str) -> str | None:
    for value in ("凌晨", "早上", "上午", "中午", "下午", "晚上", "今晚", "夜里"):
        if value in text:
            return value
    return None


def _period_range_for_text(
    text: str,
    *,
    target_date: date,
    timezone: ZoneInfo | fixed_timezone,
) -> dict[str, datetime] | None:
    if not text:
        return None

    ranges = (
        (("凌晨",), time(hour=0), time(hour=6)),
        (("早上",), time(hour=6), time(hour=9)),
        (("上午",), time(hour=6), time(hour=12)),
        (("中午",), time(hour=11), time(hour=13)),
        (("下午",), time(hour=12), time(hour=18)),
        (("晚上", "今晚", "夜里"), time(hour=18), time.max),
    )
    for names, start_at, end_at in ranges:
        if any(name in text for name in names):
            start_time = datetime.combine(target_date, start_at, tzinfo=timezone)
            if end_at == time.max:
                end_time = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=timezone)
            else:
                end_time = datetime.combine(target_date, end_at, tzinfo=timezone)
            return {"start_time": start_time, "end_time": end_time}

    return None


def _day_range(value: date, timezone: ZoneInfo | fixed_timezone) -> dict[str, datetime]:
    start_time = datetime.combine(value, time.min, tzinfo=timezone)
    return {"start_time": start_time, "end_time": start_time + timedelta(days=1)}


def _update_target_context_to_data(update_context: Mapping[str, Any]) -> dict[str, Any]:
    return _jsonable(
        {
            "keyword": update_context.get("keyword"),
            "target_event": update_context.get("target_event"),
            "target_text": update_context.get("target_text"),
            "update_text": update_context.get("update_text"),
            "target_date_text": update_context.get("target_date_text"),
            "target_time_text": update_context.get("target_time_text"),
            "target_range": _date_range_to_data(update_context.get("target_range")),
        }
    )


def _build_update_confirm_reply(
    *,
    candidate: Mapping[str, Any],
    updates: Mapping[str, Any],
    slots: Mapping[str, Any],
) -> str:
    update_summary = _build_update_summary(updates=updates, slots=slots)
    candidate_text = _format_candidate_for_reply(candidate)
    if not update_summary:
        return f"找到{candidate_text}，是否确认修改？"
    if update_summary.startswith("改到"):
        return f"找到{candidate_text}，是否将它{update_summary}？"
    return f"找到{candidate_text}，是否按以下内容修改它：{update_summary}？"


def _build_update_candidates_reply(
    candidate_events: list[Mapping[str, Any]],
    update_draft: Mapping[str, Any],
) -> str:
    summaries = [
        f"{index + 1}. {_format_candidate_for_reply(candidate)}"
        for index, candidate in enumerate(candidate_events)
    ]
    update_summary = _build_update_summary(updates=update_draft, slots={})
    action_text = f"，准备{update_summary}" if update_summary else ""
    return "我找到了多个相关日程" + action_text + "，请选择要修改哪一个：" + "；".join(summaries) + "。"


def _build_update_summary(
    *,
    updates: Mapping[str, Any],
    slots: Mapping[str, Any],
) -> str:
    parts: list[str] = []

    if updates.get("start_time"):
        parts.append(f"改到{_format_update_datetime(updates['start_time'], slots)}")
    if updates.get("end_time"):
        parts.append(f"结束时间改为{_format_datetime_value_for_voice(updates['end_time'])}")
    if updates.get("title"):
        parts.append(f"标题改为{updates['title']}")
    if updates.get("location"):
        parts.append(f"地点改为{updates['location']}")
    if updates.get("reminder_offset_minutes") is not None:
        parts.append(f"提醒改为{_format_reminder_offset(updates['reminder_offset_minutes'])}")

    return "，".join(parts)


def _format_update_datetime(value: Any, slots: Mapping[str, Any]) -> str:
    date_text = _optional_str(_first_slot_value(slots, "new_date_text", "update_date_text", "date_text"))
    time_text = _optional_str(_first_slot_value(slots, "new_time_text", "update_time_text", "time_text"))
    if date_text and time_text:
        return f"{date_text}{time_text}"
    if time_text:
        return time_text
    if date_text:
        return date_text
    return _format_datetime_value_for_voice(value)


def _format_datetime_value_for_voice(value: Any) -> str:
    try:
        parsed = _parse_datetime_slot(value)
    except ValueError:
        return str(value)
    parsed = _ensure_datetime_timezone(parsed, _voice_reply_timezone())
    return f"{parsed.month}月{parsed.day}日{_format_time_of_day(parsed)}"


def _format_reminder_offset(value: Any) -> str:
    minutes = _parse_int_slot(value, default=0)
    if minutes == 0:
        return "准时提醒"
    if minutes % 60 == 0:
        return f"提前{minutes // 60}小时"
    return f"提前{minutes}分钟"


def _event_update_from_draft(update_draft: Mapping[str, Any]) -> EventUpdate:
    data: dict[str, Any] = {}

    if "title" in update_draft:
        data["title"] = str(update_draft["title"])
    if "description" in update_draft:
        data["description"] = _optional_str(update_draft.get("description"))
    if "start_time" in update_draft:
        data["start_time"] = _parse_optional_datetime_slot(update_draft.get("start_time"))
    if "end_time" in update_draft:
        data["end_time"] = _parse_optional_datetime_slot(update_draft.get("end_time"))
    if "location" in update_draft:
        data["location"] = _optional_str(update_draft.get("location"))
    if "participants" in update_draft:
        data["participants"] = _normalize_participants(update_draft.get("participants"))
    if "priority" in update_draft:
        data["priority"] = str(update_draft["priority"])
    if "is_all_day" in update_draft:
        data["is_all_day"] = bool(update_draft.get("is_all_day"))
    if "recurrence_rule" in update_draft:
        data["recurrence_rule"] = _normalize_recurrence_rule(update_draft.get("recurrence_rule"))

    return EventUpdate(**data)


async def _rebuild_event_reminder_if_needed(
    *,
    event: Any,
    update_draft: Mapping[str, Any],
    payload: VoiceCommandRequest,
    reminder_service: ReminderService,
) -> dict[str, Any] | None:
    if "reminder_offset_minutes" not in update_draft:
        return None

    event_id = _optional_str(getattr(event, "id", None))
    event_start = _event_model_start_time(event)
    if event_id is None or event_start is None:
        return {
            "cancelled_reminders": [],
            "created_reminder": None,
            "skipped_reason": "missing_event_time",
        }

    offset_minutes = _parse_int_slot(update_draft.get("reminder_offset_minutes"), default=0)
    cancelled_reminders = await reminder_service.cancel_event_reminders(
        event_id=event_id,
        user_id=payload.user_id,
    )
    created_reminder = await reminder_service.create_reminder(
        ReminderCreate(
            event_id=event_id,
            user_id=payload.user_id,
            remind_time=event_start - timedelta(minutes=offset_minutes),
            offset_minutes=offset_minutes,
            channel="app_voice",
        )
    )

    return _jsonable(
        {
            "cancelled_reminders": [
                _model_to_dict(reminder, REMINDER_RESPONSE_FIELDS)
                for reminder in cancelled_reminders
            ],
            "created_reminder": _model_to_dict(created_reminder, REMINDER_RESPONSE_FIELDS),
        }
    )


def _event_model_start_time(event: Any) -> datetime | None:
    value = getattr(event, "start_time", None)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _event_model_end_time(event: Any) -> datetime | None:
    value = getattr(event, "end_time", None)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _conflict_end_time(
    *,
    start_time: datetime,
    end_time: datetime | None,
) -> datetime:
    if end_time is not None and end_time > start_time:
        return end_time
    return start_time + timedelta(hours=1)


def _update_conflict_range(
    *,
    existing_event: Any,
    update_draft: Mapping[str, Any],
) -> dict[str, datetime] | None:
    if "start_time" not in update_draft and "end_time" not in update_draft:
        return None

    existing_start = _event_model_start_time(existing_event)
    if existing_start is None:
        return None

    existing_end = _event_model_end_time(existing_event)
    start_time = (
        _parse_datetime_slot(update_draft["start_time"])
        if update_draft.get("start_time")
        else existing_start
    )

    if update_draft.get("end_time"):
        end_time = _parse_datetime_slot(update_draft["end_time"])
    elif existing_end is not None and existing_end > existing_start:
        end_time = start_time + (existing_end - existing_start)
    else:
        end_time = None

    return {
        "start_time": start_time,
        "end_time": _conflict_end_time(start_time=start_time, end_time=end_time),
    }


def _conflicts_to_data(conflicts: list[Any]) -> list[dict[str, Any]]:
    return [
        _jsonable(
            {
                "id": conflict.get("id") if isinstance(conflict, Mapping) else getattr(conflict, "id", None),
                "title": conflict.get("title") if isinstance(conflict, Mapping) else getattr(conflict, "title", None),
                "start_time": conflict.get("start_time") if isinstance(conflict, Mapping) else getattr(conflict, "start_time", None),
                "end_time": conflict.get("end_time") if isinstance(conflict, Mapping) else getattr(conflict, "end_time", None),
            }
        )
        for conflict in conflicts
    ]


def _build_conflict_reply(
    *,
    conflicts: list[Mapping[str, Any]],
    operation: str,
) -> str:
    conflict_title = "相关日程"
    if conflicts:
        conflict_title = str(conflicts[0].get("title") or conflict_title)

    if operation == "create_event":
        return f"这个时间你已经有{conflict_title}，是否仍然创建新的日程？"
    return f"这个时间你已经有{conflict_title}，是否仍然修改该日程？"


def _build_event_updated_reply(
    *,
    event_data: Mapping[str, Any],
    update_draft: Mapping[str, Any],
) -> str:
    title = event_data.get("title") or "该日程"
    update_summary = _build_update_summary(updates=update_draft, slots={})
    if update_summary:
        return f"已修改{title}，{update_summary}。"
    return f"已修改{title}。"


def _date_range_to_data(date_range: Mapping[str, datetime] | None) -> dict[str, Any] | None:
    if date_range is None:
        return None
    return _jsonable(
        {
            "start_time": date_range["start_time"],
            "end_time": date_range["end_time"],
        }
    )


def _format_candidate_for_reply(candidate: Mapping[str, Any]) -> str:
    title = candidate.get("title") or "该日程"
    time_text = _format_candidate_time(candidate)
    return f"{time_text}{title}"


def _build_delete_candidates_reply(candidate_events: list[Mapping[str, Any]]) -> str:
    summaries = [
        f"{index + 1}. {_format_candidate_for_reply(candidate)}"
        for index, candidate in enumerate(candidate_events)
    ]
    return "我找到了多个相关日程，请选择要删除哪一个：" + "；".join(summaries) + "。"


def _format_candidate_time(candidate: Mapping[str, Any]) -> str:
    start_time = _event_data_start_time(candidate)
    if start_time is None:
        return ""
    start_time = _ensure_datetime_timezone(start_time, _voice_reply_timezone())
    return f"{start_time.month}月{start_time.day}日{_format_time_of_day(start_time)}"


def _resolve_query_range(
    *,
    payload: VoiceCommandRequest,
    slots: Mapping[str, Any],
) -> dict[str, Any]:
    tz = _get_timezone(payload.timezone)
    base_time = _ensure_datetime_timezone(payload.client_time, tz)
    raw_text = payload.text or ""

    if _is_recent_query(raw_text=raw_text, slots=slots):
        return {
            "start_time": base_time,
            "end_time": base_time + timedelta(days=7),
            "label": "最近7天",
            "kind": "recent",
        }

    if _is_afternoon_query(raw_text=raw_text, slots=slots):
        query_date = _query_date_from_slots(slots=slots, base_time=base_time, timezone=tz)
        label = f"{_query_date_label(query_date, base_time.date(), slots)}下午"
        return {
            "start_time": datetime.combine(query_date, time(hour=12), tzinfo=tz),
            "end_time": datetime.combine(query_date, time(hour=18), tzinfo=tz),
            "label": label,
            "kind": "afternoon",
        }

    start_time = _query_start_from_slots(slots=slots, timezone=tz)
    if start_time is not None:
        end_time = _query_end_from_slots(slots=slots, timezone=tz)
        if end_time is None:
            start_time = datetime.combine(start_time.date(), time.min, tzinfo=tz)
            end_time = start_time + timedelta(days=1)

        return {
            "start_time": start_time,
            "end_time": end_time,
            "label": _query_date_label(start_time.date(), base_time.date(), slots),
            "kind": "explicit",
        }

    start_time = datetime.combine(base_time.date(), time.min, tzinfo=tz)
    return {
        "start_time": start_time,
        "end_time": start_time + timedelta(days=1),
        "label": "今天",
        "kind": "today",
    }


def _query_range_to_data(query_range: Mapping[str, Any]) -> dict[str, Any]:
    return _jsonable(
        {
            "start_time": query_range["start_time"],
            "end_time": query_range["end_time"],
            "label": query_range["label"],
            "kind": query_range["kind"],
        }
    )


def _is_recent_query(*, raw_text: str, slots: Mapping[str, Any]) -> bool:
    date_text = str(slots.get("date_text") or "")
    return "最近" in raw_text or "最近" in date_text


def _is_afternoon_query(*, raw_text: str, slots: Mapping[str, Any]) -> bool:
    time_text = str(slots.get("time_text") or "")
    if "下午" in time_text and "点" not in time_text:
        return True
    return "下午" in raw_text and "点" not in raw_text


def _query_date_from_slots(
    *,
    slots: Mapping[str, Any],
    base_time: datetime,
    timezone: ZoneInfo,
) -> date:
    start_time = _query_start_from_slots(slots=slots, timezone=timezone)
    if start_time is not None:
        return start_time.date()
    return base_time.date()


def _query_start_from_slots(
    *,
    slots: Mapping[str, Any],
    timezone: ZoneInfo,
) -> datetime | None:
    value = slots.get("start_time")
    if value in (None, ""):
        return None
    return _ensure_datetime_timezone(_parse_datetime_slot(value), timezone)


def _query_end_from_slots(
    *,
    slots: Mapping[str, Any],
    timezone: ZoneInfo,
) -> datetime | None:
    value = slots.get("end_time")
    if value in (None, ""):
        return None
    return _ensure_datetime_timezone(_parse_datetime_slot(value), timezone)


def _query_date_label(
    query_date: date,
    base_date: date,
    slots: Mapping[str, Any],
) -> str:
    date_text = str(slots.get("date_text") or "")
    if date_text in {"今天", "明天", "后天"}:
        return date_text
    if query_date == base_date:
        return "今天"
    if query_date == base_date + timedelta(days=1):
        return "明天"
    if query_date == base_date + timedelta(days=2):
        return "后天"
    return f"{query_date.month}月{query_date.day}日"


def _event_sort_key(event: Any) -> datetime:
    start_time = getattr(event, "start_time", None)
    if isinstance(start_time, datetime):
        return start_time
    if isinstance(start_time, str):
        try:
            return datetime.fromisoformat(start_time)
        except ValueError:
            pass
    return datetime.max


def _build_query_events_reply(
    *,
    events: list[Mapping[str, Any]],
    query_range: Mapping[str, Any],
) -> str:
    if not events:
        return "暂无安排。"

    summaries = [
        _format_event_for_voice(event_data=event_data, query_range=query_range)
        for event_data in events
    ]
    return f"{query_range['label']}你有 {len(events)} 个安排：" + "，".join(summaries) + "。"


def _format_event_for_voice(
    *,
    event_data: Mapping[str, Any],
    query_range: Mapping[str, Any],
) -> str:
    start_time = _event_data_start_time(event_data)
    time_text = _format_event_time_for_voice(start_time=start_time, query_range=query_range)
    title = str(event_data.get("title") or "未命名日程")
    return f"{time_text}{title}"


def _event_data_start_time(event_data: Mapping[str, Any]) -> datetime | None:
    value = event_data.get("start_time")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _format_event_time_for_voice(
    *,
    start_time: datetime | None,
    query_range: Mapping[str, Any],
) -> str:
    if start_time is None:
        return ""

    range_start = query_range["start_time"]
    if isinstance(range_start, datetime) and range_start.tzinfo is not None:
        start_time = _ensure_datetime_timezone(start_time, range_start.tzinfo)
    include_date = query_range["kind"] == "recent" or start_time.date() != range_start.date()
    date_text = f"{start_time.month}月{start_time.day}日" if include_date else ""
    return f"{date_text}{_format_time_of_day(start_time)}"


def _format_time_of_day(value: datetime) -> str:
    hour = value.hour
    minute = value.minute

    if 0 <= hour < 6:
        period = "凌晨"
    elif 6 <= hour < 12:
        period = "上午"
    elif 12 <= hour < 18:
        period = "下午"
    else:
        period = "晚上"

    display_hour = hour
    if hour == 0:
        display_hour = 12
    elif hour > 12:
        display_hour = hour - 12

    if minute == 0:
        return f"{period} {display_hour} 点"
    return f"{period} {display_hour} 点 {minute} 分"


def _get_timezone(value: str) -> ZoneInfo | fixed_timezone:
    try:
        return ZoneInfo(value)
    except Exception:
        normalized = value.strip().lower()
        if normalized in {
            "asia/shanghai",
            "asia/chongqing",
            "asia/urumqi",
            "cst",
            "utc+8",
            "utc+08",
            "utc+08:00",
            "gmt+8",
            "gmt+08",
            "gmt+08:00",
        }:
            return fixed_timezone(timedelta(hours=8), name=value.strip())
        if normalized in {"utc", "gmt", "z"}:
            return fixed_timezone(timedelta(0), name=value.strip())
        return ZoneInfo("UTC")


def _ensure_datetime_timezone(
    value: datetime,
    timezone: ZoneInfo | fixed_timezone,
) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def _build_event_created_reply(
    *,
    slots: Mapping[str, Any],
    event_data: Mapping[str, Any],
    reminder_data: Mapping[str, Any] | None,
) -> str:
    time_text = _display_time_text(slots=slots, event_data=event_data)
    title = event_data.get("title") or slots.get("title") or "日程"
    noun = "提醒" if reminder_data is not None else "日程"
    return f"已为你创建{time_text}的{noun}：{title}。"


def _display_time_text(
    *,
    slots: Mapping[str, Any],
    event_data: Mapping[str, Any],
) -> str:
    date_text = slots.get("date_text")
    time_text = slots.get("time_text")
    if date_text and time_text:
        return f"{date_text}{time_text}"
    if date_text:
        return str(date_text)
    if time_text:
        return str(time_text)

    start_time = event_data.get("start_time")
    if isinstance(start_time, str):
        try:
            parsed_start = _ensure_datetime_timezone(
                datetime.fromisoformat(start_time),
                _voice_reply_timezone(),
            )
            return parsed_start.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return start_time
    return "指定时间"


def _voice_reply_timezone() -> ZoneInfo | fixed_timezone:
    return _get_timezone(get_settings().timezone)
