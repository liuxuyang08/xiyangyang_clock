from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any

try:
    from dateutil.rrule import rrulestr
except ImportError:  # pragma: no cover - optional in stripped local environments
    rrulestr = None

WEEKDAY_NAMES = {
    "一": "MO",
    "二": "TU",
    "三": "WE",
    "四": "TH",
    "五": "FR",
    "六": "SA",
    "日": "SU",
    "天": "SU",
}


@dataclass(slots=True)
class RecurrenceParseResult:
    raw_text: str
    success: bool
    recurrence_rule: dict[str, Any] | None = None
    rrule: str | None = None
    need_followup: bool = False
    reason: str | None = None


class RecurrenceParser:
    def parse(
        self,
        text: str,
        base_time: datetime | None = None,
    ) -> RecurrenceParseResult:
        normalized_text = text.strip()
        if not normalized_text:
            return RecurrenceParseResult(
                raw_text=text,
                success=False,
                need_followup=True,
                reason="empty_recurrence_text",
            )

        parsed = self._parse_rule(normalized_text, base_time)
        if parsed is None:
            return RecurrenceParseResult(
                raw_text=text,
                success=False,
                need_followup=True,
                reason="unrecognized_recurrence_expression",
            )

        recurrence_rule, rrule_string = parsed
        return RecurrenceParseResult(
            raw_text=text,
            success=True,
            recurrence_rule=recurrence_rule,
            rrule=rrule_string,
            need_followup=False,
        )

    def _parse_rule(
        self,
        text: str,
        base_time: datetime | None,
    ) -> tuple[dict[str, Any], str] | None:
        if text == "每天":
            return self._build_rule(freq="DAILY")

        if text == "工作日":
            return self._build_rule(freq="WEEKLY", byday=["MO", "TU", "WE", "TH", "FR"])

        match = re.fullmatch(r"每月\s*([零〇一二两三四五六七八九十\d]{1,2})\s*号", text)
        if match is not None:
            month_day = self._parse_chinese_number(match.group(1))
            if month_day is None or not (1 <= month_day <= 31):
                return None
            return self._build_rule(freq="MONTHLY", bymonthday=[month_day])

        match = re.fullmatch(r"每周([一二三四五六日天])(?:\s*(上午|下午|晚上|中午)?\s*([零〇一二两三四五六七八九十\d]{1,3})点(半|[零〇一二两三四五六七八九十\d]{1,3}分?)?)?", text)
        if match is not None:
            weekday, period, hour_text, minute_text = match.groups()
            if period is None and hour_text is None:
                return self._build_rule(freq="WEEKLY", byday=[WEEKDAY_NAMES[weekday]])
            time_info = self._parse_time_parts(period, hour_text, minute_text)
            if time_info is None:
                return None
            hour, minute = time_info
            return self._build_rule(
                freq="WEEKLY",
                byday=[WEEKDAY_NAMES[weekday]],
                byhour=[hour],
                byminute=[minute],
            )

        return None

    def _parse_time_parts(
        self,
        period: str | None,
        hour_text: str | None,
        minute_text: str | None,
    ) -> tuple[int, int] | None:
        if hour_text is None:
            return None

        hour = self._parse_chinese_number(hour_text)
        if hour is None:
            return None

        minute = 0
        if minute_text == "半":
            minute = 30
        elif minute_text:
            minute = self._parse_chinese_number(minute_text.removesuffix("分"))
            if minute is None:
                return None

        if period in {"下午", "晚上"} and 1 <= hour <= 11:
            hour += 12
        if period == "中午" and 1 <= hour <= 10:
            hour += 12

        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            return None

        return hour, minute

    def _parse_chinese_number(self, value: str) -> int | None:
        if value.isdigit():
            return int(value)

        if value == "十":
            return 10

        if "十" in value:
            left, _, right = value.partition("十")
            tens = 1 if left == "" else self._single_digit(left)
            ones = 0 if right == "" else self._single_digit(right)
            if tens is None or ones is None:
                return None
            return tens * 10 + ones

        if len(value) == 1:
            return self._single_digit(value)

        total = 0
        for char in value:
            digit = self._single_digit(char)
            if digit is None:
                return None
            total = total * 10 + digit
        return total

    def _single_digit(self, value: str) -> int | None:
        mapping = {
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
        return mapping.get(value)

    def _build_rule(
        self,
        *,
        freq: str,
        byday: list[str] | None = None,
        bymonthday: list[int] | None = None,
        byhour: list[int] | None = None,
        byminute: list[int] | None = None,
    ) -> tuple[dict[str, Any], str]:
        parts = [f"FREQ={freq}"]
        rule: dict[str, Any] = {
            "type": "rrule",
            "freq": freq,
        }

        if byday:
            rule["byday"] = byday
            parts.append("BYDAY=" + ",".join(byday))

        if bymonthday:
            rule["bymonthday"] = bymonthday
            parts.append("BYMONTHDAY=" + ",".join(str(item) for item in bymonthday))

        if byhour:
            rule["byhour"] = byhour
            parts.append("BYHOUR=" + ",".join(str(item) for item in byhour))

        if byminute:
            rule["byminute"] = byminute
            parts.append("BYMINUTE=" + ",".join(str(item) for item in byminute))

        rrule_string = "RRULE:" + ";".join(parts)
        rule["rrule"] = rrule_string

        self._validate_rrule(rrule_string)

        return rule, rrule_string

    def _validate_rrule(self, rrule_string: str) -> None:
        if rrulestr is None:
            return

        try:
            rrulestr(rrule_string, dtstart=datetime.now())
        except Exception as exc:  # pragma: no cover - defensive validation
            raise ValueError(f"Invalid recurrence rule generated: {rrule_string}") from exc
