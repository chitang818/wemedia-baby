"""
浏览器启动策略单元测试
验证：
- 启动策略默认值与选项
- ignore_default_args 中必须包含 --disable-blink-features=AutomationControlled
- real_browser 模式注入 stealth_minimal.js（P0 优化：消除基础 JS 泄漏）
- compat_stealth 模式注入全量 stealth.js（含 webdriver 等 navigator 属性伪造）
"""

from __future__ import annotations

import pytest

from src.infrastructure.browser import browser_launch_policy
from src.infrastructure.browser.browser_manager import (
    UndetectedBrowserManager,
    build_patchright_default_args_to_ignore,
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
            "canvas_noise_seed": 99999,
            "timezone_id": "Asia/Shanghai",
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


def test_strict_real_browser_ignores_unsupported_automation_controlled_arg() -> None:
    """新版 Chrome 稳定版已不支持 --disable-blink-features=AutomationControlled，
    必须加入 ignore_default_args 阻止 Patchright 自动注入，消除黄色警告横幅。"""
    ignored = build_patchright_default_args_to_ignore(strict_real_browser=True)

    assert "--enable-automation" in ignored
    assert "--no-sandbox" in ignored
    assert "--disable-popup-blocking" in ignored
    assert "--disable-blink-features=AutomationControlled" in ignored


def test_non_strict_browser_ignores_unsupported_automation_controlled_arg() -> None:
    """navigator.webdriver 的隐藏由 stealth JS 脚本注入负责，不依赖此命令行标记。"""
    ignored = build_patchright_default_args_to_ignore(strict_real_browser=False)

    assert "--disable-blink-features=AutomationControlled" in ignored


@pytest.mark.asyncio
async def test_real_browser_mode_injects_minimal_stealth(monkeypatch) -> None:
    """P0 优化：real_browser 默认模式现在也会注入 stealth_minimal.js，
    消除 webdriver、焦点、插件列表等基础 JS 泄漏，而不是完全跳过注入。
    """
    monkeypatch.setattr(browser_launch_policy, "get_app_config_for_read", lambda: {})
    manager = _new_manager()
    manager.context = _FakeContext()  # type: ignore

    await manager._inject_stealth_scripts()

    # real_browser 模式现在应该注入 stealth_minimal.js，而非空列表
    assert len(manager.context.scripts) == 1  # type: ignore
    # 验证注入的是 stealth_minimal.js 内容（含 webdriver 隐藏、native toString 伪装）
    injected = manager.context.scripts[0]  # type: ignore
    assert "webdriver" in injected
    assert "__makeNativeGetter" in injected


@pytest.mark.asyncio
async def test_compat_stealth_mode_injects_full_stealth(monkeypatch) -> None:
    """compat_stealth 模式注入全量 stealth.js，
    包含 navigator.webdriver 伪造、Canvas 噪声、UA-CH 等完整指纹防护。
    同时验证新增的 native-toString 工厂函数和时区、媒体 ID 等参数化内容。
    """
    monkeypatch.setattr(
        browser_launch_policy,
        "get_app_config_for_read",
        lambda: {"browser_trust_mode": BROWSER_TRUST_MODE_COMPAT_STEALTH},
    )
    manager = _new_manager()
    manager.context = _FakeContext()  # type: ignore
    manager.profile_manager = _FakeProfileManager()  # type: ignore

    await manager._inject_stealth_scripts()

    assert len(manager.context.scripts) == 1  # type: ignore
    injected = manager.context.scripts[0]  # type: ignore
    # 验证全量 stealth.js 关键内容
    # 新版 stealth.js 使用 _nativeGetter('webdriver', undefined) 工厂函数形式
    assert "webdriver" in injected
    # 验证 P0 方向二：makeNativeGetter 工厂函数已注入（核心改进）
    assert "__makeNativeGetter" in injected
    # 验证 P1 方向六：时区占位符已被替换为实际数值（-480 对应 Asia/Shanghai）
    assert "__TIMEZONE_OFFSET__" not in injected
    assert "-480" in injected
    # 验证 P1 方向四：媒体设备 ID 占位符已被替换为确定性 UUID
    assert "__MEDIA_AUDIO_IN_ID__" not in injected


@pytest.mark.asyncio
async def test_strict_real_browser_also_injects_minimal_stealth(monkeypatch) -> None:
    """strict_real_browser（小红书等）平台同样注入 stealth_minimal.js，
    确保即使是最严格的真实浏览器模式也有基础的 webdriver 防护。
    """
    monkeypatch.setattr(
        browser_launch_policy,
        "get_app_config_for_read",
        lambda: {"browser_trust_mode": BROWSER_TRUST_MODE_COMPAT_STEALTH},
    )
    manager = _new_manager(platform="xiaohongshu")  # 小红书为 strict_real_browser
    manager.context = _FakeContext()  # type: ignore
    manager.profile_manager = _FakeProfileManager()  # type: ignore

    await manager._inject_stealth_scripts()

    # 小红书 strict_real_browser 走 _inject_minimal_stealth，不注入全量 stealth
    assert len(manager.context.scripts) == 1  # type: ignore
    injected = manager.context.scripts[0]  # type: ignore
    # 应注入 minimal 版本（含 webdriver/CDP 痕迹清理），而非全量版本
    assert "webdriver" in injected
