from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.plugins.pro.xiaohongshu.browser_environment_diagnostics import (
    attach_xhs_environment_snapshot,
    collect_xhs_browser_environment,
)
from src.plugins.pro.xiaohongshu.publish_failure_diagnostics import (
    capture_xiaohongshu_extras,
)

pytestmark = pytest.mark.unit


class _FakeContext:
    async def cookies(self, url: str):
        assert "xiaohongshu.com" in url
        return [
            {
                "name": "customer-sso-sid",
                "value": "secret-session-value",
                "domain": ".xiaohongshu.com",
                "path": "/",
                "expires": 123,
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            }
        ]


class _FakeLocator:
    @property
    def first(self):
        return self

    async def count(self):
        return 0


class _FakePage:
    url = "https://creator.xiaohongshu.com/publish/publish"
    context = _FakeContext()

    def locator(self, selector: str):
        return _FakeLocator()

    async def evaluate(self, script, *args):
        return {
            "url": self.url,
            "navigator": {
                "userAgent": "Mozilla/5.0 Chrome/122.0.0.0",
                "webdriver": False,
                "languages": ["zh-CN", "zh"],
            },
            "viewport": {
                "innerWidth": 1280,
                "innerHeight": 720,
                "outerWidth": 1280,
                "outerHeight": 800,
            },
            "webgl": {"unmaskedRenderer": "ANGLE (Intel, UHD Graphics)"},
            "riskPrompts": [{"keyword": "自动化", "snippet": "疑似自动化软件发布"}],
        }


@pytest.mark.asyncio
async def test_collect_xhs_environment_omits_cookie_values() -> None:
    snapshot = await collect_xhs_browser_environment(
        _FakePage(),
        {
            "_diagnostic_context": {
                "browser_launch": {
                    "headless": False,
                    "strict_real_browser": True,
                    "user_data_dir": "D:/profiles/profile_1",
                }
            }
        },
        stage="pre_manual_submit",
    )

    encoded = json.dumps(snapshot, ensure_ascii=False)
    assert "secret-session-value" not in encoded
    assert snapshot["cookies"][0]["name"] == "customer-sso-sid"
    assert "value" not in snapshot["cookies"][0]
    assert snapshot["launch_context"]["strict_real_browser"] is True


@pytest.mark.asyncio
async def test_attach_xhs_environment_snapshot_tracks_timeline() -> None:
    metadata: dict = {}

    await attach_xhs_environment_snapshot(metadata, _FakePage(), stage="before_upload")
    await attach_xhs_environment_snapshot(metadata, _FakePage(), stage="pre_manual_submit")

    ctx = metadata["_diagnostic_context"]
    assert ctx["xhs_environment_snapshot"]["stage"] == "pre_manual_submit"
    assert [s["stage"] for s in ctx["xhs_environment_snapshots"]] == [
        "before_upload",
        "pre_manual_submit",
    ]


@pytest.mark.asyncio
async def test_xhs_failure_diagnostics_writes_environment_snapshot(tmp_path: Path) -> None:
    metadata = {}

    extra = await capture_xiaohongshu_extras(
        _FakePage(),
        tmp_path,
        metadata,
        step_name="SubmitStep",
        reason="manual submit timeout",
        page_url=_FakePage.url,
    )

    env_path = tmp_path / "xhs_environment_snapshot.json"
    assert env_path.is_file()
    data = json.loads(env_path.read_text(encoding="utf-8"))
    assert data["cookies"][0]["name"] == "customer-sso-sid"
    assert "value" not in data["cookies"][0]
    assert extra["xhs_environment_webdriver"] is False
    assert extra["xhs_environment_risk_prompt_keywords"] == ["自动化"]

