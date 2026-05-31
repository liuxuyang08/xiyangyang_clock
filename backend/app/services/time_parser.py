from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone as fixed_timezone
import re
from zoneinfo import ZoneInfo

try:
    import dateparser
except ImportError:  # pragma: no cover - optional in stripped local environments
    dateparser = None


FUZZY_TIME_WORDS = {"上午", "中午", "下午", "晚上", "今晚", "夜里", "睡前", "上班前"}

AMBIGUOUS_EXPRESSIONS = {"月底前", "月末前", "周末", "睡前", "上班前"}

DAY_OFFSETS = {
    "今天": 0,
    "明天": 1,
    "后天": 2,
}

WEEK_PREFIXES = ("本周", "下周")

PERIOD_HOURS = {
    "凌晨": 0,
    "早上": 6,
    "上午": 0,
    "中午": 12,
    "下午": 12,
    "晚上": 12,
    "今晚": 12,
    "夜里": 12,
}

CHINESE_DIGITS = {
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

WEEKDAY_MAP = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}


@dataclass(slots=True)
class TimeParseResult:
    raw_text: str
    success: bool
    datetime: datetime | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    is_range: bool = False
    ambiguous: bool = False
    need_followup: bool = False
    is_past: bool = False
    missing_slots: list[str] = field(default_factory=list)
    reason: str | None = None


class TimeParser:
    def parse(
        self,
        text: str,
        base_time: datetime,
        timezone: str,
    ) -> TimeParseResult:
        normalized_text = text.strip()
        tz = self._get_timezone(timezone)
        base = self._ensure_timezone(base_time, tz)

        if not normalized_text:
            return TimeParseResult(
                raw_text=text,
                success=False,
                need_followup=True,
                missing_slots=["time_text"],
                reason="empty_time_text",
            )

        if self._is_ambiguous_expression(normalized_text):
            return TimeParseResult(
                raw_text=text,
                success=False,
                ambiguous=True,
                need_followup=True,
                missing_slots=["specific_time"],
                reason="ambiguous_expression",
            )

        if normalized_text in FUZZY_TIME_WORDS:
            return TimeParseResult(
                raw_text=text,
                success=False,
                need_followup=True,
                missing_slots=["specific_time"],
                reason="fuzzy_time_expression",
            )

        if self._needs_followup_for_fuzzy_period(normalized_text):
            return TimeParseResult(
                raw_text=text,
                success=False,
                need_followup=True,
                missing_slots=["specific_time"],
                reason="fuzzy_time_expression",
            )

        range_result = self._parse_week_range(normalized_text, base, tz)
        if range_result is not None:
            return range_result

        relative_result = self._parse_relative_duration(normalized_text, base, tz)
        if relative_result is not None:
            return relative_result

        weekday_result = self._parse_weekday_expression(normalized_text, base, tz)
        if weekday_result is not None:
            return self._finalize_exact_result(text, weekday_result, base)

        rule_result = self._parse_by_rules(normalized_text, base, tz)
        if rule_result is not None:
            return self._finalize_exact_result(text, rule_result, base)

        parsed = self._parse_with_dateparser(normalized_text, base, timezone, tz)
        if parsed is not None:
            return self._finalize_exact_result(text, parsed, base)

        return TimeParseResult(
            raw_text=text,
            success=False,
            need_followup=True,
            missing_slots=["datetime"],
            reason="unrecognized_time_expression",
        )

    def _parse_with_dateparser(
        self,
        text: str,
        base_time: datetime,
        timezone: str,
        tz: ZoneInfo,
    ) -> datetime | None:
        if dateparser is None:
            return None

        try:
            parsed = dateparser.parse(
                text,
                settings={
                    "RELATIVE_BASE": base_time.replace(tzinfo=None),
                    "TIMEZONE": timezone,
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "PREFER_DATES_FROM": "future",
                },
                languages=["zh"],
            )
        except Exception:
            return None
        if parsed is None:
            return None

        return parsed.astimezone(tz)

    def _parse_week_range(
        self,
        text: str,
        base_time: datetime,
        timezone: ZoneInfo,
    ) -> TimeParseResult | None:
        match = re.fullmatch(
            r"(?:(本周|下周)?)([一二三四五六日天])到(?:(本周|下周)?)([一二三四五六日天])",
            text,
        )
        if match is None:
            return None

        start_prefix, start_day, end_prefix, end_day = match.groups()
        if start_prefix is None or end_prefix is None:
            return None

        start_date = self._resolve_weekday_date(start_prefix, start_day, base_time)
        end_date = self._resolve_weekday_date(end_prefix, end_day, base_time)

        start_datetime = datetime.combine(
            start_date,
            time.min,
            tzinfo=timezone,
        )
        end_datetime = datetime.combine(
            end_date,
            time.max,
            tzinfo=timezone,
        )

        if start_datetime > end_datetime:
            return TimeParseResult(
                raw_text=text,
                success=False,
                ambiguous=True,
                need_followup=True,
                missing_slots=["specific_time"],
                reason="invalid_week_range",
            )

        is_past = end_datetime < base_time
        return TimeParseResult(
            raw_text=text,
            success=True,
            datetime=start_datetime,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            is_range=True,
            need_followup=is_past,
            is_past=is_past,
            missing_slots=["confirm_range"] if is_past else [],
            reason="parsed_range_in_past" if is_past else None,
        )

    def _parse_relative_duration(
        self,
        text: str,
        base_time: datetime,
        timezone: ZoneInfo,
    ) -> TimeParseResult | None:
        if text == "半小时后":
            target = base_time + timedelta(minutes=30)
            return self._finalize_exact_result(text, target, base_time)

        match = re.fullmatch(r"([零〇一二两三四五六七八九十\d]{1,3})分钟后", text)
        if match is not None:
            minutes = self._parse_chinese_number(match.group(1))
            if minutes is None:
                return None

            target = base_time + timedelta(minutes=minutes)
            return self._finalize_exact_result(text, target, base_time)

        match = re.fullmatch(r"([零〇一二两三四五六七八九十\d]{1,3})小时后", text)
        if match is None:
            return None

        hours = self._parse_chinese_number(match.group(1))
        if hours is None:
            return None

        target = base_time + timedelta(hours=hours)
        return self._finalize_exact_result(text, target, base_time)

    def _parse_weekday_expression(
        self,
        text: str,
        base_time: datetime,
        timezone: ZoneInfo,
    ) -> datetime | None:
        match = re.fullmatch(
            r"(?:(本周|下周)(?:周|星期)?|(?:周|星期))([一二三四五六日天])(.*)",
            text,
        )
        if match is None:
            return None

        prefix, weekday, _ = match.groups()
        target_date = self._resolve_weekday_date(prefix, weekday, base_time)
        hour_minute = self._extract_hour_minute(text)
        if hour_minute is None:
            candidate = datetime.combine(target_date, time.min, tzinfo=timezone)
        else:
            hour, minute = hour_minute
            period = self._extract_period(text)
            hour = self._normalize_hour(hour, period)
            candidate = datetime.combine(
                target_date,
                time(hour=hour, minute=minute),
                tzinfo=timezone,
            )

        if prefix is None and candidate < base_time:
            candidate = candidate + timedelta(days=7)

        return candidate

    def _resolve_weekday_date(
        self,
        prefix: str | None,
        weekday: str,
        base_time: datetime,
    ) -> date:
        base_date = base_time.date()
        weekday_index = WEEKDAY_MAP[weekday]

        if prefix == "本周":
            start_of_week = base_date - timedelta(days=base_date.weekday())
            return start_of_week + timedelta(days=weekday_index)

        if prefix == "下周":
            start_of_week = base_date - timedelta(days=base_date.weekday()) + timedelta(days=7)
            return start_of_week + timedelta(days=weekday_index)

        delta_days = (weekday_index - base_date.weekday()) % 7
        return base_date + timedelta(days=delta_days)

    def _is_ambiguous_expression(self, text: str) -> bool:
        return any(word in text for word in AMBIGUOUS_EXPRESSIONS)

    def _finalize_exact_result(
        self,
        text: str,
        value: datetime,
        base_time: datetime,
    ) -> TimeParseResult:
        is_past = value < base_time
        return TimeParseResult(
            raw_text=text,
            success=True,
            datetime=value,
            need_followup=is_past,
            is_past=is_past,
            missing_slots=["confirm_time"] if is_past else [],
            reason="parsed_time_in_past" if is_past else None,
        )

    def _parse_by_rules(
        self,
        text: str,
        base_time: datetime,
        timezone: ZoneInfo,
    ) -> datetime | None:
        day_offset = self._extract_day_offset(text)
        has_explicit_day = self._has_explicit_day_marker(text)
        hour_minute = self._extract_hour_minute(text)

        if text in DAY_OFFSETS:
            return datetime.combine(
                (base_time + timedelta(days=day_offset)).date(),
                time.min,
                tzinfo=timezone,
            )

        if hour_minute is None:
            return None

        hour, minute = hour_minute
        period = self._extract_period(text)
        hour = self._normalize_hour(hour, period)
        target_date = (base_time + timedelta(days=day_offset)).date()
        candidate = datetime.combine(
            target_date,
            time(hour=hour, minute=minute),
            tzinfo=timezone,
        )

        if not has_explicit_day and candidate < base_time:
            candidate = candidate + timedelta(days=1)

        return candidate

    def _extract_day_offset(self, text: str) -> int:
        for word, offset in DAY_OFFSETS.items():
            if word in text:
                return offset
        return 0

    def _has_explicit_day_marker(self, text: str) -> bool:
        if any(word in text for word in DAY_OFFSETS):
            return True
        if any(prefix in text for prefix in WEEK_PREFIXES):
            return True
        return False

    def _extract_period(self, text: str) -> str | None:
        for period in PERIOD_HOURS:
            if period in text:
                return period
        return None

    def _needs_followup_for_fuzzy_period(self, text: str) -> bool:
        if not any(period in text for period in FUZZY_TIME_WORDS):
            return False
        return self._extract_hour_minute(text) is None

    def _extract_hour_minute(self, text: str) -> tuple[int, int] | None:
        match = re.search(r"([零〇一二两三四五六七八九十\d]{1,3})点(半|[零〇一二两三四五六七八九十\d]{1,3}分?)?", text)
        if match is None:
            return None

        hour = self._parse_chinese_number(match.group(1))
        minute_text = match.group(2)
        minute = 0

        if minute_text == "半":
            minute = 30
        elif minute_text:
            minute = self._parse_chinese_number(minute_text.removesuffix("分"))

        if hour is None or minute is None:
            return None

        if not (0 <= hour <= 24 and 0 <= minute <= 59):
            return None

        if hour == 24:
            hour = 0

        return hour, minute

    def _parse_chinese_number(self, value: str) -> int | None:
        if value.isdigit():
            return int(value)

        if value == "十":
            return 10

        if "十" in value:
            left, _, right = value.partition("十")
            tens = 1 if left == "" else CHINESE_DIGITS.get(left)
            ones = 0 if right == "" else CHINESE_DIGITS.get(right)
            if tens is None or ones is None:
                return None
            return tens * 10 + ones

        total = 0
        for char in value:
            digit = CHINESE_DIGITS.get(char)
            if digit is None:
                return None
            total = total * 10 + digit
        return total

    def _normalize_hour(self, hour: int, period: str | None) -> int:
        if period in {"下午", "晚上", "今晚", "夜里"} and 1 <= hour <= 11:
            return hour + 12

        if period == "中午" and 1 <= hour <= 10:
            return hour + 12

        return hour

    def _get_timezone(self, timezone: str) -> ZoneInfo:
        try:
            return ZoneInfo(timezone)
        except Exception:
            named_offset = self._parse_named_timezone_fallback(timezone)
            if named_offset is not None:
                return named_offset
            offset = self._parse_fixed_offset_timezone(timezone)
            if offset is not None:
                return offset
            return ZoneInfo("UTC")

    def _parse_named_timezone_fallback(self, value: str) -> datetime.tzinfo | None:
        normalized = value.strip().lower()
        if normalized in {"asia/shanghai", "asia/chongqing", "asia/urumqi", "cst", "utc+8", "utc+08", "utc+08:00", "gmt+8", "gmt+08", "gmt+08:00"}:
            return fixed_timezone(timedelta(hours=8), name=value.strip())
        if normalized in {"utc", "gmt", "z"}:
            return fixed_timezone(timedelta(0), name=value.strip())
        return None

    def _parse_fixed_offset_timezone(self, value: str) -> datetime.tzinfo | None:
        match = re.fullmatch(r"(?:(?:UTC|GMT)\s*)?([+-])(\d{1,2})(?::?(\d{2}))?", value.strip(), re.IGNORECASE)
        if match is None:
            return None

        sign, hours_text, minutes_text = match.groups()
        hours = int(hours_text)
        minutes = int(minutes_text) if minutes_text else 0
        if hours > 14 or minutes >= 60:
            return None

        delta = timedelta(hours=hours, minutes=minutes)
        if sign == "-":
            delta = -delta
        return fixed_timezone(delta, name=value.strip())

    def _ensure_timezone(self, value: datetime, timezone: ZoneInfo) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            return value.replace(tzinfo=timezone)
        return value.astimezone(timezone)
