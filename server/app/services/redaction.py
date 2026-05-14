import re
from typing import Any

RedactionMode = str


WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s'\"<>|]+")
UNIX_PATH_RE = re.compile(r"(?<!\w)/(?:home|root|usr|etc|var|opt|tmp|srv|mnt)/[^\s'\"<>|]+")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|session|access[_-]?key|private[_-]?key)\b\s*[:=]\s*([^\s,;\"']+)"
)
# Common secret formats: GitHub PATs, AWS keys, generic long hex/base64 tokens
GITHUB_TOKEN_RE = re.compile(r"\bghp_[A-Za-z0-9]{36,}\b")
AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
LONG_HEX_RE = re.compile(r"\b[0-9a-fA-F]{40,}\b")


def _mode(value: RedactionMode | None) -> str:
    return value if value in {"auto", "contextual", "none"} else "auto"


def redact_text(
    text: str,
    mode: RedactionMode | None = "auto",
    allow_secret_preservation: bool = False,
) -> str:
    effective_mode = _mode(mode)
    if effective_mode == "auto":
        text = WINDOWS_PATH_RE.sub("<redacted_path>", text)
        text = UNIX_PATH_RE.sub("<redacted_path>", text)
        text = EMAIL_RE.sub("<redacted_email>", text)
        text = IPV4_RE.sub("<redacted_ip>", text)
    if effective_mode != "none" or not allow_secret_preservation:
        text = GITHUB_TOKEN_RE.sub("<redacted_token>", text)
        text = AWS_KEY_RE.sub("<redacted_aws_key>", text)
        text = LONG_HEX_RE.sub("<redacted_token>", text)
        text = SECRET_ASSIGNMENT_RE.sub(r"\1=<redacted_secret>", text)
    return text


def redact_value(
    value: Any,
    mode: RedactionMode | None = "auto",
    allow_secret_preservation: bool = False,
) -> Any:
    if isinstance(value, str):
        return redact_text(value, mode=mode, allow_secret_preservation=allow_secret_preservation)
    if isinstance(value, list):
        return [
            redact_value(item, mode=mode, allow_secret_preservation=allow_secret_preservation)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: redact_value(item, mode=mode, allow_secret_preservation=allow_secret_preservation)
            for key, item in value.items()
        }
    return value
