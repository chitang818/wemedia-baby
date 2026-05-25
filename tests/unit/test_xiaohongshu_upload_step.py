from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.plugins.pro.xiaohongshu.selectors import Selectors
from src.plugins.pro.xiaohongshu.steps.step_03_upload import UploadMediaStep


class _FakeLocator:
    def __init__(self, page: "_FakePage", selector: str):
        self._page = page
        self._selector = selector
        self.first = self

    async def count(self) -> int:
        if self._page.raise_on_locator:
            raise RuntimeError("locator failed")
        return 1 if self._selector in self._page.visible_selectors else 0

    async def is_visible(self) -> bool:
        if self._page.raise_on_locator:
            raise RuntimeError("visibility failed")
        return self._selector in self._page.visible_selectors


class _FakePage:
    def __init__(self) -> None:
        self.visible_selectors: set[str] = set()
        self.waits: list[int] = []
        self.raise_on_locator = False
        self.js_reupload_ok = False
        self.js_reupload_ok_after_evals = 0
        self.js_eval_count = 0
        self.js_shell_ready = True
        self.js_shell_skeleton = 0

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self, selector)

    async def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(ms)

    async def evaluate(self, script: str, *_args, **_kwargs) -> dict:
        if "publish-video-container" in script or "no_video_file_label" in script:
            self.js_eval_count += 1
            ok = self.js_reupload_ok
            if self.js_reupload_ok_after_evals > 0:
                ok = self.js_eval_count >= self.js_reupload_ok_after_evals
            if ok:
                return {"ok": True, "reason": "reupload_in_video_card"}
            return {"ok": False, "reason": "reupload_not_in_video_card"}
        return {
            "skeletonCount": self.js_shell_skeleton,
            "hasVideoFile": self.js_shell_ready,
            "hasUploadVideo": self.js_shell_ready,
            "progressText": False,
            "ready": self.js_shell_ready and self.js_shell_skeleton < 3,
        }


@pytest.mark.asyncio
async def test_xiaohongshu_video_upload_js_fast_path_skips_soft_wait(monkeypatch) -> None:
    marker = "div:has-text('视频文件') button:has-text('重新上传')"
    monkeypatch.setitem(Selectors.PUBLISH, "VIDEO_UPLOAD_SUCCESS_MARKER", [marker])

    page = _FakePage()
    page.js_reupload_ok = True
    step = UploadMediaStep()
    soft_wait = AsyncMock()
    monkeypatch.setattr(step, "_soft_ensure_publish_form_ready", soft_wait)

    result = await step._wait_for_upload_complete(
        page,
        {"upload_timeout_seconds": 1, "speed_rate": 1.0},
    )

    assert result is None
    soft_wait.assert_not_called()


@pytest.mark.asyncio
async def test_xiaohongshu_video_upload_js_succeeds_on_second_poll(monkeypatch) -> None:
    marker = "div:has-text('视频文件') button:has-text('重新上传')"
    monkeypatch.setitem(Selectors.PUBLISH, "VIDEO_UPLOAD_SUCCESS_MARKER", [marker])

    page = _FakePage()
    page.js_reupload_ok_after_evals = 2

    result = await UploadMediaStep()._wait_for_upload_complete(
        page,
        {"upload_timeout_seconds": 2, "speed_rate": 1.0},
    )

    assert result is None
    assert page.js_eval_count >= 2
    assert len(page.waits) >= 1


@pytest.mark.asyncio
async def test_xiaohongshu_video_upload_succeeds_when_reupload_visible(monkeypatch) -> None:
    marker = "div:has-text('视频文件') button:has-text('重新上传')"
    monkeypatch.setitem(Selectors.PUBLISH, "VIDEO_UPLOAD_SUCCESS_MARKER", [marker])
    monkeypatch.setitem(Selectors.PUBLISH, "REUPLOAD_BTN", ["button:has-text('重新上传')"])

    page = _FakePage()
    page.visible_selectors.add(marker)
    page.js_reupload_ok = True

    result = await UploadMediaStep()._wait_for_upload_complete(
        page,
        {"upload_timeout_seconds": 1, "speed_rate": 0.5},
    )

    assert result is None
    assert page.waits == []


@pytest.mark.asyncio
async def test_xiaohongshu_video_upload_ignores_preview_without_reupload(monkeypatch) -> None:
    reupload_marker = "div:has-text('视频文件') button:has-text('重新上传')"
    preview_marker = "div[class*='preview']"
    monkeypatch.setitem(Selectors.PUBLISH, "VIDEO_UPLOAD_SUCCESS_MARKER", [reupload_marker])
    monkeypatch.setitem(Selectors.PUBLISH, "REUPLOAD_BTN", ["button:has-text('重新上传')"])
    monkeypatch.setitem(Selectors.PUBLISH, "UPLOAD_SUCCESS_MARKER", [preview_marker])

    page = _FakePage()
    page.visible_selectors.add(preview_marker)

    result = await UploadMediaStep()._wait_for_upload_complete(
        page,
        {"upload_timeout_seconds": 1, "speed_rate": 0.5},
    )

    assert result is not None
    assert result.success is False
    assert "重新上传" in (result.error_message or "")


@pytest.mark.asyncio
async def test_xiaohongshu_ensure_publish_form_ready_waits_for_shell(monkeypatch) -> None:
    monkeypatch.setitem(Selectors.PUBLISH, "PUBLISH_FORM_READY", ["text=视频文件"])
    page = _FakePage()
    page.js_shell_ready = False
    page.js_shell_skeleton = 6

    async def _flip_ready() -> None:
        if page.waits:
            page.js_shell_ready = True
            page.js_shell_skeleton = 0
            page.visible_selectors.add("text=视频文件")

    original_wait = page.wait_for_timeout

    async def _wait(ms: int) -> None:
        await original_wait(ms)
        await _flip_ready()

    page.wait_for_timeout = _wait  # type: ignore[method-assign]

    result = await UploadMediaStep()._ensure_publish_form_ready(
        page,
        {"publish_form_ready_timeout_seconds": 2, "speed_rate": 0.5},
        phase="上传前",
    )

    assert result is None


@pytest.mark.asyncio
async def test_xiaohongshu_video_upload_reports_missing_success_selectors(monkeypatch) -> None:
    monkeypatch.setitem(Selectors.PUBLISH, "VIDEO_UPLOAD_SUCCESS_MARKER", [])

    page = _FakePage()

    result = await UploadMediaStep()._wait_for_upload_complete(
        page,
        {"upload_timeout_seconds": 1, "speed_rate": 0.5},
    )

    assert result is not None
    assert result.success is False
    assert "选择器未配置" in (result.error_message or "")
    assert result.failed_step == "步骤3 上传"
    assert page.waits == []


@pytest.mark.asyncio
async def test_xiaohongshu_video_upload_selector_without_js_confirmation_times_out(monkeypatch) -> None:
    marker = "div:has-text('视频文件') button:has-text('重新上传')"
    monkeypatch.setitem(Selectors.PUBLISH, "VIDEO_UPLOAD_SUCCESS_MARKER", [marker])

    page = _FakePage()
    page.visible_selectors.add(marker)
    page.js_reupload_ok = False

    result = await UploadMediaStep()._wait_for_upload_complete(
        page,
        {"upload_timeout_seconds": 1, "speed_rate": 0.5},
    )

    assert result is not None
    assert result.success is False
    assert "重新上传" in (result.error_message or "")


def test_xiaohongshu_upload_match_confirmed_for_js_and_marker() -> None:
    marker = "div:has-text('视频文件') button:has-text('重新上传')"
    assert UploadMediaStep._upload_match_confirmed("js:reupload_in_video_card")
    assert UploadMediaStep._upload_match_confirmed(marker)
    assert not UploadMediaStep._upload_match_confirmed("div[class*='preview']")


@pytest.mark.asyncio
async def test_xiaohongshu_video_upload_locator_errors_timeout_without_crashing(monkeypatch) -> None:
    marker = "div:has-text('视频文件') button:has-text('重新上传')"
    monkeypatch.setitem(Selectors.PUBLISH, "VIDEO_UPLOAD_SUCCESS_MARKER", [marker])

    page = _FakePage()
    page.raise_on_locator = True

    result = await UploadMediaStep()._wait_for_upload_complete(
        page,
        {"upload_timeout_seconds": 1, "speed_rate": 0.5},
    )

    assert result is not None
    assert result.success is False
    assert "重新上传" in (result.error_message or "")
