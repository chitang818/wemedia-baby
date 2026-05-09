# -*- coding: utf-8 -*-
"""
步骤3：上传素材
文件路径: src/plugins/pro/xiaohongshu/steps/step_03_upload.py

流程（根据 file_type）：
  - 视频上传：
    1. 优先通过原生 set_input_files 操作 input[type=file]
    2. 兜底：点击上传区域触发 file chooser
    3. 轮询等待上传完成
  - 图文上传：
    1. 批量 set_input_files 传入图片列表
    2. 兜底：点击上传按钮触发 file chooser
    3. 轮询等待图片缩略图渲染出现

字段依赖：
  - file_path: 素材路径
  - metadata['image_paths']: 图文模式的图片路径列表
  - metadata['file_type']: "video" 或 "image"
  - metadata['upload_timeout_seconds']: 上传超时
"""
import logging
import os
from typing import Dict, Any, Optional, List

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


_FOLDER_MARKER_PREFIX = "__FOLDER__:"


def _parse_image_paths(file_path: str, metadata: Dict[str, Any]) -> List[str]:
    """解析图片路径列表，过滤文件夹来源标记。"""
    paths = metadata.get("image_paths")
    if isinstance(paths, list) and paths:
        return [str(p).strip() for p in paths if str(p).strip()]
    return [
        p.strip() for p in str(file_path).split(",")
        if p.strip() and not p.strip().startswith(_FOLDER_MARKER_PREFIX)
    ]


class UploadMediaStep(BasePublishStep):
    """统一上传步骤：根据 file_type 上传视频或图文。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        file_type = (metadata.get("file_type") or "video").lower()

        if file_type == "image":
            return await self._upload_images(page, file_path, metadata)
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

        success_selectors = (
            Selectors.PUBLISH["UPLOAD_SUCCESS_MARKER"]
            + Selectors.PUBLISH["REUPLOAD_BTN"]
        )
        combined = ", ".join(success_selectors)

        for i in range(max_wait_seconds // 2):
            await self._await_pause(metadata)

            try:
                if await page.locator(combined).count() > 0:
                    logger.info("检测到上传成功标识")
                    USER_LOG.info("[步骤3 上传] ✓ 上传成功")
                    return None
            except Exception:
                pass

            elapsed = i * 2
            if i % 30 == 0 and i > 0:
                logger.info(f"等待上传中… ({elapsed}s/{max_wait_seconds}s)")
            if i > 0 and i % 15 == 0:
                USER_LOG.info(f"[步骤3 上传] 正在上传中，已等待 {elapsed} 秒…")

            config = metadata.get("anti_risk_config") or {}
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, int(2000 * speed_rate), metadata, config)
            except Exception:
                await page.wait_for_timeout(int(2000 * speed_rate))

        return PublishResult(success=False, error_message=f"等待上传超时 ({max_wait_seconds}秒)")

    async def _upload_images(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> Optional[PublishResult]:
        logger.info("===== 开始上传图文图片 =====")
        image_paths = _parse_image_paths(file_path, metadata)
        if not image_paths:
            return PublishResult(success=False, error_message="图文上传失败: 未提供图片路径")

        base_name = os.path.basename(str(image_paths[0]))
        USER_LOG.info(f"[步骤3 上传] ▶ 开始 图文数量={len(image_paths)} 示例={base_name}")

        if not os.path.exists(image_paths[0]):
            return PublishResult(success=False, error_message=f"图文上传失败: 找不到图片文件 -> {image_paths[0]}")

        # 策略1：直接 set_input_files（支持批量）
        try:
            file_input_selector = ", ".join(Selectors.PUBLISH["FILE_INPUT"])
            input_file = page.locator(file_input_selector).first
            if await input_file.count() > 0:
                await input_file.set_input_files(image_paths)
                logger.info(f"已 set_input_files 上传图片: {len(image_paths)} 张")
                return await self._wait_for_images_upload_complete(page, len(image_paths), metadata)
        except Exception as e:
            logger.info(f"set_input_files 上传图片失败，尝试 file chooser: {e}")

        # 策略2：点击上传按钮触发 file chooser
        try:
            upload_btn_selector = ", ".join(Selectors.PUBLISH["UPLOAD_BTN"])
            upload_btn = page.locator(upload_btn_selector).first
            if await upload_btn.count() > 0:
                async with page.expect_file_chooser(timeout=10000) as fc_info:
                    await upload_btn.click(force=True)
                fc = await fc_info.value
                await fc.set_files(image_paths)
                logger.info("通过 file chooser 上传图片完成")
                return await self._wait_for_images_upload_complete(page, len(image_paths), metadata)
        except Exception as e:
            logger.error(f"点击上传入口上传图片失败: {e}")

        return PublishResult(success=False, error_message="图文上传失败: 无法找到图片上传入口")

    async def _wait_for_images_upload_complete(
        self, page: Page, expected_count: int, metadata: Dict[str, Any]
    ) -> Optional[PublishResult]:
        max_wait_seconds = int(metadata.get("image_upload_timeout_seconds") or 120)
        logger.info(f"等待图片缩略图渲染（最长 {max_wait_seconds} 秒）…")
        USER_LOG.info(f"[步骤3 上传] 正在上传图文（最长 {max_wait_seconds} 秒）…")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        thumb_selector = ", ".join(Selectors.PUBLISH["IMAGE_THUMBNAIL"])

        for i in range(max_wait_seconds // 2):
            await self._await_pause(metadata)
            try:
                cnt = await page.locator(thumb_selector).count()
                if cnt >= 1:
                    logger.info(f"检测到图片缩略图数量={cnt}，认为上传已就绪")
                    USER_LOG.info("[步骤3 上传] ✓ 上传成功")
                    return None
            except Exception:
                pass

            elapsed = i * 2
            if i % 10 == 0 and i > 0:
                logger.info(f"等待图片就绪… ({elapsed}s/{max_wait_seconds}s)")
            if i > 0 and i % 15 == 0:
                USER_LOG.info(f"[步骤3 上传] 正在上传图文，已等待 {elapsed} 秒…")

            config = metadata.get("anti_risk_config") or {}
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, int(2000 * speed_rate), metadata, config)
            except Exception:
                await page.wait_for_timeout(int(2000 * speed_rate))

        return PublishResult(success=False, error_message=f"等待图片上传就绪超时 ({max_wait_seconds}秒)")
