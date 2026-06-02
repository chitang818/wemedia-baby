# -*- coding: utf-8 -*-
"""
步骤8：点击发布
文件路径: src/plugins/pro/xiaohongshu/steps/step_08_submit.py

流程（2026-05-25 DOM 实采）：
  1. xhs-publish-btn 为 closed Shadow Web Component，页面侧 shadowRoot 为 null
  2. 可靠点击：host.evaluate 内通过 el._sr 访问 button.ce-btn.bg-red
  3. 兜底：_sr 内 getBoundingClientRect 坐标 + 拟人 mouse.click；再兜底宿主右下角偏移
  4. 等待 submit-disabled=false，关闭定时浮层并失焦
  5. 已就绪时跳过等待轮询（快速路径）；轮询中减少重复 unlock/滚动
  6. 成功判定：published=true /publish/success / 发布成功 Toast / 笔记管理

字段依赖：
  - metadata['speed_rate']、metadata['anti_risk_config']
  - metadata['schedule_time'] / metadata['scheduled_publish_time']
"""
from __future__ import annotations

import logging
import random as _random
import time as _time
from typing import Any, Callable, Dict, Optional, Sequence

from playwright.async_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, NeedsAction, StepOutcome
from ._schedule_picker import is_schedule_picker_visible, unlock_before_submit
from .._xhs_submit_probe import (
    evaluate_sr_red_button_state,
    resolve_sr_click_center,
    snapshot_xhs_publish_btn,
    summarize_snapshot_for_log,
    url_indicates_publish_success,
)
from ..browser_environment_diagnostics import attach_xhs_environment_snapshot
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_FAILED_STEP = "SubmitStep"
_MAX_FIND_BTN_SEC = 15
_MAX_READY_BTN_SEC = 60
_MAX_READY_BTN_SEC_SCHEDULED = 120
_STAGED_FALLBACK_WAIT_SEC = 45
_SUBMIT_WAIT_STATUS_LOG_EVERY_POLLS = 7
_MAX_SUBMIT_CLICK_ATTEMPTS = 3
_POST_CLICK_VERIFY_MS = 8000
_POST_CLICK_VERIFY_MS_FAST = 5000
_SCROLL_SETTLE_MS = 100
_WAIT_POLL_INTERVAL_MS = 400
_FULL_UNLOCK_EVERY_N_POLLS = 4
_SUBMIT_TEXT_IMMEDIATE = "发布"
_SUBMIT_TEXT_SCHEDULED = "定时发布"
_SUBMIT_BTN_LABELS_IMMEDIATE: Sequence[str] = (_SUBMIT_TEXT_IMMEDIATE,)
_SUBMIT_BTN_LABELS_SCHEDULED: Sequence[str] = (
    _SUBMIT_TEXT_SCHEDULED,
    _SUBMIT_TEXT_IMMEDIATE,
)
_XHS_HOST_DESC = "xhs-publish-btn/_sr"


def _is_xhs_publish_edit_url(url: str) -> bool:
    u = (url or "").lower()
    if "published=true" in u:
        return False
    if "/publish/success" in u:
        return False
    return "creator.xiaohongshu.com" in u and "/publish/publish" in u


def _metadata_has_schedule(metadata: Dict[str, Any]) -> bool:
    return bool(
        metadata.get("scheduled_publish_time") or metadata.get("schedule_time"),
    )


def _submit_button_labels(metadata: Dict[str, Any]) -> Sequence[str]:
    if _metadata_has_schedule(metadata):
        return _SUBMIT_BTN_LABELS_SCHEDULED
    return _SUBMIT_BTN_LABELS_IMMEDIATE


def _labels_for_submit_text(
    submit_text: str, *, metadata_has_schedule: bool,
) -> Sequence[str]:
    text = (submit_text or "").strip()
    if metadata_has_schedule and text == _SUBMIT_TEXT_IMMEDIATE:
        return _SUBMIT_BTN_LABELS_SCHEDULED
    if text == _SUBMIT_TEXT_SCHEDULED or (
        text and "定时" in text and text != _SUBMIT_TEXT_IMMEDIATE
    ):
        return _SUBMIT_BTN_LABELS_SCHEDULED
    if text == _SUBMIT_TEXT_IMMEDIATE:
        return _SUBMIT_BTN_LABELS_IMMEDIATE
    if metadata_has_schedule:
        return _SUBMIT_BTN_LABELS_SCHEDULED
    return _SUBMIT_BTN_LABELS_IMMEDIATE


async def _read_xhs_publish_submit_text(page: Page) -> str:
    try:
        host = page.locator("xhs-publish-btn[is-publish='true']").first
        if await host.count() == 0:
            host = page.locator("xhs-publish-btn").first
        if await host.count() > 0:
            return (await host.get_attribute("submit-text") or "").strip()
    except Exception as e:
        logger.debug("读取 submit-text 失败: %s", e)
    return ""


async def _page_schedule_switch_appears_on(page: Page) -> bool:
    try:
        wrapper = page.locator(".post-time-wrapper").first
        if await wrapper.count() == 0:
            return False
        sim = wrapper.locator(".d-switch-simulator").first
        if await sim.count() > 0:
            cls = (await sim.get_attribute("class") or "").lower()
            if "checked" in cls or "active" in cls:
                return True
            if "unchecked" not in cls and await sim.is_visible():
                return True
        inp = wrapper.locator("input[type='checkbox']").first
        if await inp.count() > 0:
            return await inp.is_checked()
    except Exception:
        pass
    return False


async def _submit_button_labels_from_page(
    page: Page, metadata: Dict[str, Any],
) -> Sequence[str]:
    submit_text = await _read_xhs_publish_submit_text(page)
    has_schedule = _metadata_has_schedule(metadata)
    schedule_switch_on = False
    if has_schedule:
        schedule_switch_on = await _page_schedule_switch_appears_on(page)
    labels = _labels_for_submit_text(
        submit_text, metadata_has_schedule=has_schedule,
    )
    if submit_text:
        mode = "定时发布" if labels[0] == _SUBMIT_TEXT_SCHEDULED else "立即发布"
        logger.debug("发布按钮文案 submit-text=%s → %s", submit_text, mode)
    if has_schedule and schedule_switch_on and labels[0] != _SUBMIT_TEXT_SCHEDULED:
        return _SUBMIT_BTN_LABELS_SCHEDULED
    if not submit_text and (has_schedule or await _page_schedule_switch_appears_on(page)):
        return _SUBMIT_BTN_LABELS_SCHEDULED
    return labels


async def _primary_submit_label(page: Page, metadata: Dict[str, Any]) -> str:
    labels = await _submit_button_labels_from_page(page, metadata)
    return labels[0]


def _is_scheduled_submit_mode(primary_label: str) -> bool:
    return primary_label == _SUBMIT_TEXT_SCHEDULED


def _max_ready_btn_sec(primary_label: str) -> int:
    if _is_scheduled_submit_mode(primary_label):
        return _MAX_READY_BTN_SEC_SCHEDULED
    return _MAX_READY_BTN_SEC


def _format_submit_timeout_message(
    primary_label: str,
    host_state: Dict[str, Any],
    *,
    max_sec: int,
) -> str:
    disabled = host_state.get("submit_disabled")
    picker_open = host_state.get("schedule_picker_open")
    submit_text = host_state.get("submit_text") or ""
    sr_ready = host_state.get("sr_red_ready")
    has_sr = host_state.get("has_sr")
    focus_sched = host_state.get("focus_in_schedule")
    extra = ""
    if focus_sched:
        extra += "，焦点仍在定时区"
    if has_sr is not None:
        extra += f"，_sr={'有' if has_sr else '无'}"
    if sr_ready is not None:
        extra += f"，红钮就绪={'是' if sr_ready else '否'}"
    return (
        f"等待超时（{max_sec} 秒），「{primary_label}」按钮长时间不可点"
        f"（submit-disabled={disabled}，定时浮层={'开' if picker_open else '关'}，"
        f"submit-text={submit_text or '未读到'}{extra}）"
    )


async def _attach_submit_diagnostic_snapshot(
    metadata: Dict[str, Any], page: Page,
) -> None:
    try:
        snap = await snapshot_xhs_publish_btn(page)
        ctx = metadata.get("_diagnostic_context")
        if not isinstance(ctx, dict):
            ctx = {}
            metadata["_diagnostic_context"] = ctx
        ctx["xhs_publish_snapshot"] = summarize_snapshot_for_log(snap)
        ctx["xhs_publish_snapshot_raw"] = snap
    except Exception as e:
        logger.debug("写入发布钮诊断快照失败: %s", e)


async def _page_has_xhs_publish_btn(page: Page) -> bool:
    try:
        return await page.locator("xhs-publish-btn").first.count() > 0
    except Exception:
        return False


async def _get_xhs_publish_host(page: Page) -> Locator:
    for sel in (
        ".publish-page-content xhs-publish-btn[is-publish='true']",
        "xhs-publish-btn[is-publish='true']",
        "xhs-publish-btn",
    ):
        loc = page.locator(sel).first
        if await loc.count() > 0:
            return loc
    return page.locator("xhs-publish-btn").first


async def _xhs_publish_btn_disabled(loc: Locator) -> bool:
    try:
        submit_dis = await loc.get_attribute("submit-disabled")
        if submit_dis is not None and submit_dis.lower() == "true":
            return True
    except Exception:
        pass
    return False


async def _xhs_host_submit_unlocked(page: Page) -> bool:
    host = await _get_xhs_publish_host(page)
    if await host.count() == 0:
        return False
    return not await _xhs_publish_btn_disabled(host)


async def _read_xhs_publish_host_state(
    page: Page, primary_label: str, *, include_shadow_probe: bool = True,
) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "submit_text": "",
        "submit_disabled": None,
        "schedule_picker_open": False,
        "sr_red_ready": False,
        "has_sr": False,
        "focus_in_schedule": False,
    }
    try:
        if include_shadow_probe:
            snap = await snapshot_xhs_publish_btn(page)
            summary = summarize_snapshot_for_log(snap)
            state.update(summary)
        state["schedule_picker_open"] = bool(
            state.get("schedule_picker_open")
            or await is_schedule_picker_visible(page),
        )
        host = await _get_xhs_publish_host(page)
        if include_shadow_probe and await host.count() > 0:
            sr_state = await evaluate_sr_red_button_state(host, primary_label)
            state["sr_red_ready"] = bool(sr_state.get("ready"))
            if sr_state.get("submitText"):
                state["submit_text"] = sr_state["submitText"]
            if sr_state.get("reason") and not state["sr_red_ready"]:
                state["sr_block_reason"] = sr_state.get("reason")
        if not state.get("submit_text"):
            state["submit_text"] = await _read_xhs_publish_submit_text(page)
        if state.get("submit_disabled") is None and await host.count() > 0:
            state["submit_disabled"] = await _xhs_publish_btn_disabled(host)
    except Exception as e:
        logger.debug("读取发布钮状态失败: %s", e)
    return state


async def _xhs_submit_clickable(
    page: Page, primary_label: str, *, strict_real_browser: bool = False,
) -> bool:
    if not await _xhs_host_submit_unlocked(page):
        return False
    host = await _get_xhs_publish_host(page)
    if await host.count() == 0:
        return False
    if strict_real_browser:
        try:
            return bool(await host.is_visible() and await host.bounding_box())
        except Exception:
            return False
    sr_state = await evaluate_sr_red_button_state(host, primary_label)
    return bool(sr_state.get("ready"))


def _url_indicates_success(url: str) -> bool:
    return url_indicates_publish_success(url)


def _xhs_strict_real_browser_enabled(metadata: Dict[str, Any]) -> bool:
    return bool(metadata.get("xhs_strict_real_browser", True))


def _xhs_auto_click_submit_enabled(metadata: Dict[str, Any]) -> bool:
    return bool(metadata.get("xhs_auto_click_submit", False))


def _xhs_manual_submit_timeout_ms(metadata: Dict[str, Any]) -> int:
    try:
        seconds = int(metadata.get("xhs_manual_submit_timeout_seconds", 600))
    except (TypeError, ValueError):
        seconds = 600
    return max(30, min(seconds, 3600)) * 1000


async def _page_shows_publish_success_text(page: Page) -> bool:
    for sel in (
        'text="发布成功"',
        'text="定时发布成功"',
        "span:has-text('发布成功')",
    ):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue
    return False


async def _any_toast_success_visible(page: Page) -> bool:
    if await _page_shows_publish_success_text(page):
        return True
    for sel in Selectors.VERIFY.get("SUCCESS_TOAST", []) or []:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue
    return False


async def _check_publish_success(
    page: Page,
    *,
    timeout_ms: int = _POST_CLICK_VERIFY_MS,
    poll_interval_ms: int = 200,
) -> bool:
    try:
        if _url_indicates_success(page.url or ""):
            return True
    except Exception:
        pass
    for _ in range(0, max(poll_interval_ms, timeout_ms), poll_interval_ms):
        if await _any_toast_success_visible(page):
            return True
        try:
            url = page.url
            if _url_indicates_success(url):
                return True
            if await _manage_page_visible(page):
                return True
        except Exception:
            pass
        await page.wait_for_timeout(poll_interval_ms)
    return False


async def _manage_page_visible(page: Page) -> bool:
    if _is_xhs_publish_edit_url(page.url or ""):
        return False
    for sel in Selectors.VERIFY.get("MANAGE_PAGE_INDICATOR", []) or []:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue
    return False


async def _simulate_mouse_click_at(
    page: Page,
    x: float,
    y: float,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
    *,
    desc: str = "",
) -> bool:
    try:
        vp = await page.evaluate(
            "() => ({ w: window.innerWidth, h: window.innerHeight })",
        )
        vw, vh = float(vp.get("w") or 800), float(vp.get("h") or 600)
        tx = x + _random.uniform(-3, 3)
        ty = y + _random.uniform(-3, 3)
        from_x = vw / 2 + _random.uniform(-100, 100)
        from_y = vh / 2 + _random.uniform(-100, 100)
        try:
            from src.infrastructure.browser.human_behavior import HumanBehavior

            await HumanBehavior.mouse_move(
                page, from_x, from_y, tx, ty,
                steps=_random.randint(20, 35),
            )
        except Exception:
            await page.mouse.move(tx, ty, steps=_random.randint(10, 20))
            
        await page.mouse.move(tx + _random.uniform(-2, 2), ty + _random.uniform(-2, 2), steps=3)
        await page.wait_for_timeout(_random.randint(30, 80))
        await page.mouse.move(tx, ty, steps=2)
        await page.wait_for_timeout(_random.randint(80, 180))
        
        await page.mouse.down()
        await page.wait_for_timeout(_random.randint(60, 180))
        await page.mouse.up()
        
        logger.info("模拟鼠标点击发布钮 (%.0f, %.0f)%s", tx, ty, f" [{desc}]" if desc else "")
        return True
    except Exception as e:
        logger.debug("模拟鼠标点击失败: %s", e)
        return False


async def _scroll_xhs_publish_btn_into_view(
    page: Page,
    wait_ms: Optional[Callable[[int], int]] = None,
) -> None:
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
        locator = page.locator(".publish-page-content xhs-publish-btn, xhs-publish-btn[is-publish='true'], xhs-publish-btn").first
        if await locator.count() > 0:
            await HumanBehavior.scroll_to_locator(page, locator, target_ratio=0.8)
        
        settle = wait_ms(_SCROLL_SETTLE_MS) if wait_ms else _SCROLL_SETTLE_MS
        await page.wait_for_timeout(settle)
    except Exception as e:
        logger.debug("滚入 xhs-publish-btn 失败: %s", e)


async def _dismiss_blocking_overlays_before_submit(
    page: Page,
    wait_ms: Optional[Callable[[int], int]] = None,
) -> None:
    await unlock_before_submit(page, wait_ms or (lambda ms: ms))


async def _scroll_publish_form_for_submit(
    page: Page,
    wait_ms: Optional[Callable[[int], int]] = None,
) -> None:
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
        await HumanBehavior.scroll_to_bottom(page)
        
        settle = wait_ms(_SCROLL_SETTLE_MS) if wait_ms else _SCROLL_SETTLE_MS
        await page.wait_for_timeout(settle)
    except Exception:
        pass


async def _prepare_submit_surface(
    page: Page,
    wait_ms: Callable[[int], int],
    *,
    full_unlock: bool = True,
    scroll_form: bool = True,
) -> None:
    """发布前页面准备：完整解锁仅在有浮层/仍禁用时或首轮执行，轮询时走轻量路径。"""
    if full_unlock:
        await _dismiss_blocking_overlays_before_submit(page, wait_ms)
    elif await is_schedule_picker_visible(page):
        await _dismiss_blocking_overlays_before_submit(page, wait_ms)
    if scroll_form:
        await _scroll_publish_form_for_submit(page, wait_ms)
    await _scroll_xhs_publish_btn_into_view(page, wait_ms)


def _should_full_unlock_on_poll(poll_index: int, *, picker_open: bool, host_locked: bool) -> bool:
    if picker_open or host_locked:
        return True
    return poll_index == 0 or poll_index % _FULL_UNLOCK_EVERY_N_POLLS == 0


async def _resolve_legacy_submit_button(
    page: Page,
    primary_label: str,
) -> tuple[Optional[Locator], str]:
    for sel in (
        f".publish-page-content button:has-text('{primary_label}')",
        f".publish-page-footer button:has-text('{primary_label}')",
        f"#publish-container button:has-text('{primary_label}')",
    ):
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return loc, sel
        except Exception:
            continue
    return None, ""


async def _resolve_submit_button(
    page: Page,
    primary_label: str,
) -> tuple[Optional[Locator], str]:
    await _scroll_xhs_publish_btn_into_view(page)
    if await _page_has_xhs_publish_btn(page):
        host = await _get_xhs_publish_host(page)
        if await host.count() > 0:
            return host, _XHS_HOST_DESC
        return None, ""
    return await _resolve_legacy_submit_button(page, primary_label)


async def _click_xhs_publish_via_sr(
    page: Page,
    primary_label: str,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
    *,
    ignore_host_disabled: bool = False,
) -> bool:
    """主路径：获取按钮坐标后使用真实鼠标点击。"""
    host = await _get_xhs_publish_host(page)
    if await host.count() == 0:
        return False

    cx, cy, desc = await resolve_sr_click_center(
        host, primary_label, ignore_host_disabled=ignore_host_disabled,
    )
    if cx is not None and cy is not None:
        logger.info("通过 _sr 成功获取红钮坐标 (%.0f, %.0f)", cx, cy)
        return await _simulate_mouse_click_at(
            page, cx, cy, metadata, config, desc=desc,
        )

    try:
        box = await host.bounding_box()
        if box and box.get("width", 0) > 100:
            fallback_x = box["x"] + box["width"] - 120
            fallback_y = box["y"] + 45
            logger.info("无法获取红钮坐标，使用宿主右下角兜底坐标 (%.0f, %.0f)", fallback_x, fallback_y)
            return await _simulate_mouse_click_at(
                page, fallback_x, fallback_y, metadata, config, desc="host_offset_fallback_bbox",
            )
    except Exception as e:
        logger.debug("读取 host bounding_box 失败: %s", e)
        
    return False


async def _try_staged_click_despite_disabled(
    page: Page,
    primary_label: str,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
) -> bool:
    host = await _get_xhs_publish_host(page)
    if await host.count() == 0 or not await _xhs_publish_btn_disabled(host):
        return False
    logger.info("步骤8 分阶段兜底：submit-disabled 仍为 true，尝试 _sr 点击")
    USER_LOG.info(
        "[步骤8 点击发布] ▷ 发布钮仍被锁定，尝试一次 _sr 内点击（浮层/校验可能未结束）",
    )
    if await _click_xhs_publish_via_sr(
        page, primary_label, metadata, config, ignore_host_disabled=True,
    ):
        await page.wait_for_timeout(800)
        return await _check_publish_success(page, timeout_ms=3000)
    return False


async def _click_submit_with_fallback(
    page: Page,
    target_btn: Locator,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
    target_desc: str = "",
    primary_label: str = _SUBMIT_TEXT_IMMEDIATE,
    *,
    strict_real_browser: bool = False,
) -> None:
    if strict_real_browser:
        box = await target_btn.bounding_box()
        if not box:
            raise RuntimeError("发布按钮没有可点击区域")
        await _simulate_mouse_click_at(
            page,
            box["x"] + box["width"] / 2,
            box["y"] + box["height"] / 2,
            metadata,
            config,
            desc=target_desc or "strict-real-submit",
        )
        return

    if await _page_has_xhs_publish_btn(page) or target_desc == _XHS_HOST_DESC:
        if await _click_xhs_publish_via_sr(page, primary_label, metadata, config):
            return
        raise RuntimeError(
            f"未能通过 _sr 点击发布钮（主文案={primary_label}）",
        )

    try:
        await target_btn.click(timeout=8000)
        return
    except Exception:
        box = await target_btn.bounding_box()
        if not box:
            raise RuntimeError("发布按钮无 bounding_box") from None
        await _simulate_mouse_click_at(
            page,
            box["x"] + box["width"] / 2,
            box["y"] + box["height"] / 2,
            metadata,
            config,
            desc=target_desc or "legacy-submit",
        )


async def _wait_for_manual_submit(page: Page, metadata: Dict[str, Any]) -> PublishResult:
    timeout_ms = _xhs_manual_submit_timeout_ms(metadata)
    await attach_xhs_environment_snapshot(metadata, page, stage="pre_manual_submit")
    await _attach_submit_diagnostic_snapshot(metadata, page)
    try:
        await page.bring_to_front()
    except Exception:
        pass
    USER_LOG.info(
        "[XHS submit] Safe mode is waiting. Please click Publish in the browser."
    )
    logger.info(
        "XHS strict_real_browser: waiting up to %s seconds for manual publish",
        timeout_ms // 1000,
    )
    if await _check_publish_success(
        page,
        timeout_ms=timeout_ms,
        poll_interval_ms=500,
    ):
        current_url = page.url if not page.is_closed() else ""
        USER_LOG.info("[XHS submit] Publish success detected (%s)", current_url)
        return PublishResult(success=True, publish_url=current_url)
    await attach_xhs_environment_snapshot(metadata, page, stage="manual_submit_timeout")
    await _attach_submit_diagnostic_snapshot(metadata, page)
    return PublishResult(
        success=False,
        error_message=(
            "XHS safe mode filled the form and stopped before publishing; "
            "please click Publish manually in the browser."
        ),
        failed_step=_FAILED_STEP,
    )


class SubmitStep(BasePublishStep):
    _FAILED_STEP = _FAILED_STEP

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("===== 寻找并点击发布按钮（_sr Shadow）=====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}
        strict_real_browser = _xhs_strict_real_browser_enabled(metadata)
        auto_click_submit = _xhs_auto_click_submit_enabled(metadata)

        try:
            if page.is_closed():
                return PublishResult(
                    success=False,
                    error_message="发布页已关闭，无法点击发布按钮",
                    failed_step=self._FAILED_STEP,
                )
        except Exception:
            pass

        primary_label = await _primary_submit_label(page, metadata)
        mode_name = "定时发布" if _is_scheduled_submit_mode(primary_label) else "立即发布"
        logger.info("步骤8 模式: %s（submit-text 目标: %s）", mode_name, primary_label)
        USER_LOG.info("[步骤8 点击发布] ▶ 模式: %s", mode_name)

        max_ready_sec = _max_ready_btn_sec(primary_label)
        skip_ready_wait = False
        await _prepare_submit_surface(page, wait_ms, full_unlock=True, scroll_form=True)

        if await _page_has_xhs_publish_btn(page):
            if await _xhs_submit_clickable(
                page, primary_label, strict_real_browser=strict_real_browser,
            ):
                skip_ready_wait = True
                logger.info("步骤8 发布钮已就绪，跳过等待轮询")
                USER_LOG.info("[步骤8 点击发布] ▷ 发布钮已就绪，直接点击")

            wait_started = _time.monotonic()
            poll_counter = {"n": 0}
            staged_done = {"v": False}
            last_host_state: Dict[str, Any] = {}
            label_state = {"primary": primary_label}
            clickable = skip_ready_wait

            async def _wait_xhs_clickable():
                label_state["primary"] = await _primary_submit_label(page, metadata)
                current = label_state["primary"]
                picker_open = await is_schedule_picker_visible(page)
                host_locked = not await _xhs_host_submit_unlocked(page)
                full_unlock = _should_full_unlock_on_poll(
                    poll_counter["n"],
                    picker_open=picker_open,
                    host_locked=host_locked,
                )
                await _prepare_submit_surface(
                    page,
                    wait_ms,
                    full_unlock=full_unlock,
                    scroll_form=poll_counter["n"] == 0,
                )
                if await _xhs_submit_clickable(
                    page, current, strict_real_browser=strict_real_browser,
                ):
                    return True
                elapsed = _time.monotonic() - wait_started
                if (
                    not strict_real_browser
                    and not staged_done["v"]
                    and elapsed >= _STAGED_FALLBACK_WAIT_SEC
                ):
                    staged_done["v"] = True
                    if await _try_staged_click_despite_disabled(
                        page, current, metadata, config,
                    ):
                        return True
                poll_counter["n"] += 1
                if poll_counter["n"] % _SUBMIT_WAIT_STATUS_LOG_EVERY_POLLS == 0:
                    st = await _read_xhs_publish_host_state(
                        page,
                        current,
                        include_shadow_probe=not strict_real_browser,
                    )
                    last_host_state.clear()
                    last_host_state.update(st)
                    USER_LOG.info(
                        "[步骤8 点击发布] ▷ 仍等待「%s」可点"
                        "（disabled=%s，浮层=%s，_sr红钮=%s）",
                        current,
                        st.get("submit_disabled"),
                        "开" if st.get("schedule_picker_open") else "关",
                        "就绪" if st.get("sr_red_ready") else "未就绪",
                    )
                return None

            if not skip_ready_wait:
                clickable = await PluginWaitHelper.wait_for_condition(
                    page,
                    _wait_xhs_clickable,
                    timeout_ms=wait_ms(max_ready_sec * 1000),
                    poll_interval_ms=wait_ms(_WAIT_POLL_INTERVAL_MS),
                    pause_callback=lambda: self._await_pause(metadata),
                    on_poll=lambda _a: logger.info("发布钮尚未可点，继续等待…"),
                )
            primary_label = label_state["primary"]
            if not clickable and not await _xhs_submit_clickable(
                page, primary_label, strict_real_browser=strict_real_browser,
            ):
                if not last_host_state:
                    last_host_state.update(
                        await _read_xhs_publish_host_state(
                            page,
                            primary_label,
                            include_shadow_probe=not strict_real_browser,
                        ),
                    )
                await _attach_submit_diagnostic_snapshot(metadata, page)
                return PublishResult(
                    success=False,
                    error_message=_format_submit_timeout_message(
                        primary_label, last_host_state, max_sec=max_ready_sec,
                    ),
                    failed_step=self._FAILED_STEP,
                )
        else:
            async def _wait_legacy_button():
                loc, _ = await _resolve_submit_button(page, primary_label)
                return loc

            legacy_loc = await PluginWaitHelper.wait_for_condition(
                page,
                _wait_legacy_button,
                timeout_ms=wait_ms(_MAX_FIND_BTN_SEC * 1000),
                poll_interval_ms=wait_ms(1000),
                pause_callback=lambda: self._await_pause(metadata),
            )
            if not legacy_loc:
                return PublishResult(
                    success=False,
                    error_message=f"未找到 xhs-publish-btn（已等待约 {_MAX_FIND_BTN_SEC} 秒）",
                    failed_step=self._FAILED_STEP,
                )

        if strict_real_browser and not auto_click_submit:
            metadata["xhs_manual_submit_required"] = True
            return await _wait_for_manual_submit(page, metadata)

        last_click_error: Optional[str] = None
        post_verify_ms = (
            _POST_CLICK_VERIFY_MS_FAST
            if skip_ready_wait
            else _POST_CLICK_VERIFY_MS
        )
        for attempt in range(1, _MAX_SUBMIT_CLICK_ATTEMPTS + 1):
            primary_label = await _primary_submit_label(page, metadata)
            need_full = attempt > 1 or await is_schedule_picker_visible(page)
            if not await _xhs_host_submit_unlocked(page):
                need_full = True
            await _prepare_submit_surface(
                page,
                wait_ms,
                full_unlock=need_full,
                scroll_form=attempt == 1,
            )

            loc, selector = await _resolve_submit_button(page, primary_label)
            if not loc:
                await page.wait_for_timeout(wait_ms(500))
                continue

            logger.info("第 %d 次点击：%s", attempt, selector)
            try:
                await self._await_pause(metadata)
                try:
                    from src.infrastructure.anti_risk.delays import random_delay
                    await random_delay(page, wait_ms(200), metadata, config)
                except Exception:
                    await page.wait_for_timeout(wait_ms(200))

                await _click_submit_with_fallback(
                    page,
                    loc,
                    metadata,
                    config,
                    selector,
                    primary_label,
                    strict_real_browser=strict_real_browser,
                )
                USER_LOG.info("[步骤8 点击发布] ▶ 第 %d 次已触发「%s」", attempt, primary_label)
            except Exception as e:
                last_click_error = str(e)
                logger.warning("第 %d 次点击失败: %s", attempt, e)
                await page.wait_for_timeout(wait_ms(400))
                continue

            if await _check_publish_success(
                page,
                timeout_ms=wait_ms(post_verify_ms),
                poll_interval_ms=wait_ms(150),
            ):
                current_url = page.url if not page.is_closed() else ""
                logger.info("第 %d 次点击后发布成功", attempt)
                USER_LOG.info("[步骤8 点击发布] ✓ 发布成功 (%s)", current_url)
                # 发布成功后：模拟用户浏览结果页的收尾行为，避免「立即退出」的自动化特征
                await self._do_post_publish_browse(page, metadata, config, speed_rate)
                return PublishResult(success=True, publish_url=current_url)

            USER_LOG.warning("[步骤8 点击发布] 第 %d 次未确认成功，将重试", attempt)
            await page.wait_for_timeout(wait_ms(400))

        if last_click_error:
            await _attach_submit_diagnostic_snapshot(metadata, page)
            return PublishResult(
                success=False,
                error_message=f"点击「{primary_label}」失败: {last_click_error}",
                failed_step=self._FAILED_STEP,
            )

        try:
            error_checks = [
                (Selectors.SECURITY["PUBLISH_TOAST_ERROR"], "发布失败/错误"),
                (Selectors.SECURITY["PUBLISH_TOAST_FREQ"], "操作频繁"),
            ]
            for selector_list, desc in error_checks:
                for sel in selector_list:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            try:
                                text = await loc.inner_text()
                                desc = f"{desc}: {text}"
                            except Exception:
                                pass
                            if "频繁" in desc:
                                return NeedsAction(
                                    action="need_retry",
                                    message=f"发布受阻: {desc}",
                                )
                            return PublishResult(
                                success=False,
                                error_message=f"发布受阻: {desc}",
                                failed_step=self._FAILED_STEP,
                            )
                    except Exception:
                        continue
        except Exception:
            pass

        return await self._verify_publish_result(page, metadata)

    async def _verify_publish_result(
        self, page: Page, metadata: Dict[str, Any],
    ) -> PublishResult:
        logger.info("===== 验证发布结果 =====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        config = metadata.get("anti_risk_config") or {}
        try:
            current_url = page.url
            if _url_indicates_success(current_url) or await _manage_page_visible(page):
                USER_LOG.info("[步骤8 点击发布] ✓ 发布成功 (%s)", current_url)
                await self._do_post_publish_browse(page, metadata, config, speed_rate)
                return PublishResult(success=True, publish_url=current_url)
        except Exception:
            pass

        poll_interval_ms = 200
        total_wait_ms = 10000
        for _ in range(0, total_wait_ms, poll_interval_ms):
            if await _any_toast_success_visible(page):
                USER_LOG.info("[步骤8 点击发布] ✓ 发布成功（页面提示）")
                await self._do_post_publish_browse(page, metadata, config, speed_rate)
                return PublishResult(success=True, publish_url=page.url)
            try:
                current_url = page.url
                if _url_indicates_success(current_url) or await _manage_page_visible(page):
                    USER_LOG.info("[步骤8 点击发布] ✓ 发布成功 (%s)", current_url)
                    await self._do_post_publish_browse(page, metadata, config, speed_rate)
                    return PublishResult(success=True, publish_url=current_url)
            except Exception:
                pass
            await page.wait_for_timeout(poll_interval_ms)

        return PublishResult(
            success=False,
            error_message="发布后未能确认成功（无 published=true / 成功页 / Toast），请手动检查",
            failed_step=self._FAILED_STEP,
        )

    async def _do_post_publish_browse(
        self,
        page: Page,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        speed_rate: float,
    ) -> None:
        """发布成功后的随机浏览收尾，模拟用户查看发布结果页后自然离开。

        执行 1-3 次页面随机滚动，总停留 8-25 秒。
        页面关闭时静默跳过，不影响发布结果判定。
        """
        if page.is_closed():
            return
        try:
            import random as _rand
            from src.infrastructure.anti_risk.delays import random_delay

            # 计划总停留时间（受 speed_rate 影响）
            total_stay_ms = int(_rand.uniform(8000, 25000) * max(0.5, speed_rate))
            scroll_times = _rand.randint(1, 3)
            per_scroll_ms = total_stay_ms // max(1, scroll_times + 1)

            USER_LOG.info(
                "[步骤8 点击发布] ▷ 发布成功，浏览结果页 %.0f 秒…",
                total_stay_ms / 1000,
            )
            logger.info(
                "发布后收尾浏览：计划滚动 %d 次，总停留约 %.0fs",
                scroll_times,
                total_stay_ms / 1000,
            )

            for i in range(scroll_times):
                if page.is_closed():
                    break
                await self._await_pause(metadata)
                # 随机向下或向上轻微滚动，模拟查看发布结果
                direction = _rand.choice([1, 1, -1])  # 偏向向下浏览
                scroll_px = _rand.uniform(80, 280)
                try:
                    if scroll_px > 50:
                        await page.mouse.wheel(0, direction * scroll_px)
                except Exception:
                    pass
                # 每次滚动后随机停留
                if not page.is_closed():
                    await random_delay(page, per_scroll_ms, metadata, config)

            # 最终停留（剩余时间）
            if not page.is_closed():
                remaining_ms = max(0, total_stay_ms - scroll_times * per_scroll_ms)
                if remaining_ms > 500:
                    await random_delay(page, remaining_ms, metadata, config)

            logger.info("发布后收尾浏览完成")
        except Exception as e:
            logger.debug("发布后收尾浏览异常（已忽略，不影响结果）: %s", e)
