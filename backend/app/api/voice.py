from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.voice import VoiceCommandRequest, VoiceCommandResponse
from app.services.dialog_service import DialogService
from app.services.nlu_service import NLUResult, NLUService
from app.services.time_parser import TimeParser
from app.services.voice_command_log_service import VoiceCommandLogService


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

REQUIRED_SLOTS_BY_INTENT = {
    "create_event": ["title", "start_time"],
    "create_reminder": ["title", "start_time"],
    "query_event": ["date_text"],
    "update_event": ["target_event", "start_time"],
    "delete_event": ["target_event"],
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
