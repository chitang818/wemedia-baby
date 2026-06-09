# -*- coding: utf-8 -*-
"""
步骤 5B：微信视频号发布的描述和话题填写。

视频和图文发布均共用此步骤。对于图文发布，它会在图文标题（ImageTitleStep）填写之后运行。
"""
import json
import logging
from typing import Dict, Any, List

from src.infrastructure.browser.automation_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class MetadataFillStep(BasePublishStep):
    """Fill description and tags into the shared contenteditable editor."""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        description = metadata.get("description", "") or ""
        tags = metadata.get("tags", []) or []
        logger.info(f"[视频号] 步骤5B：填写描述")

        if not description and not tags:
            logger.info("[视频号] 未配置描述和话题，跳过")
            return None

        full_text = description
        if tags:
            tag_list = tags if isinstance(tags, list) else [t.strip() for t in tags.split(",") if t.strip()]
            for tag in tag_list:
                tag_text = tag if tag.startswith("#") else f"#{tag}"
                if tag_text not in full_text:
                    full_text += f" {tag_text}"

        full_text = full_text.strip()
        logger.info(f"[视频号] 待填写内容: '{full_text[:50]}...'（共{len(full_text)}字符）")

        desc_candidates: List[str] = list(
            Selectors.PUBLISH.get("DESC_EDITOR_CANDIDATES")
            or [Selectors.PUBLISH.get("DESC_EDITOR", "")]
        )
        desc_candidates = [c for c in desc_candidates if c]

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
            desc_candidates,
        )
        if not matched_sel:
            logger.warning("[视频号] 未匹配到任何 DESC_EDITOR 候选")
            return PublishResult(
                success=False,
                error_message="未找到描述输入框（所有候选均未命中）",
                failed_step="MetadataFillStep",
            )
        logger.info("[视频号] 描述输入框命中选择器: %s", matched_sel)
        sel_json = json.dumps(matched_sel)

        try:
            focus_result = await page.evaluate(
                f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return 'no_shadow';
                    const editor = shadow.querySelector({sel_json});
                    if (!editor) return 'editor_not_found';
                    editor.focus();
                    return 'focused';
                }}"""
            )
            if focus_result != "focused":
                logger.warning("[视频号] 聚焦描述输入框失败: %s", focus_result)
                return PublishResult(
                    success=False,
                    error_message=f"未找到描述输入框: {focus_result}",
                    failed_step="MetadataFillStep",
                )
        except Exception as e:
            logger.error(f"[视频号] 聚焦输入框异常: {e}")
            return PublishResult(
                success=False,
                error_message=f"聚焦描述输入框异常: {e}",
                failed_step="MetadataFillStep",
            )

        await page.wait_for_timeout(300)

        try:
            await page.evaluate(
                f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return;
                    const editor = shadow.querySelector({sel_json});
                    if (editor) {{
                        editor.focus();
                        editor.innerHTML = '';
                    }}
                }}"""
            )
        except Exception as e:
            logger.debug(f"[视频号] 清空输入框异常: {e}")

        await page.wait_for_timeout(200)

        try:
            await page.evaluate(
                f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return;
                    const editor = shadow.querySelector({sel_json});
                    if (editor) editor.focus();
                }}"""
            )
            await page.wait_for_timeout(100)
            await page.keyboard.type(full_text, delay=30)
            logger.info(f"[视频号] 已输入描述（{len(full_text)}字符）")
        except Exception as e:
            logger.warning(f"[视频号] 键盘输入失败，尝试 JS 直接写入: {e}")
            try:
                escaped_text = json.dumps(full_text)
                await page.evaluate(
                    f"""() => {{
                        const shadow = {WUJIE_SHADOW_ROOT_JS};
                        if (!shadow) return;
                        const editor = shadow.querySelector({sel_json});
                        if (editor) {{
                            editor.innerText = {escaped_text};
                            editor.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        }}
                    }}"""
                )
            except Exception as e2:
                logger.error(f"[视频号] JS 写入也失败: {e2}")
                return PublishResult(
                    success=False,
                    error_message=f"填写描述失败: {e2}",
                    failed_step="MetadataFillStep",
                )

        await page.wait_for_timeout(500)
        try:
            actual_text = await page.evaluate(
                f"""() => {{
                    const shadow = {WUJIE_SHADOW_ROOT_JS};
                    if (!shadow) return '';
                    const editor = shadow.querySelector({sel_json});
                    return editor ? editor.innerText.trim() : '';
                }}"""
            )
            if not actual_text:
                logger.error("[视频号] 验证失败：描述输入框 innerText 为空，终止发布")
                USER_LOG.error(
                    "%s ✗ 描述写入验证失败（innerText 为空），终止发布",
                    self._step_prefix(metadata, "描述"),
                )
                return PublishResult(
                    success=False,
                    error_message="描述写入验证失败：innerText 为空",
                    failed_step="MetadataFillStep",
                )
        except Exception as e:
            logger.warning("[视频号] 验证描述输入结果时异常: %s", e)

        logger.info("[视频号] 步骤5B完成：描述填写成功")
        return None
