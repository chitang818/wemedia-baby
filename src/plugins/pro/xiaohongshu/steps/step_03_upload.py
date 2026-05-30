# -*- coding: utf-8 -*-
"""
步骤3：上传素材
文件路径: src/plugins/pro/xiaohongshu/steps/step_03_upload.py

根据 metadata['file_type'] 自动分发到两套完全独立的流程：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【视频上传流程】（file_type = "video"）
  1. 去掉 openFilePicker 参数（发布页兜底防弹窗）
  2. 等待视频发布页表单就绪（"视频文件"/"上传视频"文案出现、骨架屏消退）
  3. 策略1：set_input_files 直接写入 FILE_INPUT
  4. 策略2（备）：expect_file_chooser + 点击上传区
  5. 等待「视频文件」区域内「重新上传」出现（上传完成标志）

【图文上传流程】（file_type = "image"）
  1. 解析图片路径列表
  2. 等待图文发布页就绪（input[type=file] 挂载 + 骨架屏消退）
  3. 策略1：set_input_files（IMAGE_FILE_INPUT，限定 accept=image/*）
  4. 策略2（备）：expect_file_chooser + 点击 IMAGE_UPLOAD_BTN
  5. 等待 IMAGE_UPLOAD_SUCCESS 标志（预览图出现）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

字段依赖：
  - file_path: 素材路径（视频单文件 / 图文逗号分隔列表）
  - metadata['image_paths']: 图文模式的图片路径列表（List[str]）
  - metadata['file_type']: "video"（默认）或 "image"
  - metadata['upload_timeout_seconds']: 视频上传超时（默认 300 秒）
  - metadata['image_upload_timeout_seconds']: 图文上传超时（默认 120 秒）
  - metadata['publish_form_ready_timeout_seconds']: 发布页就绪超时（默认 20 秒）
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

# 上传完成轮询配置
_UPLOAD_DONE_POLL_BASE_MS = 300
_UPLOAD_USER_LOG_INTERVAL_S = 5
# JS 快路径连续未命中若干次后再走 Playwright 选择器慢路径（视频用）
_UPLOAD_JS_MISS_BEFORE_SLOW_PATH = 3


# ──────────────────────────────────────────────────────────────────────────────
# JS 工具函数
# ──────────────────────────────────────────────────────────────────────────────

# 发布页骨架屏状态检测（视频/图文通用底层）
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
    const hasFileInput = !!document.querySelector("input[type='file']");
    return {
        skeletonCount: skeletons.length,
        hasVideoFile,
        hasUploadVideo,
        hasFileInput,
        progressText,
        // 视频页就绪标志
        ready: skeletons.length < 3 && (hasVideoFile || hasUploadVideo),
        // 图文页就绪标志（骨架屏消退 + input[type=file] 挂载）
        imageReady: skeletons.length < 3 && hasFileInput,
    };
}"""

# 视频「重新上传」出现在「视频文件」区域内的 JS 校验
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


# ──────────────────────────────────────────────────────────────────────────────
# 路径解析工具
# ──────────────────────────────────────────────────────────────────────────────

def _parse_image_paths(file_path: str, metadata: Dict[str, Any]) -> List[str]:
    """解析图片路径列表，过滤文件夹来源标记。"""
    paths = metadata.get("image_paths")
    if isinstance(paths, list) and paths:
        return [str(p).strip() for p in paths if str(p).strip()]
    return [
        p.strip() for p in str(file_path).split(",")
        if p.strip() and not p.strip().startswith(_FOLDER_MARKER_PREFIX)
    ]


# ══════════════════════════════════════════════════════════════════════════════
# 主步骤类
# ══════════════════════════════════════════════════════════════════════════════

class UploadMediaStep(BasePublishStep):
    """统一上传步骤：根据 file_type 自动分发到图文或视频两套独立流程。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        file_type = (metadata.get("file_type") or "video").lower()

        if file_type == "image":
            return await self._upload_images(page, file_path, metadata)
        return await self._upload_video(page, file_path, metadata)

    # ──────────────────────────────────────────────────────────────────────────
    # 通用底层工具
    # ──────────────────────────────────────────────────────────────────────────

    async def _read_shell_state(self, page: Page) -> Dict[str, Any]:
        """执行骨架屏状态 JS，失败时返回空字典。"""
        try:
            result = await page.evaluate(_PUBLISH_SHELL_STATE_JS)
            if isinstance(result, dict):
                return result
        except Exception as e:
            logger.debug("读取发布页加载状态失败: %s", e)
        return {}

    async def _hover_before_upload(
        self,
        page: Page,
        upload_btn_selector: str,
        metadata: Dict[str, Any],
    ) -> None:
        """上传文件前，将鼠标移至上传区域附近并短暂停顿，模拟用户找到上传区域的自然行为。

        降低 set_input_files 直接注入时「鼠标从未到达上传区域」的自动化特征。
        若定位失败则静默跳过，不影响上传主流程。
        """
        import random
        try:
            upload_area = page.locator(upload_btn_selector).first
            if await upload_area.count() == 0:
                return
            box = await upload_area.bounding_box()
            if not box:
                return
            # 在上传区域内随机选点，加 ±25px 抖动模拟人手不精准
            target_x = box["x"] + box["width"] / 2 + random.uniform(-25, 25)
            target_y = box["y"] + box["height"] / 2 + random.uniform(-12, 12)
            try:
                from src.infrastructure.browser.human_behavior import HumanBehavior
                vp = await page.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
                from_x = random.uniform(0, max(1, float(vp.get("w") or 800)) * 0.4)
                from_y = random.uniform(0, max(1, float(vp.get("h") or 600)) * 0.4)
                await HumanBehavior.mouse_move(
                    page, from_x, from_y, target_x, target_y,
                    steps=random.randint(12, 25),
                )
            except Exception:
                await page.mouse.move(target_x, target_y)
            # 在上传区域停顿 0.8-2.2 秒（模拟用户确认区域后才拖动/选择文件）
            pause_ms = random.randint(800, 2200)
            await page.wait_for_timeout(pause_ms)
            logger.debug("上传前悬停完成：(%.0f, %.0f)，停顿 %dms", target_x, target_y, pause_ms)
        except Exception as e:
            logger.debug("上传前悬停异常（已忽略）: %s", e)



    # ══════════════════════════════════════════════════════════════════════════
    # 【视频上传流程】
    # ══════════════════════════════════════════════════════════════════════════

    async def _upload_video(
        self, page: Page, file_path: str, metadata: Dict[str, Any]
    ) -> StepOutcome:
        """视频上传完整流程（原有逻辑，保持不变）。"""
        logger.info("===== 开始上传视频文件 =====")
        base_name = os.path.basename(str(file_path))
        base_name = os.path.basename(str(file_path))
        prefix = metadata.get("_step_prefix", "")
        if prefix:
            USER_LOG.info(f"{prefix} · 文件: {base_name}")
        else:
            USER_LOG.info(f"· 文件: {base_name}")

        if not os.path.exists(file_path):
            return PublishResult(success=False, error_message=f"视频文件不存在: {file_path}")

        # 前置兜底：去掉 openFilePicker 参数防止系统弹窗叠加
        guard_err = await self._guard_before_video_upload(page, metadata)
        if guard_err is not None:
            return guard_err

        # 等待视频发布页表单就绪
        form_ready = await self._ensure_video_form_ready(page, metadata)
        if form_ready is not None:
            return form_ready

        # 策略1：直接 set_input_files
        try:
            file_input_selector = ", ".join(Selectors.PUBLISH["FILE_INPUT"])
            input_file = page.locator(file_input_selector).first
            if await input_file.count() > 0:
                # 上传前：先将鼠标移动到上传区域附近，模拟用户找到并确认上传区的自然行为
                upload_btn_selector_for_hover = ", ".join(Selectors.PUBLISH["UPLOAD_BTN"])
                await self._hover_before_upload(page, upload_btn_selector_for_hover, metadata)
                await input_file.set_input_files(file_path)
                logger.info("使用 set_input_files 触发视频上传")
                return await self._wait_for_video_complete(page, metadata)
        except Exception as e:
            logger.info(f"直接 set_input_files 失败，尝试备用方案: {e}")


        # 策略2：expect_file_chooser + 点击上传区
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
                    return await self._wait_for_video_complete(page, metadata)
        except Exception as e:
            logger.error(f"点击上传区域上传视频失败: {e}")

        return PublishResult(success=False, error_message="无法找到视频上传入口，可能页面结构已变更")

    async def _guard_before_video_upload(
        self, page: Page, metadata: Dict[str, Any]
    ) -> Optional[PublishResult]:
        """步骤3 视频上传前兜底：去掉 openFilePicker 并关闭系统文件对话框。"""
        return await ensure_publish_page_without_file_picker(
            page,
            "video",
            metadata,
            pause_callback=lambda: self._await_pause(metadata),
        )

    async def _ensure_video_form_ready(
        self, page: Page, metadata: Dict[str, Any]
    ) -> Optional[PublishResult]:
        """等待视频发布页就绪：骨架屏消退 + 出现"视频文件"/"上传视频"文案。"""
        max_wait_seconds = int(metadata.get("publish_form_ready_timeout_seconds") or 20)
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        poll_ms = max(300, int(500 * speed_rate))
        ready_selectors = Selectors.PUBLISH.get("PUBLISH_FORM_READY") or []
        loading_selectors = Selectors.PUBLISH.get("PUBLISH_FORM_LOADING") or []

        logger.info("等待视频发布页表单就绪（上传前，最长 %s 秒）…", max_wait_seconds)

        def _log_wait(attempt: int) -> None:
            if attempt > 0 and attempt % 10 == 0:
                logger.info("发布页仍在加载中（上传前），请稍候…")

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
            logger.info("视频发布页表单已就绪")
            return None

        state = await self._read_shell_state(page)
        sk = int(state.get("skeletonCount") or 0)
        return PublishResult(
            success=False,
            error_message=(
                f"发布页加载超时（{max_wait_seconds}秒）：骨架屏未消退或上传区未出现"
                f"（phase=上传前, skeleton={sk}）"
            ),
            failed_step="步骤3 上传",
        )

    async def _verify_video_reupload_js(self, page: Page) -> bool:
        """JS 校验「重新上传」出现在「视频文件」区域内。"""
        try:
            result = await page.evaluate(_VERIFY_VIDEO_REUPLOAD_JS)
            if isinstance(result, dict) and result.get("ok"):
                return True
            logger.debug("JS 校验视频重新上传未通过: %s", result)
        except Exception as e:
            logger.debug("JS 校验视频重新上传异常: %s", e)
        return False

    @staticmethod
    def _video_upload_match_confirmed(matched: str) -> bool:
        """JS 或 VIDEO_UPLOAD_SUCCESS_MARKER 命中即视为完成。"""
        if not matched:
            return False
        if str(matched).startswith("js:"):
            return True
        markers = Selectors.PUBLISH.get("VIDEO_UPLOAD_SUCCESS_MARKER") or []
        return str(matched) in markers

    async def _wait_for_video_complete(
        self, page: Page, metadata: Dict[str, Any]
    ) -> Optional[PublishResult]:
        """等待视频上传完成：「视频文件」区域内可见「重新上传」，且骨架屏已消退。"""
        max_wait_seconds = int(metadata.get("upload_timeout_seconds") or 300)
        logger.info(f"等待视频文件区域出现「重新上传」按钮（最长 {max_wait_seconds} 秒）…")
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
                logger.info(f"平台上传中，已等待 {elapsed} 秒（灰色占位为加载中，非卡死）…")

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

        if not self._video_upload_match_confirmed(str(matched)):
            await self._soft_video_form_ready(page, metadata)

        logger.info(f"检测到视频文件区域「重新上传」按钮，上传成功: {matched}")
        return None

    async def _soft_video_form_ready(
        self, page: Page, metadata: Dict[str, Any]
    ) -> None:
        """上传后软等待视频页稳定，超时仅打日志不中断流程。"""
        soft_meta = {
            **metadata,
            "publish_form_ready_timeout_seconds": metadata.get(
                "publish_form_soft_ready_timeout_seconds", 3
            ),
        }
        err = await self._ensure_video_form_ready(page, soft_meta)
        if err is not None:
            logger.warning(
                "上传后视频页仍未完全稳定（软等待超时，继续流程）: %s",
                err.error_message,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # 【图文上传流程】
    # ══════════════════════════════════════════════════════════════════════════

    async def _upload_images(
        self, page: Page, file_path: str, metadata: Dict[str, Any]
    ) -> StepOutcome:
        """图文上传完整流程（完全独立，与视频流程互不影响）。"""
        logger.info("===== 开始上传图文图片 =====")
        image_paths = _parse_image_paths(file_path, metadata)
        if not image_paths:
            return PublishResult(success=False, error_message="图文上传失败: 未提供图片路径")

        base_name = os.path.basename(str(image_paths[0]))
        prefix = metadata.get("_step_prefix", "")
        if prefix:
            USER_LOG.info(f"{prefix} · 图文数量: {len(image_paths)} · 示例文件: {base_name}")
        else:
            USER_LOG.info(f"· 图文数量: {len(image_paths)} · 示例文件: {base_name}")

        # 验证文件存在
        missing = [p for p in image_paths if not os.path.exists(p)]
        if missing:
            return PublishResult(
                success=False,
                error_message=(
                    f"图文上传失败: 以下文件不存在: "
                    f"{', '.join(os.path.basename(p) for p in missing)}"
                ),
                failed_step="步骤3 上传",
            )

        # 等待图文发布页就绪（独立于视频页检测）
        form_ready = await self._ensure_image_form_ready(page, metadata)
        if form_ready is not None:
            return form_ready

        # 策略1：直接 set_input_files（优先用 accept=image/* 的 input）
        try:
            image_input_selectors = Selectors.PUBLISH.get("IMAGE_FILE_INPUT", [])
            # 上传前：先将鼠标移动到图文上传区域，模拟用户找到上传区的自然行为
            _image_upload_btn_sels = Selectors.PUBLISH.get(
                "IMAGE_UPLOAD_BTN", Selectors.PUBLISH.get("UPLOAD_BTN", [])
            )
            if _image_upload_btn_sels:
                await self._hover_before_upload(
                    page, ", ".join(_image_upload_btn_sels), metadata
                )
            for sel in image_input_selectors:
                try:
                    input_file = page.locator(sel).first
                    if await input_file.count() > 0:
                        await input_file.set_input_files(image_paths)
                        logger.info(f"已 set_input_files 上传图片: {len(image_paths)} 张（sel={sel}）")
                        return await self._wait_for_images_complete(page, len(image_paths), metadata)
                except Exception as e:
                    logger.debug(f"图文 set_input_files（{sel}）失败: {e}")
        except Exception as e:
            logger.info(f"图文 set_input_files 整体失败，尝试 file chooser: {e}")


        # 策略2：expect_file_chooser + 点击上传区域按钮
        try:
            if url_has_auto_file_picker(page.url or ""):
                logger.warning("URL 仍含 openFilePicker，跳过 file chooser 兜底以免重复弹窗")
            else:
                image_upload_btn_selectors = Selectors.PUBLISH.get(
                    "IMAGE_UPLOAD_BTN",
                    Selectors.PUBLISH.get("UPLOAD_BTN", []),
                )
                upload_btn_selector = ", ".join(image_upload_btn_selectors)
                upload_btn = page.locator(upload_btn_selector).first
                if await upload_btn.count() > 0:
                    async with page.expect_file_chooser(timeout=10000) as fc_info:
                        await upload_btn.click(force=True)
                    fc = await fc_info.value
                    await fc.set_files(image_paths)
                    logger.info(f"通过 file chooser 上传图片完成（共 {len(image_paths)} 张）")
                    return await self._wait_for_images_complete(page, len(image_paths), metadata)
        except Exception as e:
            logger.error(f"图文 file chooser 上传失败: {e}")

        return PublishResult(success=False, error_message="图文上传失败: 无法找到图片上传入口")

    async def _ensure_image_form_ready(
        self, page: Page, metadata: Dict[str, Any]
    ) -> Optional[PublishResult]:
        """图文发布页专用就绪检测。

        图文发布页（/publish/post/image）无"视频文件"/"上传视频"文案，
        不能复用视频检测逻辑。改为等待：
          - JS imageReady：骨架屏 < 3 且 input[type=file] 挂载
          - 兜底：Playwright 直接计数 input[type=file]
        """
        max_wait_seconds = int(metadata.get("publish_form_ready_timeout_seconds") or 20)
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        poll_ms = max(300, int(500 * speed_rate))

        logger.info("等待图文发布页就绪（最长 %s 秒）…", max_wait_seconds)

        def _log_wait(attempt: int) -> None:
            if attempt > 0 and attempt % 10 == 0:
                logger.info("图文发布页仍在加载中，请稍候…")

        async def _predicate() -> bool:
            state = await self._read_shell_state(page)
            # JS imageReady：骨架屏 < 3 且 input[type=file] 已挂载
            if state.get("imageReady"):
                return True
            # 兜底：骨架屏消退 + Playwright 直接计数
            sk = int(state.get("skeletonCount") or 0)
            if sk < 3:
                try:
                    cnt = await page.locator("input[type='file']").count()
                    if cnt > 0:
                        return True
                except Exception:
                    pass
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
            logger.info("图文发布页已就绪（input[type=file] 检测通过）")
            return None

        state = await self._read_shell_state(page)
        sk = int(state.get("skeletonCount") or 0)
        return PublishResult(
            success=False,
            error_message=(
                f"图文发布页加载超时（{max_wait_seconds}秒）："
                f"上传区 input 未出现（skeleton={sk}）"
            ),
            failed_step="步骤3 上传",
        )

    async def _wait_for_images_complete(
        self, page: Page, expected_count: int, metadata: Dict[str, Any]
    ) -> Optional[PublishResult]:
        """等待图文图片上传完成：预览图出现即视为就绪。"""
        max_wait_seconds = int(metadata.get("image_upload_timeout_seconds") or 120)
        logger.info(f"等待图片预览图渲染（最长 {max_wait_seconds} 秒）…")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        # 优先使用图文专用完成标志，兜底用通用缩略图选择器
        success_selectors = (
            Selectors.PUBLISH.get("IMAGE_UPLOAD_SUCCESS")
            or Selectors.PUBLISH.get("IMAGE_THUMBNAIL")
            or []
        )
        poll_ms = max(300, int(700 * speed_rate))
        max_attempts = max(1, int(max_wait_seconds * 1000 / poll_ms))
        wait_started = time.monotonic()

        for i in range(max_attempts):
            await self._await_pause(metadata)
            try:
                for sel in success_selectors:
                    cnt = await page.locator(sel).count()
                    if cnt >= 1:
                        state = await self._read_shell_state(page)
                        if int(state.get("skeletonCount") or 0) < 5:
                            logger.info(
                                f"检测到图片预览图（sel={sel}, count={cnt}），认为上传已就绪"
                            )
                            return None
            except Exception:
                pass

            elapsed = int(time.monotonic() - wait_started)
            if i % 10 == 0 and i > 0:
                logger.info(f"等待图片就绪… ({elapsed}s/{max_wait_seconds}s)")
            if i > 0 and i % 15 == 0:
                logger.info(f"正在上传图文，已等待 {elapsed} 秒…")

            await page.wait_for_timeout(poll_ms)

        return PublishResult(
            success=False,
            error_message=f"等待图片上传就绪超时 ({max_wait_seconds}秒)"
        )
