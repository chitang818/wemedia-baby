from __future__ import annotations

import pytest

from src.plugins.pro.xiaohongshu.steps.step_03_upload import UploadMediaStep


class _Locator:
    def __init__(self) -> None:
        self.scrolled = False

    @property
    def first(self):
        return self

    async def count(self) -> int:
        return 1

    async def scroll_into_view_if_needed(self) -> None:
        self.scrolled = True


class _Page:
    def __init__(self) -> None:
        self.target = _Locator()

    def locator(self, selector: str) -> _Locator:
        return self.target


@pytest.mark.asyncio
async def test_upload_preparation_only_scrolls_target_into_view() -> None:
    page = _Page()

    await UploadMediaStep()._hover_before_upload(page, "#upload", {})

    assert page.target.scrolled is True
