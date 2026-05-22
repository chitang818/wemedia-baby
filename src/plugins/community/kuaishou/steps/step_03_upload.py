# -*- coding: utf-8 -*-
"""
步骤3：上传视频 / 图片
文件路径: src/plugins/community/kuaishou/steps/step_03_upload.py

流程（视频）：
  1. 通过 input[type=file] 的 set_input_files 上传
  2. 轮询等待上传完成（上传完成文案或进度消失）

流程（图文）：
  1. 从 metadata['image_paths'] 或 file_path（逗号分隔列表）取图片路径列表
  2. 定位 #rc-tabs-0-panel-2 内的 image input（accept=image/*, multiple=True）
  3. 一次性调用 set_input_files(list) 批量上传所有图片
  4. 等待「编辑图片」区域出现，确认上传成功

  注：X-Ray 20260403 实测，快手图文页的图片 file input 为 multiple=True，
      可一次性传多张；视频 input（multiple=False）在 panel-1 中，二者并存于同一页面。

字段依赖：
  metadata['file_type']:    "video"（默认）或 "image"
  metadata['image_paths']:  图文模式时的图片路径列表（List[str] 或逗号分隔字符串）
                            若未提供则使用 file_path
"""
import logging
import os
from typing import Dict, Any, List, Optional

from playwright.async_api import Page

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from .wizard_utils import dismiss_kuaishou_publish_guides
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class UploadMediaStep(BasePublishStep):
    """上传视频或图片步骤。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        file_type = (metadata.get("file_type") or "video").lower()
        # 动态步骤前缀，供子方法日志使用
        self._prefix_video = self._step_prefix(metadata, "上传视频")
        self._prefix_image = self._step_prefix(metadata, "上传图片")

        if file_type == "image":
            return await self._upload_images(page, file_path, metadata)
        else:
            return await self._upload_video(page, file_path, metadata)

    # ------------------------------------------------------------------
    # 视频上传（原有逻辑）
    # ------------------------------------------------------------------

    async def _upload_video(
        self, page: Page, file_path: str, metadata: Dict[str, Any]
    ) -> StepOutcome:
        logger.info("===== 开始上传视频文件 =====")
        base = os.path.basename(str(file_path))
        USER_LOG.info(f"{self._prefix_video} ▶ 开始 文件={base}")

        file_input_selectors = Selectors.PUBLISH.get("FILE_INPUT", [])
        first_selector = file_input_selectors[0] if file_input_selectors else None
        if not first_selector:
            return PublishResult(success=False, error_message="FILE_INPUT 选择器未配置，请检查 selectors.py")

        try:
            input_el = page.locator(first_selector).first
            if await input_el.count() == 0:
                return PublishResult(
                    success=False,
                    error_message=f"未找到视频上传文件输入框（sel={first_selector}），可能页面结构已变更",
                )
            await input_el.set_input_files(file_path)
            logger.info("使用 set_input_files 触发视频上传（sel=%s）", first_selector)
            return await self._wait_video_upload_complete(page, metadata)
        except Exception as e:
            logger.error(f"set_input_files 上传视频失败: {e}")
            return PublishResult(success=False, error_message=f"视频上传失败: {e}")

    async def _wait_video_upload_complete(
        self, page: Page, metadata: Dict[str, Any]
    ) -> Optional[PublishResult]:
        """等待视频上传完成。"""
        max_wait_seconds = int(metadata.get("upload_timeout_seconds") or 180)
        logger.info("等待视频上传/处理就绪（最长 %s 秒）...", max_wait_seconds)
        USER_LOG.info("%s 正在上传中，等待上传成功（最长 %d 秒）…", self._prefix_video, max_wait_seconds)
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        config = metadata.get("anti_risk_config") or {}

        markers = Selectors.PUBLISH.get("UPLOAD_SUCCESS_MARKER", [])
        if not markers:
            return PublishResult(
                success=False,
                error_message="UPLOAD_SUCCESS_MARKER 选择器未配置，请检查 selectors.py",
                failed_step="上传视频",
            )

        def _log_wait(attempt: int) -> None:
            elapsed = int(attempt * max(0.2, speed_rate))
            if attempt % 60 == 0:
                logger.info("等待上传中... (%ss/%ss)", elapsed, max_wait_seconds)
            if attempt > 0 and attempt % 30 == 0:
                USER_LOG.info("%s 正在上传中，已等待 %d 秒…", self._prefix_video, elapsed)

        matched = await PluginWaitHelper.wait_for_any_visible(
            page,
            markers,
            timeout_ms=max_wait_seconds * 1000,
            poll_interval_ms=max(200, int(1000 * speed_rate)),
            pause_callback=lambda: self._await_pause(metadata),
            on_poll=_log_wait,
        )
        if matched:
            logger.info("检测到上传完成标志（is_visible）: %s", matched)
            USER_LOG.info("%s ✓ 上传成功", self._prefix_video)
            await dismiss_kuaishou_publish_guides(page, metadata)
            return None

        logger.error("视频上传状态检测超时，终止发布流程")
        USER_LOG.error("%s ✖ 上传超时，未检测到完成标志，请检查网络后重试", self._prefix_video)
        return PublishResult(
            success=False,
            error_message="视频上传超时，未检测到上传完成标志，请检查网络或视频文件后重试",
            failed_step="上传视频",
        )

    # ------------------------------------------------------------------
    # 图片上传（新增）
    # ------------------------------------------------------------------

    def _resolve_image_paths(self, file_path: str, metadata: Dict[str, Any]) -> List[str]:
        """
        从 metadata['image_paths'] 或 file_path 解析出图片路径列表。
        支持：
          - metadata['image_paths'] 为 List[str]
          - metadata['image_paths'] 为逗号分隔字符串
          - file_path 为逗号分隔字符串（兼容旧方式）
          - file_path 为单个文件路径
        """
        raw = metadata.get("image_paths")
        if raw:
            if isinstance(raw, list):
                paths = [str(p).strip() for p in raw if str(p).strip()]
            else:
                paths = [p.strip() for p in str(raw).split(",") if p.strip()]
            if paths:
                return paths

        if file_path:
            _folder_pfx = "__FOLDER__:"
            if "," in str(file_path):
                paths = [
                    p.strip() for p in str(file_path).split(",")
                    if p.strip() and not p.strip().startswith(_folder_pfx)
                ]
                if paths:
                    return paths
            fp_str = str(file_path)
            if not fp_str.startswith(_folder_pfx):
                return [fp_str]

        return []

    async def _upload_images(
        self, page: Page, file_path: str, metadata: Dict[str, Any]
    ) -> StepOutcome:
        """
        批量上传图片文件。

        X-Ray 20260403 实测结论：
          - 快手图文发布页用 File Chooser 机制：点击「上传图片」按钮（_upload-btn_ysbff_57）
            弹出文件选择框，页面监听 chooser 事件完成上传。
          - 图片 file input（accept=image/*, multiple=True）为 display:none 的隐藏元素，
            直接对它调用 set_input_files 不会触发页面上传逻辑。
          - 正确方式：expect_file_chooser + 点击「上传图片」按钮，与视频上传机制完全一致。
        """
        image_paths = self._resolve_image_paths(file_path, metadata)
        if not image_paths:
            return PublishResult(
                success=False,
                error_message="图文发布未提供图片路径，请在 metadata['image_paths'] 中指定图片列表",
                failed_step="上传图片",
            )

        # 校验所有文件存在
        missing = [p for p in image_paths if not os.path.exists(p)]
        if missing:
            return PublishResult(
                success=False,
                error_message=f"以下图片文件不存在: {', '.join(os.path.basename(p) for p in missing)}",
                failed_step="上传图片",
            )

        names = [os.path.basename(p) for p in image_paths]
        logger.info("===== 开始上传图片（共 %d 张）=====", len(image_paths))
        USER_LOG.info("%s ▶ 开始 共 %d 张: %s", self._prefix_image, len(image_paths), ", ".join(names))

        # 找到「上传图片」按钮（DOM: button._upload-btn_ysbff_57）
        upload_btn_sels = Selectors.PUBLISH.get("IMAGE_UPLOAD_BTN", [])
        upload_btn = None
        used_btn_sel = None
        for sel in upload_btn_sels:
            try:
                el = page.locator(sel).first
                if await el.count() > 0 and await el.is_visible():
                    upload_btn = el
                    used_btn_sel = sel
                    logger.debug("步骤3(图文): 命中「上传图片」按钮，sel=%s", sel)
                    break
            except Exception as e:
                logger.debug("步骤3(图文): 上传按钮选择器 %s 失败: %s", sel, e)

        if upload_btn is None:
            # 兜底：直接对隐藏的 file input 调用 set_input_files（部分情况下可能有效）
            logger.warning("步骤3(图文): 未找到「上传图片」按钮，尝试直接操作 file input")
            return await self._upload_images_via_input(page, image_paths)

        # 主路：expect_file_chooser + 点击按钮（与视频上传链路完全一致）
        try:
            async with page.expect_file_chooser(timeout=10000) as fc_info:
                await upload_btn.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(image_paths)
            logger.info(
                "已通过 file_chooser 上传 %d 张图片（btn_sel=%s）",
                len(image_paths), used_btn_sel,
            )
        except Exception as e:
            logger.warning("步骤3(图文): expect_file_chooser 失败: %s，尝试直接操作 file input", e)
            return await self._upload_images_via_input(page, image_paths)

        return await self._wait_image_upload_complete(page, metadata, len(image_paths))

    async def _upload_images_via_input(
        self, page: Page, image_paths: List[str]
    ) -> StepOutcome:
        """兜底：直接对隐藏 file input 调用 set_input_files。"""
        input_sels = Selectors.PUBLISH.get("IMAGE_FILE_INPUT", [])
        input_el = None
        used_sel = None
        for sel in input_sels:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    input_el = el
                    used_sel = sel
                    break
            except Exception as e:
                logger.debug("步骤3(图文): file input 选择器 %s 失败: %s", sel, e)

        if input_el is None:
            return PublishResult(
                success=False,
                error_message="未找到图片上传入口（按钮和 file input 均未找到），请检查是否正确进入图文发布页",
                failed_step="上传图片",
            )

        try:
            await input_el.set_input_files(image_paths)
            logger.info("已通过 file input.set_input_files 上传 %d 张图片（sel=%s）", len(image_paths), used_sel)
        except Exception as e:
            logger.error("set_input_files 上传图片失败: %s", e)
            return PublishResult(success=False, error_message=f"图片上传失败: {e}", failed_step="上传图片")

        return await self._wait_image_upload_complete(page, {}, len(image_paths))

    async def _wait_image_upload_complete(
        self, page: Page, metadata: Dict[str, Any], image_count: int
    ) -> Optional[PublishResult]:
        """等待图片上传完成：检测「编辑图片」区域出现。"""
        max_wait_seconds = int(metadata.get("upload_timeout_seconds") or 120)
        logger.info("等待图片上传就绪（最长 %d 秒）...", max_wait_seconds)
        USER_LOG.info("%s 正在上传中，等待上传成功（最长 %d 秒）…", self._prefix_image, max_wait_seconds)
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        config = metadata.get("anti_risk_config") or {}

        markers = Selectors.PUBLISH.get("IMAGE_UPLOAD_SUCCESS_MARKER", [])
        if not markers:
            return PublishResult(
                success=False,
                error_message="IMAGE_UPLOAD_SUCCESS_MARKER 选择器未配置，请检查 selectors.py",
                failed_step="上传图片",
            )

        def _log_wait(attempt: int) -> None:
            elapsed = int(attempt * max(0.2, speed_rate))
            if attempt % 40 == 0 and attempt > 0:
                logger.info("等待图片上传中... (%ds/%ds)", elapsed, max_wait_seconds)
            if attempt > 0 and attempt % 30 == 0:
                USER_LOG.info("%s 正在上传中，已等待 %d 秒…", self._prefix_image, elapsed)

        matched = await PluginWaitHelper.wait_for_any_visible(
            page,
            markers,
            timeout_ms=max_wait_seconds * 1000,
            poll_interval_ms=max(200, int(1000 * speed_rate)),
            pause_callback=lambda: self._await_pause(metadata),
            on_poll=_log_wait,
        )
        if matched:
            logger.info("检测到图片上传完成标志（is_visible）: %s", matched)
            USER_LOG.info("%s ✓ 上传成功（%d 张）", self._prefix_image, image_count)
            await dismiss_kuaishou_publish_guides(page, metadata)
            return None

        logger.error("图片上传状态检测超时，终止发布流程")
        USER_LOG.error("%s ✖ 上传超时，未检测到「编辑图片」，请检查网络后重试", self._prefix_image)
        return PublishResult(
            success=False,
            error_message="图片上传超时，未检测到上传完成标志（编辑图片区域），请检查网络或图片文件后重试",
            failed_step="上传图片",
        )
