from __future__ import annotations

import pytest
from src.infrastructure.browser.automation_api import TimeoutError as PlaywrightTimeoutError

from src.plugins.core.wait_helper import PluginWaitHelper


class _FakeLocator:
    def __init__(self, page: "_FakePage", selector: str):
        self._page = page
        self._selector = selector
        self.first = self

    async def count(self) -> int:
        return 1 if self._selector in self._page.visible_selectors else 0

    async def is_visible(self) -> bool:
        return self._selector in self._page.visible_selectors


class _FakePage:
    def __init__(self):
        self.visible_selectors: set[str] = set()
        self.waits: list[int] = []
        self.load_state_calls: list[tuple[str, int]] = []
        self.load_state_error: Exception | None = None
        self.url = "https://example.test/start"

    def locator(self, selector: str) -> _FakeLocator:
        return _FakeLocator(self, selector)

    async def wait_for_timeout(self, ms: int) -> None:
        self.waits.append(ms)

    async def wait_for_load_state(self, state: str, timeout: int) -> None:
        self.load_state_calls.append((state, timeout))
        if self.load_state_error is not None:
            raise self.load_state_error


@pytest.mark.asyncio
async def test_wait_for_any_visible_returns_first_visible_selector() -> None:
    page = _FakePage()
    page.visible_selectors.add(".ready")

    matched = await PluginWaitHelper.wait_for_any_visible(
        page,
        [".missing", ".ready"],
        timeout_ms=1000,
        poll_interval_ms=100,
    )

    assert matched == ".ready"
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_any_attached_does_not_require_visible() -> None:
    page = _FakePage()
    page.visible_selectors.add(".hidden-input")

    async def hidden() -> bool:
        return False

    locator = page.locator(".hidden-input")
    locator.is_visible = hidden

    matched = await PluginWaitHelper.wait_for_any_attached(
        page,
        [".hidden-input"],
        timeout_ms=1000,
        poll_interval_ms=100,
    )

    assert matched == ".hidden-input"
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_condition_polls_until_truthy() -> None:
    page = _FakePage()
    attempts = 0

    async def predicate():
        nonlocal attempts
        attempts += 1
        return "done" if attempts == 3 else None

    matched = await PluginWaitHelper.wait_for_condition(
        page,
        predicate,
        timeout_ms=1000,
        poll_interval_ms=100,
    )

    assert matched == "done"
    assert attempts == 3
    assert page.waits == [100, 100]


@pytest.mark.asyncio
async def test_wait_for_condition_calls_pause_and_on_poll() -> None:
    page = _FakePage()
    pauses = 0
    polls: list[int] = []
    attempts = 0

    async def pause():
        nonlocal pauses
        pauses += 1

    async def predicate():
        nonlocal attempts
        attempts += 1
        return attempts >= 2

    matched = await PluginWaitHelper.wait_for_condition(
        page,
        predicate,
        timeout_ms=1000,
        poll_interval_ms=50,
        pause_callback=pause,
        on_poll=polls.append,
    )

    assert matched is True
    assert pauses == 2
    assert polls == [0]


@pytest.mark.asyncio
async def test_wait_for_all_hidden_returns_true_when_no_selector_visible() -> None:
    page = _FakePage()

    matched = await PluginWaitHelper.wait_for_all_hidden(
        page,
        [".modal"],
        timeout_ms=1000,
        poll_interval_ms=100,
    )

    assert matched is True
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_load_state_or_timeout_returns_after_load_state() -> None:
    page = _FakePage()

    await PluginWaitHelper.wait_for_load_state_or_timeout(
        page,
        state="networkidle",
        timeout_ms=3000,
        fallback_ms=300,
    )

    assert page.load_state_calls == [("networkidle", 3000)]
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_load_state_or_timeout_falls_back_short_wait() -> None:
    page = _FakePage()
    page.load_state_error = RuntimeError("timeout")

    await PluginWaitHelper.wait_for_load_state_or_timeout(
        page,
        state="networkidle",
        timeout_ms=3000,
        fallback_ms=300,
    )

    assert page.load_state_calls == [("networkidle", 3000)]
    assert page.waits == [300]


@pytest.mark.asyncio
async def test_wait_for_load_state_or_timeout_does_not_wait_after_timeout() -> None:
    page = _FakePage()
    page.load_state_error = PlaywrightTimeoutError("networkidle timeout")

    await PluginWaitHelper.wait_for_load_state_or_timeout(
        page,
        state="networkidle",
        timeout_ms=3000,
        fallback_ms=300,
    )

    assert page.load_state_calls == [("networkidle", 3000)]
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_url_or_selectors_returns_url_match() -> None:
    page = _FakePage()
    page.url = "https://example.test/publish"

    matched = await PluginWaitHelper.wait_for_url_or_selectors(
        page,
        initial_url="https://example.test/start",
        url_keywords=["publish"],
        selectors=[".ready"],
        timeout_ms=1000,
        poll_interval_ms=100,
    )

    assert matched == {"kind": "url", "url": "https://example.test/publish"}
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_url_or_selectors_returns_selector_match() -> None:
    page = _FakePage()
    page.visible_selectors.add(".ready")

    matched = await PluginWaitHelper.wait_for_url_or_selectors(
        page,
        initial_url=page.url,
        url_keywords=["publish"],
        selectors=[".ready"],
        timeout_ms=1000,
        poll_interval_ms=100,
    )

    assert matched == {"kind": "selector", "selector": ".ready"}
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_url_or_selectors_polls_with_pause() -> None:
    page = _FakePage()
    pauses = 0

    async def pause() -> None:
        nonlocal pauses
        pauses += 1
        if pauses == 2:
            page.visible_selectors.add(".ready")

    matched = await PluginWaitHelper.wait_for_url_or_selectors(
        page,
        initial_url=page.url,
        selectors=[".ready"],
        timeout_ms=1000,
        poll_interval_ms=100,
        pause_callback=pause,
    )

    assert matched == {"kind": "selector", "selector": ".ready"}
    assert pauses == 2
    assert page.waits == [100]


@pytest.mark.asyncio
async def test_wait_for_submit_result_returns_success_url() -> None:
    page = _FakePage()
    page.url = "https://example.test/manage"

    matched = await PluginWaitHelper.wait_for_submit_result(
        page,
        success_url_keywords=["manage"],
        success_selectors=[".success"],
        error_selectors=[".error"],
        timeout_ms=1000,
        poll_interval_ms=100,
    )

    assert matched == {
        "status": "success",
        "kind": "url",
        "url": "https://example.test/manage",
    }
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_submit_result_returns_success_selector() -> None:
    page = _FakePage()
    page.visible_selectors.add(".success")

    matched = await PluginWaitHelper.wait_for_submit_result(
        page,
        success_url_keywords=["manage"],
        success_selectors=[".success"],
        error_selectors=[".error"],
        timeout_ms=1000,
        poll_interval_ms=100,
    )

    assert matched == {
        "status": "success",
        "kind": "selector",
        "selector": ".success",
        "url": page.url,
    }
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_submit_result_returns_error_selector() -> None:
    page = _FakePage()
    page.visible_selectors.add(".error")

    matched = await PluginWaitHelper.wait_for_submit_result(
        page,
        success_url_keywords=["manage"],
        success_selectors=[".success"],
        error_selectors=[".error"],
        timeout_ms=1000,
        poll_interval_ms=100,
    )

    assert matched == {
        "status": "error",
        "kind": "selector",
        "selector": ".error",
        "url": page.url,
    }
    assert page.waits == []


@pytest.mark.asyncio
async def test_wait_for_submit_result_returns_none_on_timeout() -> None:
    page = _FakePage()

    matched = await PluginWaitHelper.wait_for_submit_result(
        page,
        success_url_keywords=["manage"],
        success_selectors=[".success"],
        error_selectors=[".error"],
        timeout_ms=1,
        poll_interval_ms=100,
    )

    assert matched is None
