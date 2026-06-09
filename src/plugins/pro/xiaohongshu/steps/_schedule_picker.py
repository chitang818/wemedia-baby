# -*- coding: utf-8 -*-
"""定时发布日期浮层关闭与发布前失焦（步骤7/8 共用）。"""

from __future__ import annotations

import logging
from typing import Callable, Sequence

from src.infrastructure.browser.automation_api import Page

from ..selectors import Selectors

logger = logging.getLogger(__name__)

_SCHEDULE_PICKER_CLOSE_WAIT_MS = 3000
_SCHEDULE_PICKER_POLL_MS = 150

_RIGHT_BLANK_CLICK_SELECTORS: Sequence[str] = (
    "div[class*='preview']",
    "[class*='phone-preview']",
    "[class*='video-preview']",
    ".publish-page-preview",
    ".publish-preview",
)


async def is_schedule_picker_visible(page: Page) -> bool:
    for sel in Selectors.SETTINGS.get("SCHEDULE_DATE_PICKER", []) or []:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue
    return False


async def click_publish_page_right_blank(
    page: Page, wait_ms: Callable[[int], int],
) -> bool:
    """在页面右侧预览区空白处点击，用于关闭定时时间选择浮层。"""
    for sel in _RIGHT_BLANK_CLICK_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            box = await loc.bounding_box()
            if not box or box.get("width", 0) < 40 or box.get("height", 0) < 40:
                continue
            x = box["x"] + box["width"] * 0.55
            y = box["y"] + box["height"] * 0.35
            await page.mouse.click(x, y)
            await page.wait_for_timeout(wait_ms(150))
            logger.debug("已在右侧预览区空白点击: %s", sel)
            return True
        except Exception as e:
            logger.debug("右侧空白点击失败 %s: %s", sel, e)
            continue
    try:
        vp = await page.evaluate(
            "() => ({ w: window.innerWidth, h: window.innerHeight })",
        )
        w = float(vp.get("w") or 1200)
        h = float(vp.get("h") or 800)
        await page.mouse.click(w * 0.82, h * 0.4)
        await page.wait_for_timeout(wait_ms(150))
        logger.debug("已在视口右侧空白点击")
        return True
    except Exception as e:
        logger.debug("视口右侧空白点击失败: %s", e)
        return False


async def dismiss_schedule_date_picker_and_wait(
    page: Page, wait_ms: Callable[[int], int],
) -> bool:
    """点右侧空白 + Escape，轮询直到定时日期浮层消失。"""
    if not await is_schedule_picker_visible(page):
        return True

    await click_publish_page_right_blank(page, wait_ms)
    elapsed = 0
    while elapsed < _SCHEDULE_PICKER_CLOSE_WAIT_MS:
        if not await is_schedule_picker_visible(page):
            logger.debug("定时日期浮层已关闭（右侧空白点击）")
            return True
        await page.wait_for_timeout(_SCHEDULE_PICKER_POLL_MS)
        elapsed += _SCHEDULE_PICKER_POLL_MS

    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(wait_ms(120))
    except Exception:
        pass
    await click_publish_page_right_blank(page, wait_ms)

    elapsed = 0
    while elapsed < _SCHEDULE_PICKER_CLOSE_WAIT_MS:
        if not await is_schedule_picker_visible(page):
            return True
        await page.wait_for_timeout(_SCHEDULE_PICKER_POLL_MS)
        elapsed += _SCHEDULE_PICKER_POLL_MS
    return not await is_schedule_picker_visible(page)


async def blur_publish_form_focus(page: Page, wait_ms: Callable[[int], int]) -> None:
    """失焦当前输入，避免定时时间框焦点阻塞底部发布钮解锁。"""
    try:
        await page.evaluate(
            """() => {
                const ae = document.activeElement;
                if (ae && typeof ae.blur === 'function') ae.blur();
            }"""
        )
    except Exception as e:
        logger.debug("blur activeElement 失败: %s", e)
    for sel in (".publish-page-content", ".publish-page-container"):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0:
                await loc.click(position={"x": 24, "y": 24}, timeout=2000)
                await page.wait_for_timeout(wait_ms(80))
                break
        except Exception:
            continue


async def _blur_schedule_time_focus(page: Page, wait_ms: Callable[[int], int]) -> None:
    """定时时间 input 仍持焦点时失焦，避免 submit-disabled 不解除。"""
    try:
        focused = await page.evaluate(
            """() => {
                const wrap = document.querySelector('.post-time-wrapper');
                const ae = document.activeElement;
                if (!wrap || !ae || !wrap.contains(ae)) return false;
                if (typeof ae.blur === 'function') ae.blur();
                return true;
            }"""
        )
        if focused:
            await page.wait_for_timeout(wait_ms(80))
    except Exception as e:
        logger.debug("定时区失焦失败: %s", e)
    try:
        anchor = page.locator(".publish-page-content-settings").first
        if await anchor.count() > 0:
            await anchor.click(position={"x": 20, "y": 20}, timeout=2000)
            await page.wait_for_timeout(wait_ms(100))
    except Exception:
        pass


async def unlock_before_submit(page: Page, wait_ms: Callable[[int], int]) -> None:
    """步骤8 前：关定时浮层、关其它 popover、定时区失焦、表单失焦。"""
    await dismiss_schedule_date_picker_and_wait(page, wait_ms)
    for sel in (
        "body > .post-time-date-picker-popover-class",
        "body > .d-popover.d-dropdown",
        "body > .d-popover.custom-dropdown-44",
    ):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(wait_ms(120))
        except Exception:
            continue
    await _blur_schedule_time_focus(page, wait_ms)
    try:
        anchor = page.locator(".publish-page-content-settings").first
        if await anchor.count() > 0:
            await anchor.click(position={"x": 12, "y": 12}, timeout=2000)
            await page.wait_for_timeout(wait_ms(100))
    except Exception:
        pass
    await blur_publish_form_focus(page, wait_ms)
    # 定时开关已开时，再关一次浮层（步骤7 刚写完时间常见残留）
    if await is_schedule_picker_visible(page):
        await dismiss_schedule_date_picker_and_wait(page, wait_ms)
