# -*- coding: utf-8 -*-
"""
步骤5：封面设置
文件路径: src/plugins/pro/baijiahao/steps/step_05_cover.py

流程：
  - 默认（first_frame）：不做额外操作，百家号默认使用视频截图帧作为封面
  - 自定义（custom）：
    1. 点击封面设置入口（更改封面）
    2. 找到上传入口，set_input_files 传入封面图片
    3. 确认封面

字段依赖：
  - metadata['cover_type']: "first_frame" / "custom"
  - metadata['cover_path']: custom 的本地路径
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class CoverSettingStep(BasePublishStep):
    """封面设置：按配置选择默认封面或上传自定义封面。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        cover_type = (metadata.get("cover_type") or "first_frame").strip().lower()
        cover_path = (metadata.get("cover_path") or "").strip()

        if cover_path and cover_type != "custom":
            cover_type = "custom"

        logger.info(f"===== 封面设置: cover_type={cover_type} =====")

        if cover_type == "first_frame":
            logger.info("使用默认封面（视频截图帧），跳过封面设置")
            USER_LOG.info("[步骤5 封面设置] ✓ 跳过（使用默认封面）")
            return None

        # 自定义封面上传
        if cover_type == "custom" and cover_path:
            if not Path(cover_path).exists():
                logger.warning(f"封面文件不存在: {cover_path}，跳过封面设置")
                USER_LOG.info("[步骤5 封面设置] ✓ 跳过（封面文件不存在）")
                return None

            config = metadata.get("anti_risk_config") or {}
            USER_LOG.info("[步骤5 封面设置] ▶ 尝试上传自定义封面")

            # 点击封面设置入口
            for selector in Selectors.PUBLISH["COVER_BTN"]:
                try:
                    btn = page.locator(selector).first
                    if await btn.count() > 0 and await btn.is_visible():
                        try:
                            from src.infrastructure.anti_risk.human_like import human_click
                            await human_click(page, btn, metadata, config)
                        except Exception:
                            await btn.click()

                        await PluginWaitHelper.wait_for_any_visible(
                            page,
                            Selectors.PUBLISH.get("COVER_MODAL", []),
                            timeout_ms=2_000,
                            poll_interval_ms=250,
                            pause_callback=lambda: self._await_pause(metadata),
                        )

                        logger.info(f"已点击封面设置按钮: {selector}")
                        break
                except Exception:
                    continue

            # 检测封面弹窗是否打开
            modal_open = False
            for selector in Selectors.PUBLISH["COVER_MODAL"]:
                try:
                    if await page.locator(selector).count() > 0:
                        modal_open = True
                        break
                except Exception:
                    continue

            if modal_open:
                return await self._handle_cover_upload(page, cover_path, metadata)

            # 弹窗未打开，尝试直接通过 file input 上传
            for selector in Selectors.PUBLISH["COVER_FILE_INPUT"]:
                try:
                    inp = page.locator(selector).first
                    if await inp.count() > 0:
                        await inp.set_input_files(cover_path)
                        await PluginWaitHelper.wait_for_any_visible(page, Selectors.PUBLISH.get("COVER_CONFIRM_BTN", []), timeout_ms=3_000, poll_interval_ms=300, pause_callback=lambda: self._await_pause(metadata))
                        logger.info("通过 file input 直接上传封面")
                        USER_LOG.info("[步骤5 封面设置] ✓ 封面已上传")
                        return None
                except Exception:
                    continue

            logger.warning("未能找到封面设置入口，跳过封面设置")
            USER_LOG.info("[步骤5 封面设置] ✓ 跳过（未找到入口）")
            return None

        logger.info("无需设置封面，跳过")
        USER_LOG.info("[步骤5 封面设置] ✓ 跳过")
        return None

    async def _handle_cover_upload(
        self, page: Page, cover_path: str, metadata: Dict[str, Any]
    ) -> Optional[PublishResult]:
        """在封面弹窗中上传并确认封面。"""
        logger.info("封面弹窗已打开，上传自定义封面")
        config = metadata.get("anti_risk_config") or {}

        for sel in Selectors.PUBLISH.get("COVER_UPLOAD_BTN", []):
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click()
                    await PluginWaitHelper.wait_for_any_attached(page, Selectors.PUBLISH.get("COVER_FILE_INPUT", []), timeout_ms=2_000, poll_interval_ms=250, pause_callback=lambda: self._await_pause(metadata))
                    break
            except Exception:
                continue

        for sel in Selectors.PUBLISH.get("COVER_FILE_INPUT", []):
            try:
                inp = page.locator(sel).first
                if await inp.count() > 0:
                    await inp.set_input_files(cover_path)
                    await PluginWaitHelper.wait_for_any_visible(page, Selectors.PUBLISH.get("COVER_CONFIRM_BTN", []), timeout_ms=3_000, poll_interval_ms=300, pause_callback=lambda: self._await_pause(metadata))

                    for confirm_sel in Selectors.PUBLISH.get("COVER_CONFIRM_BTN", []):
                        try:
                            cbtn = page.locator(confirm_sel).first
                            if await cbtn.count() > 0 and await cbtn.is_visible():
                                try:
                                    from src.infrastructure.anti_risk.human_like import human_click
                                    await human_click(page, cbtn, metadata, config)
                                except Exception:
                                    await cbtn.click()
                                await PluginWaitHelper.wait_for_all_hidden(page, Selectors.PUBLISH.get("COVER_MODAL", []), timeout_ms=2_000, poll_interval_ms=250, pause_callback=lambda: self._await_pause(metadata))
                                logger.info("已确认封面设置")
                                USER_LOG.info("[步骤5 封面设置] ✓ 封面已上传并确认")
                                return None
                        except Exception:
                            continue

                    logger.info("封面已上传但未找到确认按钮")
                    USER_LOG.info("[步骤5 封面设置] ✓ 封面已上传")
                    return None
            except Exception:
                continue

        logger.warning("封面弹窗内上传失败")
        USER_LOG.info("[步骤5 封面设置] ✓ 跳过（弹窗内操作失败）")
        return None
