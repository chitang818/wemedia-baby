"""Unified Patchright browser automation API.

Production browser automation must import from this module instead of
``playwright.async_api`` so Patchright is the only runtime engine.
"""

from __future__ import annotations

try:
    from patchright.async_api import (
        Browser,
        BrowserContext,
        Locator,
        Page,
        Playwright,
        TimeoutError,
        async_playwright,
        expect,
    )
except ImportError as exc:  # pragma: no cover - depends on installation state
    raise RuntimeError(
        "Patchright is required for WeMediaBaby browser automation. "
        "Install dependencies with `pip install -r requirements.txt`."
    ) from exc

ENGINE_NAME = "patchright"
_START_PATCHRIGHT = async_playwright


async def start_patchright() -> Playwright:
    """Start the required Patchright runtime."""
    return await _START_PATCHRIGHT().start()

__all__ = [
    "Browser",
    "BrowserContext",
    "ENGINE_NAME",
    "Locator",
    "Page",
    "Playwright",
    "TimeoutError",
    "async_playwright",
    "expect",
    "start_patchright",
]
