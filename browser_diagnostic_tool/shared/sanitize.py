"""Sanitization helpers for diagnostic snapshots."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .constants import SENSITIVE_KEYWORDS

COOKIE_SAFE_FIELDS = ("name", "domain", "path", "expires", "httpOnly", "secure", "sameSite")
REDACTED = "***REDACTED***"


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_KEYWORDS)


def sanitize_cookie_list(cookies: Any) -> list[dict[str, Any]]:
    """Return cookie metadata without values or auth-bearing fields."""

    if not isinstance(cookies, Sequence) or isinstance(cookies, (str, bytes, bytearray)):
        return []
    sanitized: list[dict[str, Any]] = []
    for item in cookies:
        if not isinstance(item, Mapping):
            continue
        sanitized.append({field: item.get(field) for field in COOKIE_SAFE_FIELDS if field in item})
    return sanitized


def redact_sensitive(value: Any) -> Any:
    """Recursively redact sensitive values while preserving report shape."""

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, child in value.items():
            key_str = str(key)
            if key_str == "cookies":
                out[key_str] = sanitize_cookie_list(child)
            elif _is_sensitive_key(key_str):
                if key_str in COOKIE_SAFE_FIELDS:
                    out[key_str] = child
                else:
                    out[key_str] = REDACTED
            else:
                out[key_str] = redact_sensitive(child)
        return out
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    return value


def contains_forbidden_secret_fields(value: Any) -> bool:
    """Return True if a structure still contains obvious secret-bearing fields."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            key_str = str(key).lower()
            if key_str in {"value", "authorization", "access_token", "refresh_token"}:
                if child != REDACTED:
                    return True
            if contains_forbidden_secret_fields(child):
                return True
    elif isinstance(value, list):
        return any(contains_forbidden_secret_fields(item) for item in value)
    return False
