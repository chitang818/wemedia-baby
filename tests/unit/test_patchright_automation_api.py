from __future__ import annotations

import tempfile

import pytest
from patchright.async_api import TimeoutError as PatchrightTimeoutError

from src.infrastructure.browser import automation_api
from src.infrastructure.browser.automation_api import async_playwright, expect
from src.infrastructure.browser.browser_manager import (
    build_patchright_default_args_to_ignore,
)
from tests.helpers.patchright_env import patchright_page_or_skip


def test_automation_api_exports_patchright_runtime() -> None:
    assert automation_api.ENGINE_NAME == "patchright"
    assert automation_api.async_playwright.__module__.startswith("patchright.")
    assert automation_api.TimeoutError is PatchrightTimeoutError


@pytest.mark.asyncio
async def test_automation_api_expect_accepts_patchright_locator() -> None:
    async with patchright_page_or_skip() as page:
        await page.set_content("<button>Publish</button>")
        locator = page.get_by_role("button", name="Publish")
        assert isinstance(locator, automation_api.Locator)
        await expect(locator).to_be_visible()


@pytest.mark.asyncio
async def test_patchright_timeout_uses_automation_api_error_type() -> None:
    async with patchright_page_or_skip() as page:
        with pytest.raises(automation_api.TimeoutError):
            await page.locator("#missing").wait_for(timeout=10)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_project_launch_policy_keeps_webdriver_hidden() -> None:
    with tempfile.TemporaryDirectory(prefix="wmb-patchright-test-") as profile_dir:
        async with async_playwright() as patchright:
            context = await patchright.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",
                headless=False,
                no_viewport=True,
                args=["--window-position=-32000,-32000"],
                ignore_default_args=build_patchright_default_args_to_ignore(),
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                fingerprint = await page.evaluate(
                    """() => ({
                        webdriver: navigator.webdriver,
                        userAgent: navigator.userAgent,
                        hasChrome: Boolean(window.chrome),
                    })"""
                )
            finally:
                await context.close()

    assert fingerprint["webdriver"] is False
    assert fingerprint["hasChrome"] is True
    assert "Playwright" not in fingerprint["userAgent"]
    assert "Patchright" not in fingerprint["userAgent"]
