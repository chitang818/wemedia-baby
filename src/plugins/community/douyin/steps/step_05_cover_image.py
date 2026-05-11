# -*- coding: utf-8 -*-
"""
步骤5：图文封面（主链挂载，默认立即完成）
文件路径: src/plugins/community/douyin/steps/step_05_cover_image.py

默认：平台以首张上传图为封面，本步不操作 DOM，直接返回成功（与 Runner 的「步骤5/9 图文封面」日志一致）。
仅在以下情况才执行原有点击/弹窗逻辑：
  - `metadata["image_cover_interactive"] is True`（强制走完整交互，含 first_frame 点首张）
  - 或 `cover_type == "custom"` 且提供 `cover_path`
  - 或 `cover_type == "ai"`

流程（仅交互模式）：
  - 首帧（first_frame）：无弹窗情况下，直接在图文主页面的缩略图列表第一张点击设为候选封面。
  - 本地图片（custom）：
      1. 点击封面主页面按钮呼出封面配置弹窗
      2. 找到弹窗内的上传入口，使用 set_input_files 传入路径
      3. 延迟后点击确认
  - AI封面（ai）：
      1. 点击封面主页面按钮呼出弹窗
      2. 切换至 AI 选项卡，等待运算出候选
      3. 选择第一张候选并确认

字段依赖：
  - metadata['cover_type']: custom / first_frame / ai
  - metadata['cover_path']: custom 的本地路径
"""
import logging
from typing import Dict, Any, Optional

from playwright.async_api import Page, Locator

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class CoverImageStep(BasePublishStep):
    """图文封面：默认跳过；显式配置或 image_cover_interactive 时再操作页面。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        cover_type = (metadata.get("cover_type") or "first_frame").strip().lower() if metadata.get("cover_type") else "first_frame"
        cover_path = (metadata.get("cover_path") or "").strip()
        if cover_path and cover_type != "custom":
            cover_type = "custom"

        explicit_ui = (
            metadata.get("image_cover_interactive") is True
            or (cover_type == "custom" and bool(cover_path))
            or cover_type == "ai"
        )
        if not explicit_ui:
            logger.info("图文封面步骤：默认首张上传图即为封面，跳过页面操作")
            return None

        logger.info("===== 图文封面设置（交互模式） =====")
        USER_LOG.info("图文封面 ▶ 按配置操作页面")
        config = metadata.get("anti_risk_config") or {}

        # 图文封面交互优先命中 OpenClaw 报告中的「编辑封面」入口 ref=e256；
        # 同一套 COVER_BTN 候选里还可能包含视频页面 ref=e153，因此在图文步骤内做排序。
        cover_btn_selectors = list(Selectors.PUBLISH.get("COVER_BTN") or [])
        cover_btn_selectors.sort(key=lambda s: 0 if "[ref=e256]" in s else 1)

        for selector in cover_btn_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click
                        await human_click(page, btn, metadata, config)
                    except Exception:
                        await btn.click()
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay
                        await random_delay(page, 800, metadata, config)
                    except Exception:
                        await page.wait_for_timeout(800)
                    logger.info(f"已点击图文封面按钮: {selector}")
                    USER_LOG.info("图文封面 ▶ 已点击封面入口")
                    break
            except Exception:
                continue

        if await self._is_cover_modal_open(page):
            return await self._handle_cover_modal(page, metadata, cover_type, cover_path)

        # 无弹窗时：图文页常用“第一张图即封面”
        if cover_type == "first_frame":
            try:
                img_thumb_selector = ", ".join(Selectors.PUBLISH.get("IMAGE_THUMBNAIL", []))
                thumbs = page.locator(img_thumb_selector)
                cnt = await thumbs.count()
                if cnt > 0:
                    first_thumb = thumbs.nth(0)
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click
                        await human_click(page, first_thumb, metadata, config)
                    except Exception:
                        await first_thumb.click()
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay
                        await random_delay(page, 300, metadata, config)
                    except Exception:
                        await page.wait_for_timeout(300)
                    logger.info("已在图文图片列表中点击第一张图片作为封面候选")
                    USER_LOG.info("图文封面 ✓ 已选择第一张作为候选")
                    return None
            except Exception:
                pass

        logger.info("未能找到图文封面设置入口，跳过图文封面设置")
        USER_LOG.info("图文封面 ✓ 跳过（未找到入口）")
        return None

    async def _is_cover_modal_open(self, page: Page) -> bool:
        for selector in Selectors.PUBLISH.get("COVER_MODAL", []):
            try:
                if await page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    async def _handle_cover_modal(
        self, page: Page, metadata: Dict[str, Any], cover_type: str, cover_path: str
    ) -> Optional[PublishResult]:
        await self._await_pause(metadata)
        logger.info("图文封面弹窗已打开，按配置执行: %s", cover_type)
        USER_LOG.info("图文封面 ▶ 弹窗已打开，选择并确认")

        # 封面弹窗 scope：弹窗内按钮/输入框必须从此 scope 内查找
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
            return PublishResult(success=False, error_message="封面弹窗未就绪，无法按规范定位弹窗内按钮")

        if cover_type == "custom" and cover_path:
            if await self._handle_cover_upload_local(page, cover_modal_scope, cover_path):
                USER_LOG.info("图文封面 ✓ 已上传本地封面并确认")
                return None
        if cover_type == "ai":
            if await self._handle_cover_ai(page, cover_modal_scope):
                USER_LOG.info("图文封面 ✓ 已选择 AI 智能封面并确认")
                return None

        clicked = False
        thumb_selector = ", ".join(Selectors.PUBLISH.get("COVER_THUMB", [])) or "img"
        try:
            thumbs = cover_modal_scope.locator(thumb_selector)
            cnt = await thumbs.count()
            if cnt > 0:
                await thumbs.nth(0).click()
                clicked = True
                await page.wait_for_timeout(300)
                logger.info(f"已选择图文封面缩略图: {thumb_selector}")
        except Exception:
            pass

        for selector in Selectors.PUBLISH.get("COVER_CONFIRM_BTN", []):
            try:
                btn = cover_modal_scope.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(800)
                    logger.info(f"已确认图文封面: {selector}")
                    USER_LOG.info("图文封面 ✓ 已确认")
                    return None
            except Exception:
                continue

        if clicked:
            logger.warning("已选择图文封面但未找到确认按钮，继续流程（可能自动保存）")
            return None

        logger.warning("图文封面弹窗操作失败：未找到缩略图或确认按钮")
        return None

    async def _handle_cover_upload_local(self, page: Page, modal_scope: Locator, cover_path: str) -> bool:
        from pathlib import Path
        if not Path(cover_path).exists():
            return False
        for sel in Selectors.PUBLISH.get("COVER_UPLOAD_BTN", []):
            try:
                btn = modal_scope.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(800)
                    break
            except Exception:
                continue
        for sel in Selectors.PUBLISH.get("COVER_FILE_INPUT", []):
            try:
                inp = modal_scope.locator(sel).first
                if await inp.count() > 0:
                    await inp.set_input_files(cover_path)
                    await page.wait_for_timeout(2000)
                    for confirm_sel in Selectors.PUBLISH.get("COVER_CONFIRM_BTN", []):
                        try:
                            cbtn = modal_scope.locator(confirm_sel).first
                            if await cbtn.count() > 0 and await cbtn.is_visible():
                                await cbtn.click()
                                await page.wait_for_timeout(1000)
                                return True
                        except Exception:
                            continue
                    return True
            except Exception:
                continue
        return False

    async def _handle_cover_ai(self, page: Page, modal_scope: Locator) -> bool:
        for sel in Selectors.PUBLISH.get("COVER_AI_OPTION", []):
            try:
                loc = modal_scope.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    await page.wait_for_timeout(1500)
                    thumbs = modal_scope.locator(", ".join(Selectors.PUBLISH.get("COVER_THUMB", [])) or "img")
                    if await thumbs.count() > 0:
                        await thumbs.nth(0).click()
                        await page.wait_for_timeout(300)
                    for confirm_sel in Selectors.PUBLISH.get("COVER_CONFIRM_BTN", []):
                        try:
                            cbtn = modal_scope.locator(confirm_sel).first
                            if await cbtn.count() > 0 and await cbtn.is_visible():
                                await cbtn.click()
                                await page.wait_for_timeout(1000)
                                return True
                        except Exception:
                            continue
                    return True
            except Exception:
                continue
        return False

