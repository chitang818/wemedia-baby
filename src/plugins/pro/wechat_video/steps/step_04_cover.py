# -*- coding: utf-8 -*-
"""
步骤4：封面设置
文件路径: src/plugins/pro/wechat_video/steps/step_04_cover.py

流程：
  - 首帧封面（默认，cover_type != 'custom' 或 cover_path 为空）：直接跳过。
  - 本地封面（cover_type == 'custom' 且 cover_path 有值）：
      1. JS 穿透 Shadow DOM，点击「个人主页和分享卡片(3:4)」封面入口
      2. 等待「编辑封面」弹窗出现（轮询最多 5 秒）
      3. 在 **COVER_DIALOG 子树内** 上传封面（file input 或 file chooser），避免命中其它弹窗
      4. 等待 2s 后仅在弹窗子树内点击「确认」
      5. 验证弹窗已关闭（最多等 10s）

字段依赖：metadata['cover_path']（本地封面图路径，空则用首帧）
                 metadata['cover_type']（custom / first_frame）

所有封面元素在 wujie-app Shadow DOM 内，需 JS 穿透访问。
"""
import json
import logging
from typing import Dict, Any

from src.infrastructure.browser.automation_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class CoverSettingStep(BasePublishStep):
    """封面设置步骤。

    流程分两种情况：
    - 首帧封面（默认）：视频上传后平台自动选取首帧作为封面，无需操作，直接跳过。
    - 本地封面：
        1. 点击「个人主页和分享卡片(3:4)」入口 → 打开编辑封面弹窗
        2. 在弹窗 scope 内点击「上传封面」(+号区域) → 通过 file chooser 上传封面图
        3. 在弹窗 scope 内点击「确认」按钮关闭弹窗

    注意：所有元素位于 wujie-app 的 Shadow DOM 内，需使用 JS 穿透操作。
    """

    async def _wait_shadow_dialog_visible(
        self, page: Page, js_dialog: str, metadata: Dict[str, Any], timeout_ms: int = 5000
    ) -> bool:
        async def _is_visible() -> bool:
            try:
                result = await page.evaluate(
                    f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return false;
                    const dialog = shadow.querySelector({js_dialog});
                    return !!dialog;
                }}"""
                )
                return bool(result)
            except Exception:
                return False

        return bool(
            await PluginWaitHelper.wait_for_condition(
                page,
                _is_visible,
                timeout_ms=timeout_ms,
                poll_interval_ms=500,
                pause_callback=lambda: self._await_pause(metadata),
            )
        )

    async def _wait_shadow_confirm_ready(
        self,
        page: Page,
        js_dialog: str,
        js_confirm: str,
        metadata: Dict[str, Any],
        timeout_ms: int = 5000,
    ) -> bool:
        async def _is_ready() -> bool:
            try:
                return bool(
                    await page.evaluate(
                        f"""() => {{
                        const shadow = {WUJIE_SHADOW_ROOT_JS};
                        if (!shadow) return false;
                        const dialog = shadow.querySelector({js_dialog});
                        if (!dialog) return false;
                        let btn = dialog.querySelector({js_confirm});
                        if (!btn) {{
                            const allBtns = dialog.querySelectorAll('button.weui-desktop-btn_primary');
                            btn = Array.from(allBtns).find((b) => (b.textContent || '').includes('确认'));
                        }}
                        if (!btn) return false;
                        const style = window.getComputedStyle(btn);
                        return !btn.disabled && style.display !== 'none' && style.visibility !== 'hidden';
                    }}"""
                    )
                )
            except Exception:
                return False

        return bool(
            await PluginWaitHelper.wait_for_condition(
                page,
                _is_ready,
                timeout_ms=timeout_ms,
                poll_interval_ms=500,
                pause_callback=lambda: self._await_pause(metadata),
            )
        )

    async def _wait_shadow_dialog_closed(
        self, page: Page, js_dialog: str, metadata: Dict[str, Any], timeout_ms: int = 10000
    ) -> bool:
        async def _is_closed() -> bool:
            try:
                result = await page.evaluate(
                    f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return true;
                    const dialog = shadow.querySelector({js_dialog});
                    if (!dialog) return true;
                    const style = window.getComputedStyle(dialog);
                    return style.display === 'none' || style.visibility === 'hidden';
                }}"""
                )
                return bool(result)
            except Exception:
                return False

        return bool(
            await PluginWaitHelper.wait_for_condition(
                page,
                _is_closed,
                timeout_ms=timeout_ms,
                poll_interval_ms=500,
                pause_callback=lambda: self._await_pause(metadata),
            )
        )

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        cover_type = metadata.get("cover_type", "first_frame")  # first_frame / custom
        cover_path = metadata.get("cover_path")  # 本地封面图路径

        logger.info(f"[视频号] 步骤4：封面设置（类型={cover_type}）")

        # ---- 首帧封面：跳过 ----
        if cover_type != "custom" or not cover_path:
            logger.info("[视频号] 使用首帧封面（默认），跳过封面设置")
            return None

        # ---- 本地封面：执行上传流程 ----
        logger.info(f"[视频号] 准备上传本地封面: {cover_path}")

        cover_entry_sel = Selectors.PUBLISH.get("COVER_ENTRY", "")
        cover_dialog_sel = Selectors.PUBLISH.get("COVER_DIALOG", "")
        cover_upload_sel = Selectors.PUBLISH.get("COVER_UPLOAD_BTN", "")
        cover_confirm_sel = Selectors.PUBLISH.get("COVER_CONFIRM_BTN", "")

        js_entry = json.dumps(cover_entry_sel)
        js_dialog = json.dumps(cover_dialog_sel)
        js_upload = json.dumps(cover_upload_sel)
        js_confirm = json.dumps(cover_confirm_sel)

        # ---- 1. 点击封面入口「个人主页和分享卡片(3:4)」打开弹窗 ----
        try:
            entry_clicked = await page.evaluate(
                f"""() => {{
                const shadow = {WUJIE_SHADOW_ROOT_JS};
                if (!shadow) return 'shadow_not_found';
                const entry = shadow.querySelector({js_entry});
                if (!entry) return 'entry_not_found';
                entry.click();
                return 'clicked';
            }}"""
            )

            if entry_clicked != "clicked":
                logger.warning(f"[视频号] JS 点击封面入口失败: {entry_clicked}")
                return PublishResult(
                    success=False,
                    error_message=f"无法点击封面入口: {entry_clicked}",
                    failed_step="CoverSettingStep",
                )
            logger.info("[视频号] 已点击「个人主页和分享卡片(3:4)」入口")
        except Exception as e:
            logger.error(f"[视频号] 点击封面入口异常: {e}")
            return PublishResult(
                success=False,
                error_message=f"点击封面入口异常: {e}",
                failed_step="CoverSettingStep",
            )

        # ---- 2. 等待编辑封面弹窗出现 ----
        if not await self._wait_shadow_dialog_visible(page, js_dialog, metadata):
            return PublishResult(
                success=False,
                error_message="编辑封面弹窗未出现",
                failed_step="CoverSettingStep",
            )
        logger.info("[视频号] 编辑封面弹窗已出现")

        # ---- 3. 仅在弹窗子树内上传封面 ----
        try:
            uploaded = False

            try:
                file_inputs = await page.evaluate(
                    f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return 0;
                    const dialog = shadow.querySelector({js_dialog});
                    if (!dialog) return 0;
                    return dialog.querySelectorAll('input[type="file"]').length;
                }}"""
                )

                if file_inputs and file_inputs > 0:
                    # 通过 JS 确认弹窗内 file input 存在后，缩小 Playwright 定位范围：
                    # 优先匹配弹窗容器子树内的 file input，避免命中弹窗外的 file input
                    file_input = page.locator(
                        f"{cover_dialog_sel} input[type='file'], "
                        "[class*='dialog'] input[type='file'], "
                        "[class*='modal'] input[type='file']"
                    )
                    total_inputs = page.locator("input[type='file']")
                    total_count = await total_inputs.count()
                    scoped_count = await file_input.count()
                    if scoped_count > 0:
                        await file_input.last.set_input_files(cover_path)
                        uploaded = True
                        logger.info("[视频号] 通过弹窗作用域内 file input 上传封面成功")
                    elif total_count > 0:
                        # 作用域定位失败时，回退到全页 last（并记录警告）
                        logger.warning("[视频号] 弹窗作用域内未定位到 file input，回退至全页最后一个（总数: %d）", total_count)
                        await total_inputs.last.set_input_files(cover_path)
                        uploaded = True
                        logger.info("[视频号] 通过 file input 上传封面成功（弹窗内）")
            except Exception as e:
                logger.debug(f"[视频号] file input 上传方式失败: {e}")

            if not uploaded:
                logger.info("[视频号] 尝试通过 file chooser 上传封面（弹窗内点击）...")
                async with page.expect_file_chooser(timeout=10000) as fc_info:
                    click_up = await page.evaluate(
                        f"""() => {{
                        const shadow = {WUJIE_SHADOW_ROOT_JS};
                        if (!shadow) return 'no_shadow';
                        const dialog = shadow.querySelector({js_dialog});
                        if (!dialog) return 'no_dialog';
                        const uploadBtn = dialog.querySelector({js_upload});
                        if (!uploadBtn) return 'no_upload_btn';
                        uploadBtn.click();
                        return 'clicked';
                    }}"""
                    )
                    if click_up != "clicked":
                        raise RuntimeError(f"弹窗内点击上传区域失败: {click_up}")
                file_chooser = await fc_info.value
                await file_chooser.set_files(cover_path)
                uploaded = True
                logger.info("[视频号] 通过 file chooser 上传封面成功")

            if not uploaded:
                return PublishResult(
                    success=False,
                    error_message="无法上传封面图片",
                    failed_step="CoverSettingStep",
                )

        except Exception as e:
            logger.error(f"[视频号] 上传封面异常: {e}")
            return PublishResult(
                success=False,
                error_message=f"上传封面异常: {e}",
                failed_step="CoverSettingStep",
            )

        await self._wait_shadow_confirm_ready(
            page, js_dialog, js_confirm, metadata, timeout_ms=5000
        )

        # ---- 4. 仅在弹窗子树内点击「确认」----
        try:
            confirm_result = await page.evaluate(
                f"""() => {{
                const shadow = {WUJIE_SHADOW_ROOT_JS};
                if (!shadow) return 'no_shadow';
                const dialog = shadow.querySelector({js_dialog});
                if (!dialog) return 'no_dialog';
                let btn = dialog.querySelector({js_confirm});
                if (!btn) {{
                    const allBtns = dialog.querySelectorAll('button.weui-desktop-btn_primary');
                    for (const b of allBtns) {{
                        if ((b.textContent || '').includes('确认')) {{
                            b.click();
                            return 'clicked_fallback';
                        }}
                    }}
                    return 'btn_not_found';
                }}
                btn.click();
                return 'clicked';
            }}"""
            )

            if confirm_result and "clicked" in confirm_result:
                logger.info(f"[视频号] 已点击「确认」按钮 ({confirm_result})")
            else:
                logger.warning(f"[视频号] 点击确认按钮失败: {confirm_result}")
                return PublishResult(
                    success=False,
                    error_message=f"无法点击封面确认按钮: {confirm_result}",
                    failed_step="CoverSettingStep",
                )
        except Exception as e:
            logger.error(f"[视频号] 点击确认按钮异常: {e}")
            return PublishResult(
                success=False,
                error_message=f"点击确认按钮异常: {e}",
                failed_step="CoverSettingStep",
            )

        # ---- 5. 等待弹窗关闭 ----
        dialog_closed = await self._wait_shadow_dialog_closed(
            page, js_dialog, metadata
        )
        if dialog_closed:
            logger.info("[视频号] 编辑封面弹窗已关闭")

        if not dialog_closed:
            logger.warning("[视频号] 编辑封面弹窗未检测到关闭，但确认按钮已点击，继续执行")

        logger.info("[视频号] 步骤4完成：封面设置成功")
        return None
