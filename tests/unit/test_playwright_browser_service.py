import asyncio

import pytest

from src.services.browser.playwright_service import PlaywrightBrowserService


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", 1),
        ("2", 2),
        ("20", 8),
        ("bad", 2),
    ],
)
def test_browser_launch_concurrency_env(monkeypatch, raw, expected):
    monkeypatch.setenv("WMB_BROWSER_LAUNCH_CONCURRENCY", raw)

    assert PlaywrightBrowserService._read_browser_launch_concurrency() == expected


@pytest.mark.asyncio
async def test_open_browser_for_account_uses_launch_semaphore(monkeypatch):
    service = PlaywrightBrowserService(None)
    service._browser_launch_semaphore = asyncio.Semaphore(1)
    running = 0
    max_running = 0

    async def fake_open(**kwargs):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.01)
        running -= 1

    monkeypatch.setattr(service, "_open_browser_base", fake_open)

    await asyncio.gather(
        service.open_browser_for_account(
            account_id=1,
            platform_username="a",
            platform="douyin",
            platform_url="about:blank",
        ),
        service.open_browser_for_account(
            account_id=2,
            platform_username="b",
            platform="douyin",
            platform_url="about:blank",
        ),
    )

    assert max_running == 1
