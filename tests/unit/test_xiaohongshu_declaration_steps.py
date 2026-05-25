from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.publish.work_declaration import (
    KEY_XHS_CONTENT_ATTR,
    KEY_XHS_CONTENT_ATTR_AUTO,
    KEY_XHS_ORIGINAL,
    XHS_ATTR_MARKETING,
)
from src.plugins.pro.xiaohongshu.steps.step_06A_original_declaration import (
    OriginalDeclarationStep,
)
from src.plugins.pro.xiaohongshu.steps.step_06B_work_declaration import (
    WorkDeclarationStep,
)


class _FakePage:
    def __init__(self) -> None:
        self.waits: list[int] = []
        self.keyboard = MagicMock()
        self.keyboard.press = AsyncMock()

    async def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(ms)


class _FakeCheckbox:
    def __init__(self, checked: bool = False) -> None:
        self.checked = checked
        self.check_calls = 0
        self.uncheck_calls = 0

    async def scroll_into_view_if_needed(self) -> None:
        return None

    async def is_checked(self) -> bool:
        return self.checked

    async def check(self, force: bool = False, **_kwargs) -> None:
        self.check_calls += 1
        self.checked = True

    async def uncheck(self, force: bool = False, **_kwargs) -> None:
        self.uncheck_calls += 1
        self.checked = False

    async def get_attribute(self, _name: str) -> None:
        return None

    async def element_handle(self) -> None:
        return None


class _FakeSwitch:
    def __init__(self, *, toggles_checkbox: _FakeCheckbox) -> None:
        self.toggles_checkbox = toggles_checkbox
        self.click_calls = 0

    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True

    async def scroll_into_view_if_needed(self) -> None:
        return None


class _FakeEntry:
    def __init__(self) -> None:
        self.clicked = False

    async def scroll_into_view_if_needed(self) -> None:
        return None

    async def click(self, timeout: int = 0) -> None:
        self.clicked = True

    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True


class _FakePanel:
    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True

    async def wait_for(self, *, state: str, timeout: int = 0) -> None:
        return None


async def _noop_scroll(_page) -> None:
    return None


@pytest.mark.asyncio
async def test_xhs_original_declaration_skips_without_config() -> None:
    result = await OriginalDeclarationStep().execute(_FakePage(), "", {})

    assert result is None


@pytest.mark.asyncio
async def test_xhs_original_declaration_uses_enable_flow(monkeypatch) -> None:
    step = OriginalDeclarationStep()
    checkbox = _FakeCheckbox(checked=False)
    called: list[bool] = []

    async def fake_find(_page):
        return checkbox

    async def fake_verify(_page, _cb):
        return checkbox.checked

    async def fake_set(_page, _cb, want, _meta, _cfg):
        called.append(want)
        checkbox.checked = want
        return True

    monkeypatch.setattr(step, "_find_original_checkbox", fake_find)
    monkeypatch.setattr(step, "_verify_original_enabled", fake_verify)
    monkeypatch.setattr(step, "_set_original_checked", fake_set)
    monkeypatch.setattr(step, "_scroll_settings_section_into_view", _noop_scroll)

    result = await step.execute(
        _FakePage(),
        "",
        {"privacy_settings": {KEY_XHS_ORIGINAL: True}},
    )

    assert result is None
    assert called == [True]
    assert checkbox.checked is True
    assert checkbox.check_calls == 0


@pytest.mark.asyncio
async def test_xhs_original_declaration_requires_dialog_flow(monkeypatch) -> None:
    step = OriginalDeclarationStep()
    checkbox = _FakeCheckbox(checked=False)
    enable_called: list[bool] = []

    async def fake_enable(*_args, **_kwargs):
        enable_called.append(True)
        checkbox.checked = True
        return True

    monkeypatch.setattr(step, "_find_original_checkbox", AsyncMock(return_value=checkbox))
    monkeypatch.setattr(step, "_scroll_settings_section_into_view", _noop_scroll)
    monkeypatch.setattr(
        step,
        "_verify_original_enabled",
        AsyncMock(side_effect=[False, True]),
    )

    async def fake_set(_page, _cb, want, _meta, _cfg):
        assert want is True
        return await fake_enable()

    monkeypatch.setattr(step, "_set_original_checked", fake_set)

    result = await step.execute(
        _FakePage(),
        "",
        {"privacy_settings": {KEY_XHS_ORIGINAL: True}},
    )

    assert result is None
    assert enable_called == [True]
    assert checkbox.check_calls == 0


@pytest.mark.asyncio
async def test_xhs_original_declaration_fails_when_verify_after_enable(monkeypatch) -> None:
    step = OriginalDeclarationStep()
    checkbox = _FakeCheckbox(checked=False)

    monkeypatch.setattr(step, "_find_original_checkbox", AsyncMock(return_value=checkbox))
    monkeypatch.setattr(step, "_scroll_settings_section_into_view", _noop_scroll)
    monkeypatch.setattr(step, "_verify_original_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(step, "_set_original_checked", AsyncMock(return_value=True))

    result = await step.execute(
        _FakePage(),
        "",
        {"privacy_settings": {KEY_XHS_ORIGINAL: True}},
    )

    assert result is not None
    assert result.success is False
    assert "开关" in (result.error_message or "")


@pytest.mark.asyncio
async def test_xhs_original_declaration_enable_calls_dialog_complete(monkeypatch) -> None:
    step = OriginalDeclarationStep()
    checkbox = _FakeCheckbox(checked=False)
    order: list[str] = []

    async def fake_click_switch(*_args, **_kwargs):
        order.append("switch")
        return True

    async def fake_wait_outcome(*_args, **_kwargs):
        order.append("wait")
        return "dialog"

    async def fake_complete(*_args, **_kwargs):
        order.append("complete")
        checkbox.checked = True
        return True

    verify_calls = 0

    async def fake_verify(_page, _cb):
        nonlocal verify_calls
        verify_calls += 1
        return verify_calls >= 2

    empty_wrapper = MagicMock()
    empty_wrapper.count = AsyncMock(return_value=0)

    monkeypatch.setattr(step, "_original_wrapper", lambda _page: empty_wrapper)
    monkeypatch.setattr(step, "_verify_original_enabled", fake_verify)
    monkeypatch.setattr(step, "_is_original_dialog_open", AsyncMock(return_value=False))
    monkeypatch.setattr(step, "_click_switch_to_open", fake_click_switch)
    monkeypatch.setattr(step, "_wait_dialog_or_enabled", fake_wait_outcome)
    monkeypatch.setattr(step, "_complete_original_dialog", fake_complete)

    ok = await step._enable_original(_FakePage(), empty_wrapper, checkbox, {}, {})

    assert ok is True
    assert order == ["switch", "wait", "complete"]
    assert checkbox.check_calls == 0


@pytest.mark.asyncio
async def test_xhs_original_declaration_switch_click_retries_until_response(
    monkeypatch,
) -> None:
    step = OriginalDeclarationStep()
    checkbox = _FakeCheckbox(checked=False)
    attempts: list[int] = []

    class _Target:
        async def count(self) -> int:
            return 1

        async def is_visible(self) -> bool:
            return True

    class _Wrapper:
        async def count(self) -> int:
            return 1

        def locator(self, sel: str):
            return _LocatorResult(_Target())

    async def fake_collect(_wrapper):
        return [_Target()]

    async def fake_try_click(*_args, **_kwargs):
        attempts.append(1)

    async def fake_wait_response(_page, _cb, **_kwargs):
        return len(attempts) >= 2

    monkeypatch.setattr(step, "_original_wrapper", lambda _page: _Wrapper())
    monkeypatch.setattr(step, "_find_original_label", AsyncMock(return_value=None))
    monkeypatch.setattr(step, "_verify_original_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(step, "_is_original_dialog_open", AsyncMock(return_value=False))
    monkeypatch.setattr(step, "_read_switch_visual_on", AsyncMock(return_value=False))
    monkeypatch.setattr(step, "_collect_switch_click_targets", fake_collect)
    monkeypatch.setattr(step, "_try_click_switch_target", fake_try_click)
    monkeypatch.setattr(step, "_wait_switch_response", fake_wait_response)
    monkeypatch.setattr(step, "_switch_interaction_detected", AsyncMock(return_value=False))

    ok = await step._click_switch_to_open(
        _FakePage(), _Wrapper(), checkbox, {}, {}
    )

    assert ok is True
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_xhs_original_declaration_enable_without_dialog(monkeypatch) -> None:
    step = OriginalDeclarationStep()
    checkbox = _FakeCheckbox(checked=True)

    monkeypatch.setattr(step, "_verify_original_enabled", AsyncMock(side_effect=[False, True]))
    monkeypatch.setattr(step, "_is_original_dialog_open", AsyncMock(return_value=False))
    monkeypatch.setattr(step, "_click_switch_to_open", AsyncMock(return_value=True))
    monkeypatch.setattr(step, "_wait_dialog_or_enabled", AsyncMock(return_value="enabled"))
    fake_complete = AsyncMock()
    monkeypatch.setattr(step, "_complete_original_dialog", fake_complete)

    empty_wrapper = MagicMock()
    empty_wrapper.count = AsyncMock(return_value=0)

    ok = await step._enable_original(_FakePage(), empty_wrapper, checkbox, {}, {})

    assert ok is True
    fake_complete.assert_not_called()


@pytest.mark.asyncio
async def test_xhs_original_declaration_fails_when_dialog_not_closed(monkeypatch) -> None:
    step = OriginalDeclarationStep()
    checkbox = _FakeCheckbox(checked=False)

    monkeypatch.setattr(step, "_verify_original_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(step, "_is_original_dialog_open", AsyncMock(return_value=False))
    monkeypatch.setattr(step, "_click_switch_to_open", AsyncMock(return_value=True))
    monkeypatch.setattr(step, "_wait_dialog_or_enabled", AsyncMock(return_value="dialog"))
    monkeypatch.setattr(step, "_complete_original_dialog", AsyncMock(return_value=False))

    empty_wrapper = MagicMock()
    empty_wrapper.count = AsyncMock(return_value=0)

    ok = await step._enable_original(_FakePage(), empty_wrapper, checkbox, {}, {})

    assert ok is False


class _LocatorResult:
    def __init__(self, first: Any) -> None:
        self.first = first


@pytest.mark.asyncio
async def test_xhs_original_declaration_collects_d_switch_targets() -> None:
    from src.plugins.pro.xiaohongshu.selectors import Selectors

    switch = _FakeSwitch(toggles_checkbox=_FakeCheckbox())

    class _Wrapper:
        async def count(self) -> int:
            return 1

        def locator(self, _sel: str) -> _LocatorResult:
            return _LocatorResult(switch)

    wrapper = _Wrapper()
    targets = []
    if await wrapper.count() > 0:
        for sel in Selectors.SETTINGS.get("ORIGINAL_DECLARATION_SWITCH", []):
            loc = wrapper.locator(sel).first
            if await loc.count() > 0:
                targets.append(loc)

    assert len(targets) == len(Selectors.SETTINGS["ORIGINAL_DECLARATION_SWITCH"])
    assert ".original-wrapper" in Selectors.SETTINGS["ORIGINAL_DECLARATION_SWITCH"][0]


@pytest.mark.asyncio
async def test_xhs_original_declaration_dialog_selectors_present() -> None:
    from src.plugins.pro.xiaohongshu.selectors import Selectors

    settings = Selectors.SETTINGS
    assert "ORIGINAL_DECLARATION_DIALOG" in settings
    assert "ORIGINAL_DECLARATION_AGREEMENT" in settings
    assert "ORIGINAL_DECLARATION_CONFIRM_BTN" in settings
    assert any("声明原创" in s for s in settings["ORIGINAL_DECLARATION_CONFIRM_BTN"])


@pytest.mark.asyncio
async def test_xhs_original_declaration_prefers_original_wrapper_checkbox(
    monkeypatch,
) -> None:
    step = OriginalDeclarationStep()
    scoped_calls: list[str] = []

    class _Checkbox:
        async def count(self) -> int:
            return 1

    class _Wrapper:
        async def count(self) -> int:
            return 1

        def locator(self, sel: str):
            scoped_calls.append(sel)
            if "checkbox" in sel:
                return _LocatorResult(_Checkbox())
            return _LocatorResult(_Checkbox())

    monkeypatch.setattr(step, "_original_wrapper", lambda _page: _Wrapper())

    result = await step._find_original_checkbox(_FakePage())

    assert result is not None
    assert scoped_calls == ["input[type='checkbox']"]


@pytest.mark.asyncio
async def test_xhs_original_declaration_read_switch_visual_on(monkeypatch) -> None:
    step = OriginalDeclarationStep()

    class _Sim:
        async def count(self) -> int:
            return 1

        async def get_attribute(self, name: str) -> str:
            if name == "class":
                return "d-switch-simulator checked --color-bg-fill"
            return ""

    class _Wrapper:
        async def count(self) -> int:
            return 1

        def locator(self, sel: str):
            if "d-switch-simulator" in sel:
                return _LocatorResult(_Sim())
            return _LocatorResult(_Sim())

    monkeypatch.setattr(step, "_original_wrapper", lambda _page: _Wrapper())

    assert await step._read_switch_visual_on(_FakePage()) is True


@pytest.mark.asyncio
async def test_xhs_original_declaration_reports_missing_checkbox(monkeypatch) -> None:
    step = OriginalDeclarationStep()

    async def fake_find(_page):
        return None

    monkeypatch.setattr(step, "_find_original_checkbox", fake_find)
    monkeypatch.setattr(step, "_scroll_settings_section_into_view", _noop_scroll)

    result = await step.execute(
        _FakePage(),
        "",
        {"privacy_settings": {KEY_XHS_ORIGINAL: True}},
    )

    assert result is not None
    assert result.success is False
    assert "原创声明" in (result.error_message or "")


@pytest.mark.asyncio
async def test_xhs_content_type_declaration_skips_when_auto_disabled() -> None:
    result = await WorkDeclarationStep().execute(
        _FakePage(),
        "",
        {
            "privacy_settings": {
                KEY_XHS_CONTENT_ATTR: XHS_ATTR_MARKETING,
                KEY_XHS_CONTENT_ATTR_AUTO: False,
            }
        },
    )

    assert result is None


@pytest.mark.asyncio
async def test_xhs_content_type_declaration_selects_target(monkeypatch) -> None:
    step = WorkDeclarationStep()
    entry = _FakeEntry()
    panel = _FakePanel()
    selected: list[str] = []
    visible_checks: list[bool] = []

    async def fake_visible(_page, _label):
        visible_checks.append(True)
        return len(visible_checks) > 1

    async def fake_entry(_page):
        return entry

    async def fake_open(_page, _entry, _meta, _cfg):
        return panel

    async def fake_click(_page, _panel, label, _meta, _cfg):
        selected.append(label)
        return True

    async def fake_confirm(_page):
        return None

    monkeypatch.setattr(step, "_ensure_no_blocking_dialog", _noop_scroll)
    monkeypatch.setattr(step, "_scroll_content_settings_into_view", _noop_scroll)
    monkeypatch.setattr(step, "_target_label_visible_in_settings", fake_visible)
    monkeypatch.setattr(step, "_find_entry", fake_entry)
    monkeypatch.setattr(step, "_open_content_type_panel", fake_open)
    monkeypatch.setattr(step, "_click_target_option", fake_click)
    monkeypatch.setattr(step, "_click_confirm_if_present", fake_confirm)

    result = await step.execute(
        _FakePage(),
        "",
        {
            "privacy_settings": {
                KEY_XHS_CONTENT_ATTR: XHS_ATTR_MARKETING,
                KEY_XHS_CONTENT_ATTR_AUTO: True,
            }
        },
    )

    assert result is None
    assert selected == ["内容包含营销广告"]


@pytest.mark.asyncio
async def test_xhs_content_type_waits_content_dropdown_polling(monkeypatch) -> None:
    step = WorkDeclarationStep()
    calls: list[str] = []

    async def fake_find(_page):
        calls.append("find")
        return _FakePanel() if len(calls) >= 2 else None

    monkeypatch.setattr(step, "_find_content_panel_locator", fake_find)

    page = _FakePage()
    panel = await step._wait_content_type_panel(page, timeout_ms=800)

    assert panel is not None
    assert calls == ["find", "find"]


@pytest.mark.asyncio
async def test_xhs_content_type_open_panel_retries_entry(monkeypatch) -> None:
    step = WorkDeclarationStep()
    entry = _FakeEntry()
    attempts: list[int] = []

    async def fake_wait(_page, **_kwargs):
        attempts.append(1)
        return _FakePanel() if len(attempts) >= 2 else None

    monkeypatch.setattr(step, "_dismiss_open_content_panel", _noop_scroll)
    monkeypatch.setattr(step, "_wait_content_type_panel", fake_wait)
    monkeypatch.setattr(
        "src.infrastructure.anti_risk.human_like.human_click",
        AsyncMock(),
    )

    panel = await step._open_content_type_panel(_FakePage(), entry, {}, {})

    assert panel is not None
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_xhs_content_type_declaration_reports_missing_panel(monkeypatch) -> None:
    step = WorkDeclarationStep()
    entry = _FakeEntry()

    async def fake_visible(_page, _label):
        return False

    async def fake_entry(_page):
        return entry

    async def fake_open(_page, _entry, _meta, _cfg):
        return None

    monkeypatch.setattr(step, "_ensure_no_blocking_dialog", _noop_scroll)
    monkeypatch.setattr(step, "_scroll_content_settings_into_view", _noop_scroll)
    monkeypatch.setattr(step, "_target_label_visible_in_settings", fake_visible)
    monkeypatch.setattr(step, "_find_entry", fake_entry)
    monkeypatch.setattr(step, "_open_content_type_panel", fake_open)

    result = await step.execute(
        _FakePage(),
        "",
        {
            "privacy_settings": {
                KEY_XHS_CONTENT_ATTR: XHS_ATTR_MARKETING,
                KEY_XHS_CONTENT_ATTR_AUTO: True,
            }
        },
    )

    assert result is not None
    assert result.success is False
    assert "浮层" in (result.error_message or "")


@pytest.mark.asyncio
async def test_xhs_content_type_declaration_fails_when_entry_label_missing(
    monkeypatch,
) -> None:
    step = WorkDeclarationStep()
    entry = _FakeEntry()
    panel = _FakePanel()

    async def fake_visible(_page, _label):
        return False

    monkeypatch.setattr(step, "_ensure_no_blocking_dialog", _noop_scroll)
    monkeypatch.setattr(step, "_scroll_content_settings_into_view", _noop_scroll)
    monkeypatch.setattr(step, "_target_label_visible_in_settings", fake_visible)
    monkeypatch.setattr(step, "_find_entry", AsyncMock(return_value=entry))
    monkeypatch.setattr(step, "_open_content_type_panel", AsyncMock(return_value=panel))
    monkeypatch.setattr(step, "_click_target_option", AsyncMock(return_value=True))
    monkeypatch.setattr(step, "_click_confirm_if_present", AsyncMock())

    result = await step.execute(
        _FakePage(),
        "",
        {
            "privacy_settings": {
                KEY_XHS_CONTENT_ATTR: XHS_ATTR_MARKETING,
                KEY_XHS_CONTENT_ATTR_AUTO: True,
            }
        },
    )

    assert result is not None
    assert result.success is False
    assert "入口未显示" in (result.error_message or "")


@pytest.mark.asyncio
async def test_xhs_content_type_declaration_reports_missing_entry(monkeypatch) -> None:
    step = WorkDeclarationStep()

    async def fake_visible(_page, _label):
        return False

    async def fake_entry(_page):
        return None

    monkeypatch.setattr(step, "_ensure_no_blocking_dialog", _noop_scroll)
    monkeypatch.setattr(step, "_target_label_visible_in_settings", fake_visible)
    monkeypatch.setattr(step, "_find_entry", fake_entry)

    result = await step.execute(
        _FakePage(),
        "",
        {
            "privacy_settings": {
                KEY_XHS_CONTENT_ATTR: XHS_ATTR_MARKETING,
                KEY_XHS_CONTENT_ATTR_AUTO: True,
            }
        },
    )

    assert result is not None
    assert result.success is False
    assert "添加内容类型声明" in (result.error_message or "")
