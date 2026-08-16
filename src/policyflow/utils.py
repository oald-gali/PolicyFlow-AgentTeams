from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


TRACE_GENESIS_HASH = hashlib.sha256(b"policyflow-trace-genesis/v1").hexdigest()


SENSITIVE_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "invoice_number",
    "phone",
    "token",
}


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def trace_event_hash(event: Any) -> str:
    if isinstance(event, BaseModel):
        payload = event.model_dump(mode="json", exclude={"event_hash"})
    else:
        payload = dict(event)
        payload.pop("event_hash", None)
    return sha256_text(canonical_json(payload))


def verify_trace_chain(events: list[Any]) -> tuple[bool, str | None, str]:
    previous_hash = TRACE_GENESIS_HASH
    for index, event in enumerate(events):
        payload = event.model_dump(mode="json") if isinstance(event, BaseModel) else event
        if payload.get("previous_hash") != previous_hash:
            return False, f"trace event {index} has an invalid previous_hash", previous_hash
        if payload.get("event_hash") != trace_event_hash(event):
            return False, f"trace event {index} has an invalid event_hash", previous_hash
        previous_hash = payload["event_hash"]
    return True, None, previous_hash


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    digest = sha256_text("|".join(canonical_json(part) for part in parts))[:length]
    return f"{prefix}_{digest}"


def redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(part in lowered for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if lowered == "employee_id" and isinstance(value, str):
        return f"{value[:4]}***{value[-2:]}" if len(value) > 6 else "[REDACTED]"
    if "email" in lowered and isinstance(value, str) and "@" in value:
        local, domain = value.split("@", 1)
        return f"{local[:1]}***@{domain}"
    if isinstance(value, str):
        value = re.sub(r"(?i)bearer\s+[a-z0-9._-]+", "Bearer [REDACTED]", value)
        value = re.sub(r"(?<!\d)1\d{10}(?!\d)", "1**********", value)
    return value


def redact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            result[key] = redact_mapping(item)
        elif isinstance(item, list):
            result[key] = [redact_mapping(v) if isinstance(v, dict) else redact_value(key, v) for v in item]
        else:
            result[key] = redact_value(key, item)
    return result


def contains_prompt_injection(text: str) -> bool:
    normalized = text.casefold()
    markers = (
        "ignore previous",
        "ignore all rules",
        "system prompt",
        "绕过审批",
        "忽略制度",
        "忽略规则",
        "不要审计",
        "直接调用工具",
    )
    return any(marker in normalized for marker in markers)
