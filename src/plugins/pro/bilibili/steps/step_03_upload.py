# -*- coding: utf-8 -*-
"""
步骤3：上传素材
文件路径: src/plugins/pro/bilibili/steps/step_03_upload.py

流程：
  - 视频上传：
    1. 优先通过原生 set_input_files 操作 input[type=file]
    2. 兜底：点击上传区域触发 file chooser
    3. 轮询等待上传完成：以是否出现视频信息容器或「重新上传」按钮为判定标准

字段依赖：
  - file_path: 视频文件路径
  - metadata['upload_timeout_seconds']: 上传超时（默认 300 秒）
  - metadata['speed_rate']: 等待倍率
"""
import logging
import os
from typing import Dict, Any, Optional

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class UploadMediaStep(BasePublishStep):
    """上传视频文件到B站。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        return await self._upload_video(page, file_path, metadata)

    async def _upload_video(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> Optional[PublishResult]:
        logger.info("===== 开始上传视频文件 =====")
        base_name = os.path.basename(str(file_path))
        USER_LOG.info(f"[步骤3 上传] ▶ 开始 文件={base_name}")

        if not os.path.exists(file_path):
            return PublishResult(success=False, error_message=f"视频文件不存在: {file_path}")

        # 策略1：直接 set_input_files
        try:
            file_input_selector = ", ".join(Selectors.PUBLISH["FILE_INPUT"])
            input_file = page.locator(file_input_selector).first
            if await input_file.count() > 0:
                await input_file.set_input_files(file_path)
                logger.info("使用 set_input_files 触发视频上传")
                return await self._wait_for_upload_complete(page, metadata)
        except Exception as e:
            logger.info(f"直接 set_input_files 失败，尝试备用方案: {e}")

        # 策略2：点击上传区域触发 file chooser
        try:
            upload_btn_selector = ", ".join(Selectors.PUBLISH["UPLOAD_BTN"])
            upload_btn = page.locator(upload_btn_selector).first
            if await upload_btn.count() > 0:
                async with page.expect_file_chooser(timeout=10000) as fc_info:
                    await upload_btn.click(force=True)
                fc = await fc_info.value
                await fc.set_files(file_path)
                logger.info("通过 file chooser 上传视频完成")
                return await self._wait_for_upload_complete(page, metadata)
        except Exception as e:
            logger.error(f"点击上传区域上传视频失败: {e}")

        return PublishResult(success=False, error_message="无法找到视频上传入口，可能页面结构已变更")

    async def _wait_for_upload_complete(self, page: Page, metadata: Dict[str, Any]) -> Optional[PublishResult]:
        """等待上传完成：检测上传成功标识或重新上传按钮出现。"""
        max_wait_seconds = int(metadata.get("upload_timeout_seconds") or 300)
        logger.info(f"等待上传就绪（最长 {max_wait_seconds} 秒）…")
        USER_LOG.info(f"[步骤3 上传] 正在上传中（最长 {max_wait_seconds} 秒）…")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        poll_ms = max(300, int(700 * speed_rate))
        max_attempts = max(1, int(max_wait_seconds * 1000 / poll_ms))

        success_selectors = (
            Selectors.PUBLISH["UPLOAD_SUCCESS_MARKER"]
            + Selectors.PUBLISH["REUPLOAD_BTN"]
        )
        combined = ", ".join(success_selectors)

        for i in range(max_attempts):
            await self._await_pause(metadata)

            try:
                if await page.locator(combined).count() > 0:
                    logger.info("检测到上传成功标识")
                    USER_LOG.info("[步骤3 上传] ✓ 上传成功")
                    return None
            except Exception:
                pass

            # B站上传后标题输入框会出现，也可作为判定依据
            try:
                title_selector = ", ".join(Selectors.PUBLISH["TITLE_INPUT"])
                if await page.locator(title_selector).count() > 0:
                    if await page.locator(title_selector).first.is_visible():
                        logger.info("检测到标题输入框已出现，视为上传就绪")
                        USER_LOG.info("[步骤3 上传] ✓ 上传成功")
                        return None
            except Exception:
                pass

            elapsed = int(i * poll_ms / 1000)
            if i % 30 == 0 and i > 0:
                logger.info(f"等待上传中… ({elapsed}s/{max_wait_seconds}s)")
            if i > 0 and i % 15 == 0:
                USER_LOG.info(f"[步骤3 上传] 正在上传中，已等待 {elapsed} 秒…")

            await page.wait_for_timeout(poll_ms)

        return PublishResult(success=False, error_message=f"等待上传超时 ({max_wait_seconds}秒)")
