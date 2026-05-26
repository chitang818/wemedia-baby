from __future__ import annotations

import pytest

from src.plugins.community.douyin.steps.step_05_cover_video import CoverVideoStep


class _FakeLocator:
    def __init__(self, visible: bool = True, name: str = "") -> None:
        self._visible = visible
        self._name = name
        self.clicked = False

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def count(self) -> int:
        return 1 if self._visible else 0

    async def is_visible(self) -> bool:
        return self._visible

    async def click(self) -> None:
        self.clicked = True

    def locator(self, _selector: str) -> "_FakeLocator":
        return _FakeLocator(visible=False, name=f"child:{self._name}")


class _FakeModal(_FakeLocator):
    def __init__(self) -> None:
        super().__init__(visible=True, name="modal")
        self.title = _FakeLocator(visible=True, name="title")
        self.set_vertical = _FakeLocator(visible=True, name="set_vertical")
        self.close = _FakeLocator(visible=True, name="close")
        self.skip = _FakeLocator(visible=True, name="skip")
        self.x_btn = _FakeLocator(visible=True, name="x_btn")

    def get_by_text(self, text: str) -> _FakeLocator:
        if text == "设置竖封面获更多流量":
            return self.title
        return _FakeLocator(visible=False, name=f"text:{text}")

    def get_by_role(self, role: str, name: str | None = None) -> _FakeLocator:
        if role == "button" and name == "设置竖封面":
            return self.set_vertical
        if role == "button" and name == "暂不设置":
            return self.skip
        return _FakeLocator(visible=False, name=f"role:{role}:{name}")

    def get_by_label(self, label: str) -> _FakeLocator:
        if label == "关闭":
            return self.close
        return _FakeLocator(visible=False, name=f"label:{label}")

    def locator(self, selector: str) -> _FakeLocator:
        # 兜底分支不会走到，这里仅保证接口完整
        return _FakeLocator(visible=False, name=f"selector:{selector}")


class _FakeGroup:
    def __init__(self, modal: _FakeModal) -> None:
        self._modal = modal

    async def count(self) -> int:
        return 1

    def nth(self, _idx: int) -> _FakeModal:
        return self._modal


class _FakePage:
    def __init__(self, modal: _FakeModal) -> None:
        self._modal = modal

    def locator(self, _selector: str) -> _FakeGroup:
        return _FakeGroup(self._modal)


@pytest.mark.asyncio
async def test_vertical_promo_prefers_set_vertical_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """出现竖封面引导弹窗时，应优先点击「设置竖封面」而不是关闭/暂不设置。"""
    step = CoverVideoStep()
    modal = _FakeModal()
    page = _FakePage(modal)

    async def _always_hidden(_page: object, _locator: object, timeout_ms: int = 2000) -> bool:
        return True

    monkeypatch.setattr(step, "_wait_locator_hidden", _always_hidden)

    handled = await step._dismiss_vertical_cover_promo_if_present(page)  # pylint: disable=protected-access

    assert handled is True
    assert modal.set_vertical.clicked is True
    assert modal.close.clicked is False
    assert modal.skip.clicked is False

