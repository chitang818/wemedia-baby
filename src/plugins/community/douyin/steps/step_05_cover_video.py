# -*- coding: utf-8 -*-
"""
步骤5：视频封面设置
文件路径: src/plugins/community/douyin/steps/step_05_cover_video.py

流程规范归纳：
  总判断标准为页面底部出现「封面效果检测通过」标志（COVER_SUCCESS_INDICATOR）。
  - AI推荐（ai）：仅在页面主区域「AI智能推荐封面」的候选格中点击其一，无需进入弹窗。
  - 首帧（first_frame）：
      1. 点击左上侧封面缩略图上的「选择封面」按钮激活弹窗
      2. 弹窗中顺序：点击“设置横封面”按钮 → 点击“完成” → 等待封底检测
  - 本地上传（custom）：
      1. 激活弹窗
      2. 点击“上传封面”操作 file chooser 或 set_input_files
      3. 选择横封面并点击“完成”（或直接视为成功）

字段依赖：
  - metadata['cover_type']: custom / first_frame / ai
  - metadata['cover_path']: 本地封面需要
"""
import logging
import re
import time
from typing import Dict, Any, Optional

from src.infrastructure.browser.automation_api import Page, Locator

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class CoverVideoStep(BasePublishStep):
    """视频封面设置：方向一 本地/首帧（进弹窗）；方向二 AI（主页面红框内直选）。完成判定均为「封面效果检测通过」."""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        cover_type = (metadata.get("cover_type") or "first_frame").strip().lower() if metadata.get("cover_type") else "first_frame"
        cover_path = (metadata.get("cover_path") or "").strip()
        if cover_path and cover_type != "custom":
            cover_type = "custom"
        logger.info("===== 视频封面设置 =====")
        USER_LOG.info("[步骤5/9 视频封面] ▶ 尝试设置")

        # 【方向二】AI 智能推荐封面：仅在主页面红框区域（AI智能推荐封面）内点击第一个推荐缩略图，不进弹窗
        if cover_type == "ai":
            if await self._try_click_ai_recommend_cover(page, metadata):
                if await self._wait_cover_success_indicator(page, metadata):
                    USER_LOG.info("[步骤5/9 视频封面] ✓ 已选择AI智能推荐封面")
                    return None
                return PublishResult(success=False, error_message="已点击AI推荐封面，但未检测到「封面效果检测通过」")
            logger.error("未能在主页面「AI智能推荐封面」区域找到可点击缩略图")
            USER_LOG.error("[步骤5/9 视频封面] ✖ 失败（找不到AI封面）")
            return PublishResult(success=False, error_message="AI智能推荐封面未找到或无法点击，任务宣告失败！")

        # 【方向一】本地/首帧：点击「选择封面」（竖封面3:4 或 横封面4:3 上方）→ 进弹窗操作
        # 如果已经有封面弹窗，直接在弹窗中操作
        if await self._is_cover_modal_open(page):
            result = await self._handle_cover_modal(page, metadata, cover_type, cover_path)
            if result is None:
                if not await self._wait_cover_success_indicator(page, metadata):
                    return PublishResult(success=False, error_message="弹窗内已操作，但未检测到「封面效果检测通过」")
            return result

        config = metadata.get("anti_risk_config") or {}
        await self._wait_cover_section_ready(page)

        btn = await self._resolve_vertical_cover_entry(page)
        if btn is None:
            logger.error("未解析到竖封面「选择封面」入口")
            USER_LOG.error("[步骤5/9 视频封面] ✖ 失败：未找到「选择封面」入口")
            return PublishResult(success=False, error_message="未找到竖封面「选择封面」入口")

        modal_opened = False
        for attempt in range(2):
            try:
                await btn.scroll_into_view_if_needed()
                if attempt == 0:
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click
                        await human_click(page, btn, metadata, config, use_operation_delay=False)
                    except Exception:
                        await btn.click()
                else:
                    await btn.click(force=True)
                logger.info("已点击竖封面「选择封面」入口（第 %d 次）", attempt + 1)
            except Exception as e:
                logger.warning("点击封面入口异常: %s", e)

            if await self._wait_cover_modal_visible(page, timeout_ms=3000):
                USER_LOG.info("[步骤5/9 视频封面] ▶ 已成功激活封面弹窗")
                modal_opened = True
                break
            logger.info("弹窗未就绪，准备第 %d 次重试", attempt + 2)

        if modal_opened:
            result = await self._handle_cover_modal(page, metadata, cover_type, cover_path)
            if result is None:
                if not await self._wait_cover_success_indicator(page, metadata):
                    return PublishResult(success=False, error_message="弹窗内已点击完成，但未检测到「封面效果检测通过」")
            return result

        logger.error("未找到竖封面「选择封面」入口或点击后弹窗未打开")
        USER_LOG.error("[步骤5/9 视频封面] ✖ 失败：未打开封面设置弹窗")
        return PublishResult(
            success=False,
            error_message="未找到竖封面「选择封面」入口或点击后弹窗未打开",
        )

    async def _wait_cover_section_ready(self, page: Page, timeout_ms: int = 1000) -> None:
        """检查封面区域是否已渲染（描述步骤已完成，通常已就绪）。"""
        for sel in ("[ref=e165]", "[ref=e153]", "div.cover-Jg3T4p"):
            try:
                await page.locator(sel).first.wait_for(state="visible", timeout=timeout_ms)
                return
            except Exception:
                continue

    async def _resolve_vertical_cover_entry(self, page: Page) -> Optional[Locator]:
        """定位竖封面 3:4「选择封面」区域。
        按 DOM 报告：[ref=e165] → div.cover-Jg3T4p 第一个 div。
        """
        for sel in Selectors.PUBLISH.get("COVER_BTN") or []:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    logger.info("已解析竖封面「选择封面」入口: %s", sel)
                    return loc
            except Exception:
                continue
        return None

    async def _wait_cover_modal_visible(self, page: Page, timeout_ms: int = 3000) -> bool:
        """等待封面弹窗出现（Playwright 原生 wait_for，基于事件驱动）。"""
        for sel in (Selectors.PUBLISH.get("COVER_MODAL") or []):
            try:
                await page.locator(sel).first.wait_for(state="visible", timeout=timeout_ms)
                return True
            except Exception:
                continue
        return False

    async def _wait_modal_confirm_visible(
        self, page: Page, modal_scope: Locator, timeout_ms: int = 3000
    ) -> Optional[Locator]:
        async def _find_confirm() -> Optional[Locator]:
            for sel in (Selectors.PUBLISH.get("COVER_CONFIRM_BTN") or []):
                try:
                    loc = modal_scope.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        return loc
                except Exception:
                    continue
            return None

        found = await PluginWaitHelper.wait_for_condition(
            page,
            _find_confirm,
            timeout_ms=timeout_ms,
            poll_interval_ms=250,
        )
        return found if isinstance(found, Locator) else None

    async def _is_cover_modal_open(self, page: Page) -> bool:
        for selector in Selectors.PUBLISH.get("COVER_MODAL", []):
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _wait_locator_hidden(
        self, page: Page, locator: Locator, timeout_ms: int = 2000
    ) -> bool:
        return bool(
            await PluginWaitHelper.wait_for_condition(
                page,
                lambda: self._is_locator_hidden(locator),
                timeout_ms=timeout_ms,
                poll_interval_ms=250,
            )
        )

    async def _is_locator_hidden(self, locator: Locator) -> bool:
        try:
            return await locator.count() == 0 or not await locator.is_visible()
        except Exception:
            return True

    async def _see_cover_warning_indicator(self, page: Page) -> bool:
        """当前页是否出现「竖/横/封面存在N个问题」类提示（封面已上传但有质量提醒，仍视为成功）。"""
        # 匹配：竖封面存在1个问题、横封面存在1个问题、封面存在2个问题 等
        pattern = re.compile(r"(竖|横)?封面存在\d+个问题")
        try:
            # 页面中任意包含该文案的可见元素即视为已出现
            loc = page.get_by_text(pattern)
            if await loc.count() == 0:
                return False
            first = loc.first
            return await first.is_visible()
        except Exception:
            return False

    async def _see_cover_missing_indicator(self, page: Page) -> bool:
        """当前页是否出现「横/竖双封面缺失」提示，表示横竖封面均未设置。"""
        selectors = Selectors.PUBLISH.get("COVER_MISSING_INDICATOR") or []
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _see_cover_success_indicator(self, page: Page) -> bool:
        """当前页是否已出现「封面效果检测通过」「封面检测通过」或「X封面存在N个问题」提示（不等待）。
        任一出现均视为封面上传/设置成功（后者为有质量提醒但已上传）。
        若出现「横/竖双封面缺失」则明确未成功。"""
        # 先检查是否有缺失提示
        if await self._see_cover_missing_indicator(page):
            return False
        selectors = Selectors.PUBLISH.get("COVER_SUCCESS_INDICATOR") or []
        if selectors:
            for sel in selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        return True
                except Exception:
                    continue
        return await self._see_cover_warning_indicator(page)

    async def _wait_cover_success_indicator(self, page: Page, metadata: Dict[str, Any], timeout_ms: int = 12000) -> bool:
        """等待主页面出现「封面效果检测通过」或「X封面存在N个问题」提示（两方向共用）。
        用 Playwright wait_for 事件驱动，任一指示符出现立即返回。"""
        selectors = Selectors.PUBLISH.get("COVER_SUCCESS_INDICATOR") or []
        if not selectors:
            USER_LOG.warning("[步骤5/9 视频封面] 未配置 COVER_SUCCESS_INDICATOR，无法判定封面是否成功")
            return False
        USER_LOG.info("[步骤5/9 视频封面] 等待「封面效果检测通过」…（最长 %d 秒）", timeout_ms // 1000)

        # 先尝试 wait_for（事件驱动，毫秒级响应）
        for sel in selectors:
            try:
                await page.locator(sel).first.wait_for(state="visible", timeout=timeout_ms)
                if await self._see_cover_warning_indicator(page):
                    USER_LOG.info("[步骤5/9 视频封面] ✓ 封面已设置（存在质量提醒，继续流程）")
                else:
                    USER_LOG.info("[步骤5/9 视频封面] ✓ 封面效果检测通过")
                return True
            except Exception:
                # 该候选未命中，继续试下一条
                if await self._see_cover_success_indicator(page):
                    USER_LOG.info("[步骤5/9 视频封面] ✓ 封面效果检测通过")
                    return True

        logger.warning("等待封面成功提示超时（%d ms）", timeout_ms)
        USER_LOG.warning("[步骤5/9 视频封面] ✖ 封面效果检测超时，封面可能未生效")
        return False

    async def _try_click_ai_recommend_cover(self, page: Page, metadata: Dict[str, Any]) -> bool:
        """方向二：在主页面「AI智能推荐封面」红框内点击第一个推荐缩略图（唯一 DOM），不进弹窗。"""
        config = metadata.get("anti_risk_config") or {}
        for sel in (Selectors.PUBLISH.get("COVER_AI_RECOMMEND_FIRST") or []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click
                        await human_click(page, loc, metadata, config)
                    except Exception:
                        await loc.click()
                    await self._wait_cover_success_indicator(page, metadata, timeout_ms=3000)
                    logger.info("已在「AI智能推荐封面」区域点击第一个推荐缩略图: %s", sel)
                    return True
            except Exception:
                continue
        return False

    async def _dismiss_vertical_cover_promo_if_present(self, page: Page) -> bool:
        """若出现「设置竖封面获更多流量」推荐弹窗：优先点击「设置竖封面」清除上层遮挡。"""
        for sel in (Selectors.PUBLISH.get("COVER_VERTICAL_PROMO_MODAL") or []):
            try:
                group = page.locator(sel)
                n = await group.count()
                if n == 0:
                    continue
                for idx in range(n):
                    try:
                        modal = group.nth(idx)
                        if not await modal.is_visible():
                            continue
                        try:
                            title = modal.get_by_text("设置竖封面获更多流量").first
                            if await title.count() == 0 or not await title.is_visible():
                                continue
                        except Exception:
                            continue

                        # 优先：按业务要求点击「设置竖封面」，让上层引导弹窗先退出
                        try:
                            v_btn = modal.get_by_role("button", name="设置竖封面").first
                            if await v_btn.count() > 0 and await v_btn.is_visible():
                                await v_btn.click()
                                logger.info("已点击「设置竖封面」处理「设置竖封面获更多流量」弹窗")
                                USER_LOG.info("[步骤5/9 视频封面] 已处理「设置竖封面获更多流量」弹窗（点击设置竖封面）")
                                await self._wait_locator_hidden(page, modal)
                                return True
                        except Exception:
                            pass

                        for btn_sel in (Selectors.PUBLISH.get("COVER_VERTICAL_PROMO_BTN") or []):
                            try:
                                if ">>" in btn_sel:
                                    parts = [p.strip() for p in btn_sel.split(">>")]
                                    btn = modal
                                    for part in parts[1:]:
                                        btn = btn.locator(part)
                                    btn = btn.first
                                else:
                                    btn = modal.locator(btn_sel).first
                                if await btn.count() > 0 and await btn.is_visible():
                                    await btn.click()
                                    logger.info("已点击「设置竖封面」关闭推荐弹窗（selector=%s）", btn_sel)
                                    USER_LOG.info("[步骤5/9 视频封面] 已处理「设置竖封面获更多流量」弹窗（点击设置竖封面）")
                                    await self._wait_locator_hidden(page, modal)
                                    return True
                            except Exception:
                                continue

                        # 兜底：右上角关闭（与横封面推广弹窗一致）
                        try:
                            close_btn = modal.get_by_label("关闭").first
                            if await close_btn.count() > 0 and await close_btn.is_visible():
                                await close_btn.click()
                                logger.info("已点击「关闭」处理「设置竖封面获更多流量」弹窗")
                                USER_LOG.info("[步骤5/9 视频封面] 已关闭「设置竖封面获更多流量」弹窗")
                                await self._wait_locator_hidden(page, modal)
                                return True
                        except Exception:
                            pass

                        try:
                            x_btn = modal.get_by_role("button", name=re.compile(r"^[×xX]$")).first
                            if await x_btn.count() > 0 and await x_btn.is_visible():
                                await x_btn.click()
                                logger.info("已点击「×」处理「设置竖封面获更多流量」弹窗")
                                USER_LOG.info("[步骤5/9 视频封面] 已关闭「设置竖封面获更多流量」弹窗")
                                await self._wait_locator_hidden(page, modal)
                                return True
                        except Exception:
                            pass

                        try:
                            skip_btn = modal.get_by_role("button", name="暂不设置").first
                            if await skip_btn.count() > 0 and await skip_btn.is_visible():
                                await skip_btn.click()
                                logger.info("已点击「暂不设置」处理「设置竖封面获更多流量」弹窗")
                                USER_LOG.info("[步骤5/9 视频封面] 已关闭「设置竖封面获更多流量」弹窗（暂不设置）")
                                await self._wait_locator_hidden(page, modal)
                                return True
                        except Exception:
                            pass

                    except Exception:
                        continue
            except Exception:
                continue
        return False

    async def _dismiss_horizontal_cover_traffic_promo_if_present(self, page: Page) -> bool:
        """若出现「设置横封面获更多流量」弹窗，则优先关闭；关闭不可用时点「设置横封面」进入流程，避免卡住。"""
        for sel in (Selectors.PUBLISH.get("COVER_HORIZONTAL_TRAFFIC_PROMO_MODAL") or []):
            try:
                modal = page.locator(sel).first
                if await modal.count() == 0 or not await modal.is_visible():
                    continue

                # 保险：确认标题文案存在，避免误关其它 dialog
                try:
                    title = modal.get_by_text("设置横封面获更多流量").first
                    if await title.count() == 0 or not await title.is_visible():
                        continue
                except Exception:
                    continue

                # 优先按 DOM 报告：右上角 aria-label=关闭 的按钮
                try:
                    close_btn = modal.get_by_label("关闭").first
                    if await close_btn.count() > 0 and await close_btn.is_visible():
                        await close_btn.click()
                        logger.info("已点击「关闭」处理「设置横封面获更多流量」弹窗")
                        USER_LOG.info("[步骤5/9 视频封面] 已关闭「设置横封面获更多流量」弹窗")
                        await self._wait_locator_hidden(page, modal)
                        return True
                except Exception:
                    pass

                # 兜底：部分版本 close 可能是「×」文本按钮
                try:
                    x_btn = modal.get_by_role("button", name=re.compile(r"^[×xX]$")).first
                    if await x_btn.count() > 0 and await x_btn.is_visible():
                        await x_btn.click()
                        logger.info("已点击「×」处理「设置横封面获更多流量」弹窗")
                        USER_LOG.info("[步骤5/9 视频封面] 已关闭「设置横封面获更多流量」弹窗")
                        await self._wait_locator_hidden(page, modal)
                        return True
                except Exception:
                    pass

                # 兜底：尝试使用配置的关闭选择器（如果未来不再提供 aria-label）
                for btn_sel in (Selectors.PUBLISH.get("COVER_HORIZONTAL_TRAFFIC_PROMO_CLOSE") or []):
                    try:
                        btn = modal.locator(btn_sel).first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.click()
                            logger.info("已点击关闭按钮（selector=%s）处理「设置横封面获更多流量」弹窗", btn_sel)
                            USER_LOG.info("[步骤5/9 视频封面] 已关闭「设置横封面获更多流量」弹窗")
                            await self._wait_locator_hidden(page, modal)
                            return True
                    except Exception:
                        continue

                # 兜底：直接点击弹窗内「设置横封面」进入横封面设置（你提到的替代方案）
                for btn_sel in (Selectors.PUBLISH.get("COVER_HORIZONTAL_TRAFFIC_PROMO_PRIMARY_BTN") or []):
                    try:
                        btn = modal.locator(btn_sel).first
                        if await btn.count() > 0 and await btn.is_visible():
                            await btn.click()
                            logger.info("已点击「设置横封面」处理「设置横封面获更多流量」弹窗")
                            USER_LOG.info("[步骤5/9 视频封面] 已处理「设置横封面获更多流量」弹窗（点击设置横封面）")
                            await self._wait_locator_hidden(page, modal)
                            return True
                    except Exception:
                        continue

                # 再兜底：点击「暂不设置」也会关闭弹窗（与报告一致）
                try:
                    skip_btn = modal.get_by_role("button", name="暂不设置").first
                    if await skip_btn.count() > 0 and await skip_btn.is_visible():
                        await skip_btn.click()
                        logger.info("已点击「暂不设置」处理「设置横封面获更多流量」弹窗")
                        USER_LOG.info("[步骤5/9 视频封面] 已关闭「设置横封面获更多流量」弹窗（暂不设置）")
                        await self._wait_locator_hidden(page, modal)
                        return True
                except Exception:
                    pass

                break
            except Exception:
                continue
        return False

    async def _handle_cover_modal(
        self, page: Page, metadata: Dict[str, Any], cover_type: str, cover_path: str
    ) -> Optional[PublishResult]:
        await self._await_pause(metadata)
        logger.info("封面弹窗已打开（视频），按配置执行: %s", cover_type)
        USER_LOG.info("[步骤5/9 视频封面] ▶ 弹窗已打开，选择并确认")

        # 有几率先出现「设置竖封面获更多流量」推荐弹窗：优先点击「设置竖封面」消除遮挡
        await self._dismiss_vertical_cover_promo_if_present(page)
        # 有的账号会弹出「设置横封面获更多流量」弹窗遮挡操作，先尝试关闭
        await self._dismiss_horizontal_cover_traffic_promo_if_present(page)

        # 封面主弹窗 scope：弹窗内所有按钮/输入框都必须从此 scope 内查找
        cover_modal_scope: Optional[Locator] = None
        for sel in (Selectors.PUBLISH.get("COVER_MODAL") or []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    cover_modal_scope = loc
                    break
            except Exception:
                continue
        if cover_modal_scope is None:
            logger.warning("[步骤5/9 视频封面] 未找到封面弹窗 scope，按规范放弃弹窗内定位操作")
            return PublishResult(success=False, error_message="封面弹窗未就绪，无法按规范定位弹窗内按钮")

        # 分支一：本地图片封面 —— 点击上传封面 → 上传封面图片 → 上传成功后点击完成
        if cover_type == "custom" and cover_path:
            ok = await self._handle_cover_upload_local(page, cover_modal_scope, cover_path)
            if ok:
                USER_LOG.info("[步骤5/9 视频封面] ✓ 已上传本地封面并确认")
                return None
            logger.warning("本地封面上传未成功，尝试首帧兜底")

        # 分支二：首帧封面（或兜底）
        # 流程说明（3.1.3 D 步）：
        # 1. 弹窗打开后点击「设置横封面」→ 弹窗切换到横封面卡片（图2）
        # 2. 点击「完成」→ 触发封面检测，主页面出现「封面效果检测通过」（图3）
        clicked_horizontal = False
        # 弹窗可能在此时“晚出现”并遮挡按钮，点击前再扫一次
        await self._dismiss_vertical_cover_promo_if_present(page)
        await self._dismiss_horizontal_cover_traffic_promo_if_present(page)
        for sel in (Selectors.PUBLISH.get("COVER_HORIZONTAL_BTN") or []):
            try:
                btn = cover_modal_scope.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    clicked_horizontal = True
                    logger.info("弹窗内已点击「设置横封面」: %s", sel)
                    USER_LOG.info("[步骤5/9 视频封面] 已点击「设置横封面」")
                    break
            except Exception:
                continue

        if not clicked_horizontal:
            logger.warning("未找到或未点击「设置横封面」按钮")
            return PublishResult(success=False, error_message="视频封面设置失败，未找到「设置横封面」按钮")

        # 等待「完成」按钮出现（横封面卡片切换后才出现），用 wait_for 事件驱动
        # 在等待前再扫一次：有的账号会在切换横封面卡片后弹出引导弹窗
        await self._dismiss_vertical_cover_promo_if_present(page)
        await self._dismiss_horizontal_cover_traffic_promo_if_present(page)
        confirm_loc: Optional[Locator] = None
        for sel in (Selectors.PUBLISH.get("COVER_CONFIRM_BTN") or []):
            try:
                loc = cover_modal_scope.locator(sel).first
                await loc.wait_for(state="visible", timeout=3000)
                confirm_loc = loc
                logger.info("已检测到「完成」按钮: %s", sel)
                USER_LOG.info("[步骤5/9 视频封面] 已跳转到设置横封面卡片")
                break
            except Exception:
                continue

        if confirm_loc is None:
            logger.warning("未检测到「完成」按钮，尝试直接点击")

        # 点击「完成」前再扫一次（竖向推广弹窗常在横封面 Tab 上出现）
        await self._dismiss_vertical_cover_promo_if_present(page)
        await self._dismiss_horizontal_cover_traffic_promo_if_present(page)

        # 点击「完成」
        clicked_confirm = False
        for sel in (Selectors.PUBLISH.get("COVER_CONFIRM_BTN") or []):
            try:
                btn = cover_modal_scope.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    clicked_confirm = True
                    logger.info("已点击「完成」按钮")
                    USER_LOG.info("[步骤5/9 视频封面] 已点击「完成」")
                    break
            except Exception:
                continue

        if not clicked_confirm:
            logger.warning("未找到或未点击「完成」按钮")
            return PublishResult(success=False, error_message="视频封面设置失败，未找到「完成」按钮")

        # 立即检测一次（弹窗关闭后封面检测可能瞬间完成）
        if await self._see_cover_success_indicator(page):
            USER_LOG.info("[步骤5/9 视频封面] ✓ 封面设置成功")
        return None

    async def _handle_cover_upload_local(self, page: Page, modal_scope: Locator, cover_path: str) -> bool:
        """弹窗内：点击上传封面 → 选择本地图片 → 等待上传成功 → 点击完成。"""
        from pathlib import Path
        if not Path(cover_path).exists():
            logger.warning("本地封面文件不存在: %s", cover_path)
            return False
        for sel in Selectors.PUBLISH.get("COVER_UPLOAD_BTN", []):
            try:
                btn = modal_scope.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await self._wait_modal_confirm_visible(page, modal_scope, timeout_ms=3000)
                    break
            except Exception:
                continue
        for sel in Selectors.PUBLISH.get("COVER_FILE_INPUT", []):
            try:
                inp = modal_scope.locator(sel).first
                if await inp.count() > 0:
                    await inp.set_input_files(cover_path)
                    await self._wait_modal_confirm_visible(page, modal_scope, timeout_ms=4000)

                    found_confirm = False
                    # 弹窗内固定顺序（图1→图2→图3）：先点「设置横封面」→ 等待 → 再点「完成」才触发封面检测
                    # 弹窗可能在此时弹出并遮挡按钮，点击前先关闭
                    await self._dismiss_vertical_cover_promo_if_present(page)
                    await self._dismiss_horizontal_cover_traffic_promo_if_present(page)
                    for hor_sel in (Selectors.PUBLISH.get("COVER_HORIZONTAL_BTN") or []):
                        try:
                            btn_h = modal_scope.locator(hor_sel).first
                            if await btn_h.count() > 0 and await btn_h.is_visible():
                                await btn_h.click()
                                await self._wait_modal_confirm_visible(page, modal_scope, timeout_ms=3000)
                                break
                        except Exception:
                            continue

                    await self._dismiss_vertical_cover_promo_if_present(page)
                    await self._dismiss_horizontal_cover_traffic_promo_if_present(page)

                    for confirm_sel in Selectors.PUBLISH.get("COVER_CONFIRM_BTN", []):
                        try:
                            cbtn = modal_scope.locator(confirm_sel).first
                            if await cbtn.count() > 0 and await cbtn.is_visible():
                                await cbtn.click()
                                await self._wait_cover_success_indicator(page, {}, timeout_ms=4000)
                                found_confirm = True
                                break
                        except Exception:
                            continue

                    if not found_confirm:
                        logger.info("图片已放入 input，但未找到或无需点击'确认'按钮，视作设置完成")
                    return True
            except Exception as e:
                logger.warning(f"填入封面 input 发生异常: {e}")
                continue
        return False




