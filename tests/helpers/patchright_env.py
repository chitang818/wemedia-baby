from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from src.infrastructure.browser.automation_api import async_playwright


def is_patchright_driver_environment_error(exc: Exception) -> bool:
    """Return True for local sandbox/permission failures before test logic runs."""
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "connection closed while reading from the driver" in text
        or ("eperm" in text and "lstat" in text)
    )


@asynccontextmanager
async def patchright_page_or_skip(
    *,
    viewport: dict[str, int] | None = None,
    headless: bool = True,
) -> AsyncIterator[Any]:
    patchright_cm = async_playwright()
    try:
        patchright = await patchright_cm.__aenter__()
    except Exception as exc:
        if is_patchright_driver_environment_error(exc):
            pytest.skip(f"Patchright driver unavailable in this environment: {exc}")
        raise

    browser = None
    try:
        try:
            browser = await patchright.chromium.launch(
                channel="chrome",
                headless=headless,
            )
        except Exception as exc:
            if is_patchright_driver_environment_error(exc):
                pytest.skip(f"Patchright browser unavailable in this environment: {exc}")
            raise
        page = await browser.new_page(viewport=viewport)
        yield page
    finally:
        if browser is not None:
            await browser.close()
        await patchright_cm.__aexit__(None, None, None)
