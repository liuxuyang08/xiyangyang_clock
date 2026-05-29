from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone as fixed_timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.event import EventCreate
from app.schemas.reminder import ReminderCreate
from app.schemas.voice import VoiceCommandRequest, VoiceCommandResponse
from app.services.calendar_service import CalendarService
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
    "update_event": ["target_event", "start_time"],
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


async def get_dialog_service(
    session: AsyncSession = Depends(get_db_session),
) -> DialogService:
    return DialogService(session)


async def get_calendar_service(
    session: AsyncSession = Depends(get_db_session),
) -> CalendarService:
    return CalendarService(session)


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
        time_parse_details = _normalize_time_slots(
            slots=slots,
            base_time=payload.client_time,
            timezone=payload.timezone,
            time_parser=time_parser,
        )
        missing_slots = _resolve_missing_slots(
            intent=intent,
            slots=slots,
            nlu_missing_slots=nlu_result.missing_slots,
            time_missing_slots=time_parse_details.get("missing_slots", []),
        )
        entities = _jsonable(
            {
                "slots": slots,
                "missing_slots": missing_slots,
                "time_parse": time_parse_details,
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
                intent=intent,
                slots=slots,
                nlu_result=nlu_result,
                time_parse_details=time_parse_details,
                voice_command_id=voice_command_id,
                calendar_service=calendar_service,
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
    intent: str,
    slots: dict[str, Any],
    nlu_result: NLUResult,
    time_parse_details: dict[str, Any],
    voice_command_id: str | None,
    calendar_service: CalendarService,
    reminder_service: ReminderService,
    voice_command_log_service: VoiceCommandLogService,
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
        action="event_created",
        need_user_reply=False,
        reply=_build_event_created_reply(
            slots=slots,
            event_data=event_data,
            reminder_data=reminder_data,
        ),
        data={
            "voice_command_id": voice_command_id,
            "intent": intent,
            "confidence": nlu_result.confidence,
            "event": event_data,
            "reminder": reminder_data,
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
        if parsed.start_datetime is not None:
            slots["start_time"] = parsed.start_datetime.isoformat()
        elif parsed.datetime is not None:
            slots["start_time"] = parsed.datetime.isoformat()

        if parsed.end_datetime is not None:
            slots["end_time"] = parsed.end_datetime.isoformat()

    return result


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
) -> list[str]:
    if intent == "query_event":
        return []

    if intent == "delete_event":
        has_delete_context = any(
            slots.get(field)
            for field in ("target_event", "date_text", "time_text", "start_time")
        )
        return [] if has_delete_context else ["target_event"]

    missing_slots: list[str] = []
    for slot in [*nlu_missing_slots, *time_missing_slots]:
        if slot == "intent" and intent != "unknown":
            continue
        if slot != "intent" and slots.get(slot):
            continue
        if slot not in missing_slots:
            missing_slots.append(slot)

    for slot in REQUIRED_SLOTS_BY_INTENT.get(intent, []):
        if not slots.get(slot) and slot not in missing_slots:
            missing_slots.append(slot)

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
            return datetime.fromisoformat(start_time).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return start_time
    return "指定时间"
