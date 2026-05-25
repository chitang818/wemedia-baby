# -*- coding: utf-8 -*-
"""
步骤8：点击发布
文件路径: src/plugins/pro/xiaohongshu/steps/step_08_submit.py

流程：
  1. 在发布表单区内定位发布按钮，等待其出现并可点
  2. 多级点击兜底（标准 click → 拟人 → force → 坐标）
  3. 若未响应则第二次点击
  4. 检查拦截弹窗（错误提示、操作频繁等）
  5. 验证发布成功：Toast / URL 离开发布页 / 笔记管理

字段依赖：
  - metadata['speed_rate']: 影响等待与延时
  - metadata['anti_risk_config']: 风控配置
"""
from __future__ import annotations

import logging
import random as _random
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, NeedsAction, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_FAILED_STEP = "SubmitStep"
_MAX_FIND_BTN_SEC = 10
_MAX_READY_BTN_SEC = 120


def _is_xhs_publish_edit_url(url: str) -> bool:
    """是否仍在创作者发布编辑页。"""
    u = (url or "").lower()
    return "creator.xiaohongshu.com" in u and "/publish/publish" in u


def _publish_form_roots(page: Page) -> list[Locator]:
    roots: list[Locator] = []
    for sel in Selectors.PUBLISH.get("SUBMIT_SCOPE", []) or []:
        roots.append(page.locator(sel).first)
    if not roots:
        roots.append(page.locator(".publish-page-content").first)
    return roots


async def _submit_control_ready(loc: Locator) -> bool:
    """按钮可见、未 disabled、未 aria-disabled。"""
    try:
        if not await loc.is_visible():
            return False
        if not await loc.is_enabled():
            return False
        dis = await loc.get_attribute("disabled")
        if dis is not None and str(dis).lower() not in ("", "false"):
            return False
        aria = (await loc.get_attribute("aria-disabled") or "").lower()
        if aria == "true":
            return False
        cls = (await loc.get_attribute("class") or "").lower()
        if "disabled" in cls and "button" in cls:
            return False
        return True
    except Exception:
        return False


async def _is_btn_actionable(loc: Locator) -> bool:
    """简化遮盖检测：有尺寸且 enabled。"""
    try:
        if not await _submit_control_ready(loc):
            return False
        box = await loc.bounding_box()
        return bool(box and box.get("width", 0) >= 1 and box.get("height", 0) >= 1)
    except Exception:
        return True


async def _resolve_submit_button(page: Page) -> Tuple[Optional[Locator], str]:
    """在发布主表单区内解析「发布」按钮。"""
    candidates: list[Tuple[Locator, str]] = []

    for root in _publish_form_roots(page):
        try:
            if await root.count() == 0:
                continue
            by_role = root.get_by_role("button", name="发布", exact=True)
            cnt = await by_role.count()
            for i in range(cnt):
                loc = by_role.nth(i)
                try:
                    if await loc.is_visible():
                        candidates.append((loc, f"scope.get_by_role(发布)[{i}]"))
                except Exception:
                    continue
        except Exception:
            continue

    if not candidates:
        for sel in Selectors.PUBLISH.get("SUBMIT_BTN", []) or []:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                if await loc.is_visible():
                    candidates.append((loc, sel))
                    break
            except Exception:
                continue

    if not candidates:
        return None, ""

    if len(candidates) == 1:
        return candidates[0]

    logger.info("发现 %d 个「发布」按钮候选，执行遮盖检测筛选…", len(candidates))
    for loc, desc in candidates:
        if await _is_btn_actionable(loc):
            logger.info("选定发布按钮: %s", desc)
            return loc, desc
    logger.warning("候选均未通过遮盖检测，退化使用第一个")
    return candidates[0]


async def _click_submit_with_fallback(
    page: Page,
    target_btn: Locator,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    try:
        await target_btn.click(timeout=8000)
        logger.info("发布按钮标准 click 成功")
        return
    except Exception as e:
        logger.info("标准 click 失败，尝试拟人移动: %s", e)

    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior

        box = await target_btn.bounding_box()
        if box:
            vp = await page.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
            vw, vh = vp.get("w") or 800, vp.get("h") or 600
            from_x = _random.uniform(0, max(1, vw))
            from_y = _random.uniform(0, max(1, vh))
            to_x = box["x"] + box["width"] * _random.uniform(0.3, 0.7)
            to_y = box["y"] + box["height"] * _random.uniform(0.3, 0.7)
            await HumanBehavior.mouse_move(
                page, from_x, from_y, to_x, to_y, steps=_random.randint(18, 30),
            )
            await page.wait_for_timeout(_random.randint(80, 200))
        await target_btn.click(timeout=8000)
        logger.info("拟人移动后 click 成功")
        return
    except Exception as e:
        logger.info("拟人 click 失败，尝试 force: %s", e)

    try:
        await target_btn.click(timeout=8000, force=True)
        logger.info("force click 成功")
        return
    except Exception as e:
        logger.info("force click 失败，坐标兜底: %s", e)

    box = await target_btn.bounding_box()
    if not box:
        raise RuntimeError("发布按钮无 bounding_box")
    await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    logger.info("坐标兜底 click 执行完毕")


async def _any_toast_success_visible(page: Page) -> bool:
    for sel in Selectors.VERIFY.get("SUCCESS_TOAST", []) or []:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue
    return False


def _url_indicates_success(url: str) -> bool:
    if not url or "xiaohongshu.com" not in url.lower():
        return False
    if _is_xhs_publish_edit_url(url):
        return False
    for kw in Selectors.VERIFY.get("SUCCESS_URL_KEYWORDS", []) or []:
        if kw in url:
            return True
    if "creator.xiaohongshu.com" in url.lower() and "/publish/publish" not in url.lower():
        return True
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


class SubmitStep(BasePublishStep):
    _FAILED_STEP = _FAILED_STEP

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """点击发布按钮并验证最终结果。"""
        await self._await_pause(metadata)
        logger.info("===== 寻找并点击发布按钮 =====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        target_btn: Optional[Locator] = None
        target_selector = ""

        async def _find_submit_button():
            loc, selector = await _resolve_submit_button(page)
            if loc:
                return loc, selector
            return None

        found = await PluginWaitHelper.wait_for_condition(
            page,
            _find_submit_button,
            timeout_ms=wait_ms(_MAX_FIND_BTN_SEC * 1000),
            poll_interval_ms=wait_ms(1000),
            pause_callback=lambda: self._await_pause(metadata),
            on_poll=lambda attempt: logger.info(
                "发布按钮尚未出现，第 %d 次…", attempt + 1,
            ),
        )
        if found:
            target_btn, target_selector = found
        else:
            return PublishResult(
                success=False,
                error_message="未找到发布按钮（已等待约 10 秒），页面结构可能已变更",
                failed_step=self._FAILED_STEP,
            )

        async def _wait_ready_submit_button():
            loc, selector = await _resolve_submit_button(page)
            if loc:
                try:
                    await loc.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass
                if await _submit_control_ready(loc):
                    return loc, selector
            return None

        ready = await PluginWaitHelper.wait_for_condition(
            page,
            _wait_ready_submit_button,
            timeout_ms=_MAX_READY_BTN_SEC * 1000,
            poll_interval_ms=wait_ms(700),
            pause_callback=lambda: self._await_pause(metadata),
            on_poll=lambda _attempt: logger.info(
                "发布按钮已出现但尚不可点，继续等待（转码或必填项）…",
            ),
        )
        if ready:
            target_btn, target_selector = ready
        else:
            loc, selector = await _resolve_submit_button(page)
            if loc and await _submit_control_ready(loc):
                target_btn, target_selector = loc, selector
            else:
                return PublishResult(
                    success=False,
                    error_message=f"等待超时（{_MAX_READY_BTN_SEC} 秒），发布按钮始终不可点",
                    failed_step=self._FAILED_STEP,
                )

        if target_btn is None or not await _submit_control_ready(target_btn):
            return PublishResult(
                success=False,
                error_message="发布按钮状态异常，无法点击",
                failed_step=self._FAILED_STEP,
            )

        logger.info("发布按钮已就绪（%s），执行点击…", target_selector)
        try:
            await self._await_pause(metadata)
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, wait_ms(200), metadata, config)
            except Exception:
                await page.wait_for_timeout(wait_ms(200))

            try:
                await target_btn.scroll_into_view_if_needed()
                await page.wait_for_timeout(150)
            except Exception:
                pass

            await _click_submit_with_fallback(page, target_btn, metadata, config)
            USER_LOG.info("[步骤8 点击发布] ▶ 已点击发布按钮")

            detected = False
            poll_ms = wait_ms(200)
            for _ in range(10):
                await page.wait_for_timeout(poll_ms)
                if await _any_toast_success_visible(page):
                    detected = True
                    logger.info("检测到「发布成功」提示")
                    break
                try:
                    if _url_indicates_success(page.url):
                        detected = True
                        logger.info("检测到页面跳转: %s", page.url)
                        break
                except Exception:
                    pass

            if not detected:
                logger.info("未检测到即时反馈，执行第二次点击…")
                try:
                    loc, _ = await _resolve_submit_button(page)
                    if loc and await loc.count() > 0:
                        await _click_submit_with_fallback(page, loc, metadata, config)
                        logger.info("已执行第二次点击")
                except Exception as e:
                    logger.warning("第二次点击异常: %s", e)

        except Exception as e:
            return PublishResult(
                success=False,
                error_message=f"点击发布按钮失败: {e}",
                failed_step=self._FAILED_STEP,
            )

        logger.info("检查是否存在错误弹窗…")
        try:
            from src.infrastructure.anti_risk.delays import random_delay
            await random_delay(page, wait_ms(300), metadata, config)
        except Exception:
            await page.wait_for_timeout(wait_ms(300))

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
                            logger.warning("检测到异常: %s", desc)
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
        except Exception as e:
            logger.debug("检查弹窗异常: %s", e)

        return await self._verify_publish_result(page, metadata)

    async def _verify_publish_result(
        self, page: Page, metadata: Dict[str, Any],
    ) -> PublishResult:
        """验证发布结果。"""
        logger.info("===== 验证发布结果 =====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        try:
            current_url = page.url
            if _url_indicates_success(current_url):
                logger.info("页面已跳转: %s", current_url)
                USER_LOG.info("[步骤8 点击发布] ✓ 发布成功 (%s)", current_url)
                return PublishResult(success=True, publish_url=current_url)
            if await _manage_page_visible(page):
                logger.info("检测到笔记管理页特征")
                USER_LOG.info("[步骤8 点击发布] ✓ 发布成功（笔记管理）")
                return PublishResult(success=True, publish_url=current_url)
        except Exception:
            pass

        poll_interval_ms = 200
        total_wait_ms = 8000
        logger.info("轮询检测发布结果…")
        for _ in range(0, total_wait_ms, poll_interval_ms):
            if await _any_toast_success_visible(page):
                logger.info("检测到「发布成功」Toast")
                USER_LOG.info("[步骤8 点击发布] ✓ 发布成功！")
                return PublishResult(success=True, publish_url=page.url)

            try:
                current_url = page.url
                if _url_indicates_success(current_url):
                    USER_LOG.info("[步骤8 点击发布] ✓ 发布成功 (%s)", current_url)
                    return PublishResult(success=True, publish_url=current_url)
                if await _manage_page_visible(page):
                    USER_LOG.info("[步骤8 点击发布] ✓ 发布成功（笔记管理）")
                    return PublishResult(success=True, publish_url=current_url)
            except Exception:
                pass

            await page.wait_for_timeout(poll_interval_ms)

        try:
            await PluginWaitHelper.wait_for_url_or_selectors(
                page,
                initial_url=page.url,
                timeout_ms=int(5000 * speed_rate),
                poll_interval_ms=300,
                pause_callback=lambda: self._await_pause(metadata),
            )
            current_url = page.url
            if _url_indicates_success(current_url) or await _manage_page_visible(page):
                USER_LOG.info("[步骤8 点击发布] ✓ 发布成功 (%s)", current_url)
                return PublishResult(success=True, publish_url=current_url)
        except Exception:
            pass

        logger.warning("未能确认发布成功，请手动检查")
        return PublishResult(
            success=False,
            error_message="发布后未能确认成功（未检测到发布成功提示或页面跳转），请手动检查",
            failed_step=self._FAILED_STEP,
        )
