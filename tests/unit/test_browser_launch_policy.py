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


def _new_manager(platform: str = "douyin") -> UndetectedBrowserManager:
    manager = UndetectedBrowserManager.__new__(UndetectedBrowserManager)
    manager.platform = platform
    return manager


def test_strict_real_browser_filters_automation_controlled_default_arg() -> None:
    ignored = build_playwright_default_args_to_ignore(strict_real_browser=True)

    assert "--enable-automation" in ignored
    assert "--no-sandbox" in ignored
    assert "--disable-popup-blocking" in ignored
    assert "--disable-blink-features=AutomationControlled" in ignored


def test_non_strict_browser_ignores_automation_controlled_launch_arg() -> None:
    ignored = build_playwright_default_args_to_ignore(strict_real_browser=False)

    assert "--disable-blink-features=AutomationControlled" in ignored


def test_real_browser_launch_args_skip_legacy_stealth_flags() -> None:
    manager = _new_manager()

    args = manager._get_launch_args(compat_stealth=False)

    assert "--start-maximized" in args
    assert "--no-first-run" in args
    assert "--disable-session-crashed-bubble" in args
    assert "--disable-dev-shm-usage" not in args
    assert "--webrtc-ip-handling-policy=default_public_interface_only" not in args
    assert "--disable-webrtc-hw-encoding" not in args
    assert "--disable-webrtc-hw-decoding" not in args
    assert "--disable-infobars" not in args
    assert "--disable-blink-features=AutomationControlled" not in args
    assert "--no-sandbox" not in args


def test_compat_stealth_launch_args_keep_legacy_flags() -> None:
    manager = _new_manager()

    args = manager._get_launch_args(compat_stealth=True)

    assert "--disable-dev-shm-usage" in args
    assert "--webrtc-ip-handling-policy=default_public_interface_only" in args
    assert "--disable-webrtc-hw-encoding" in args
    assert "--disable-webrtc-hw-decoding" in args
    assert "--start-maximized" in args
    assert "--no-first-run" in args
    assert "--disable-blink-features=AutomationControlled" not in args


def test_publishing_mode_disallows_no_sandbox_fallback() -> None:
    manager = _new_manager()

    assert (
        manager._get_no_sandbox_fallback_args(
            compat_stealth=False,
            publishing=True,
        )
        is None
    )


def test_non_publish_no_sandbox_fallback_keeps_mode_specific_args() -> None:
    manager = _new_manager()

    real_args = manager._get_no_sandbox_fallback_args(
        compat_stealth=False,
        publishing=False,
    )
    legacy_args = manager._get_no_sandbox_fallback_args(
        compat_stealth=True,
        publishing=False,
    )

    assert real_args is not None
    assert real_args[0] == "--no-sandbox"
    assert "--webrtc-ip-handling-policy=default_public_interface_only" not in real_args
    assert legacy_args is not None
    assert legacy_args[0] == "--no-sandbox"
    assert "--webrtc-ip-handling-policy=default_public_interface_only" in legacy_args


@pytest.mark.asyncio
async def test_real_browser_mode_skips_stealth_injection(monkeypatch) -> None:
    monkeypatch.setattr(browser_launch_policy, "get_app_config_for_read", lambda: {})
    manager = _new_manager()
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
    manager = _new_manager()
    manager.context = _FakeContext()
    manager.profile_manager = _FakeProfileManager()

    await manager._inject_stealth_scripts()

    assert len(manager.context.scripts) == 1
    assert 'navigator, "webdriver"' in manager.context.scripts[0]
