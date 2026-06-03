from __future__ import annotations

from browser_diagnostic_tool.shared.sanitize import (
    contains_forbidden_secret_fields,
    redact_sensitive,
    sanitize_cookie_list,
)


def test_sanitize_cookie_list_omits_cookie_values() -> None:
    cookies = [
        {
            "name": "sid",
            "value": "secret",
            "domain": ".example.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }
    ]

    clean = sanitize_cookie_list(cookies)

    assert clean == [
        {
            "name": "sid",
            "domain": ".example.com",
            "path": "/",
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax",
        }
    ]
    assert "value" not in clean[0]


def test_redact_sensitive_nested_values() -> None:
    data = {
        "headers": {"Authorization": "Bearer abc"},
        "cookies": [{"name": "a1", "value": "secret", "domain": ".x.test"}],
        "page": {"title": "ok"},
    }

    clean = redact_sensitive(data)

    assert clean["headers"]["Authorization"] == "***REDACTED***"
    assert clean["cookies"][0] == {"name": "a1", "domain": ".x.test"}
    assert not contains_forbidden_secret_fields(clean)

