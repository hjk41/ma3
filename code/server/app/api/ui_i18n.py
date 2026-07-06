"""SSR UI internationalization for the ma3 user portal."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from app.core.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES = ("zh-CN", "en-US")
DEFAULT_LOCALE = "zh-CN"
LOCALE_COOKIE = "ma3_locale"
_I18N_DIR = Path(__file__).resolve().parent / "i18n"


class _SafeDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def normalize_locale(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip().replace("_", "-")
    lower = raw.lower()
    if lower in {"zh", "zh-cn", "zh-hans", "zh-hans-cn"}:
        return "zh-CN"
    if lower == "en" or lower.startswith("en-"):
        return "en-US"
    if raw in SUPPORTED_LOCALES:
        return raw
    return None


def parse_accept_language(value: str | None) -> str | None:
    if not value:
        return None
    candidates: list[tuple[float, str]] = []
    for part in value.split(","):
        chunk = part.strip()
        if not chunk:
            continue
        if ";q=" in chunk:
            tag, q = chunk.split(";q=", 1)
            try:
                weight = float(q.strip())
            except ValueError:
                weight = 0.0
        else:
            tag = chunk
            weight = 1.0
        normalized = normalize_locale(tag.strip())
        if normalized:
            candidates.append((weight, normalized))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


@lru_cache
def catalog(locale: str) -> dict[str, Any]:
    path = _I18N_DIR / f"{locale}.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def tr(locale: str, key: str, **params: Any) -> str:
    loc = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    value = catalog(loc).get(key)
    if value is None and loc != DEFAULT_LOCALE:
        value = catalog(DEFAULT_LOCALE).get(key)
    if value is None:
        logger.warning("missing i18n key: %s (locale=%s)", key, loc)
        return f"[[{key}]]"
    if isinstance(value, dict):
        logger.warning("i18n key %s is plural object; use tr_count()", key)
        value = value.get("other") or value.get("one") or f"[[{key}]]"
    text = str(value)
    if params:
        return text.format_map(_SafeDict(params))
    return text


def tr_count(locale: str, key: str, count: int, **params: Any) -> str:
    loc = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    value = catalog(loc).get(key)
    if value is None and loc != DEFAULT_LOCALE:
        value = catalog(DEFAULT_LOCALE).get(key)
    if isinstance(value, dict):
        branch = "one" if count == 1 and loc == "en-US" else "other"
        text = str(value.get(branch) or value.get("other") or value.get("one") or f"[[{key}]]")
    elif value is None:
        logger.warning("missing i18n key: %s (locale=%s)", key, loc)
        text = f"[[{key}]]"
    else:
        text = str(value)
    merged = {"count": count, **params}
    return text.format_map(_SafeDict(merged))


def resolve_locale(request: Request) -> str:
    query_lang = normalize_locale(request.query_params.get("lang"))
    if query_lang:
        return query_lang
    cookie_lang = normalize_locale(request.cookies.get(LOCALE_COOKIE))
    if cookie_lang:
        return cookie_lang
    header_lang = parse_accept_language(request.headers.get("accept-language"))
    if header_lang:
        return header_lang
    return DEFAULT_LOCALE


def locale_switch_url(request: Request, target_locale: str) -> str:
    parsed = urlparse(str(request.url))
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if target_locale == DEFAULT_LOCALE:
        params.pop("lang", None)
    else:
        params["lang"] = target_locale
    query = urlencode(params)
    return urlunparse(parsed._replace(query=query))


def set_locale_cookie(response: Response, locale: str, request: Request) -> None:
    secure = (
        str(request.url.scheme).lower() == "https"
        or (settings.public_base_url or "").startswith("https://")
    )
    response.set_cookie(
        LOCALE_COOKIE,
        locale,
        max_age=31536000,
        samesite="lax",
        httponly=False,
        secure=secure,
    )


def maybe_set_locale_cookie(response: Response, request: Request, locale: str) -> None:
    if request.query_params.get("lang") is not None:
        normalized = normalize_locale(request.query_params.get("lang"))
        if normalized:
            set_locale_cookie(response, normalized, request)


def get_translator(request: Request) -> Callable[..., str]:
    locale = resolve_locale(request)
    return lambda key, **params: tr(locale, key, **params)


def ui_locale(request: Request) -> tuple[str, Callable[..., str]]:
    locale = resolve_locale(request)
    return locale, lambda key, **params: tr(locale, key, **params)


def html_response(request: Request, html: str, *, status_code: int = 200) -> HTMLResponse:
    response = HTMLResponse(html, status_code=status_code)
    maybe_set_locale_cookie(response, request, resolve_locale(request))
    return response


def render_locale_switcher(request: Request, locale: str) -> str:
    from app.api.ui_theme import esc

    if locale == "en-US":
        label = tr(locale, "shell.locale.switch_zh")
        href = locale_switch_url(request, "zh-CN")
    else:
        label = tr(locale, "shell.locale.switch_en")
        href = locale_switch_url(request, "en-US")
    return f'<a href="{esc(href)}">{esc(label)}</a>'
