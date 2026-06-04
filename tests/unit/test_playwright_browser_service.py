import asyncio
from types import SimpleNamespace

import pytest

import src.services.browser.playwright_service as playwright_service
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


@pytest.mark.asyncio
async def test_extract_nickname_falls_back_to_http_verification(monkeypatch):
    service = PlaywrightBrowserService(None)
    calls = {}

    class FakePlugin:
        async def extract_user_info(self, context):
            return SimpleNamespace(nickname=None)

    async def fake_verify_login_status(**kwargs):
        calls.update(kwargs)
        return {
            "is_valid": True,
            "is_logged_in": True,
            "username": "real_nickname",
        }

    monkeypatch.setattr(playwright_service, "USE_PLUGIN_SYSTEM", True)
    monkeypatch.setattr(
        playwright_service.PluginManager,
        "get_login_plugin",
        lambda platform: FakePlugin(),
    )
    monkeypatch.setattr(
        playwright_service,
        "verify_login_status",
        fake_verify_login_status,
    )

    nickname = await service._extract_nickname(
        context=object(),
        platform="xiaohongshu",
        cookies={"access-token-creator.xiaohongshu.com": "token"},
        account_id=21,
        account_name="profile_ab9612ae9785",
    )

    assert nickname == "real_nickname"
    assert calls["platform"] == "xiaohongshu"
    assert calls["account_id"] == 21
    assert calls["timeout"] == 12


@pytest.mark.asyncio
async def test_xhs_publish_blocks_when_detached_chrome_profile_is_running(monkeypatch, tmp_path):
    class FakeAccountManager:
        async def get_account_by_id(self, account_id):
            return {
                "id": account_id,
                "platform": "xiaohongshu",
                "platform_username": "xhs_user",
                "profile_folder_name": "profile_xhs",
            }

        async def ensure_account_has_profile_folder(self, account_id):
            return True

    service = PlaywrightBrowserService(FakeAccountManager())

    monkeypatch.setattr(
        "src.infrastructure.browser.detached_chrome_launcher.DetachedChromeLauncher.get_user_data_dir",
        lambda **kwargs: tmp_path,
    )
    monkeypatch.setattr(
        "src.infrastructure.browser.detached_chrome_launcher.DetachedChromeLauncher.find_profile_process",
        lambda _path: 12345,
    )

    with pytest.raises(RuntimeError, match="普通 Chrome 窗口仍在运行"):
        await service.open_browser_for_db_account(1, publish_mode=True)
