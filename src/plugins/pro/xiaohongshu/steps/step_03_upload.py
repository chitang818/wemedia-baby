# -*- coding: utf-8 -*-
"""
步骤3：上传素材
文件路径: src/plugins/pro/xiaohongshu/steps/step_03_upload.py

流程（根据 file_type）：
  - 视频上传：
    1. 等待发布页骨架屏消退、上传区就绪
    2. 优先通过原生 set_input_files 操作 input[type=file]
    3. 兜底：点击上传区域触发 file chooser
    4. 轮询等待「视频文件」区域内「重新上传」出现且页面稳定
  - 图文上传：
    1. 批量 set_input_files 传入图片列表
    2. 兜底：点击上传按钮触发 file chooser
    3. 轮询等待图片缩略图渲染出现

字段依赖：
  - file_path: 素材路径
  - metadata['image_paths']: 图文模式的图片路径列表
  - metadata['file_type']: "video" 或 "image"
  - metadata['upload_timeout_seconds']: 上传超时
  - metadata['publish_form_ready_timeout_seconds']: 等待发布表单就绪（默认 20 秒）
"""
import logging
import os
import time
from typing import Any, Dict, List, Optional

from playwright.async_api import Page

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from .publish_page_guard import (
    ensure_publish_page_without_file_picker,
    url_has_auto_file_picker,
)

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_FOLDER_MARKER_PREFIX = "__FOLDER__:"

# 发布页骨架屏与上传完成态：用 JS 判断可见 DOM，避免 input 已挂载但界面仍灰块占位
_PUBLISH_SHELL_STATE_JS = """() => {
    const norm = (s) => (s || '').replace(/\\s+/g, '').trim();
    const visible = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) return false;
        const st = window.getComputedStyle(el);
        if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity) < 0.05) return false;
        return true;
    };
    const root =
        document.querySelector('[class*="publish"]') ||
        document.querySelector('main') ||
        document.body;
    const skeletonSel = '[class*="skeleton"], .el-skeleton, .el-skeleton__item, [class*="Skeleton"]';
    const skeletons = Array.from(root.querySelectorAll(skeletonSel)).filter(visible);
    const bodyText = norm(root.innerText || document.body.innerText || '');
    const hasVideoFile = bodyText.includes('视频文件');
    const hasUploadVideo = bodyText.includes('上传视频');
    const progressText = /上传中|处理中|转码中|解析中/.test(bodyText);
    return {
        skeletonCount: skeletons.length,
        hasVideoFile,
        hasUploadVideo,
        progressText,
        ready: skeletons.length < 3 && (hasVideoFile || hasUploadVideo),
    };
}"""

_VERIFY_VIDEO_REUPLOAD_JS = """() => {
    const norm = (s) => (s || '').replace(/\\s+/g, '').trim();
    const visible = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        if (r.width < 4 || r.height < 4) return false;
        const st = window.getComputedStyle(el);
        if (st.display === 'none' || st.visibility === 'hidden' || parseFloat(st.opacity) < 0.05) return false;
        return true;
    };
    const findReuploadNear = (start) => {
        let node = start;
        for (let depth = 0; depth < 10 && node; depth++) {
            const host =
                node.closest(
                    '[class*="card"], [class*="upload"], [class*="video"], section, article, div'
                ) || node;
            const hits = Array.from(host.querySelectorAll('button, span, a, div')).filter(
                (el) => visible(el) && norm(el.textContent) === '重新上传'
            );
            if (hits.length) return true;
            node = host.parentElement;
        }
        return false;
    };
    const root =
        document.querySelector('#publish-container.publish-video-container') ||
        document.querySelector('.publish-video-container') ||
        document.querySelector('#publish-container') ||
        document.querySelector('.publish-page-container') ||
        document.querySelector('[class*="publish-page"]') ||
        document.body;
    const labels = [];
    root.querySelectorAll('span, div, label, p, h3, h4, button').forEach((el) => {
        if (visible(el) && norm(el.textContent) === '视频文件') {
            labels.push(el);
        }
    });
    if (!labels.length) {
        return { ok: false, reason: 'no_video_file_label' };
    }
    for (const label of labels) {
        if (findReuploadNear(label)) {
            return { ok: true, reason: 'reupload_in_video_card' };
        }
    }
    return { ok: false, reason: 'reupload_not_in_video_card' };
}"""

# JS 快路径连续未命中若干次后再走 Playwright 选择器慢路径
_UPLOAD_JS_MISS_BEFORE_SLOW_PATH = 3
# 上传完成轮询间隔（ms），与封面步骤对齐
_UPLOAD_DONE_POLL_BASE_MS = 300
_UPLOAD_USER_LOG_INTERVAL_S = 5


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

    async def _read_shell_state(self, page: Page) -> Dict[str, Any]:
        try:
            result = await page.evaluate(_PUBLISH_SHELL_STATE_JS)
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.debug("读取发布页加载状态失败: %s", e)
        return {}

    async def _ensure_publish_form_ready(
        self, page: Page, metadata: Dict[str, Any], *, phase: str
    ) -> Optional[PublishResult]:
        """等待骨架屏消退且上传区文案出现，避免在灰块占位阶段误操作。"""
        max_wait_seconds = int(metadata.get("publish_form_ready_timeout_seconds") or 20)
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        poll_ms = max(300, int(500 * speed_rate))
        ready_selectors = Selectors.PUBLISH.get("PUBLISH_FORM_READY") or []
        loading_selectors = Selectors.PUBLISH.get("PUBLISH_FORM_LOADING") or []

        logger.info(
            "等待发布页表单就绪（%s，最长 %s 秒）…",
            phase,
            max_wait_seconds,
        )
        USER_LOG.info(
            f"[步骤3 上传] 等待发布页加载完成（{phase}，最长 {max_wait_seconds} 秒）…"
        )

        def _log_wait(attempt: int) -> None:
            if attempt > 0 and attempt % 10 == 0:
                USER_LOG.info(
                    f"[步骤3 上传] 发布页仍在加载中（{phase}），请稍候…"
                )

        async def _predicate() -> bool:
            state = await self._read_shell_state(page)
            if state.get("ready"):
                return True
            if ready_selectors:
                matched = await PluginWaitHelper.first_visible_selector(page, ready_selectors)
                if matched and int(state.get("skeletonCount") or 0) < 3:
                    return True
            if loading_selectors:
                still_loading = await PluginWaitHelper.first_visible_selector(
                    page, loading_selectors
                )
                if still_loading:
                    return False
            return False

        ready = await PluginWaitHelper.wait_for_condition(
            page,
            _predicate,
            timeout_ms=max_wait_seconds * 1000,
            poll_interval_ms=poll_ms,
            pause_callback=lambda: self._await_pause(metadata),
            on_poll=_log_wait,
        )
        if ready:
            logger.info("发布页表单已就绪: phase=%s", phase)
            return None

        state = await self._read_shell_state(page)
        sk = int(state.get("skeletonCount") or 0)
        return PublishResult(
            success=False,
            error_message=(
                f"发布页加载超时（{max_wait_seconds}秒）：骨架屏未消退或上传区未出现"
                f"（phase={phase}, skeleton={sk}）"
            ),
            failed_step="步骤3 上传",
        )

    async def _soft_ensure_publish_form_ready(
        self, page: Page, metadata: Dict[str, Any], *, phase: str
    ) -> None:
        """上传后软等待：超时仅打日志，不中断步骤。"""
        soft_meta = {
            **metadata,
            "publish_form_ready_timeout_seconds": metadata.get(
                "publish_form_soft_ready_timeout_seconds", 3
            ),
        }
        err = await self._ensure_publish_form_ready(page, soft_meta, phase=phase)
        if err is not None:
            logger.warning(
                "上传后发布页仍未完全稳定（软等待超时，继续流程）: %s",
                err.error_message,
            )

    async def _guard_before_upload(
        self, page: Page, metadata: Dict[str, Any]
    ) -> Optional[PublishResult]:
        """步骤3 上传前兜底：去掉 openFilePicker 并关闭系统文件对话框。"""
        file_type = (metadata.get("file_type") or "video").lower()
        return await ensure_publish_page_without_file_picker(
            page,
            file_type,
            metadata,
            pause_callback=lambda: self._await_pause(metadata),
        )

    async def _upload_video(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> Optional[PublishResult]:
        logger.info("===== 开始上传视频文件 =====")
        base_name = os.path.basename(str(file_path))
        USER_LOG.info(f"[步骤3 上传] ▶ 开始 文件={base_name}")

        if not os.path.exists(file_path):
            return PublishResult(success=False, error_message=f"视频文件不存在: {file_path}")

        guard_err = await self._guard_before_upload(page, metadata)
        if guard_err is not None:
            return guard_err

        form_ready = await self._ensure_publish_form_ready(page, metadata, phase="上传前")
        if form_ready is not None:
            return form_ready

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

        # 策略2：仅当 URL 无 openFilePicker 时才点击触发 file chooser，避免叠加系统对话框
        try:
            if url_has_auto_file_picker(page.url or ""):
                logger.warning("URL 仍含 openFilePicker，跳过 file chooser 兜底以免重复弹窗")
            else:
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

    async def _verify_video_reupload_js(self, page: Page) -> bool:
        try:
            result = await page.evaluate(_VERIFY_VIDEO_REUPLOAD_JS)
            if isinstance(result, dict) and result.get("ok"):
                return True
            logger.debug("JS 校验视频重新上传未通过: %s", result)
        except Exception as e:
            logger.debug("JS 校验视频重新上传异常: %s", e)
        return False

    @staticmethod
    def _upload_match_confirmed(matched: str) -> bool:
        """JS 或 VIDEO_UPLOAD_SUCCESS_MARKER 命中即视为上传完成，无需上传后软等待。"""
        if not matched:
            return False
        if str(matched).startswith("js:"):
            return True
        markers = Selectors.PUBLISH.get("VIDEO_UPLOAD_SUCCESS_MARKER") or []
        return str(matched) in markers

    async def _wait_for_upload_complete(self, page: Page, metadata: Dict[str, Any]) -> Optional[PublishResult]:
        """等待视频上传完成：「视频文件」区域内可见「重新上传」，且骨架屏已消退。"""
        max_wait_seconds = int(metadata.get("upload_timeout_seconds") or 300)
        logger.info(f"等待视频文件区域出现「重新上传」按钮（最长 {max_wait_seconds} 秒）…")
        USER_LOG.info(
            f"[步骤3 上传] 平台正在上传视频，等待「重新上传」出现（最长 {max_wait_seconds} 秒）…"
            " 期间灰色占位为正常加载"
        )
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        success_selectors = list(Selectors.PUBLISH.get("VIDEO_UPLOAD_SUCCESS_MARKER") or [])
        if not success_selectors:
            return PublishResult(
                success=False,
                error_message="小红书视频上传成功选择器未配置：缺少 VIDEO_UPLOAD_SUCCESS_MARKER",
                failed_step="步骤3 上传",
            )

        poll_ms = max(200, int(_UPLOAD_DONE_POLL_BASE_MS * speed_rate))
        progress_selectors = Selectors.PUBLISH.get("UPLOAD_PROGRESS") or []
        wait_started = time.monotonic()
        last_user_log_elapsed = -_UPLOAD_USER_LOG_INTERVAL_S
        js_miss_streak = 0

        def _log_wait(attempt: int) -> None:
            nonlocal last_user_log_elapsed
            elapsed = int(time.monotonic() - wait_started)
            if attempt % 40 == 0 and attempt > 0:
                logger.info(
                    f"等待视频文件区域出现「重新上传」按钮… ({elapsed}s/{max_wait_seconds}s)"
                )
            if elapsed >= last_user_log_elapsed + _UPLOAD_USER_LOG_INTERVAL_S and elapsed > 0:
                last_user_log_elapsed = elapsed
                USER_LOG.info(
                    f"[步骤3 上传] 平台上传中，已等待 {elapsed} 秒"
                    "（灰色占位为加载中，非卡死）…"
                )

        async def _upload_done_predicate() -> Optional[str]:
            nonlocal js_miss_streak
            if await self._verify_video_reupload_js(page):
                js_miss_streak = 0
                return "js:reupload_in_video_card"

            js_miss_streak += 1
            if js_miss_streak < _UPLOAD_JS_MISS_BEFORE_SLOW_PATH:
                return None

            matched = await PluginWaitHelper.first_visible_selector(page, success_selectors)
            if not matched:
                return None
            if not await self._verify_video_reupload_js(page):
                return None

            state = await self._read_shell_state(page)
            sk = int(state.get("skeletonCount") or 0)
            if sk >= 5:
                return None
            if state.get("progressText"):
                return None
            if progress_selectors:
                progress = await PluginWaitHelper.first_visible_selector(page, progress_selectors)
                if progress:
                    return None
            return matched

        matched = await PluginWaitHelper.wait_for_condition(
            page,
            _upload_done_predicate,
            timeout_ms=max_wait_seconds * 1000,
            poll_interval_ms=poll_ms,
            pause_callback=lambda: self._await_pause(metadata),
            on_poll=_log_wait,
        )
        if not matched:
            state = await self._read_shell_state(page)
            sk = int(state.get("skeletonCount") or 0)
            return PublishResult(
                success=False,
                error_message=(
                    f"等待视频上传超时 ({max_wait_seconds}秒)，"
                    f"未在「视频文件」区域确认「重新上传」（skeleton={sk}）"
                ),
                failed_step="步骤3 上传",
            )

        if not self._upload_match_confirmed(str(matched)):
            await self._soft_ensure_publish_form_ready(page, metadata, phase="上传后")

        logger.info(f"检测到视频文件区域「重新上传」按钮，上传成功: {matched}")
        USER_LOG.info("[步骤3 上传] ✓ 上传成功")
        return None

    async def _upload_images(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> Optional[PublishResult]:
        logger.info("===== 开始上传图文图片 =====")
        image_paths = _parse_image_paths(file_path, metadata)
        if not image_paths:
            return PublishResult(success=False, error_message="图文上传失败: 未提供图片路径")

        base_name = os.path.basename(str(image_paths[0]))
        USER_LOG.info(f"[步骤3 上传] ▶ 开始 图文数量={len(image_paths)} 示例={base_name}")

        if not os.path.exists(image_paths[0]):
            return PublishResult(success=False, error_message=f"图文上传失败: 找不到图片文件 -> {image_paths[0]}")

        guard_err = await self._guard_before_upload(page, metadata)
        if guard_err is not None:
            return guard_err

        form_ready = await self._ensure_publish_form_ready(page, metadata, phase="上传前")
        if form_ready is not None:
            return form_ready

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

        try:
            if url_has_auto_file_picker(page.url or ""):
                logger.warning("URL 仍含 openFilePicker，跳过 file chooser 兜底以免重复弹窗")
            else:
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
        poll_ms = max(300, int(700 * speed_rate))
        max_attempts = max(1, int(max_wait_seconds * 1000 / poll_ms))

        thumb_selector = ", ".join(Selectors.PUBLISH["IMAGE_THUMBNAIL"])

        for i in range(max_attempts):
            await self._await_pause(metadata)
            try:
                cnt = await page.locator(thumb_selector).count()
                if cnt >= 1:
                    state = await self._read_shell_state(page)
                    if int(state.get("skeletonCount") or 0) < 5:
                        logger.info(f"检测到图片缩略图数量={cnt}，认为上传已就绪")
                        USER_LOG.info("[步骤3 上传] ✓ 上传成功")
                        return None
            except Exception:
                pass

            elapsed = int(i * poll_ms / 1000)
            if i % 10 == 0 and i > 0:
                logger.info(f"等待图片就绪… ({elapsed}s/{max_wait_seconds}s)")
            if i > 0 and i % 15 == 0:
                USER_LOG.info(f"[步骤3 上传] 正在上传图文，已等待 {elapsed} 秒…")

            await page.wait_for_timeout(poll_ms)

        return PublishResult(success=False, error_message=f"等待图片上传就绪超时 ({max_wait_seconds}秒)")
