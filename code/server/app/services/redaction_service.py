from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bsk-proj-[A-Za-z0-9_-]{10,}\b"), "[REDACTED:api_key]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), "[REDACTED:api_key]"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "[REDACTED:token]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED:token]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED:aws_key]"),
    (re.compile(r"\bma3v4_[A-Za-z0-9_-]{16,}\b"), "[REDACTED:api_key]"),
    (re.compile(r"\bma3k_[A-Za-z0-9_-]{16,}\b"), "[REDACTED:api_key]"),
    (re.compile(r"\bma3mcp_[A-Za-z0-9_-]{16,}\b"), "[REDACTED:token]"),
    (re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s\"']+"), r"\1[REDACTED:token]"),
    (re.compile(r'(?i)"password"\s*:\s*"[^"]+"'), '"password": "[REDACTED:password]"'),
    (re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s\"',]+"), r"\1[REDACTED:api_key]"),
    (re.compile(r"(?i)(password\s*[=:]\s*)[^\s\"',]+"), r"\1[REDACTED:password]"),
    (re.compile(r"(?i)(secret\s*[=:]\s*)[^\s\"',]+"), r"\1[REDACTED:secret]"),
    (re.compile(r"https?://[^/\s:@]+:[^@\s/]+@"), "https://[REDACTED:credentials]@"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "[REDACTED:jwt]"),
)


def redact_text(text: str) -> str:
    out = text
    for pattern, repl in _SECRET_PATTERNS:
        out = pattern.sub(repl, out)
    return out


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item) for key, item in value.items()}
    return value


def redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return redact_value(deepcopy(payload))
