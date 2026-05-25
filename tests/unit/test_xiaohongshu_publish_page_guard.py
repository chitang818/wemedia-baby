from __future__ import annotations

import pytest

from src.plugins.pro.xiaohongshu.steps.publish_page_guard import (
    clean_publish_url,
    ensure_publish_page_without_file_picker,
    strip_open_file_picker_from_url,
    url_has_auto_file_picker,
)


def test_url_has_auto_file_picker_detects_param() -> None:
    url = (
        "https://creator.xiaohongshu.com/publish/publish?"
        "from=homepage&target=video&source=official&openFilePicker=true"
    )
    assert url_has_auto_file_picker(url) is True
    assert url_has_auto_file_picker(clean_publish_url("video")) is False


def test_strip_open_file_picker_from_url() -> None:
    dirty = (
        "https://creator.xiaohongshu.com/publish/publish?"
        "from=homepage&target=video&source=official&openFilePicker=true"
    )
    cleaned = strip_open_file_picker_from_url(dirty, file_type="video")
    assert "openFilePicker" not in cleaned
    assert "openfilepicker" not in cleaned.lower()
    assert "target=video" in cleaned
    assert "source=official" in cleaned


def test_clean_publish_url_matches_step2_direct_nav() -> None:
    assert clean_publish_url("video") == (
        "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video"
    )
    assert clean_publish_url("image") == (
        "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=image"
    )


class _FakeKeyboard:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def press(self, key: str) -> None:
        self.keys.append(key)


class _FakePage:
    def __init__(self, url: str) -> None:
        self._url = url
        self.keyboard = _FakeKeyboard()
        self.gotos: list[str] = []
        self.waits: list[int] = []

    @property
    def url(self) -> str:
        return self._url

    async def goto(self, url: str, **kwargs) -> None:
        self.gotos.append(url)
        self._url = url

    async def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(ms)


@pytest.mark.asyncio
async def test_ensure_publish_page_without_file_picker_navigates_and_escapes() -> None:
    dirty = (
        "https://creator.xiaohongshu.com/publish/publish?"
        "from=homepage&target=video&openFilePicker=true"
    )
    page = _FakePage(dirty)

    result = await ensure_publish_page_without_file_picker(page, "video", {"speed_rate": 0.5})

    assert result is None
    assert page.keyboard.keys == ["Escape", "Escape"]
    assert len(page.gotos) == 1
    assert "openFilePicker" not in page.gotos[0]
    assert page.url == clean_publish_url("video")


@pytest.mark.asyncio
async def test_ensure_publish_page_noop_when_url_clean() -> None:
    clean = clean_publish_url("video")
    page = _FakePage(clean)

    result = await ensure_publish_page_without_file_picker(page, "video", {})

    assert result is None
    assert page.gotos == []
    assert page.keyboard.keys == []
