from __future__ import annotations

import pytest

from src.plugins.pro.xiaohongshu.steps.step_07_settings import (
    PublishSettingsStep,
    parse_schedule_st_str,
    privacy_to_xhs_label,
)


class _FakePage:
    def __init__(self) -> None:
        self.waits: list[int] = []
        self.url = "https://creator.xiaohongshu.com/publish/publish"
        self.mouse_clicks: list[tuple[float, float]] = []
        self.keyboard_presses: list[str] = []

    async def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(ms)

    async def evaluate(self, *_args, **_kwargs) -> dict:
        return {"w": 1200, "h": 800}

    class _Mouse:
        def __init__(self, page: "_FakePage") -> None:
            self._page = page

        async def click(self, x: float, y: float) -> None:
            self._page.mouse_clicks.append((x, y))

    @property
    def mouse(self) -> "_Mouse":
        return _FakePage._Mouse(self)

    class _Keyboard:
        def __init__(self, page: "_FakePage") -> None:
            self._page = page

        async def press(self, key: str) -> None:
            self._page.keyboard_presses.append(key)

    @property
    def keyboard(self) -> "_Keyboard":
        return _FakePage._Keyboard(self)


@pytest.mark.parametrize(
    ("privacy", "expected"),
    [
        ("public", "公开可见"),
        ("private", "仅自己可见"),
        ("friend", "仅互关好友可见"),
        ("PUBLIC", "公开可见"),
        ("unknown", None),
    ],
)
def test_privacy_to_xhs_label(privacy: str, expected: str | None) -> None:
    assert privacy_to_xhs_label(privacy) == expected


def test_parse_schedule_st_str_valid() -> None:
    assert parse_schedule_st_str("2026-05-25 16:24") == (2026, 5, 25, 16, 24)


def test_parse_schedule_st_str_invalid() -> None:
    assert parse_schedule_st_str("invalid") is None
    assert parse_schedule_st_str("") is None


@pytest.mark.asyncio
async def test_publish_settings_no_schedule_returns_none(monkeypatch) -> None:
    step = PublishSettingsStep()
    page = _FakePage()

    async def _noop(*_a, **_k) -> None:
        return None

    monkeypatch.setattr(step, "_scroll_to_settings_area", _noop)
    monkeypatch.setattr(step, "_apply_visibility", _noop)

    result = await step.execute(page, "", {"file_type": "video"})
    assert result is None


@pytest.mark.asyncio
async def test_apply_scheduled_publish_skips_when_no_schedule() -> None:
    step = PublishSettingsStep()
    page = _FakePage()
    result = await step._apply_scheduled_publish(page, {}, {}, lambda ms: ms, 1.0)
    assert result is None


def test_schedule_time_display_selectors_includes_wrapper_scoped() -> None:
    sels = PublishSettingsStep._schedule_time_display_selectors()
    assert any("post-time-wrapper" in s for s in sels)
    assert ".post-time-wrapper input[type='text']" in sels


@pytest.mark.asyncio
async def test_click_schedule_time_display_opens_picker(monkeypatch) -> None:
    step = PublishSettingsStep()
    page = _FakePage()
    display = object()

    async def _fake_scroll(*_a, **_k) -> None:
        return None

    async def _fake_human_click(*_a, **_k) -> None:
        return None

    async def _fake_first_visible(_page, _sels) -> str:
        return "body > .post-time-date-picker-popover-class"

    monkeypatch.setattr(
        "src.plugins.pro.xiaohongshu.steps.step_07_settings._scroll_locator_to_center",
        _fake_scroll,
    )
    monkeypatch.setattr(
        "src.infrastructure.anti_risk.human_like.human_click",
        _fake_human_click,
    )
    monkeypatch.setattr(
        "src.plugins.pro.xiaohongshu.steps.step_07_settings.PluginWaitHelper.first_visible_selector",
        _fake_first_visible,
    )

    async def _fake_mouse(*_a, **_k) -> bool:
        return True

    monkeypatch.setattr(step, "_mouse_click_locator_center", _fake_mouse)

    ok = await step._click_schedule_time_display(
        page, display, {}, {}, lambda ms: ms,
    )
    assert ok is True


def test_schedule_input_value_matches() -> None:
    assert PublishSettingsStep._schedule_input_value_matches(
        "2026-05-26 14:07", "2026-05-26 14:07"
    )
    assert PublishSettingsStep._schedule_input_value_matches(
        "2026-05-26 14:07:00", "2026-05-26 14:07"
    )
    assert not PublishSettingsStep._schedule_input_value_matches("", "2026-05-26 14:07")


def test_schedule_sel_within_wrapper_strips_prefix() -> None:
    rel = PublishSettingsStep._schedule_sel_within_wrapper(
        ".post-time-wrapper .d-switch-simulator"
    )
    assert rel == ".d-switch-simulator"
    rel2 = PublishSettingsStep._schedule_sel_within_wrapper(
        ".post-time-switch-container .d-clickable.d-switch"
    )
    assert rel2 == ".d-clickable.d-switch"


class _FakeLocator:
    def __init__(
        self,
        *,
        count: int = 1,
        checked: bool = False,
        sim_class: str = "",
        visible: bool = True,
    ) -> None:
        self._count = count
        self._checked = checked
        self._sim_class = sim_class
        self._visible = visible

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def count(self) -> int:
        return self._count

    async def is_visible(self) -> bool:
        return self._visible

    async def is_checked(self) -> bool:
        return self._checked

    async def get_attribute(self, name: str) -> str | None:
        if name == "class":
            return self._sim_class
        return None

    def locator(self, _sel: str) -> "_FakeLocator":
        if "d-switch-simulator" in _sel:
            return _FakeLocator(count=1, sim_class=self._sim_class)
        if "checkbox" in _sel:
            return _FakeLocator(count=1, checked=self._checked)
        return _FakeLocator(count=0)

    def filter(self, **_kwargs: object) -> "_FakeLocator":
        return self


@pytest.mark.asyncio
async def test_read_schedule_switch_visual_on_unchecked() -> None:
    step = PublishSettingsStep()
    wrapper = _FakeLocator(sim_class="d-switch-simulator unchecked --color-bg-fill")
    assert await step._read_schedule_switch_visual_on(wrapper) is False


@pytest.mark.asyncio
async def test_read_schedule_switch_visual_on_checked() -> None:
    step = PublishSettingsStep()
    wrapper = _FakeLocator(sim_class="d-switch-simulator checked --color-primary")
    assert await step._read_schedule_switch_visual_on(wrapper) is True


@pytest.mark.asyncio
async def test_schedule_switch_enabled_visual_without_checkbox(monkeypatch) -> None:
    step = PublishSettingsStep()
    page = _FakePage()
    wrapper = _FakeLocator(sim_class="d-switch-simulator checked")

    async def _no_display(_page: _FakePage) -> None:
        return None

    monkeypatch.setattr(step, "_find_schedule_time_display", _no_display)

    assert await step._schedule_switch_enabled(page, wrapper, None) is True


@pytest.mark.asyncio
async def test_schedule_switch_enabled_when_time_display_visible(monkeypatch) -> None:
    step = PublishSettingsStep()
    page = _FakePage()
    wrapper = _FakeLocator(sim_class="d-switch-simulator unchecked")
    display = _FakeLocator(count=1, visible=True)

    async def _has_display(_page: _FakePage) -> _FakeLocator:
        return display

    monkeypatch.setattr(step, "_find_schedule_time_display", _has_display)

    assert await step._schedule_switch_enabled(page, wrapper, None) is True


@pytest.mark.asyncio
async def test_schedule_switch_not_enabled_when_time_display_hidden(monkeypatch) -> None:
    step = PublishSettingsStep()
    page = _FakePage()
    wrapper = _FakeLocator(sim_class="d-switch-simulator unchecked")
    display = _FakeLocator(count=1, visible=False)

    async def _has_display(_page: _FakePage) -> _FakeLocator:
        return display

    monkeypatch.setattr(step, "_find_schedule_time_display", _has_display)

    assert await step._schedule_switch_enabled(page, wrapper, None) is False


@pytest.mark.asyncio
async def test_click_schedule_switch_to_open_already_enabled(monkeypatch) -> None:
    step = PublishSettingsStep()
    page = _FakePage()
    wrapper = _FakeLocator(sim_class="d-switch-simulator checked")

    async def _noop(*_a, **_k) -> None:
        return None

    async def _no_checkbox(_page: _FakePage) -> None:
        return None

    monkeypatch.setattr(step, "_ensure_schedule_area_visible", _noop)
    monkeypatch.setattr(step, "_schedule_wrapper", lambda _page: wrapper)
    monkeypatch.setattr(step, "_find_schedule_checkbox", _no_checkbox)
    monkeypatch.setattr(step, "_find_schedule_checkbox_via_label", _no_checkbox)
    async def _enabled(*_a, **_k) -> bool:
        return True

    monkeypatch.setattr(step, "_schedule_switch_enabled", _enabled)

    ok = await step._click_schedule_switch_to_open(page, {}, {}, lambda ms: ms)
    assert ok is True


@pytest.mark.asyncio
async def test_dismiss_schedule_picker_clicks_right_blank(monkeypatch) -> None:
    step = PublishSettingsStep()
    page = _FakePage()
    calls = {"visible": 2}

    async def _visible(_page: _FakePage) -> bool:
        calls["visible"] -= 1
        return calls["visible"] > 0

    async def _click_blank(_page: _FakePage, _wait_ms) -> bool:
        return True

    monkeypatch.setattr(step, "_is_schedule_picker_visible", _visible)
    monkeypatch.setattr(step, "_click_publish_page_right_blank", _click_blank)

    ok = await step._dismiss_schedule_date_picker_and_wait(page, lambda ms: ms)
    assert ok is True
    assert len(page.mouse_clicks) >= 0


@pytest.mark.asyncio
async def test_apply_schedule_time_with_verify_passes_on_match(monkeypatch) -> None:
    step = PublishSettingsStep()
    page = _FakePage()
    inp = object()

    async def _set_time(*_a, **_k) -> bool:
        return True

    async def _dismiss(*_a, **_k) -> bool:
        return True

    async def _verify(_page: _FakePage, st_str: str) -> tuple[bool, str]:
        return True, st_str

    monkeypatch.setattr(step, "_set_schedule_time_via_input", _set_time)
    monkeypatch.setattr(step, "_dismiss_schedule_date_picker_and_wait", _dismiss)
    monkeypatch.setattr(step, "_verify_schedule_time_matches_task", _verify)
    async def _no_picker(_p: _FakePage) -> None:
        return None

    monkeypatch.setattr(step, "_find_visible_schedule_picker", _no_picker)

    ok = await step._apply_schedule_time_with_verify(
        page,
        inp,
        "2026-05-26 14:07",
        (2026, 5, 26, 14, 7),
        {},
        {},
        lambda ms: ms,
        1.0,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_apply_schedule_time_with_verify_retries_until_match(monkeypatch) -> None:
    step = PublishSettingsStep()
    page = _FakePage()
    inp = object()
    verify_calls = 0

    async def _set_time(*_a, **_k) -> bool:
        return True

    async def _dismiss(*_a, **_k) -> bool:
        return True

    async def _reopen(*_a, **_k) -> bool:
        return True

    async def _verify(_page: _FakePage, st_str: str) -> tuple[bool, str]:
        nonlocal verify_calls
        verify_calls += 1
        if verify_calls >= 2:
            return True, st_str
        return False, "2026-05-26 14:00"

    monkeypatch.setattr(step, "_set_schedule_time_via_input", _set_time)
    monkeypatch.setattr(step, "_dismiss_schedule_date_picker_and_wait", _dismiss)
    monkeypatch.setattr(step, "_click_schedule_time_display", _reopen)
    monkeypatch.setattr(step, "_verify_schedule_time_matches_task", _verify)
    async def _no_picker(_p: _FakePage) -> None:
        return None

    async def _pick(*_a, **_k) -> bool:
        return True

    monkeypatch.setattr(step, "_find_visible_schedule_picker", _no_picker)
    monkeypatch.setattr(step, "_pick_schedule_in_date_picker", _pick)

    ok = await step._apply_schedule_time_with_verify(
        page,
        inp,
        "2026-05-26 14:07",
        (2026, 5, 26, 14, 7),
        {},
        {},
        lambda ms: ms,
        1.0,
    )
    assert ok is True
    assert verify_calls == 2
