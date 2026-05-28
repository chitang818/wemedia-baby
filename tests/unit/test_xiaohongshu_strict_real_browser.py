from __future__ import annotations

import pytest

from src.infrastructure.browser.browser_manager import UndetectedBrowserManager
from src.plugins.pro.xiaohongshu.steps import step_08_submit


class _FakeContext:
    def __init__(self) -> None:
        self.add_init_script_called = False

    async def add_init_script(self, _script: str) -> None:
        self.add_init_script_called = True


@pytest.mark.asyncio
async def test_xiaohongshu_strict_browser_skips_stealth_injection() -> None:
    manager = UndetectedBrowserManager.__new__(UndetectedBrowserManager)
    manager.platform = "xiaohongshu"
    manager.context = _FakeContext()

    await manager._inject_stealth_scripts()

    assert manager.context.add_init_script_called is False


def test_xiaohongshu_submit_defaults_to_manual_in_strict_mode() -> None:
    metadata = {}

    assert step_08_submit._xhs_strict_real_browser_enabled(metadata) is True
    assert step_08_submit._xhs_auto_click_submit_enabled(metadata) is False


@pytest.mark.asyncio
async def test_xiaohongshu_strict_submit_uses_mouse_not_shadow_js(monkeypatch) -> None:
    calls = {}

    class FakeLocator:
        async def bounding_box(self):
            return {"x": 10, "y": 20, "width": 100, "height": 40}

        async def click(self, *args, **kwargs):
            raise AssertionError("locator.click must not be used in strict mode")

    async def fake_mouse_click(page, x, y, metadata, config, *, desc=""):
        calls["mouse"] = {
            "page": page,
            "x": x,
            "y": y,
            "metadata": metadata,
            "config": config,
            "desc": desc,
        }
        return True

    async def fake_sr_click(*args, **kwargs):
        raise AssertionError("_sr click must not be used in strict mode")

    monkeypatch.setattr(step_08_submit, "_simulate_mouse_click_at", fake_mouse_click)
    monkeypatch.setattr(step_08_submit, "_click_xhs_publish_via_sr", fake_sr_click)

    await step_08_submit._click_submit_with_fallback(
        page=object(),
        target_btn=FakeLocator(),
        metadata={"xhs_strict_real_browser": True},
        config={},
        target_desc="xhs-publish-btn/_sr",
        primary_label="发布",
        strict_real_browser=True,
    )

    assert calls["mouse"]["x"] == 60
    assert calls["mouse"]["y"] == 40
