from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any


UNKNOWN_INTENT = "unknown"


@dataclass(slots=True)
class NLUResult:
    intent: str
    confidence: float
    slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)
    raw_text: str = ""


class NLUService:
    def parse(self, text: str) -> NLUResult:
        normalized_text = self._normalize(text)
        if not normalized_text:
            return NLUResult(
                intent=UNKNOWN_INTENT,
                confidence=0.0,
                missing_slots=["text"],
                raw_text=text,
            )

        intent, confidence = self._detect_intent(normalized_text)
        slots = self._extract_slots(normalized_text, intent)
        missing_slots = self._detect_missing_slots(intent, slots)

        return NLUResult(
            intent=intent,
            confidence=confidence,
            slots=slots,
            missing_slots=missing_slots,
            raw_text=text,
        )

    def _detect_intent(self, text: str) -> tuple[str, float]:
        if self._contains_any(text, ["帮助", "怎么用", "你能做什么", "使用说明", "help"]):
            return "help", 0.95

        if self._contains_any(text, ["撤销", "退回", "恢复上一步", "上一步撤回"]):
            return "undo", 0.95

        if self._is_confirm(text):
            return "confirm", 0.95

        if self._is_deny(text):
            return "deny", 0.95

        if self._contains_any(text, ["取消提醒", "关闭提醒", "不要提醒", "不用提醒", "提醒取消"]):
            return "cancel_reminder", 0.9

        if self._contains_any(text, ["提醒我", "叫我", "到时候提醒", "设置提醒", "加个提醒"]):
            return "create_reminder", 0.88

        if self._contains_any(text, ["删除", "删掉", "删了", "不要了", "取消日程", "取消安排"]):
            return "delete_event", 0.88

        if self._contains_any(text, ["改到", "换成", "提前到", "推迟到", "改成", "调整到", "延期到"]):
            return "update_event", 0.88

        if self._contains_any(text, ["今天有什么", "明天有什么", "后天有什么", "查一下", "查下", "查询", "看看", "有哪些安排", "有什么安排"]):
            return "query_event", 0.86

        if "安排" in text:
            if self._contains_any(text, ["有什么", "哪些", "查询", "查一下", "查下", "看看"]):
                return "query_event", 0.82
            return "create_event", 0.78

        if self._contains_any(text, ["添加", "新增", "创建", "新建", "记一下", "帮我安排"]):
            return "create_event", 0.84

        return UNKNOWN_INTENT, 0.0

    def _extract_slots(self, text: str, intent: str) -> dict[str, Any]:
        slots: dict[str, Any] = {}

        time_text = self._extract_time_text(text)
        if time_text:
            slots["time_text"] = time_text

        title = self._extract_title(text, intent, time_text)
        if title:
            slots["title"] = title

        if intent in {"delete_event", "update_event", "cancel_reminder"}:
            target_text = self._extract_target_text(text)
            if target_text:
                slots["target_text"] = target_text

        return slots

    def _detect_missing_slots(self, intent: str, slots: dict[str, Any]) -> list[str]:
        if intent == UNKNOWN_INTENT:
            return ["intent"]

        required_slots = {
            "create_event": ["title", "time_text"],
            "query_event": [],
            "update_event": ["target_text", "time_text"],
            "delete_event": ["target_text"],
            "create_reminder": ["title", "time_text"],
            "cancel_reminder": ["target_text"],
            "confirm": [],
            "deny": [],
            "undo": [],
            "help": [],
        }

        return [slot for slot in required_slots.get(intent, []) if slot not in slots]

    def _extract_time_text(self, text: str) -> str | None:
        patterns = [
            r"(今天|明天|后天|本周[一二三四五六日天]|下周[一二三四五六日天]|周[一二三四五六日天])(?:上午|下午|晚上|中午)?[零〇一二两三四五六七八九十\d]{0,3}点?半?",
            r"(上午|下午|晚上|中午)[零〇一二两三四五六七八九十\d]{1,3}点半?",
            r"[零〇一二两三四五六七八九十\d]{1,3}小时后",
            r"半小时后",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match is not None:
                return match.group(0)
        return None

    def _extract_title(
        self,
        text: str,
        intent: str,
        time_text: str | None,
    ) -> str | None:
        if intent not in {"create_event", "create_reminder"}:
            return None

        cleaned = text
        for word in ["提醒我", "添加", "新增", "创建", "新建", "安排", "帮我安排", "设置提醒", "加个提醒", "记一下", "叫我"]:
            cleaned = cleaned.replace(word, "")
        if time_text:
            cleaned = cleaned.replace(time_text, "")
        cleaned = cleaned.strip(" ，,。.!！")
        return cleaned or None

    def _extract_target_text(self, text: str) -> str | None:
        cleaned = text
        for word in ["删除", "删掉", "删了", "取消日程", "取消安排", "取消提醒", "关闭提醒", "不要提醒", "不用提醒", "不要了", "改到", "换成", "提前到", "推迟到", "改成", "调整到", "延期到"]:
            cleaned = cleaned.replace(word, " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。.!！")
        return cleaned or None

    def _is_confirm(self, text: str) -> bool:
        return text in {"确认", "是的", "对", "对的", "可以", "好的", "没错", "确定"}

    def _is_deny(self, text: str) -> bool:
        return text in {"不用了", "取消", "不是", "不对", "不要", "算了", "否", "不用"}

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _normalize(self, text: str) -> str:
        return re.sub(r"\s+", "", text.strip().lower())
