# -*- coding: utf-8 -*-
"""
步骤 5A：微信视频号图文发布专用的标题填写。

此步骤仅适用于图文发布。它在文件上传之后、描述填写之前运行，
因为页面布局将图文标题输入框放在了描述输入框的上方。
"""
import json
import logging
from typing import Any, Dict, List

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS

logger = logging.getLogger(__name__)


class ImageTitleStep(BasePublishStep):
    """Fill the image-post title input on the image publishing page."""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        file_type = (metadata.get("file_type") or "video").lower()
        if file_type != "image":
            return None

        title = (metadata.get("title") or "").strip()
        logger.info("[视频号] 步骤5A：填写图文标题（内容='%s'）", title)
        if not title:
            logger.info("[视频号] 图文任务未配置标题，跳过图文标题填写")
            return None

        max_length = 22
        if len(title) > max_length:
            title = title[:max_length]
            logger.warning("[视频号] 图文标题超过 %s 字，已截断为: '%s'", max_length, title)

        candidates: List[str] = list(
            Selectors.PUBLISH.get("IMAGE_TITLE_INPUT_CANDIDATES")
            or [Selectors.PUBLISH.get("IMAGE_TITLE_INPUT", "")]
        )
        candidates = [item for item in candidates if item]

        matched_sel = await page.evaluate(
            f"""(cands) => {{
                const shadow = {WUJIE_SHADOW_ROOT_JS};
                if (!shadow) return null;
                for (const sel of cands) {{
                    try {{
                        const el = shadow.querySelector(sel);
                        if (el) return sel;
                    }} catch (e) {{
                    }}
                }}
                return null;
            }}""",
            candidates,
        )
        if not matched_sel:
            return PublishResult(
                success=False,
                error_message="未找到图文标题输入框",
                failed_step="ImageTitleStep",
            )

        sel_json = json.dumps(matched_sel)

        try:
            focus_result = await page.evaluate(
                f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return 'no_shadow';
                    const input = shadow.querySelector({sel_json});
                    if (!input) return 'input_not_found';
                    input.focus();
                    input.click();
                    return 'focused';
                }}"""
            )
            if focus_result != "focused":
                return PublishResult(
                    success=False,
                    error_message=f"未找到图文标题输入框: {focus_result}",
                    failed_step="ImageTitleStep",
                )
        except Exception as e:
            return PublishResult(
                success=False,
                error_message=f"聚焦图文标题输入框异常: {e}",
                failed_step="ImageTitleStep",
            )

        await page.wait_for_timeout(200)

        try:
            await page.evaluate(
                f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return;
                    const input = shadow.querySelector({sel_json});
                    if (input) {{
                        input.focus();
                        input.value = '';
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    }}
                }}"""
            )
        except Exception as e:
            logger.debug("[视频号] 清空图文标题输入框异常: %s", e)

        await page.wait_for_timeout(100)

        try:
            await page.evaluate(
                f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return;
                    const input = shadow.querySelector({sel_json});
                    if (input) input.focus();
                }}"""
            )
            await page.wait_for_timeout(100)
            await page.keyboard.type(title, delay=30)
        except Exception as e:
            logger.warning("[视频号] 键盘输入图文标题失败，尝试 JS 回填: %s", e)
            try:
                escaped = json.dumps(title)
                await page.evaluate(
                    f"""() => {{
                        const shadow = {WUJIE_SHADOW_ROOT_JS};
                        if (!shadow) return;
                        const input = shadow.querySelector({sel_json});
                        if (input) {{
                            const setter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value'
                            ).set;
                            setter.call(input, {escaped});
                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}"""
                )
            except Exception as e2:
                return PublishResult(
                    success=False,
                    error_message=f"填写图文标题失败: {e2}",
                    failed_step="ImageTitleStep",
                )

        await page.wait_for_timeout(300)

        try:
            actual = await page.evaluate(
                f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return '';
                    const input = shadow.querySelector({sel_json});
                    return input ? (input.value || '').trim() : '';
                }}"""
            )
            if not actual:
                return PublishResult(
                    success=False,
                    error_message="图文标题写入验证失败：input.value 为空",
                    failed_step="ImageTitleStep",
                )
        except Exception as e:
            logger.warning("[视频号] 图文标题回读验证异常: %s", e)

        logger.info("[视频号] 步骤5A完成：图文标题填写成功")
        return None
