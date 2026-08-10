"""Small in-process per-key sliding-window rate limiter."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from threading import Lock

_windows: dict[str, list[float]] = {}
_lock = Lock()


def _timestamp(now: datetime | None) -> float:
    return (now or datetime.now(timezone.utc)).timestamp()


def check_rate_limit(api_key_id: str, *, rpm: int, now: datetime | None = None) -> dict[str, int | bool]:
    current = _timestamp(now)
    limit = max(1, int(rpm))
    with _lock:
        window = [stamp for stamp in _windows.get(api_key_id, []) if stamp > current - 60]
        if len(window) >= limit:
            retry_after = max(1, math.ceil(60 - (current - window[0])))
            _windows[api_key_id] = window
            return {"allowed": False, "retry_after": retry_after}
        window.append(current)
        _windows[api_key_id] = window
    return {"allowed": True, "retry_after": 0}


def reset() -> None:
    with _lock:
        _windows.clear()
