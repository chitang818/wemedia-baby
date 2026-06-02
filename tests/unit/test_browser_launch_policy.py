from __future__ import annotations

import pytest

from src.infrastructure.browser import browser_launch_policy
from src.infrastructure.browser.browser_manager import (
    UndetectedBrowserManager,
    build_playwright_default_args_to_ignore,
)
from src.infrastructure.common.config.app_config_keys import (
    BROWSER_TRUST_MODE_COMPAT_STEALTH,
    BROWSER_TRUST_MODE_REAL,
)


class _FakeContext:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    async def add_init_script(self, script: str) -> None:
        self.scripts.append(script)


class _FakeProfileManager:
    def get_fingerprint(self):
        return {
            "hardware_concurrency": 8,
            "device_memory": 16,
            "webgl_vendor": "Google Inc. (NVIDIA)",
            "webgl_renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
            "screen_width": 1920,
            "screen_height": 1080,
            "screen_avail_width": 1920,
            "screen_avail_height": 1040,
            "screen_color_depth": 24,
            "screen_pixel_depth": 24,
            "platform": "Win32",
            "max_touch_points": 0,
            "vendor": "Google Inc.",
            "vendor_sub": "",
            "product_sub": "20030107",
            "languages": ["zh-CN", "zh", "en"],
            "ua_ch": {},
        }


def test_browser_launch_policy_defaults_to_real_browser(monkeypatch) -> None:
    monkeypatch.setattr(browser_launch_policy, "get_app_config_for_read", lambda: {})

    policy = browser_launch_policy.get_browser_launch_policy()

    assert policy.trust_mode == BROWSER_TRUST_MODE_REAL
    assert policy.use_real_browser is True
    assert policy.use_compat_stealth is False
    assert policy.force_visible_publish is True


def test_browser_launch_policy_accepts_compat_stealth(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_launch_policy,
        "get_app_config_for_read",
        lambda: {"browser_trust_mode": BROWSER_TRUST_MODE_COMPAT_STEALTH},
    )

    policy = browser_launch_policy.get_browser_launch_policy()

    assert policy.use_compat_stealth is True


def test_strict_real_browser_keeps_automation_controlled_launch_arg() -> None:
    ignored = build_playwright_default_args_to_ignore(strict_real_browser=True)

    assert "--enable-automation" in ignored
    assert "--disable-blink-features=AutomationControlled" not in ignored


def test_non_strict_browser_ignores_automation_controlled_launch_arg() -> None:
    ignored = build_playwright_default_args_to_ignore(strict_real_browser=False)

    assert "--disable-blink-features=AutomationControlled" in ignored


@pytest.mark.asyncio
async def test_real_browser_mode_skips_stealth_injection(monkeypatch) -> None:
    monkeypatch.setattr(browser_launch_policy, "get_app_config_for_read", lambda: {})
    manager = UndetectedBrowserManager.__new__(UndetectedBrowserManager)
    manager.platform = "douyin"
    manager.context = _FakeContext()

    await manager._inject_stealth_scripts()

    assert manager.context.scripts == []


@pytest.mark.asyncio
async def test_compat_stealth_mode_keeps_legacy_injection(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_launch_policy,
        "get_app_config_for_read",
        lambda: {"browser_trust_mode": BROWSER_TRUST_MODE_COMPAT_STEALTH},
    )
    manager = UndetectedBrowserManager.__new__(UndetectedBrowserManager)
    manager.platform = "douyin"
    manager.context = _FakeContext()
    manager.profile_manager = _FakeProfileManager()

    await manager._inject_stealth_scripts()

    assert len(manager.context.scripts) == 1
    assert 'navigator, "webdriver"' in manager.context.scripts[0]
