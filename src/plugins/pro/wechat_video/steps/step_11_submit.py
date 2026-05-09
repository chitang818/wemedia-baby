# -*- coding: utf-8 -*-
"""
步骤11：点击发布按钮并验证结果
文件路径: src/plugins/pro/wechat_video/steps/step_11_submit.py

流程：
  1. 查找发布按钮（Selectors.PUBLISH.SUBMIT_BTN，轮询匹配；命中后校验按钮文案为「发表」）
  2. 等待按钮可用（视频转码中按钮禁用，最多等 3 分钟）
  3. 偏右真实鼠标点击「发表」（避免与「手机预览」相邻误触）；2s 内无响应则第二次同样策略点击

重要：本步骤不操作表单区域「声明原创」复选框（该操作仅在步骤10）；此处仅点击底部「发表」，
     以及发表成功后可能出现的「广告分成」类弹窗内的「直接发表」或「声明原创」按钮（非表单勾选框）。

  4. 检测错误弹窗：
     - PUBLISH_TOAST_ERROR → 直接失败
     - PUBLISH_TOAST_FREQ（操作频繁/风控）→ 冷却后触发重试（NeedsAction）
  5. 验证发布结果（优先级由高到低）：
     a. 已在管理页（URL 特征）→ 成功
     b. 等待 URL 跳转至管理页（10s）→ 成功
     c. 轮询检测「发布成功」Toast（6s）→ 成功
     d. 检测管理页特征元素（MANAGE_PAGE_INDICATOR）→ 成功
     e. 兜底再等 URL 跳转（5s）→ 成功
     f. 全部失败 → 报告失败，提示手动检查

字段依赖：metadata['speed_rate']（0.5-2.0，影响等待时长）
               metadata['anti_risk_config']（冷却时长等风控配置）
"""
import logging
import re
import time
from typing import Any, Dict, Union

from playwright.async_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
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
from .step_08_schedule import (
    _parse_schedule_time,
    _read_schedule_picker_state,
    _schedule_matches_target,
)
from .step_10_original import _get_is_original, wechat_main_original_checked

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class SubmitStep(BasePublishStep):
    """点击发布按钮并验证发布结果。

    不点击表单「声明原创」复选框（步骤10已处理）；仅定位底部「发表」按钮并点击。
    发表后的营销弹窗内可能点「直接发表」或弹窗按钮「声明原创」，与表单勾选无关。

    流程：
    1. 查找发布按钮（Shadow 命中后校验文案为「发表」）
    2. 等待按钮可用（视频转码期间可能禁用）
    3. 精准解析后偏右真实鼠标点击「发表」
    4. 检测错误弹窗/风控拦截
    5. 验证发布结果（Toast / URL 跳转 / 管理页特征）
    """

    # 与 wujie_shadow.WUJIE_SHADOW_QUERY_SELECTOR_FN_JS 一致：统一宿主解析后再 querySelector
    _WUJIE_SHADOW_QUERY_FN = WUJIE_SHADOW_QUERY_SELECTOR_FN_JS

    @staticmethod
    async def _shadow_node_is_submit_button(node: Any) -> bool:
        """避免宽泛 CSS 误点到其它主按钮；仅接受可见文案为「发表」的 button。"""
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
        """无障碍等路径回退时再次确认不是「手机预览」等相邻按钮。"""
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

    # 点击「发表」后可能出现的「广告分成 / 声明原创」营销弹窗；返回按钮视口中心供真实鼠标点击
    _POST_SUBMIT_AD_SHARE_MODAL_XY_JS = """
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
        if (!isAdShare) {
            continue;
        }
        const nodes = dlg.querySelectorAll(
            'button, a.weui-desktop-btn, a[class*="weui-desktop-btn"]'
        );
        for (const b of nodes) {
            const tx = (b.textContent || '').replace(/\\s+/g, '').trim();
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

    async def _handle_post_submit_original_revenue_modal(
        self,
        page: Page,
        metadata: Dict[str, Any],
        *,
        total_ms: int = 8000,
    ) -> None:
        """处理发表后的「声明原创有机会获得广告分成」弹窗。

        - 任务未勾选声明原创：点击「直接发表」，走不声明原创的发表路径。
        - 任务已勾选声明原创：点击弹窗内「声明原创」（与步骤10表单勾选配套）。
        若未加入分成计划或页面未出此弹窗，轮询内无命中则快速返回。
        """
        is_orig = _get_is_original(metadata)
        deadline = time.monotonic() + total_ms / 1000.0
        while time.monotonic() < deadline:
            try:
                r = await page.evaluate(self._POST_SUBMIT_AD_SHARE_MODAL_XY_JS, is_orig)
            except Exception as e:
                logger.debug("[视频号] 检测发表后广告分成弹窗异常: %s", e)
                r = None
            if isinstance(r, dict) and "x" in r and "y" in r and "kind" in r:
                xy = (float(r["x"]), float(r["y"]))
                if await real_mouse_click_xy(page, xy):
                    if r.get("kind") == "direct":
                        logger.info("[视频号] 已真实点击「直接发表」，关闭广告分成引导弹窗（任务未勾选声明原创）")
                        USER_LOG.info("[步骤11/11 点击发布] ▶ 已点「直接发表」（未声明原创）")
                    else:
                        logger.info("[视频号] 已真实点击弹窗内「声明原创」（任务已勾选声明原创）")
                        USER_LOG.info("[步骤11/11 点击发布] ▶ 已点弹窗「声明原创」")
                    await page.wait_for_timeout(350)
                    return
                logger.warning("[视频号] 广告分成弹窗命中按钮但 mouse.click 失败")
            await page.wait_for_timeout(200)

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """点击发布按钮并验证最终结果"""
        await self._await_pause(metadata)
        logger.info("[视频号] 步骤11：点击发表按钮")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        # ---- 1. 查找发布按钮 ----
        submit_selectors = Selectors.PUBLISH.get("SUBMIT_BTN", [])
        target_btn: Union[Locator, Any, None] = None
        target_selector = ""

        # 等待无界微前端加载完成
        try:
            await page.wait_for_selector("#container-wrap > div.container-center > div > wujie-app", state="attached", timeout=5000)
        except Exception as e:
            logger.debug("[视频号] 等待无界容器超时或异常: %s", e)

        # 优先：Shadow 内 form-btns 遍历，文案严格「发表」且排除「手机预览」，主按钮 + 最靠右
        try:
            resolved = await page.evaluate_handle(WUJIE_SHADOW_RESOLVE_SUBMIT_BTN_JS)
            if resolved and str(resolved) != "JSHandle@null":
                if await self._shadow_node_is_submit_button(resolved):
                    target_btn = resolved
                    target_selector = "shadow_resolve_submit_btn"
                    logger.info("[视频号] 已精准解析底部「发表」按钮（已排除手机预览/保存草稿）")
        except Exception as e:
            logger.debug("[视频号] shadow 精准解析发表按钮异常: %s", e)

        # 回退：无障碍语义（需再校验文案，避免同名可访问名误命中）
        if target_btn is None:
            try:
                a11y = page.get_by_role("button", name=re.compile(r"^发表$")).first
                if await a11y.count() > 0 and await a11y.is_visible():
                    if await self._locator_is_strict_submit_button(a11y):
                        target_btn = a11y
                        target_selector = "get_by_role(button,name=发表)"
                        logger.info("[视频号] 使用无障碍语义定位发表按钮")
            except Exception as e:
                logger.debug("[视频号] get_by_role(发表) 未命中: %s", e)

        for sel in submit_selectors:
            if target_btn is not None:
                break
            try:
                el = await page.evaluate_handle(self._WUJIE_SHADOW_QUERY_FN, sel)
                if el and str(el) != "JSHandle@null":
                    # 判断可见性
                    is_visible = await el.evaluate("(node) => node.offsetWidth > 0 || node.offsetHeight > 0 || node.getClientRects().length > 0")
                    if not is_visible:
                        continue
                    if not await self._shadow_node_is_submit_button(el):
                        logger.debug("[视频号] 选择器命中元素但文案非「发表」，跳过: %s", sel)
                        continue
                    target_btn = el
                    target_selector = sel
                    logger.info("[视频号] 找到发表按钮: %s", sel)
                    break
            except Exception as e:
                logger.debug("[视频号] 检索发表按钮异常: %s", e)
                continue

        if not target_btn:
            return PublishResult(
                success=False,
                error_message="未找到发布按钮，可能页面结构已变更",
                failed_step="SubmitStep",
            )

        # ---- 2. 等待按钮可用（视频转码期间按钮可能禁用） ----
        max_wait_seconds = 180  # 最多等待3分钟
        is_ready = False

        for i in range(max_wait_seconds // 3):
            await self._await_pause(metadata)
            try:
                if isinstance(target_btn, Locator):
                    is_disabled = not await target_btn.is_enabled()
                else:
                    is_disabled = await target_btn.evaluate("(node) => node.disabled")
            except Exception as e:
                logger.debug("[视频号] 检查按钮禁用状态异常: %s", e)
                is_disabled = False
            
            if not is_disabled:
                is_ready = True
                break
            logger.info("[视频号] 发布按钮当前不可用（可能仍在转码中），继续等待...")
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, wait_ms(3000), metadata, config)
            except Exception as e:
                logger.debug("[视频号] 等待按钮可用异常: %s", e)
                await page.wait_for_timeout(wait_ms(3000))

        if not is_ready:
            return PublishResult(
                success=False,
                error_message="等待视频转码/处理超时，发布按钮始终不可用",
                failed_step="SubmitStep",
            )

        # ---- 2.5 定时发表：发表前再读一次 picker（防止后续步骤或 Vue 未提交导致后台时间偏差）
        sched_raw = (
            metadata.get("scheduled_publish_time")
            or metadata.get("schedule_time")
            or ""
        )
        if sched_raw:
            parsed_s = _parse_schedule_time(str(sched_raw).strip())
            if parsed_s:
                st_pre = await _read_schedule_picker_state(page)
                ok_s, msg_s = _schedule_matches_target(st_pre, parsed_s)
                if not ok_s:
                    logger.error("[视频号] 发表前定时校验失败: %s", msg_s)
                    return PublishResult(
                        success=False,
                        error_message=(
                            "发表前检测到定时时间与任务不一致（表单内部值可能未同步，"
                            "常见于浏览器时区与视频号后台不一致）。任务要求: "
                            f"{sched_raw}。详情: {msg_s}"
                        ),
                        failed_step="SubmitStep",
                    )
                logger.info("[视频号] 发表前定时校验通过 → %s", sched_raw)

        # ---- 2.6 声明原创任务：发表前只读校验主区已勾选（避免步骤 10 假成功）----
        if _get_is_original(metadata):
            main_ok, main_det = await wechat_main_original_checked(page)
            if not main_ok:
                logger.error("[视频号] 发表前校验：表单「声明原创」未勾选（detail=%s）", main_det)
                return PublishResult(
                    success=False,
                    error_message=(
                        "发表前检测到表单「声明原创」未勾选，请确认步骤 10 已完成或页面未遮挡。"
                        f"（detail={main_det}）"
                    ),
                    failed_step="SubmitStep",
                )
            logger.info("[视频号] 发表前声明原创主勾选校验通过")

        # ---- 3. 点击发布按钮（偏右真实鼠标，避免点到「手机预览」）----
        logger.info("[视频号] 发布按钮已就绪，准备点击...")
        try:
            await self._await_pause(metadata)
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, wait_ms(300), metadata, config)
            except Exception as e:
                logger.debug("[视频号] random_delay 异常: %s", e)
                await page.wait_for_timeout(wait_ms(300))

            # 重新定位按钮并确认滚动可见
            if isinstance(target_btn, Locator):
                await target_btn.scroll_into_view_if_needed()
            else:
                await target_btn.evaluate("(node) => node.scrollIntoView({behavior: 'smooth', block: 'center'})")
            await page.wait_for_timeout(300)

            # 不用 human_click：矩形内随机点易落在靠左区域，与「手机预览」相邻时偶发误触
            if isinstance(target_btn, Locator):
                box = await target_btn.bounding_box()
                if not await real_mouse_click_bbox_biased_right(page, box or {}):
                    try:
                        await target_btn.click(timeout=10000)
                    except Exception:
                        return PublishResult(
                            success=False,
                            error_message="发表按钮真实鼠标点击失败，请勿遮挡浏览器窗口",
                            failed_step="SubmitStep",
                        )
            else:
                if not await js_handle_click_biased_right(page, target_btn):
                    return PublishResult(
                        success=False,
                        error_message="发表按钮真实鼠标点击失败（Shadow 内坐标无效或 mouse.click 异常），请勿遮挡窗口",
                        failed_step="SubmitStep",
                    )

            logger.info("[视频号] 已点击发布按钮（第一次）")
            USER_LOG.info("[步骤11/11 点击发布] ▶ 已点击发布按钮")

            # 未勾选原创时，发表后常出现「广告分成」引导弹窗，需点「直接发表」才能继续
            await self._handle_post_submit_original_revenue_modal(
                page, metadata, total_ms=int(wait_ms(6000))
            )

            # 短暂等待后检测是否需要二次点击
            detected_early = False
            for _ in range(10):
                await page.wait_for_timeout(200)
                # 检测成功标识：优先用 Playwright 原生 locator（支持 :has-text），
                # 不走 evaluate_handle + 原生 querySelector（后者不支持 :has-text 伪类）
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
                # 检测 URL 跳转
                try:
                    if "manage" in page.url or "post/list" in page.url:
                        detected_early = True
                        logger.info("[视频号] 2s 内检测到页面已跳转")
                        break
                except Exception as e:
                    logger.debug("[视频号] 2s 内检测 URL 异常: %s", e)

            # 未检测到任何响应，尝试第二次点击（同样优先原生 click）
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
                            logger.warning("[视频号] 第二次 Shadow 解析后偏右点击失败，尝试沿用首次句柄")
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
                    logger.warning(f"[视频号] 第二次点击异常: {e}")

            await self._handle_post_submit_original_revenue_modal(
                page, metadata, total_ms=int(wait_ms(8000))
            )

        except Exception as e:
            return PublishResult(
                success=False,
                error_message=f"点击发布按钮失败: {str(e)}",
                failed_step="SubmitStep",
            )

        # ---- 4. 检测错误弹窗/风控拦截 ----
        logger.info("[视频号] 检查发布后是否存在弹窗或错误提示...")
        try:
            from src.infrastructure.anti_risk.delays import random_delay
            await random_delay(page, wait_ms(300), metadata, config)
        except Exception as e:
            logger.debug("[视频号] 发布后延迟异常: %s", e)
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
                            logger.warning(f"[视频号] 检测到异常提示: {desc}")
                            # 尝试读取提示文本
                            try:
                                text = await page.locator(sel).inner_text()
                                desc = f"{desc}: {text}"
                            except Exception as e:
                                logger.debug("[视频号] 读取弹窗文本异常: %s", e)

                            # 操作频繁：冷却后重试
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
                        logger.debug("[视频号] 检查单条弹窗选择器异常: %s", e)
                        continue
        except Exception as e:
            logger.debug(f"[视频号] 检查弹窗出现异常（不影响主流程）: {e}")

        # ---- 5. 验证发布结果 ----
        return await self._verify_publish_result(page, metadata)

    async def _verify_publish_result(self, page: Page, metadata: Dict[str, Any]) -> PublishResult:
        """验证发布结果：先查 URL 跳转，再轮询 Toast，最后兜底检测管理页特征。"""
        logger.info("[视频号] ===== 验证发布结果 =====")

        # ── 方式0：若已跳转到管理页则直接成功 ──
        try:
            current_url = page.url
            if self._is_manage_page(current_url):
                logger.info(f"[视频号] 页面已在作品管理页: {current_url}，视为发布成功")
                USER_LOG.info(f"[步骤11/11 点击发布] ✓ 发布成功 ({current_url})")
                return PublishResult(success=True, publish_url=current_url)
        except Exception as e:
            logger.debug("[视频号] 检查当前 URL 是否管理页异常: %s", e)

        # ── 方式1：等待 URL 跳转（10秒） ──
        try:
            await page.wait_for_url(
                lambda url: self._is_manage_page(url),
                timeout=10000
            )
            logger.info(f"[视频号] 检测到页面跳转: {page.url}")
            USER_LOG.info(f"[步骤11/11 点击发布] ✓ 发布成功 ({page.url})")
            return PublishResult(success=True, publish_url=page.url)
        except Exception as e:
            logger.debug("[视频号] 等待 URL 跳转(10s) 异常: %s", e)

        # ── 方式2：轮询 Toast（6秒） ──
        success_toast = Selectors.VERIFY.get("SUCCESS_TOAST", "")
        if success_toast:
            logger.info("[视频号] 检测「已发表」Toast…")
            poll_interval_ms = 150
            total_wait_ms = 6000

            for _ in range(0, total_wait_ms, poll_interval_ms):
                try:
                    # 先普通DOM找一下
                    loc = page.locator(success_toast).first
                    if await loc.count() > 0 and await loc.is_visible():
                        logger.info("[视频号] ✓ (普通)检测到「已发表」Toast")
                        USER_LOG.info("[步骤11/11 点击发布] ✓ 发布成功！")
                        return PublishResult(success=True, publish_url=page.url)
                except Exception as e:
                    logger.debug("[视频号] 轮询 Toast(普通DOM) 异常: %s", e)

                try:
                    # 在 wujie Shadow DOM 内用 JS 文本匹配查找 Toast span
                    # 不能把 :has-text() 传给 evaluate_handle，原生 querySelector 不认识该伪类
                    toast_text = "已发表"
                    el = await page.evaluate_handle(
                        """(text) => {
                            const shadow = (function() {
                                var paths = [
                                    '#container-wrap > div.container-center > div > div.main-body > div.third-line > div > wujie-app',
                                    '#container-wrap > div.container-center > div > wujie-app'
                                ];
                                for (var i = 0; i < paths.length; i++) {
                                    var w = document.querySelector(paths[i]);
                                    if (w && w.shadowRoot) return w.shadowRoot;
                                }
                                var all = document.querySelectorAll('wujie-app');
                                for (var j = 0; j < all.length; j++) {
                                    if (all[j].shadowRoot) return all[j].shadowRoot;
                                }
                                return null;
                            })();
                            if (!shadow) return null;
                            var spans = shadow.querySelectorAll('span');
                            for (var k = 0; k < spans.length; k++) {
                                if ((spans[k].textContent || '').includes(text)) return spans[k];
                            }
                            return null;
                        }""",
                        toast_text,
                    )
                    if el and str(el) != "JSHandle@null":
                        is_visible = await el.evaluate("(node) => node.offsetWidth > 0 || node.offsetHeight > 0 || node.getClientRects().length > 0")
                        if is_visible:
                            logger.info("[视频号] ✓ (Shadow)检测到「已发表」Toast")
                            USER_LOG.info("[步骤11/11 点击发布] ✓ 发布成功！")
                            try:
                                await page.wait_for_url(
                                    lambda url: self._is_manage_page(url),
                                    timeout=5000
                                )
                            except Exception as e:
                                logger.debug("[视频号] Toast 后等待跳转异常: %s", e)
                            return PublishResult(success=True, publish_url=page.url)
                except Exception as e:
                    logger.debug("[视频号] 轮询 Toast(Shadow) 异常: %s", e)
                await page.wait_for_timeout(poll_interval_ms)
                # 每轮顺带检查 URL
                try:
                    if self._is_manage_page(page.url):
                        logger.info(f"[视频号] 轮询中检测到已跳转: {page.url}")
                        USER_LOG.info(f"[步骤11/11 点击发布] ✓ 发布成功 ({page.url})")
                        return PublishResult(success=True, publish_url=page.url)
                except Exception as e:
                    logger.debug("[视频号] 轮询中检查 URL 异常: %s", e)

        # ── 方式3：检测管理页特征元素（要求 is_visible()）──
        manage_selectors = Selectors.VERIFY.get("MANAGE_PAGE_INDICATOR", [])
        for sel in manage_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    logger.info(f"[视频号] 检测到管理页特征（is_visible）: {sel}，视为发布成功")
                    USER_LOG.info("[步骤11/11 点击发布] ✓ 发布成功！")
                    return PublishResult(success=True, publish_url=page.url)
            except Exception as e:
                logger.debug("[视频号] 检测管理页特征选择器异常: %s", e)
                continue

        # ── 未能确认成功 ──
        current_url = page.url
        if "post/create" in current_url:
            logger.warning(f"[视频号] 页面仍停留在发布页，可能发布遇到静默阻挡: {current_url}")

        logger.warning("[视频号] 未能确认发布成功，请手动检查")
        return PublishResult(
            success=False,
            error_message="发布后未能确认成功（未检测到成功提示或页面跳转），请手动检查",
            failed_step="SubmitStep",
        )

    @staticmethod
    def _is_manage_page(url: str) -> bool:
        """判断 URL 是否为视频号管理页（严格：必须含 manage 或 post/list，且不在发布编辑页）。
        去除宽泛的 content 条件，避免发布页 URL 含 content 时误判。
        """
        if "channels.weixin.qq.com" not in url:
            return False
        if "post/create" in url:
            return False
        return "manage" in url or "post/list" in url
