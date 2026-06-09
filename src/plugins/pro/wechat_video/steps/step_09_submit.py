# -*- coding: utf-8 -*-
"""
步骤9：点击发布（提交发表）
文件路径：src/plugins/pro/wechat_video/steps/step_09_submit.py

说明：
  - 本步骤会在「高级设置」（步骤8：定时/音乐/短标题/原创声明等）之后执行。
  - 负责点击「发表」并处理发布后的弹窗与校验逻辑（例如原创声明关联的弹窗流程）。
"""

import logging
import re
import time
from typing import Any, Dict, Union

from src.infrastructure.browser.automation_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, NeedsAction, StepOutcome
from ..selectors import Selectors
from ..shadow_mouse import (
    js_handle_click_biased_right,
    real_mouse_click_bbox_biased_right,
    real_mouse_click_xy,
)
from ..wujie_shadow import (
    WUJIE_SHADOW_QUERY_SELECTOR_FN_JS,
    WUJIE_SHADOW_RESOLVE_SUBMIT_BTN_JS,
)
from .step_08B_schedule import (
    _parse_schedule_time,
    _read_schedule_picker_state,
    _schedule_matches_target,
)
from .step_08D_original import _get_is_original, wechat_main_original_checked

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class SubmitStep(BasePublishStep):
    """Click submit and verify publish result."""

    _WUJIE_SHADOW_QUERY_FN = WUJIE_SHADOW_QUERY_SELECTOR_FN_JS

    _POST_SUBMIT_AD_SHARE_MODAL_XY_JS = r"""
(isOrig) => {
    function collectDialogs() {
        const out = [];
        try {
            document.querySelectorAll('.weui-desktop-dialog').forEach((d) => out.push(d));
        } catch (e) {}
        try {
            document.querySelectorAll('wujie-app').forEach((w) => {
                if (w.shadowRoot) {
                    w.shadowRoot.querySelectorAll('.weui-desktop-dialog').forEach((d) => out.push(d));
                }
            });
        } catch (e) {}
        return out;
    }
    const dlgs = collectDialogs();
    for (const dlg of dlgs) {
        const text = dlg.innerText || '';
        const isAdShare =
            text.includes('广告分成') ||
            text.includes('创作分成计划') ||
            text.includes('声明原创的视频有机会');
        if (!isAdShare) continue;
        const nodes = dlg.querySelectorAll(
            'button, a.weui-desktop-btn, a[class*="weui-desktop-btn"]'
        );
        for (const b of nodes) {
            const tx = (b.textContent || '').replace(/\s+/g, '').trim();
            let hit = false;
            let kind = '';
            if (!isOrig && (tx === '直接发表' || tx === '直接发布')) {
                hit = true;
                kind = 'direct';
            }
            if (isOrig && tx === '声明原创') {
                hit = true;
                kind = 'original';
            }
            if (!hit) continue;
            try {
                b.scrollIntoView({ block: 'center', inline: 'nearest' });
            } catch (e) {}
            const r = b.getBoundingClientRect();
            if (r.width > 1 && r.height > 1) {
                return {
                    kind: kind,
                    x: r.left + r.width / 2,
                    y: r.top + r.height / 2,
                };
            }
        }
    }
    return null;
}
"""

    @staticmethod
    async def _shadow_node_is_submit_button(node: Any) -> bool:
        try:
            return await node.evaluate(
                """(n) => {
                if (!n || n.tagName !== 'BUTTON') return false;
                const t = (n.innerText || n.textContent || '').replace(/\\s+/g, '').trim();
                if (t === '手机预览' || t === '保存草稿') return false;
                return t === '发表';
            }"""
            )
        except Exception:
            return False

    @staticmethod
    async def _locator_is_strict_submit_button(loc: Locator) -> bool:
        try:
            return await loc.evaluate(
                """(n) => {
                if (!n || n.tagName !== 'BUTTON') return false;
                const t = (n.innerText || n.textContent || '').replace(/\\s+/g, '').trim();
                if (t === '手机预览' || t === '保存草稿') return false;
                return t === '发表';
            }"""
            )
        except Exception:
            return False

    async def _handle_post_submit_original_revenue_modal(
        self,
        page: Page,
        metadata: Dict[str, Any],
        *,
        total_ms: int = 8000,
    ) -> None:
        is_orig = _get_is_original(metadata)
        deadline = time.monotonic() + total_ms / 1000.0
        while time.monotonic() < deadline:
            try:
                r = await page.evaluate(self._POST_SUBMIT_AD_SHARE_MODAL_XY_JS, is_orig)
            except Exception as e:
                logger.debug("[视频号] 检测发布后广告分成弹窗异常: %s", e)
                r = None
            if isinstance(r, dict) and "x" in r and "y" in r and "kind" in r:
                xy = (float(r["x"]), float(r["y"]))
                if await real_mouse_click_xy(page, xy):
                    if r.get("kind") == "direct":
                        logger.info("[视频号] 已点击“直接发表”关闭广告分成弹窗")
                        USER_LOG.info("%s ▶ 已点“直接发表”", self._step_prefix(metadata, "点击发布"))
                    else:
                        logger.info("[视频号] 已点击弹窗内“声明原创”")
                        USER_LOG.info("%s ▶ 已点弹窗“声明原创”", self._step_prefix(metadata, "点击发布"))
                    await page.wait_for_timeout(350)
                    return
                logger.warning("[视频号] 广告分成弹窗命中按钮但 mouse.click 失败")
            await page.wait_for_timeout(200)

    async def _handle_keep_editing_dialog(
        self, page: Page, metadata: Dict[str, Any], *, total_ms: int = 3000
    ) -> bool:
        deadline = time.monotonic() + total_ms / 1000.0
        while time.monotonic() < deadline:
            try:
                title = page.get_by_text("将此次编辑保留？").first
                if await title.count() > 0 and await title.is_visible():
                    discard = page.get_by_role("button", name=re.compile(r"^不保存$")).first
                    if await discard.count() > 0 and await discard.is_visible():
                        await discard.click(timeout=3000)
                        logger.info("[视频号] 已处理“将此次编辑保留？”弹窗：点击“不保存”")
                        USER_LOG.info(
                            "%s ▶ 已处理编辑保留弹窗：不保存",
                            self._step_prefix(metadata, "点击发布"),
                        )
                        await page.wait_for_timeout(300)
                        return True
            except Exception as e:
                logger.debug("[视频号] 处理编辑保留弹窗异常: %s", e)
            await page.wait_for_timeout(150)
        return False

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("[视频号] 发表步骤：点击发表按钮")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}
        file_type = (metadata.get("file_type") or "video").lower()

        submit_selectors = Selectors.PUBLISH.get("SUBMIT_BTN", [])
        target_btn: Union[Locator, Any, None] = None

        try:
            await page.wait_for_selector(
                "#container-wrap > div.container-center > div > wujie-app",
                state="attached",
                timeout=5000,
            )
        except Exception as e:
            logger.debug("[视频号] 等待 Wujie 容器异常: %s", e)

        try:
            resolved = await page.evaluate_handle(WUJIE_SHADOW_RESOLVE_SUBMIT_BTN_JS)
            if resolved and str(resolved) != "JSHandle@null":
                if await self._shadow_node_is_submit_button(resolved):
                    target_btn = resolved
                    logger.info("[视频号] 已精准解析底部“发表”按钮（已排除手机预览/保存草稿）")
        except Exception as e:
            logger.debug("[视频号] Shadow 精准解析发表按钮异常: %s", e)

        if target_btn is None:
            try:
                a11y = page.get_by_role("button", name=re.compile(r"^发表$")).first
                if await a11y.count() > 0 and await a11y.is_visible():
                    if await self._locator_is_strict_submit_button(a11y):
                        target_btn = a11y
                        logger.info("[视频号] 使用无障碍语义定位发表按钮")
            except Exception as e:
                logger.debug("[视频号] get_by_role(发表) 未命中: %s", e)

        for sel in submit_selectors:
            if target_btn is not None:
                break
            try:
                el = await page.evaluate_handle(self._WUJIE_SHADOW_QUERY_FN, sel)
                if el and str(el) != "JSHandle@null":
                    is_visible = await el.evaluate(
                        "(node) => node.offsetWidth > 0 || node.offsetHeight > 0 || node.getClientRects().length > 0"
                    )
                    if not is_visible:
                        continue
                    if not await self._shadow_node_is_submit_button(el):
                        continue
                    target_btn = el
                    logger.info("[视频号] 找到发表按钮: %s", sel)
                    break
            except Exception as e:
                logger.debug("[视频号] 搜索发表按钮异常: %s", e)

        if not target_btn:
            return PublishResult(
                success=False,
                error_message="未找到发表按钮，可能页面结构已变化",
                failed_step="SubmitStep",
            )

        async def _submit_button_ready() -> bool:
            try:
                if isinstance(target_btn, Locator):
                    is_disabled = not await target_btn.is_enabled()
                else:
                    is_disabled = await target_btn.evaluate("(node) => node.disabled")
            except Exception:
                is_disabled = False
            return not is_disabled

        is_ready = bool(
            await PluginWaitHelper.wait_for_condition(
                page,
                _submit_button_ready,
                timeout_ms=180_000,
                poll_interval_ms=700,
                pause_callback=lambda: self._await_pause(metadata),
                on_poll=lambda _attempt: logger.info(
                    "[???] ??????????????..."
                ),
            )
        )

        if not is_ready:
            return PublishResult(
                success=False,
                error_message="等待发布按钮可用超时",
                failed_step="SubmitStep",
            )

        sched_raw = metadata.get("scheduled_publish_time") or metadata.get("schedule_time") or ""
        if sched_raw:
            parsed_s = _parse_schedule_time(str(sched_raw).strip())
            if parsed_s:
                st_pre = await _read_schedule_picker_state(page)
                ok_s, msg_s = _schedule_matches_target(st_pre, parsed_s)
                if not ok_s:
                    logger.error("[视频号] 发表前定时校验失败: %s", msg_s)
                    return PublishResult(
                        success=False,
                        error_message=f"发表前检测到定时时间与任务不一致。详情: {msg_s}",
                        failed_step="SubmitStep",
                    )
                logger.info("[视频号] 发表前定时校验通过 → %s", sched_raw)

        if file_type == "video" and _get_is_original(metadata):
            main_ok, main_det = await wechat_main_original_checked(page)
            if not main_ok:
                logger.error("[视频号] 发表前校验：表单“声明原创”未勾选（detail=%s）", main_det)
                return PublishResult(
                    success=False,
                    error_message=f"发表前检测到表单“声明原创”未勾选。（detail={main_det}）",
                    failed_step="SubmitStep",
                )
            logger.info("[视频号] 发表前声明原创主勾选校验通过")

        logger.info("[视频号] 发布按钮已就绪，准备点击...")
        try:
            await self._await_pause(metadata)
            try:
                from src.infrastructure.anti_risk.delays import random_delay

                await random_delay(page, wait_ms(300), metadata, config)
            except Exception:
                await page.wait_for_timeout(wait_ms(300))

            if isinstance(target_btn, Locator):
                await target_btn.scroll_into_view_if_needed()
            else:
                await target_btn.evaluate(
                    "(node) => { try { node.scrollIntoView({behavior: 'smooth', block: 'center'}); } catch (e) {} }"
                )
            await page.wait_for_timeout(300)

            if isinstance(target_btn, Locator):
                box = await target_btn.bounding_box()
                if not await real_mouse_click_bbox_biased_right(page, box or {}):
                    await target_btn.click(timeout=10000)
            else:
                if not await js_handle_click_biased_right(page, target_btn):
                    return PublishResult(
                        success=False,
                        error_message="发表按钮真实鼠标点击失败，请勿遮挡浏览器窗口",
                        failed_step="SubmitStep",
                    )

            logger.info("[视频号] 已点击发布按钮（第一次）")
            USER_LOG.info("%s ▶ 已点击发布按钮", self._step_prefix(metadata, "点击发布"))

            await self._handle_post_submit_original_revenue_modal(
                page, metadata, total_ms=int(wait_ms(6000))
            )

            detected_early = False
            for _ in range(10):
                await page.wait_for_timeout(200)
                try:
                    success_sel = Selectors.VERIFY.get("SUCCESS_TOAST", "")
                    if success_sel:
                        loc = page.locator(success_sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            detected_early = True
                            logger.info("[视频号] 2s 内检测到发布成功标识")
                            break
                except Exception as e:
                    logger.debug("[视频号] 2s 内检测成功标识异常: %s", e)
                try:
                    if self._is_manage_page(page.url):
                        detected_early = True
                        logger.info("[视频号] 2s 内检测到页面已跳转")
                        break
                except Exception as e:
                    logger.debug("[视频号] 2s 内检测 URL 异常: %s", e)
                try:
                    if await self._handle_keep_editing_dialog(page, metadata, total_ms=150):
                        detected_early = True
                        break
                except Exception as e:
                    logger.debug("[视频号] 早期处理编辑保留弹窗异常: %s", e)

            if not detected_early:
                logger.info("[视频号] 2s 内未检测到响应，执行第二次点击...")
                try:
                    h2 = await page.evaluate_handle(WUJIE_SHADOW_RESOLVE_SUBMIT_BTN_JS)
                    if h2 and str(h2) != "JSHandle@null" and await self._shadow_node_is_submit_button(h2):
                        await h2.evaluate(
                            "(node) => { try { node.scrollIntoView({behavior: 'smooth', block: 'center'}); } catch (e) {} }"
                        )
                        await page.wait_for_timeout(100)
                        if not await js_handle_click_biased_right(page, h2):
                            if not isinstance(target_btn, Locator):
                                await js_handle_click_biased_right(page, target_btn)
                    elif isinstance(target_btn, Locator):
                        await target_btn.scroll_into_view_if_needed()
                        await page.wait_for_timeout(100)
                        box2 = await target_btn.bounding_box()
                        if not await real_mouse_click_bbox_biased_right(page, box2 or {}):
                            await target_btn.click(timeout=10000, force=True)
                    else:
                        await target_btn.evaluate(
                            "(node) => { try { node.scrollIntoView({behavior: 'smooth', block: 'center'}); } catch (e) {} }"
                        )
                        await page.wait_for_timeout(100)
                        if not await js_handle_click_biased_right(page, target_btn):
                            logger.warning("[视频号] 第二次真实点击发表按钮失败")
                    logger.info("[视频号] 已执行第二次点击")
                except Exception as e:
                    logger.warning("[视频号] 第二次点击异常: %s", e)

            await self._handle_post_submit_original_revenue_modal(
                page, metadata, total_ms=int(wait_ms(8000))
            )
            await self._handle_keep_editing_dialog(page, metadata, total_ms=int(wait_ms(2000)))

        except Exception as e:
            return PublishResult(
                success=False,
                error_message=f"点击发布按钮失败: {str(e)}",
                failed_step="SubmitStep",
            )

        logger.info("[视频号] 检查发布后是否存在弹窗或错误提示...")
        try:
            from src.infrastructure.anti_risk.delays import random_delay

            await random_delay(page, wait_ms(300), metadata, config)
        except Exception:
            await page.wait_for_timeout(wait_ms(300))

        try:
            error_checks = [
                (Selectors.SECURITY.get("PUBLISH_TOAST_ERROR", []), "发布失败/错误"),
                (Selectors.SECURITY.get("PUBLISH_TOAST_FREQ", []), "操作频繁/风控拦截"),
            ]
            for selectors_list, desc in error_checks:
                for sel in selectors_list:
                    try:
                        if await page.locator(sel).count() > 0:
                            if "频繁" in desc or "风控" in desc:
                                try:
                                    from src.infrastructure.anti_risk.delays import cooldown_before_retry

                                    sec = config.get("cooldown_after_frequent_seconds", 180)
                                    await cooldown_before_retry(float(sec), reason="操作频繁")
                                    return NeedsAction(action="need_retry", message="操作频繁，已冷却后重试")
                                except Exception as e:
                                    logger.warning("[视频号] 风控冷却失败: %s", e)
                            return PublishResult(
                                success=False,
                                error_message=f"点击发布后受阻: {desc}",
                                failed_step="SubmitStep",
                            )
                    except Exception as e:
                        logger.debug("[视频号] 检查错误提示异常: %s", e)
        except Exception as e:
            logger.debug("[视频号] 检查发布后弹窗异常: %s", e)

        return await self._verify_publish_result(page, metadata)

    async def _verify_publish_result(self, page: Page, metadata: Dict[str, Any]) -> PublishResult:
        logger.info("[视频号] ===== 验证发布结果 =====")

        try:
            await self._handle_keep_editing_dialog(page, metadata, total_ms=800)
        except Exception:
            pass

        try:
            current_url = page.url
            if self._is_manage_page(current_url):
                logger.info("[视频号] 页面已在作品管理页: %s", current_url)
                USER_LOG.info(
                    "%s ✓ 发布成功 (%s)",
                    self._step_prefix(metadata, "点击发布"),
                    current_url,
                )
                return PublishResult(success=True, publish_url=current_url)
        except Exception as e:
            logger.debug("[视频号] 检查当前 URL 是否管理页异常: %s", e)

        try:
            await page.wait_for_url(lambda url: self._is_manage_page(url), timeout=10000)
            logger.info("[视频号] 检测到页面跳转: %s", page.url)
            USER_LOG.info(
                "%s ✓ 发布成功 (%s)",
                self._step_prefix(metadata, "点击发布"),
                page.url,
            )
            return PublishResult(success=True, publish_url=page.url)
        except Exception as e:
            logger.debug("[视频号] 等待 URL 跳转异常: %s", e)

        success_toast = Selectors.VERIFY.get("SUCCESS_TOAST", "")
        if success_toast:
            logger.info("[视频号] 检测“已发表”Toast…")
            for _ in range(40):
                try:
                    loc = page.locator(success_toast).first
                    if await loc.count() > 0 and await loc.is_visible():
                        logger.info("[视频号] 检测到“已发表”Toast")
                        USER_LOG.info("%s ✓ 发布成功", self._step_prefix(metadata, "点击发布"))
                        return PublishResult(success=True, publish_url=page.url)
                except Exception as e:
                    logger.debug("[视频号] 轮询 Toast 异常: %s", e)
                try:
                    await self._handle_keep_editing_dialog(page, metadata, total_ms=100)
                except Exception:
                    pass
                try:
                    if self._is_manage_page(page.url):
                        logger.info("[视频号] 轮询中检测到已跳转: %s", page.url)
                        USER_LOG.info(
                            "%s ✓ 发布成功 (%s)",
                            self._step_prefix(metadata, "点击发布"),
                            page.url,
                        )
                        return PublishResult(success=True, publish_url=page.url)
                except Exception as e:
                    logger.debug("[视频号] 轮询中检测 URL 异常: %s", e)
                await page.wait_for_timeout(150)

        manage_selectors = Selectors.VERIFY.get("MANAGE_PAGE_INDICATOR", [])
        for sel in manage_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    logger.info("[视频号] 检测到管理页特征元素: %s", sel)
                    USER_LOG.info("%s ✓ 发布成功", self._step_prefix(metadata, "点击发布"))
                    return PublishResult(success=True, publish_url=page.url)
            except Exception as e:
                logger.debug("[视频号] 检测管理页特征异常: %s", e)

        current_url = page.url
        if "post/create" in current_url or "finderNewLifeCreate" in current_url:
            logger.warning("[视频号] 页面仍停留在发布页: %s", current_url)

        logger.warning("[视频号] 未能确认发布成功，请手动检查")
        return PublishResult(
            success=False,
            error_message="发布后未能确认成功，请手动检查",
            failed_step="SubmitStep",
        )

    @staticmethod
    def _is_manage_page(url: str) -> bool:
        if "channels.weixin.qq.com" not in url:
            return False
        if "post/create" in url or "finderNewLifeCreate" in url:
            return False
        return (
            "manage" in url
            or "post/list" in url
            or "finderNewLifePostList" in url
        )
