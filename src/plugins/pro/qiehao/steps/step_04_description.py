# -*- coding: utf-8 -*-
"""
步骤4：作品描述（标题、简介、标签）
文件路径: src/plugins/pro/qiehao/steps/step_04_description.py

流程：
  1. 标题填写：定位标题输入框，清空后逐字输入（企鹅号标题 6~30 字）
  2. 简介填写：定位描述编辑区域，清空后逐字输入
  3. 标签输入（可选）：逐个输入标签并按 Enter 确认

字段依赖：
  - metadata['title']: 标题（6~30 字）
  - metadata['description']: 简介
  - metadata['tags']: 标签列表
  - metadata['speed_rate']: 打字速度倍率
"""
import logging
from typing import Dict, Any, List

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class MetadataFillStep(BasePublishStep):
    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """填写元数据：标题 + 简介 + 标签。"""
        await self._await_pause(metadata)
        title = metadata.get("title", "") or ""
        description = metadata.get("description", "") or ""
        tags = metadata.get("tags", []) or []
        tags = (
            tags
            if isinstance(tags, list)
            else [t.strip() for t in str(tags).split(",") if t.strip()]
        )

        logger.info(
            f"开始填写元数据: 标题={title[:20]}…, 简介长度={len(description)}, 标签数={len(tags)}"
        )

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        desc_delay = max(20, int(50 * speed_rate))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        # ── 1. 标题（企鹅号要求 6~30 字） ──
        if title:
            title_text = title.strip()[:30]
            for selector in Selectors.PUBLISH["TITLE_INPUT"]:
                try:
                    title_input = page.locator(selector).first
                    if await title_input.count() > 0 and await title_input.is_visible():
                        try:
                            from src.infrastructure.anti_risk.human_like import human_type_text
                            await title_input.click()
                            await page.keyboard.press("Control+A")
                            await page.keyboard.press("Backspace")
                            try:
                                from src.infrastructure.anti_risk.delays import random_delay
                                await random_delay(page, wait_ms(300), metadata, config)
                            except Exception:
                                await page.wait_for_timeout(wait_ms(300))
                            await human_type_text(page, selector, title_text, metadata, config)
                        except Exception:
                            await title_input.click()
                            await page.keyboard.press("Control+A")
                            await page.keyboard.press("Backspace")
                            await title_input.type(title_text, delay=max(10, int(30 * speed_rate)))
                        logger.info(f"已填写标题: {selector}")
                        t_display = title_text[:25] + "…" if len(title_text) > 25 else title_text or "（空）"
                        USER_LOG.info(f"[步骤4 作品描述] ▶ 标题已填写：{t_display}")
                        break
                except Exception:
                    continue

        # ── 2. 简介 ──
        if description:
            editor_selectors = list(Selectors.PUBLISH["DESC_EDITOR"])
            for selector in editor_selectors:
                try:
                    edit_box = page.locator(selector).first
                    if await edit_box.count() > 0 and await edit_box.is_visible():
                        logger.info(f"找到编辑器: {selector}")

                        try:
                            from src.infrastructure.anti_risk.human_like import human_click
                            await human_click(page, edit_box, metadata, config)
                        except Exception:
                            await edit_box.click()

                        try:
                            from src.infrastructure.anti_risk.delays import random_delay
                            await random_delay(page, wait_ms(500), metadata, config)
                        except Exception:
                            await page.wait_for_timeout(wait_ms(500))

                        await page.keyboard.press("Control+A")
                        await page.keyboard.press("Backspace")
                        try:
                            from src.infrastructure.anti_risk.delays import random_delay
                            await random_delay(page, wait_ms(300), metadata, config)
                        except Exception:
                            await page.wait_for_timeout(wait_ms(300))

                        full_text = description.strip()
                        await edit_box.type(full_text, delay=desc_delay)

                        try:
                            from src.infrastructure.anti_risk.delays import random_delay
                            await random_delay(page, wait_ms(800), metadata, config)
                        except Exception:
                            await page.wait_for_timeout(wait_ms(800))

                        desc_display = (full_text[:35] + "…") if len(full_text) > 35 else (full_text or "（空）")
                        USER_LOG.info(f"[步骤4 作品描述] ▶ 简介已填写：{desc_display}")
                        logger.info("简介填写完成")
                        break
                except Exception as e:
                    logger.warning(f"使用选择器 {selector} 填写简介失败: {e}")
                    continue

        # ── 3. 标签 ──
        if tags:
            await self._fill_tags(page, tags, metadata, config, speed_rate)

        USER_LOG.info(f"[步骤4 作品描述] ✓ 元数据填写完成，标签数={len(tags)}")
        logger.info("元数据填写完成")
        return None

    async def _fill_tags(
        self, page: Page, tags: List[str], metadata: Dict[str, Any],
        config: dict, speed_rate: float
    ) -> None:
        """逐个输入标签并按 Enter 确认。"""
        wait_ms = lambda ms: int(ms * speed_rate)

        for selector in Selectors.PUBLISH["TAG_INPUT"]:
            try:
                tag_input = page.locator(selector).first
                if await tag_input.count() > 0 and await tag_input.is_visible():
                    logger.info(f"找到标签输入框: {selector}")
                    for i, tag in enumerate(tags[:10]):
                        tag = tag.strip().lstrip('#')
                        if not tag:
                            continue
                        try:
                            await tag_input.click()
                            await tag_input.type(tag, delay=max(10, int(30 * speed_rate)))
                            await page.keyboard.press("Enter")
                            try:
                                from src.infrastructure.anti_risk.delays import random_delay
                                await random_delay(page, wait_ms(500), metadata, config)
                            except Exception:
                                await page.wait_for_timeout(wait_ms(500))
                            logger.info(f"已输入标签 [{i+1}/{len(tags)}]: {tag}")
                        except Exception as e:
                            logger.warning(f"输入标签 '{tag}' 失败: {e}")
                            break
                    return
            except Exception:
                continue

        logger.warning("未找到标签输入框，跳过标签输入")
