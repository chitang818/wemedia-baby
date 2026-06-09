# -*- coding: utf-8 -*-
"""Plugin wait helpers.

Centralizes short DOM polling loops so plugin steps can wait for real page
state instead of relying on repeated fixed sleeps.
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, Iterable, Optional, TypeVar

from src.infrastructure.browser.automation_api import Page, TimeoutError as PlaywrightTimeoutError

T = TypeVar("T")


AsyncPredicate = Callable[[], Awaitable[Optional[T] | bool]]
AsyncHook = Callable[[], Awaitable[None]]


class PluginWaitHelper:
    """Small polling helpers for Playwright plugin steps."""

    @staticmethod
    async def wait_for_condition(
        page: Page,
        predicate: AsyncPredicate[T],
        *,
        timeout_ms: int,
        poll_interval_ms: int = 500,
        pause_callback: Optional[AsyncHook] = None,
        on_poll: Optional[Callable[[int], None]] = None,
    ) -> Optional[T] | bool:
        """Poll ``predicate`` until it returns a truthy value or times out.

        ``predicate`` may return ``True`` or an object such as a matched selector.
        The helper uses short waits and yields to asyncio between polls, keeping
        qasync/Qt responsive during long upload or submit waits.
        """
        timeout_ms = max(0, int(timeout_ms))
        poll_interval_ms = max(50, int(poll_interval_ms))
        deadline = time.monotonic() + timeout_ms / 1000
        attempt = 0

        while True:
            if pause_callback is not None:
                await pause_callback()

            result = await predicate()
            if result:
                return result

            now = time.monotonic()
            if now >= deadline:
                return None

            if on_poll is not None:
                on_poll(attempt)
            attempt += 1

            remaining_ms = int(max(0, (deadline - now) * 1000))
            await page.wait_for_timeout(min(poll_interval_ms, remaining_ms))
            await asyncio.sleep(0)

    @staticmethod
    async def first_visible_selector(page: Page, selectors: Iterable[str]) -> Optional[str]:
        for selector in selectors or []:
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    return selector
            except Exception:
                continue
        return None

    @staticmethod
    async def first_attached_selector(page: Page, selectors: Iterable[str]) -> Optional[str]:
        for selector in selectors or []:
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0:
                    return selector
            except Exception:
                continue
        return None

    @staticmethod
    async def wait_for_any_visible(
        page: Page,
        selectors: Iterable[str],
        *,
        timeout_ms: int,
        poll_interval_ms: int = 500,
        pause_callback: Optional[AsyncHook] = None,
        on_poll: Optional[Callable[[int], None]] = None,
    ) -> Optional[str]:
        return await PluginWaitHelper.wait_for_condition(
            page,
            lambda: PluginWaitHelper.first_visible_selector(page, selectors),
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            pause_callback=pause_callback,
            on_poll=on_poll,
        )

    @staticmethod
    async def wait_for_any_attached(
        page: Page,
        selectors: Iterable[str],
        *,
        timeout_ms: int,
        poll_interval_ms: int = 500,
        pause_callback: Optional[AsyncHook] = None,
        on_poll: Optional[Callable[[int], None]] = None,
    ) -> Optional[str]:
        return await PluginWaitHelper.wait_for_condition(
            page,
            lambda: PluginWaitHelper.first_attached_selector(page, selectors),
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            pause_callback=pause_callback,
            on_poll=on_poll,
        )

    @staticmethod
    async def wait_for_load_state_or_timeout(
        page: Page,
        *,
        state: str = "networkidle",
        timeout_ms: int,
        fallback_ms: int = 300,
    ) -> None:
        """Wait for a Playwright load state, falling back to a short fixed wait.

        This keeps old "wait after navigation" safety behavior while allowing
        fast pages to continue as soon as the browser reports a stable state.
        If the target state never arrives, Playwright's timeout consumes the
        same upper bound that an old fixed wait would have used.
        """
        timeout_ms = max(0, int(timeout_ms))
        fallback_ms = max(0, int(fallback_ms))
        try:
            await page.wait_for_load_state(state, timeout=timeout_ms)
            return
        except PlaywrightTimeoutError:
            return
        except Exception:
            if timeout_ms <= 0 or fallback_ms <= 0:
                return
            await page.wait_for_timeout(min(fallback_ms, timeout_ms))

    @staticmethod
    async def wait_for_url_or_selectors(
        page: Page,
        *,
        initial_url: Optional[str] = None,
        url_keywords: Iterable[str] = (),
        selectors: Iterable[str] = (),
        timeout_ms: int,
        poll_interval_ms: int = 500,
        pause_callback: Optional[AsyncHook] = None,
        on_poll: Optional[Callable[[int], None]] = None,
    ) -> Optional[dict]:
        """Wait until URL changes/matches keywords or any selector is visible/attached."""

        initial_url = initial_url or ""
        keywords = [str(k) for k in (url_keywords or []) if k]
        selector_list = [str(s) for s in (selectors or []) if s]

        async def predicate() -> Optional[dict]:
            try:
                current_url = page.url or ""
                if current_url and current_url != initial_url:
                    if not keywords or any(k in current_url for k in keywords):
                        return {"kind": "url", "url": current_url}
                if keywords and any(k in current_url for k in keywords):
                    return {"kind": "url", "url": current_url}
            except Exception:
                pass

            attached = await PluginWaitHelper.first_attached_selector(page, selector_list)
            if attached:
                return {"kind": "selector", "selector": attached}
            return None

        result = await PluginWaitHelper.wait_for_condition(
            page,
            predicate,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            pause_callback=pause_callback,
            on_poll=on_poll,
        )
        return result if isinstance(result, dict) else None

    @staticmethod
    async def wait_for_submit_result(
        page: Page,
        *,
        success_selectors: Iterable[str] = (),
        success_url_keywords: Iterable[str] = (),
        error_selectors: Iterable[str] = (),
        timeout_ms: int = 10000,
        poll_interval_ms: int = 300,
        pause_callback: Optional[AsyncHook] = None,
        on_poll: Optional[Callable[[int], None]] = None,
    ) -> Optional[dict]:
        """Wait for submit success/error signals without a final fixed sleep."""

        success_selector_list = [str(s) for s in (success_selectors or []) if s]
        success_keywords = [str(k) for k in (success_url_keywords or []) if k]
        error_selector_list = [str(s) for s in (error_selectors or []) if s]

        async def predicate() -> Optional[dict]:
            try:
                current_url = page.url or ""
                if any(k in current_url for k in success_keywords):
                    return {"status": "success", "kind": "url", "url": current_url}
            except Exception:
                pass

            success_selector = await PluginWaitHelper.first_visible_selector(
                page, success_selector_list
            )
            if success_selector:
                return {
                    "status": "success",
                    "kind": "selector",
                    "selector": success_selector,
                    "url": getattr(page, "url", ""),
                }

            error_selector = await PluginWaitHelper.first_visible_selector(page, error_selector_list)
            if error_selector:
                return {
                    "status": "error",
                    "kind": "selector",
                    "selector": error_selector,
                    "url": getattr(page, "url", ""),
                }
            return None

        result = await PluginWaitHelper.wait_for_condition(
            page,
            predicate,
            timeout_ms=timeout_ms,
            poll_interval_ms=poll_interval_ms,
            pause_callback=pause_callback,
            on_poll=on_poll,
        )
        return result if isinstance(result, dict) else None

    @staticmethod
    async def no_visible_selector(page: Page, selectors: Iterable[str]) -> bool:
        return await PluginWaitHelper.first_visible_selector(page, selectors) is None

    @staticmethod
    async def wait_for_all_hidden(
        page: Page,
        selectors: Iterable[str],
        *,
        timeout_ms: int,
        poll_interval_ms: int = 500,
        pause_callback: Optional[AsyncHook] = None,
        on_poll: Optional[Callable[[int], None]] = None,
    ) -> bool:
        return bool(
            await PluginWaitHelper.wait_for_condition(
                page,
                lambda: PluginWaitHelper.no_visible_selector(page, selectors),
                timeout_ms=timeout_ms,
                poll_interval_ms=poll_interval_ms,
                pause_callback=pause_callback,
                on_poll=on_poll,
            )
        )
