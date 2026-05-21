# -*- coding: utf-8 -*-
"""
wujie Shadow DOM 内元素视口坐标与真实鼠标点击（浏览器 isTrusted），
供定时、声明原创、发表等步骤共用，避免 evaluate 内 el.click() 不写 Vue model。
"""
import logging
from typing import Optional, Tuple

from playwright.async_api import Page

from .wujie_shadow import (
    WUJIE_SHADOW_ROOT_JS,
    WUJIE_SHADOW_QUERY_SELECTOR_FN_JS,
)

logger = logging.getLogger(__name__)

# shadow 已解析；tail_js 内可使用变量 shadow，须 return {x,y} 或 null
_SHADOW_XY_PREFIX = "const shadow = " + WUJIE_SHADOW_ROOT_JS + ";" "if (!shadow) return null;"


async def shadow_eval_center(page: Page, tail_js: str) -> Optional[Tuple[float, float]]:
    """执行 tail_js（在 shadow 非空之后），须 return {{x,y}} 或 null。"""
    js = "() => { " + _SHADOW_XY_PREFIX + tail_js + "}"
    try:
        r = await page.evaluate(js)
        if isinstance(r, dict) and "x" in r and "y" in r:
            return (float(r["x"]), float(r["y"]))
        return None
    except Exception as e:
        logger.debug("[视频号] shadow_eval_center 异常: %s", e)
        return None


async def get_shadow_el_center(page: Page, css: str) -> Optional[Tuple[float, float]]:
    """`shadow.querySelector(css)` 的元素视口中心。"""
    try:
        handle = await page.evaluate_handle(WUJIE_SHADOW_QUERY_SELECTOR_FN_JS, css)
        if not handle or str(handle) == "JSHandle@null":
            return None
        await handle.evaluate(
            """(el) => {
            try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
        }"""
        )
        rect = await handle.evaluate(
            """(el) => {
            const r = el.getBoundingClientRect();
            return r.width > 1 && r.height > 1
                ? { x: r.left + r.width / 2, y: r.top + r.height / 2 }
                : null;
        }"""
        )
        if isinstance(rect, dict) and "x" in rect and "y" in rect:
            return (float(rect["x"]), float(rect["y"]))
        return None
    except Exception as e:
        logger.debug("[视频号] get_shadow_el_center(%r) 异常: %s", css, e)
        return None


async def real_mouse_click_xy(page: Page, xy: Optional[Tuple[float, float]]) -> bool:
    if not xy:
        return False
    try:
        await page.mouse.click(xy[0], xy[1])
        return True
    except Exception as e:
        logger.debug("[视频号] real_mouse_click_xy 失败: %s", e)
        return False


async def js_handle_click_center(page: Page, handle) -> bool:
    """对 Playwright JSHandle 指向的 DOM 节点做真实鼠标点击（用于 Shadow 内 button 等）。"""
    if not handle or str(handle) == "JSHandle@null":
        return False
    try:
        await handle.evaluate(
            """(el) => {
            try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
        }"""
        )
        rect = await handle.evaluate(
            """(el) => {
            const r = el.getBoundingClientRect();
            return r.width > 1 && r.height > 1
                ? { x: r.left + r.width / 2, y: r.top + r.height / 2 }
                : null;
        }"""
        )
        if not isinstance(rect, dict) or "x" not in rect:
            return False
        await page.mouse.click(float(rect["x"]), float(rect["y"]))
        return True
    except Exception as e:
        logger.debug("[视频号] js_handle_click_center 失败: %s", e)
        return False


async def js_handle_click_biased_right(
    page: Page,
    handle,
    *,
    x_ratio: float = 0.78,
    y_ratio: float = 0.5,
) -> bool:
    """对 Shadow 内按钮做真实鼠标点击，落点在元素内部略偏右，避免与左侧「手机预览」相邻时误触。"""
    if not handle or str(handle) == "JSHandle@null":
        return False
    try:
        await handle.evaluate(
            """(el) => {
            try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
        }"""
        )
        rect = await handle.evaluate(
            """(el, args) => {
            const r = el.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) return null;
            const xr = args.xr;
            const yr = args.yr;
            const mx = Math.min(8, Math.max(2, r.width * 0.12));
            const my = Math.min(6, Math.max(2, r.height * 0.12));
            const iw = Math.max(1, r.width - 2 * mx);
            const ih = Math.max(1, r.height - 2 * my);
            return {
                x: r.left + mx + iw * xr,
                y: r.top + my + ih * yr,
            };
        }""",
            {"xr": float(x_ratio), "yr": float(y_ratio)},
        )
        if not isinstance(rect, dict) or "x" not in rect:
            return False
        await page.mouse.click(float(rect["x"]), float(rect["y"]))
        return True
    except Exception as e:
        logger.debug("[视频号] js_handle_click_biased_right 失败: %s", e)
        return False


async def real_mouse_click_bbox_biased_right(page: Page, box: dict) -> bool:
    """根据 Playwright bounding_box 在矩形内略偏右处点击（用于无障碍 Locator 回退路径）。"""
    if not box:
        return False
    try:
        x, y, w, h = float(box["x"]), float(box["y"]), float(box["width"]), float(box["height"])
        if w < 2 or h < 2:
            return False
        mx = min(8.0, max(2.0, w * 0.12))
        my = min(6.0, max(2.0, h * 0.12))
        iw = max(1.0, w - 2 * mx)
        ih = max(1.0, h - 2 * my)
        cx = x + mx + iw * 0.78
        cy = y + my + ih * 0.5
        await page.mouse.click(cx, cy)
        return True
    except Exception as e:
        logger.debug("[视频号] real_mouse_click_bbox_biased_right 失败: %s", e)
        return False
