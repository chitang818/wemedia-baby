# -*- coding: utf-8 -*-
"""
步骤5：填写视频描述与话题
文件路径: src/plugins/pro/wechat_video/steps/step_05_description.py

流程：
  - description 和 tags 均为空：直接跳过。
  - 有内容时：
      1. 将 description 和 tags 拼接为完整文本（话题格式为 #关键词，空格分隔）
      2. JS 穿透 Shadow DOM 聚焦 contenteditable 输入框（Selectors.PUBLISH.DESC_EDITOR）
      3. 清空原有内容（innerHTML = ''）
      4. page.keyboard.type() 逐字输入（delay=30ms，模拟真实打字防风控）
         降级：JS 直接写入 innerText 并触发 input 事件
      5. 验证输入框内容不为空

字段依赖：metadata['description']（视频描述文本）
               metadata['tags']（话题列表或逗号字符串）

DOM：<div contenteditable="" data-placeholder="添加描述" class="input-editor">
所有元素在 wujie-app Shadow DOM 内，需 JS 穿透访问。
"""
import json
import logging
from typing import Dict, Any, List

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from ..wujie_shadow import WUJIE_SHADOW_ROOT_JS

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class MetadataFillStep(BasePublishStep):
    """填写视频描述和话题。

    视频号的「视频描述」输入框是一个 contenteditable div，
    描述文本和 #话题 在同一个输入框中填写。
    该元素位于 wujie-app 的 Shadow DOM 内部。
    """

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        description = metadata.get("description", "") or ""
        tags = metadata.get("tags", []) or []
        logger.info(f"[视频号] 步骤5：填写视频描述")

        # 如果没有描述和话题，跳过
        if not description and not tags:
            logger.info("[视频号] 未配置描述和话题，跳过")
            return None

        # 拼接完整文本：描述 + 话题
        full_text = description
        if tags:
            tag_list = tags if isinstance(tags, list) else [t.strip() for t in tags.split(",") if t.strip()]
            for tag in tag_list:
                tag_text = tag if tag.startswith("#") else f"#{tag}"
                # 避免重复添加（描述中已包含的话题）
                if tag_text not in full_text:
                    full_text += f" {tag_text}"

        full_text = full_text.strip()
        logger.info(f"[视频号] 待填写内容: '{full_text[:50]}...'（共{len(full_text)}字符）")

        # ---- 通过 JS 穿透 Shadow DOM 操作输入框（顺序对齐 DOM 报告：placeholder/语义优先） ----
        desc_candidates: List[str] = list(
            Selectors.PUBLISH.get("DESC_EDITOR_CANDIDATES")
            or [Selectors.PUBLISH.get("DESC_EDITOR", "")]
        )
        desc_candidates = [c for c in desc_candidates if c]

        _pick_desc_editor_sel = f"""
        (cands) => {{
            const shadow = {WUJIE_SHADOW_ROOT_JS};
            if (!shadow) return null;
            for (const sel of cands) {{
                try {{
                    const el = shadow.querySelector(sel);
                    if (el) return sel;
                }} catch (e) {{ /* invalid selector */ }}
            }}
            return null;
        }}
        """

        matched_sel = await page.evaluate(_pick_desc_editor_sel, desc_candidates)
        if not matched_sel:
            logger.warning("[视频号] 未匹配到任何 DESC_EDITOR 候选")
            return PublishResult(
                success=False,
                error_message="未找到视频描述输入框（所有候选均未命中）",
                failed_step="MetadataFillStep",
            )
        logger.info("[视频号] 描述输入框命中选择器: %s", matched_sel)
        sel_json = json.dumps(matched_sel)

        # 1. 先聚焦输入框
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
                    error_message=f"未找到视频描述输入框: {focus_result}",
                    failed_step="MetadataFillStep",
                )
            logger.info("[视频号] 已聚焦视频描述输入框")
        except Exception as e:
            logger.error(f"[视频号] 聚焦输入框异常: {e}")
            return PublishResult(
                success=False,
                error_message=f"聚焦描述输入框异常: {e}",
                failed_step="MetadataFillStep",
            )

        await page.wait_for_timeout(300)

        # 2. 清空现有内容
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
            logger.info("[视频号] 已清空描述输入框")
        except Exception as e:
            logger.debug(f"[视频号] 清空输入框异常（非关键）: {e}")

        await page.wait_for_timeout(200)

        # 3. 通过键盘逐字输入（模拟真实打字，防风控）
        try:
            # 先用 JS 重新聚焦
            await page.evaluate(
                f"""() => {{
                const shadow = {WUJIE_SHADOW_ROOT_JS};
                if (!shadow) return;
                const editor = shadow.querySelector({sel_json});
                if (editor) editor.focus();
            }}"""
            )

            await page.wait_for_timeout(100)

            # 使用 page.keyboard.type 逐字输入
            await page.keyboard.type(full_text, delay=30)
            logger.info(f"[视频号] 已输入视频描述（{len(full_text)}字符）")
        except Exception as e:
            logger.warning(f"[视频号] 键盘输入失败，尝试 JS 直接写入: {e}")
            # 降级：JS 直接写入
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
                logger.info("[视频号] 已通过 JS 直接写入描述")
            except Exception as e2:
                logger.error(f"[视频号] JS 写入也失败: {e2}")
                return PublishResult(
                    success=False,
                    error_message=f"填写描述失败: {e2}",
                    failed_step="MetadataFillStep",
                )

        # 4. 严格验证：读回 innerText，为空则视为填写失败，返回发布失败
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

            if actual_text:
                logger.info(f"[视频号] 验证成功，输入框内容: '{actual_text[:30]}...'")
            else:
                logger.error("[视频号] 验证失败：描述输入框 innerText 为空，终止发布")
                USER_LOG.error("[步骤5/11 视频描述] ✗ 描述写入验证失败（innerText 为空），终止发布")
                return PublishResult(
                    success=False,
                    error_message="视频描述写入验证失败：innerText 为空",
                    failed_step="MetadataFillStep",
                )
        except Exception as e:
            logger.warning("[视频号] 验证描述输入框内容时异常: %s", e)

        logger.info("[视频号] 步骤5完成：视频描述填写成功")
        return None
