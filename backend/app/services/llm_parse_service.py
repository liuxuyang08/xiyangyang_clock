from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import os
import re
from typing import Any

try:  # pragma: no cover - optional dependency in stripped local environments
    import httpx
except ImportError:  # pragma: no cover - graceful fallback when httpx is absent
    httpx = None

def _load_openai_api_key() -> str:
    try:
        from app.core.config import get_settings
    except Exception:
        return os.getenv("OPENAI_API_KEY", "")

    try:
        return getattr(get_settings(), "openai_api_key", "") or os.getenv("OPENAI_API_KEY", "")
    except Exception:
        return os.getenv("OPENAI_API_KEY", "")


LLM_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"


@dataclass(slots=True)
class LLMParseResult:
    raw_text: str
    intent: str
    confidence: float
    slots: dict[str, Any] = field(default_factory=dict)
    missing_slots: list[str] = field(default_factory=list)


class LLMParseService:
    """增强能力：LLM 只负责结构化解析，不执行任何业务操作。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        client: Any | None = None,
        timeout: float = 12.0,
    ) -> None:
        self.api_key = api_key or _load_openai_api_key()
        self.model = model
        self.client = client
        self.timeout = timeout

    def parse(
        self,
        text: str,
        *,
        conversation_context: Any | None = None,
        base_time: datetime | None = None,
        timezone: str = "Asia/Shanghai",
    ) -> LLMParseResult | None:
        normalized_text = text.strip()
        if not normalized_text or not self.api_key:
            return None

        if self.client is None and httpx is None:
            return None

        payload = self._request_structured_parse(
            text=normalized_text,
            conversation_context=conversation_context,
            base_time=base_time,
            timezone=timezone,
        )
        if payload is None:
            return None

        return self._coerce_result(normalized_text, payload)

    def _request_structured_parse(
        self,
        *,
        text: str,
        conversation_context: Any | None,
        base_time: datetime | None,
        timezone: str,
    ) -> dict[str, Any] | None:
        request_body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": self._build_messages(
                text=text,
                conversation_context=conversation_context,
                base_time=base_time,
                timezone=timezone,
            ),
        }

        try:
            if self.client is not None:
                response = self.client.post(
                    LLM_API_URL,
                    headers=self._headers(),
                    json=request_body,
                    timeout=self.timeout,
                )
            else:
                assert httpx is not None  # for type-checking and runtime safety
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        LLM_API_URL,
                        headers=self._headers(),
                        json=request_body,
                    )
            response.raise_for_status()
            response_payload = response.json()
        except Exception:
            return None

        try:
            content = response_payload["choices"][0]["message"]["content"]
        except Exception:
            return None

        if not isinstance(content, str):
            return None

        return self._parse_json_content(content)

    def _build_messages(
        self,
        *,
        text: str,
        conversation_context: Any | None,
        base_time: datetime | None,
        timezone: str,
    ) -> list[dict[str, str]]:
        context_json = json.dumps(
            conversation_context,
            ensure_ascii=False,
            default=str,
        ) if conversation_context is not None else "null"

        request_json = json.dumps(
            {
                "text": text,
                "base_time": base_time.isoformat() if base_time is not None else None,
                "timezone": timezone,
                "conversation_context": conversation_context,
                "output_schema": {
                    "intent": "string",
                    "confidence": "number",
                    "slots": "object",
                    "missing_slots": "array",
                },
                "allowed_intents": [
                    "create_event",
                    "query_event",
                    "update_event",
                    "delete_event",
                    "create_reminder",
                    "cancel_reminder",
                    "confirm",
                    "deny",
                    "undo",
                    "help",
                    "unknown",
                ],
                "slot_hints": [
                    "title",
                    "date_text",
                    "time_text",
                    "start_time",
                    "end_time",
                    "location",
                    "participants",
                    "reminder_offset_minutes",
                    "recurrence_text",
                    "target_event",
                ],
            },
            ensure_ascii=False,
            default=str,
        )

        return [
            {
                "role": "system",
                "content": (
                    "你是一个中文日历语音命令的结构化解析器。"
                    "你只负责抽取结构化字段，不执行任何业务操作，不给出业务决策。"
                    "请只输出 JSON 对象，不要输出额外解释。"
                    "输出必须包含 intent、confidence、slots、missing_slots。"
                    "confidence 为 0 到 1 之间的小数。"
                    "slots 中优先提取 title、date_text、time_text、start_time、end_time、location、participants、reminder_offset_minutes、recurrence_text、target_event。"
                    "可以结合 conversation_context 理解当前对话上下文，但不要编造不存在的信息。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请根据下面的输入返回结构化 JSON：\n"
                    f"{context_json}\n"
                    "输入内容：\n"
                    f"{request_json}"
                ),
            },
        ]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _parse_json_content(self, content: str) -> dict[str, Any] | None:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.removeprefix("json").strip()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if match is None:
                return None
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

        if not isinstance(payload, dict):
            return None

        return payload

    def _coerce_result(
        self,
        raw_text: str,
        payload: dict[str, Any],
    ) -> LLMParseResult | None:
        intent = str(payload.get("intent", "unknown")).strip() or "unknown"
        confidence = self._coerce_confidence(payload.get("confidence"))

        slots = payload.get("slots")
        if not isinstance(slots, dict):
            slots = {}

        missing_slots = payload.get("missing_slots")
        if not isinstance(missing_slots, list):
            missing_slots = []

        return LLMParseResult(
            raw_text=raw_text,
            intent=intent,
            confidence=confidence,
            slots=slots,
            missing_slots=[str(item) for item in missing_slots if item is not None],
        )

    def _coerce_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except Exception:
            return 0.0

        if confidence < 0:
            return 0.0
        if confidence > 1:
            return 1.0
        return confidence
