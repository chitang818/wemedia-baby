# -*- coding: utf-8 -*-
"""
步骤3：上传视频/图文素材
文件路径: src/plugins/pro/wechat_video/steps/step_03_upload.py

流程：
  1. 优先通过 file input（Selectors.PUBLISH.FILE_INPUT）直接 set_input_files 上传
  2. 若 file input 不可用，退而通过 file chooser 触发上传：
     点击上传按钮（Selectors.PUBLISH.UPLOAD_BTN）→ expect_file_chooser → set_files
  3. 等待「删除」按钮（上传成功标识）出现：
     - 主路径：wujie Shadow 内轮询（与 3.2 第 5.1 节一致，避免 page.locator 未穿透导致假超时）
     - 辅路径：Playwright locator（若页面未包在 Shadow 或已穿透）
     - 最长等待 3 分钟（180000ms）

字段依赖：file_path（上传的本地文件路径）
                 metadata['file_type']（video/image）
"""
import logging
import re
from typing import Dict, Any, List

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, StepOutcome
from .page_diagnostics import log_page_diagnostics
from ..selectors import Selectors
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

# Shadow 内用标准 CSS + 文案判断（勿用 Playwright 专有 :has-text）
_SHADOW_UPLOAD_SUCCESS_JS = f"""
() => {{
    const shadow = {WUJIE_SHADOW_ROOT_JS};
    if (!shadow) return false;
    const inners = shadow.querySelectorAll('div.finder-tag-wrap div.tag-inner');
    for (const el of inners) {{
        const t = (el.textContent || '').trim();
        if (t === '删除' || t.includes('删除')) return true;
    }}
    for (const el of shadow.querySelectorAll('div.tag-inner')) {{
        const t = (el.textContent || '').trim();
        if (t === '删除') return true;
    }}
    return false;
}}
"""

_SHADOW_IMAGE_UPLOAD_SUCCESS_JS = f"""
(expected) => {{
    const shadow = {WUJIE_SHADOW_ROOT_JS};
    if (!shadow) return {{ ok: false, reason: 'no_shadow', count: 0 }};

    const scope = shadow.querySelector('.post-edit-wrap.material-edit-wrap') || shadow;
    const visible = (el) => {{
        if (!el) return false;
        const rect = el.getBoundingClientRect();
        if (rect.width < 2 || rect.height < 2) return false;
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    }};
    const textOf = (el) => (el.innerText || el.textContent || '').replace(/\\s+/g, '').trim();

    const deleteHits = Array.from(scope.querySelectorAll('*'))
        .filter((el) => visible(el) && textOf(el).includes('删除'));
    if (deleteHits.length > 0) {{
        return {{ ok: true, reason: 'delete_control', count: deleteHits.length }};
    }}

    const previewImages = Array.from(scope.querySelectorAll('img'))
        .filter((img) => visible(img) && (img.currentSrc || img.src));
    if (previewImages.length > 0) {{
        return {{ ok: true, reason: 'image_preview', count: previewImages.length }};
    }}

    const previewItems = Array.from(scope.querySelectorAll(
        '.ant-upload-list-item, .ant-upload-list-picture-card-container, ' +
        '[class*="upload-list"] [class*="item"], [class*="preview"]'
    )).filter(visible);
    const uploadingItems = previewItems.filter((el) => /上传中|uploading/i.test(textOf(el) + ' ' + el.className));
    if (previewItems.length > 0 && uploadingItems.length === 0) {{
        return {{ ok: true, reason: 'upload_list_item', count: previewItems.length }};
    }}

    return {{ ok: false, reason: 'waiting_preview', count: 0, expected }};
}}
"""


class UploadMediaStep(BasePublishStep):
    """上传视频或图文素材，等待上传完成。"""

    _VIDEO_CREATE_PAGE_URL = "platform/post/create"
    _IMAGE_CREATE_PAGE_URL = "platform/post/finderNewLifeCreate"

    @staticmethod
    def _split_image_file_paths(file_path: str) -> List[str]:
        """Image tasks pass comma-separated paths; Playwright needs list[str]."""
        return [
            item.strip().strip('"')
            for item in str(file_path or "").split(",")
            if item.strip()
        ]

    async def _ensure_on_create_page(self, page: Page, file_type: str) -> bool:
        """校验当前是否在发布创建页；若页面意外跳转则尝试重新导航。
        连续发布时前一任务失败可能导致页面回到首页，此处做兜底恢复。"""
        target_path = (
            self._VIDEO_CREATE_PAGE_URL
            if file_type == "video"
            else self._IMAGE_CREATE_PAGE_URL
        )
        if target_path in page.url:
            return True
        logger.warning("[视频号] 上传前检测到页面不在发布页 (url=%s)，尝试重新导航", page.url)
        try:
            await page.goto(
                f"https://channels.weixin.qq.com/{target_path}",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await PluginWaitHelper.wait_for_any_attached(
                page,
                Selectors.PUBLISH.get("FILE_INPUT", []),
                timeout_ms=5000,
                poll_interval_ms=500,
            )
            if target_path in page.url:
                logger.info("[视频号] 已重新导航回发布页")
                return True
        except Exception as e:
            logger.warning("[视频号] 重新导航至发布页失败: %s", e)
        return False

    async def _upload_image_files(self, page: Page, image_files: List[str]) -> bool:
        """Use the confirmed image upload input inside the wujie shadow app."""
        try:
            file_input = page.locator(
                'wujie-app .post-edit-wrap.material-edit-wrap input[type="file"][accept*="image"]'
            ).first
            await file_input.wait_for(state="attached", timeout=15000)
            await file_input.set_input_files(image_files, timeout=30000)
            logger.info("[视频号] 图文图片已写入上传控件: %s 张", len(image_files))
            return True
        except Exception as e:
            logger.warning("[视频号] 图文图片上传控件 locator.set_input_files 失败: %s", e)
            return False

    async def _wait_image_upload_success(self, page: Page, expected_count: int) -> bool:
        """Wait for image-page preview/delete markers, not video-page markers."""
        max_wait_ms = 180000
        poll_ms = 500
        attempts = max(1, max_wait_ms // poll_ms)
        last_result = None

        for _ in range(attempts):
            try:
                result = await page.evaluate(_SHADOW_IMAGE_UPLOAD_SUCCESS_JS, expected_count)
                last_result = result
                if isinstance(result, dict) and result.get("ok"):
                    logger.info(
                        "[视频号] 图文上传成功判断通过: reason=%s count=%s expected=%s",
                        result.get("reason"),
                        result.get("count"),
                        expected_count,
                    )
                    return True
            except Exception as e:
                logger.debug("[视频号] 图文上传成功判断异常: %s", e)

            await page.wait_for_timeout(poll_ms)

        logger.warning("[视频号] 图文上传成功判断超时，最后状态: %s", last_result)
        return False

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        file_type = (metadata.get("file_type") or "video").lower()
        logger.info(f"[视频号] 正在上传{file_type}文件: {file_path}")

        if not await self._ensure_on_create_page(page, file_type):
            await log_page_diagnostics(
                page,
                logger,
                "上传前页面不在发布页",
                level=logging.WARNING,
                max_items=30,
            )
            return PublishResult(
                success=False,
                error_message="页面不在发布页且无法自动恢复，请检查浏览器状态",
                failed_step="UploadMediaStep",
            )

        # 尝试通过 file input 直接上传
        if file_type == "image":
            image_files = self._split_image_file_paths(file_path)
            if not image_files:
                return PublishResult(
                    success=False,
                    error_message="未解析到可上传的图文图片路径",
                    failed_step="UploadMediaStep",
                )

            uploaded = await self._upload_image_files(page, image_files)
            if not uploaded:
                await log_page_diagnostics(
                    page,
                    logger,
                    "未找到图文图片上传入口",
                    level=logging.WARNING,
                    max_items=40,
                )
                return PublishResult(
                    success=False,
                    error_message="未找到图文图片上传入口",
                    failed_step="UploadMediaStep",
                )

            logger.info("[视频号] 图文图片正在上传，等待预览/删除控件出现...")
            if not await self._wait_image_upload_success(page, len(image_files)):
                await log_page_diagnostics(
                    page,
                    logger,
                    "图文图片上传后未检测到预览或删除控件",
                    level=logging.WARNING,
                    max_items=40,
                )
                return PublishResult(
                    success=False,
                    error_message="图文图片上传超时，未检测到预览或删除控件",
                    failed_step="UploadMediaStep",
                )

            logger.info("[视频号] 步骤3完成：图文图片上传成功")
            return None

        file_input_selectors = Selectors.PUBLISH.get("FILE_INPUT", [])
        uploaded = False

        # Layer1：优先「上传时长」（视频号主按钮文案），再放宽到含「上传」
        try:
            for pattern in (re.compile(r"上传时长"), re.compile(r"上传")):
                upload_btn_l1 = page.get_by_role("button", name=pattern).first
                if await upload_btn_l1.count() > 0:
                    async with page.expect_file_chooser(timeout=15000) as fc_info:
                        try:
                            from src.infrastructure.anti_risk.human_like import human_click

                            await human_click(
                                page,
                                upload_btn_l1,
                                metadata,
                                metadata.get("anti_risk_config"),
                            )
                        except Exception:
                            await upload_btn_l1.click()
                    await fc_info.value.set_files(file_path)
                    uploaded = True
                    logger.info("[视频号] 通过 get_by_role(button, 上传…) + file chooser 上传成功")
                    break
        except Exception as e:
            logger.debug("[视频号] L1 上传按钮路径未命中或失败: %s", e)

        for sel in file_input_selectors:
            try:
                file_input = page.locator(sel).first
                if await file_input.count() > 0:
                    await file_input.set_input_files(file_path)
                    uploaded = True
                    logger.info(f"[视频号] 通过 {sel} 上传文件成功")
                    break
            except Exception as e:
                logger.debug(f"[视频号] 通过 {sel} 上传失败: {e}")
                continue

        # 兜底：通过 file chooser 上传
        if not uploaded:
            upload_selectors = Selectors.PUBLISH.get("UPLOAD_BTN", [])
            for sel in upload_selectors:
                try:
                    upload_btn = page.locator(sel).first
                    if await upload_btn.count() > 0:
                        async with page.expect_file_chooser() as fc_info:
                            try:
                                from src.infrastructure.anti_risk.human_like import human_click

                                await human_click(page, upload_btn, metadata, metadata.get("anti_risk_config"))
                            except Exception:
                                await upload_btn.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(file_path)
                        uploaded = True
                        logger.info("[视频号] 通过 file chooser 上传文件成功")
                        break
                except Exception as e:
                    logger.debug(f"[视频号] 通过 {sel} file chooser 上传失败: {e}")
                    continue

        if not uploaded:
            await log_page_diagnostics(
                page,
                logger,
                "未找到文件上传入口",
                level=logging.WARNING,
                max_items=40,
            )
            return PublishResult(
                success=False,
                error_message="未找到文件上传入口",
                failed_step="UploadMediaStep",
            )

        # 等待上传完成：Shadow 内轮询为主，locator 为辅（3.2 / DOM 对照表）
        logger.info("[视频号] 文件正在上传，等待「删除」成功标识...")
        success_selectors = Selectors.PUBLISH.get("UPLOAD_SUCCESS_MARKER", [])
        max_wait_ms = 180000
        poll_ms = 500
        attempts = max(1, max_wait_ms // poll_ms)
        upload_confirmed = False

        for _ in range(attempts):
            try:
                if await page.evaluate(_SHADOW_UPLOAD_SUCCESS_JS):
                    upload_confirmed = True
                    logger.info("[视频号] Shadow 内检测到「删除」标识，上传成功")
                    break
            except Exception as e:
                logger.debug("[视频号] Shadow 检测上传成功异常: %s", e)

            for sel in success_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        upload_confirmed = True
                        logger.info(f"[视频号] locator 检测到上传成功: {sel}")
                        break
                except Exception:
                    continue
            if upload_confirmed:
                break

            await page.wait_for_timeout(poll_ms)

        if not upload_confirmed:
            await log_page_diagnostics(
                page,
                logger,
                "上传超时未检测到删除标识",
                level=logging.WARNING,
                max_items=40,
            )
            return PublishResult(
                success=False,
                error_message="上传超时（3分钟内未检测到「删除」按钮），请检查文件或网络",
                failed_step="UploadMediaStep",
            )

        logger.info("[视频号] 步骤3完成：文件上传成功")
        return None
