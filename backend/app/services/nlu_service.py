from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import importlib.util
from pathlib import Path
import re
import sys
from typing import Any

try:
    from .time_parser import TimeParser
except ImportError:  # pragma: no cover - supports direct file loading in tests
    time_parser_path = Path(__file__).with_name("time_parser.py")
    spec = importlib.util.spec_from_file_location("time_parser", time_parser_path)
    if spec is None or spec.loader is None:
        raise
    time_parser_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = time_parser_module
    spec.loader.exec_module(time_parser_module)
    TimeParser = time_parser_module.TimeParser

try:
    from .llm_parse_service import LLMParseService
except ImportError:  # pragma: no cover - supports direct file loading in tests
    llm_parse_service_path = Path(__file__).with_name("llm_parse_service.py")
    spec = importlib.util.spec_from_file_location("llm_parse_service", llm_parse_service_path)
    if spec is None or spec.loader is None:
        raise
    llm_parse_service_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = llm_parse_service_module
    spec.loader.exec_module(llm_parse_service_module)
    LLMParseService = llm_parse_service_module.LLMParseService


CHINESE_NUMBER = r"[零〇一二两三四五六七八九十\d]{1,3}"
PERIOD = r"(?:凌晨|早上|上午|中午|下午|晚上|今晚|夜里)"

DATE_PATTERN = re.compile(r"(今天|明天|后天|(?:本周|下周)?(?:周|星期)[一二三四五六日天]|(?:本周|下周)[一二三四五六日天])")
TIME_POINT_PATTERN = re.compile(rf"({PERIOD}?{CHINESE_NUMBER}点(?:半|{CHINESE_NUMBER}分)?)")
RELATIVE_TIME_PATTERN = re.compile(rf"(半小时后|{CHINESE_NUMBER}小时后|{CHINESE_NUMBER}分钟后)")
RECURRENCE_PATTERN = re.compile(
    rf"(每天|工作日|每周[一二三四五六日天](?:{PERIOD}?{CHINESE_NUMBER}点(?:半|{CHINESE_NUMBER}分)?)?|每月\s*{CHINESE_NUMBER}\s*号)"
)
REMINDER_OFFSET_PATTERN = re.compile(rf"提前(半小时|{CHINESE_NUMBER}(?:分钟|小时))")


@dataclass(slots=True)
class DateTimeParts:
    date_text: str | None = None
    time_text: str | None = None
    expression: str | None = None


@dataclass(slots=True)
class NLUResult:
    raw_text: str
    intent: str
    confidence: float
    slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)


class NLUService:
    def __init__(
        self,
        time_parser: TimeParser | None = None,
        llm_parse_service: LLMParseService | None = None,
        enable_llm: bool = True,
    ) -> None:
        self.time_parser = time_parser or TimeParser()
        self.llm_parse_service = llm_parse_service
        self.enable_llm = enable_llm

    def parse(
        self,
        text: str,
        base_time: datetime | None = None,
        timezone: str = "Asia/Shanghai",
        conversation_context: Any | None = None,
    ) -> NLUResult:
        normalized_text = text.strip()
        if base_time is None:
            base_time = datetime.now()

        llm_result = self._parse_with_llm(
            text=normalized_text,
            conversation_context=conversation_context,
            base_time=base_time,
            timezone=timezone,
        )
        if llm_result is not None:
            return llm_result

        intent, confidence = self._detect_intent(normalized_text)
        slots = self._extract_slots(
            text=normalized_text,
            intent=intent,
            base_time=base_time,
            timezone=timezone,
        )
        missing_slots = self._missing_required_slots(intent, slots)

        return NLUResult(
            raw_text=normalized_text,
            intent=intent,
            confidence=confidence,
            slots=slots,
            missing_slots=missing_slots,
        )

    def _parse_with_llm(
        self,
        *,
        text: str,
        conversation_context: Any | None,
        base_time: datetime,
        timezone: str,
    ) -> NLUResult | None:
        if not self.enable_llm:
            return None

        llm_service = self.llm_parse_service or LLMParseService()
        try:
            llm_result = llm_service.parse(
                text,
                conversation_context=conversation_context,
                base_time=base_time,
                timezone=timezone,
            )
        except Exception:
            return None

        if llm_result is None:
            return None

        missing_slots = llm_result.missing_slots or self._missing_required_slots(
            llm_result.intent,
            llm_result.slots,
        )

        return NLUResult(
            raw_text=llm_result.raw_text,
            intent=llm_result.intent,
            confidence=llm_result.confidence,
            slots=llm_result.slots,
            missing_slots=missing_slots,
        )

    def _detect_intent(self, text: str) -> tuple[str, float]:
        if not text:
            return "unknown", 0.0

        if text in {"确认", "是的", "对", "没错", "可以"}:
            return "confirm", 0.95

        if text in {"不用了", "不是", "不对", "取消"}:
            return "deny", 0.9

        if any(word in text for word in {"撤销", "上一步", "回退"}):
            return "undo", 0.9

        if any(word in text for word in {"帮助", "怎么用", "能做什么", "你能做什么"}):
            return "help", 0.9

        if any(word in text for word in {"改到", "换成", "提前到", "推迟到"}):
            return "update_event", 0.9

        if any(word in text for word in {"取消提醒", "不要提醒"}):
            return "cancel_reminder", 0.9

        if "提醒我" in text or text.startswith("提醒"):
            return "create_reminder", 0.9

        if any(word in text for word in {"删除", "不要了", "取消"}):
            return "delete_event", 0.85

        if any(word in text for word in {"今天有什么", "明天有什么", "查一下", "查询", "有什么安排"}):
            return "query_event", 0.85

        if any(word in text for word in {"添加", "新增", "安排", "创建"}):
            return "create_event", 0.8

        if self._find_datetime_parts(text).expression and any(
            word in text for word in {"开会", "会议", "健身", "上课", "吃饭", "见面", "例会"}
        ):
            return "create_event", 0.75

        return "unknown", 0.0

    def _extract_slots(
        self,
        text: str,
        intent: str,
        base_time: datetime,
        timezone: str,
    ) -> dict[str, Any]:
        slots: dict[str, Any] = {}

        self._extract_recurrence(text, slots)
        self._extract_reminder_offset(text, slots)
        self._extract_people_and_location(text, slots)

        if intent == "update_event":
            self._extract_update_slots(text, slots, base_time, timezone)
            return slots

        if intent in {"delete_event", "cancel_reminder"}:
            self._extract_target_slots(text, intent, slots, base_time, timezone)
            return slots

        date_time_parts = self._extract_date_time_slots(
            text=text,
            slots=slots,
            base_time=base_time,
            timezone=timezone,
        )

        if intent in {"create_event", "create_reminder"}:
            title = self._extract_title(text, slots, date_time_parts.expression)
            if title:
                slots["title"] = title

        return slots

    def _extract_update_slots(
        self,
        text: str,
        slots: dict[str, Any],
        base_time: datetime,
        timezone: str,
    ) -> None:
        match = re.search(r"(改到|换成|提前到|推迟到)", text)
        if match is None:
            return

        target_text = text[: match.start()]
        new_time_text = text[match.end() :]

        target_parts = self._find_datetime_parts(target_text)
        new_parts = self._find_datetime_parts(new_time_text)

        if target_parts.date_text:
            slots["date_text"] = target_parts.date_text
        if new_parts.date_text:
            slots["date_text"] = new_parts.date_text
        if new_parts.time_text:
            slots["time_text"] = new_parts.time_text

        target_event = self._clean_target_event(target_text, target_parts)
        if target_event:
            slots["target_event"] = target_event

        expression = new_parts.expression
        if new_parts.time_text and not new_parts.date_text and target_parts.date_text:
            expression = f"{target_parts.date_text}{new_parts.time_text}"
        elif new_parts.time_text and not new_parts.date_text and slots.get("date_text"):
            expression = f"{slots['date_text']}{new_parts.time_text}"
        if expression:
            self._parse_time_expression(expression, slots, base_time, timezone)

    def _extract_target_slots(
        self,
        text: str,
        intent: str,
        slots: dict[str, Any],
        base_time: datetime,
        timezone: str,
    ) -> None:
        parts = self._find_datetime_parts(text)
        if parts.date_text:
            slots["date_text"] = parts.date_text
        if parts.time_text:
            slots["time_text"] = parts.time_text
        if parts.expression:
            self._parse_time_expression(parts.expression, slots, base_time, timezone)

        target_text = text
        if intent == "cancel_reminder":
            target_text = re.sub(r"^(请|帮我)?(取消提醒|不要提醒|取消)", "", target_text)
        else:
            target_text = re.sub(r"^(请|帮我)?(删除|取消|不要了?)", "", target_text)

        target_event = self._clean_target_event(target_text, parts)
        if target_event:
            slots["target_event"] = target_event

    def _extract_date_time_slots(
        self,
        text: str,
        slots: dict[str, Any],
        base_time: datetime,
        timezone: str,
    ) -> DateTimeParts:
        parts = self._find_datetime_parts(text)
        if parts.date_text:
            slots["date_text"] = parts.date_text
        if parts.time_text:
            slots["time_text"] = parts.time_text
        if parts.expression:
            self._parse_time_expression(parts.expression, slots, base_time, timezone)
        return parts

    def _parse_time_expression(
        self,
        expression: str,
        slots: dict[str, Any],
        base_time: datetime,
        timezone: str,
    ) -> None:
        parsed = self.time_parser.parse(expression, base_time=base_time, timezone=timezone)
        if not parsed.success:
            return

        if parsed.start_datetime is not None:
            slots["start_time"] = parsed.start_datetime.isoformat()
        elif parsed.datetime is not None:
            slots["start_time"] = parsed.datetime.isoformat()

        if parsed.end_datetime is not None:
            slots["end_time"] = parsed.end_datetime.isoformat()

    def _find_datetime_parts(self, text: str) -> DateTimeParts:
        relative_match = RELATIVE_TIME_PATTERN.search(text)
        if relative_match is not None:
            time_text = relative_match.group(1)
            return DateTimeParts(time_text=time_text, expression=time_text)

        date_match = DATE_PATTERN.search(text)
        time_match = TIME_POINT_PATTERN.search(text)

        date_text = date_match.group(1) if date_match else None
        time_text = time_match.group(1) if time_match else None
        expression: str | None = None

        if date_match and time_match:
            start = min(date_match.start(), time_match.start())
            end = max(date_match.end(), time_match.end())
            expression = text[start:end]
        elif date_text:
            expression = date_text
        elif time_text:
            expression = time_text

        return DateTimeParts(
            date_text=date_text,
            time_text=time_text,
            expression=expression,
        )

    def _extract_recurrence(self, text: str, slots: dict[str, Any]) -> None:
        match = RECURRENCE_PATTERN.search(text)
        if match is not None:
            slots["recurrence_text"] = match.group(1)

    def _extract_reminder_offset(self, text: str, slots: dict[str, Any]) -> None:
        match = REMINDER_OFFSET_PATTERN.search(text)
        if match is None:
            return

        offset_text = match.group(1)
        if offset_text == "半小时":
            slots["reminder_offset_minutes"] = 30
            return

        number_text = offset_text[:-2]
        unit = offset_text[-2:]
        number = self._parse_chinese_number(number_text)
        if number is None:
            return

        slots["reminder_offset_minutes"] = number * 60 if unit == "小时" else number

    def _extract_people_and_location(self, text: str, slots: dict[str, Any]) -> None:
        people_location_match = re.search(
            r"(?:和|跟|与)(?P<people>.+?)在(?P<location>.+?)(?P<action>开会|见面|吃饭|讨论|沟通|上课)",
            text,
        )
        if people_location_match is not None:
            people = self._split_people(people_location_match.group("people"))
            if people:
                slots["participants"] = people
            slots["location"] = people_location_match.group("location").strip()
            return

        location_match = re.search(r"在(?P<location>.+?)(?:开会|见面|吃饭|讨论|沟通|上课|健身)", text)
        if location_match is not None:
            slots["location"] = location_match.group("location").strip()

    def _extract_title(
        self,
        text: str,
        slots: dict[str, Any],
        time_expression: str | None,
    ) -> str | None:
        people_location_match = re.search(
            r"(?:和|跟|与).+?在.+?(?P<action>开会|见面|吃饭|讨论|沟通|上课)",
            text,
        )
        if people_location_match is not None:
            return people_location_match.group("action")

        candidate = text
        for value in (
            slots.get("recurrence_text"),
            time_expression,
            slots.get("date_text"),
            slots.get("time_text"),
        ):
            if value:
                candidate = candidate.replace(value, "", 1)

        candidate = re.sub(r"^(请|帮我|给我)?(提醒我|提醒|添加|新增|安排|创建)", "", candidate)
        candidate = candidate.replace("提醒我", "")
        candidate = self._remove_people_and_location(candidate, slots)
        candidate = self._clean_text(candidate)

        return candidate or None

    def _clean_target_event(self, text: str, parts: DateTimeParts) -> str | None:
        candidate = re.sub(r"^(把|将|请把|帮我把)", "", text)
        for value in (parts.expression, parts.date_text, parts.time_text):
            if value:
                candidate = candidate.replace(value, "", 1)
        candidate = re.sub(r"(今天|明天|后天)?(凌晨|早上|上午|中午|下午|晚上|今晚|夜里)", "", candidate)
        candidate = self._clean_text(candidate)
        return candidate or None

    def _remove_people_and_location(self, text: str, slots: dict[str, Any]) -> str:
        candidate = text
        location = slots.get("location")
        if isinstance(location, str):
            candidate = re.sub(rf"在{re.escape(location)}", "", candidate)

        participants = slots.get("participants")
        if isinstance(participants, list):
            for person in participants:
                candidate = re.sub(rf"(和|跟|与){re.escape(str(person))}", "", candidate)
        return candidate

    def _clean_text(self, text: str) -> str:
        cleaned = re.sub(r"[，。,.！？!?\s]", "", text)
        cleaned = re.sub(r"^(的|要|我|一下)+", "", cleaned)
        cleaned = re.sub(r"(的|要|一下)+$", "", cleaned)
        return cleaned

    def _split_people(self, text: str) -> list[str]:
        return [
            item.strip()
            for item in re.split(r"[、,，]|和|跟|与", text)
            if item.strip()
        ]

    def _missing_required_slots(self, intent: str, slots: dict[str, Any]) -> list[str]:
        required_by_intent = {
            "create_event": ["title", "start_time"],
            "create_reminder": ["title", "start_time"],
            "query_event": ["date_text"],
            "update_event": ["target_event", "start_time"],
            "delete_event": ["target_event"],
            "cancel_reminder": ["target_event"],
            "unknown": ["intent"],
        }
        required_slots = required_by_intent.get(intent, [])
        return [slot for slot in required_slots if not slots.get(slot)]

    def _parse_chinese_number(self, value: str) -> int | None:
        if value.isdigit():
            return int(value)

        if value == "半":
            return 0

        digits = {
            "零": 0,
            "〇": 0,
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }

        if value == "十":
            return 10

        if "十" in value:
            left, _, right = value.partition("十")
            tens = 1 if left == "" else digits.get(left)
            ones = 0 if right == "" else digits.get(right)
            if tens is None or ones is None:
                return None
            return tens * 10 + ones

        total = 0
        for char in value:
            digit = digits.get(char)
            if digit is None:
                return None
            total = total * 10 + digit
        return total
