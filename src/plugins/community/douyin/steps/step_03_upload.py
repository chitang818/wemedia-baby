# -*- coding: utf-8 -*-
"""
步骤3：上传素材
文件路径: src/plugins/community/douyin/steps/step_03_upload.py

流程（根据 file_type）：
  - 视频上传：
    1. 优先通过原生 set_input_files 操作 input[type=file]
    2. 兜底方案：点击上传区域触发 file chooser 对话框操作
    3. 轮询等待上传完成：以是否出现「重新上传」文字为判定标准（VIDEO_UPLOAD_SUCCESS_MARKER）
  - 图文上传：
    1. 优先原生的多文件 set_input_files 批量传入图片列表
    2. 兜底：点击上传按钮触发 file chooser 进行多图上传
    3. 轮询等待上传完成：以预览区出现「清空并重新上传」按钮为准（IMAGE_UPLOAD_SUCCESS_MARKER）

字段依赖：
  - file_path (直传) / metadata['image_paths']: 素材路径
  - metadata['file_type']: "video" 或 "image"
  - metadata['upload_timeout_seconds']: 视频上传超时
  - metadata['image_upload_timeout_seconds']: 图文上传超时
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
    paths = metadata.get("image_paths")
    if isinstance(paths, list) and paths:
        return [str(p).strip() for p in paths if str(p).strip()]
    # 兼容历史：逗号分隔，过滤文件夹来源标记
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
        base = os.path.basename(str(file_path))
        USER_LOG.info(f"[步骤3/9 上传视频/图文] ▶ 开始 文件={base} 路径={file_path}")

        # 唯一方案：通过 FILE_INPUT 的第一个选择器直接 set_input_files
        first_selector = Selectors.PUBLISH["FILE_INPUT"][0]
        try:
            input_file = page.locator(first_selector).first
            if await input_file.count() == 0:
                return PublishResult(success=False, error_message=f"未找到视频上传文件输入框（sel={first_selector}），可能页面结构已变更")
            await input_file.set_input_files(file_path)
            logger.info("使用 set_input_files 触发视频上传（sel=%s）", first_selector)
            return await self._wait_for_video_upload_complete(page, metadata)
        except Exception as e:
            logger.error(f"set_input_files 上传视频失败: {e}")
            return PublishResult(success=False, error_message=f"视频上传失败: {e}")

    async def _wait_for_video_upload_complete(self, page: Page, metadata: Dict[str, Any]) -> Optional[PublishResult]:
        """等待视频上传完成：仅当页面出现「重新上传」区域（label.upload-btn-PdfuUv）时判定为成功。"""
        max_wait_seconds = int(metadata.get("upload_timeout_seconds") or 180)
        logger.info("等待视频上传/转码就绪（最长 %s 分钟），检测「重新上传」按钮是否出现...", max_wait_seconds // 60)
        USER_LOG.info("[步骤3/9 上传视频/图文] 正在上传中，等待上传成功（最长 %d 秒）…", max_wait_seconds)
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        # 唯一判定：出现 label.upload-btn-PdfuUv（重新上传）即代表视频已上传成功
        success_marker = ", ".join(Selectors.PUBLISH["VIDEO_UPLOAD_SUCCESS_MARKER"])
        for i in range(max_wait_seconds // 2):
            await self._await_pause(metadata)
            if await page.locator(success_marker).count() > 0:
                logger.info("检测到「重新上传」按钮已出现，视频上传成功")
                USER_LOG.info("[步骤3/9 上传视频/图文] ✓ 上传成功")
                return None

            elapsed = i * 2
            if i % 30 == 0:
                logger.info(f"等待上传中... ({elapsed}s/{max_wait_seconds}s)")
            if i > 0 and i % 15 == 0:
                USER_LOG.info("[步骤3/9 上传视频/图文] 正在上传中，已等待 %d 秒，等待「重新上传」按钮出现…", elapsed)
            config = metadata.get("anti_risk_config") or {}
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, int(2000 * speed_rate), metadata, config)
            except Exception:
                await page.wait_for_timeout(int(2000 * speed_rate))
            # 每轮让出一次事件循环控制权，防止长时间上传等待期间 Qt UI 无响应
            import asyncio as _asyncio
            await _asyncio.sleep(0)

        return PublishResult(success=False, error_message=f"等待视频上传超时 ({max_wait_seconds}秒)")

    async def _upload_images(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> Optional[PublishResult]:
        logger.info("===== 开始上传图文图片 =====")
        image_paths = _parse_image_paths(file_path, metadata)
        base = os.path.basename(str(image_paths[0])) if image_paths else ""
        USER_LOG.info(f"[步骤3/9 上传视频/图文] ▶ 开始 图文数量={len(image_paths)} 文件示例={base} 路径={file_path}")

        if not image_paths:
            return PublishResult(success=False, error_message="图文上传失败: 未提供图片路径")
        if not os.path.exists(image_paths[0]):
            return PublishResult(success=False, error_message=f"图文上传失败: 找不到图片文件 -> {image_paths[0]}")

        # 唯一方案：通过 IMAGE_FILE_INPUT 的第一个选择器直接 set_input_files
        first_selector = Selectors.PUBLISH["IMAGE_FILE_INPUT"][0]
        try:
            input_file = page.locator(first_selector).first
            if await input_file.count() == 0:
                return PublishResult(success=False, error_message=f"未找到图片上传文件输入框（sel={first_selector}），可能页面结构已变更")
            await input_file.set_input_files(image_paths)
            logger.info(f"已 set_input_files 上传图片: {len(image_paths)} 张（sel={first_selector}）")
            return await self._wait_for_images_upload_complete(page, metadata)
        except Exception as e:
            logger.error(f"set_input_files 上传图片失败: {e}")
            return PublishResult(success=False, error_message=f"图文上传失败: {e}")

    async def _image_upload_success_visible(self, page: Page) -> bool:
        """图文上传成功：预览区「清空并重新上传」按钮已显示，只检测第一个选择器。"""
        markers = Selectors.PUBLISH.get("IMAGE_UPLOAD_SUCCESS_MARKER") or []
        if not markers:
            return False
        sel = markers[0]
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            pass
        return False

    async def _wait_for_images_upload_complete(self, page: Page, metadata: Dict[str, Any]) -> Optional[PublishResult]:
        max_wait_seconds = int(metadata.get("image_upload_timeout_seconds") or 180)
        logger.info("等待图文上传完成：检测「清空并重新上传」按钮（最长 %s 分钟）...", max_wait_seconds // 60)
        USER_LOG.info("[步骤3/9 上传视频/图文] 正在上传图文，等待「清空并重新上传」出现（最长 %d 秒）…", max_wait_seconds)
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        for i in range(max_wait_seconds // 2):
            await self._await_pause(metadata)
            if await self._image_upload_success_visible(page):
                logger.info("已检测到「清空并重新上传」按钮，图文上传成功")
                USER_LOG.info("[步骤3/9 上传视频/图文] ✓ 上传成功")
                return None

            elapsed = i * 2
            if i % 10 == 0:
                logger.info(f"等待图文上传就绪... ({elapsed}s/{max_wait_seconds}s)")
            if i > 0 and i % 15 == 0:
                USER_LOG.info("[步骤3/9 上传视频/图文] 正在上传图文，已等待 %d 秒，等待「清空并重新上传」…", elapsed)
            config = metadata.get("anti_risk_config") or {}
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, int(2000 * speed_rate), metadata, config)
            except Exception:
                await page.wait_for_timeout(int(2000 * speed_rate))
            # 每轮让出一次事件循环控制权，防止长时间上传等待期间 Qt UI 无响应
            import asyncio as _asyncio
            await _asyncio.sleep(0)

        return PublishResult(
            success=False,
            error_message=f"等待图文上传超时 ({max_wait_seconds}秒)，未出现「清空并重新上传」按钮",
        )
