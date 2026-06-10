"""浏览器启动策略单元测试。"""

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


def test_browser_launch_policy_is_fixed_to_visible_real_browser(monkeypatch) -> None:
    monkeypatch.setattr(
        browser_launch_policy,
        "get_app_config_for_read",
        lambda: {"browser_trust_mode": BROWSER_TRUST_MODE_COMPAT_STEALTH},
    )

    policy = browser_launch_policy.get_browser_launch_policy()

    assert policy.trust_mode == BROWSER_TRUST_MODE_REAL
    assert policy.use_real_browser is True
    assert policy.use_compat_stealth is False
    assert policy.force_visible_publish is True
    assert policy.respect_platform_interval is False
    assert policy.stop_on_risk_prompt is True


def test_standard_chrome_does_not_replace_patchright_default_args() -> None:
    assert build_patchright_default_args_to_ignore(strict_real_browser=True) == []
    assert build_patchright_default_args_to_ignore(strict_real_browser=False) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["douyin", "xiaohongshu", "wechat_video"])
async def test_all_platforms_skip_stealth_injection(platform: str) -> None:
    manager = UndetectedBrowserManager.__new__(UndetectedBrowserManager)
    manager.platform = platform
    manager.context = _FakeContext()  # type: ignore

    await manager._inject_stealth_scripts()

    assert manager.context.scripts == []  # type: ignore
