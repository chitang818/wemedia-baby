# -*- coding: utf-8 -*-
"""
步骤4：作品描述（标题与正文）
文件路径: src/plugins/pro/xiaohongshu/steps/step_04_description.py

流程：
  1. 标题填写：定位标题输入框（TITLE_INPUT），清空后逐字输入（小红书标题限 20 字）
  2. 正文/描述填写：
     - 定位 contenteditable 编辑器（DESC_EDITOR）
     - 拟人点击聚焦，全选清空旧内容
     - 逐字输入 description 全文
     - 若末尾为 #话题，补按空格以触发话题识别
  3. 话题标签（可选）：
     - 若 tags 中有话题未在 description 中以 #形式出现，单独输入

字段依赖：
  - metadata['title']: 标题（小红书限 20 字）
  - metadata['description']: 描述/正文
  - metadata['tags']: 话题标签列表
  - metadata['speed_rate']: 打字速度倍率
"""
import logging
import re
from typing import Dict, Any

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class MetadataFillStep(BasePublishStep):
    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """填写元数据：标题 + 正文（含已确认的 #话题）。"""
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
            f"开始填写元数据: 标题={title[:20]}…, 正文长度={len(description)}, 话题数={len(tags)}"
        )

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        desc_delay = max(20, int(50 * speed_rate))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        # ── 1. 标题 ──
        if title:
            title_text = title.strip()[:20]  # 小红书标题限制 20 字
            for selector in Selectors.PUBLISH["TITLE_INPUT"]:
                try:
                    title_input = page.locator(selector).first
                    if await title_input.count() > 0 and await title_input.is_visible():
                        try:
                            from src.infrastructure.anti_risk.human_like import human_type_text
                            await human_type_text(page, selector, title_text, metadata, config)
                        except Exception:
                            await title_input.click()
                            await page.keyboard.press("Control+A")
                            await page.keyboard.press("Backspace")
                            await title_input.type(title_text, delay=max(10, int(30 * speed_rate)))
                        logger.info(f"已填写标题: {selector}")
                        t_display = title_text[:15] + "…" if len(title_text) > 15 else title_text or "（空）"
                        USER_LOG.info(f"[步骤4 作品描述] ▶ 标题已填写：{t_display}")
                        break
                except Exception:
                    continue

        # ── 2. 正文/描述 ──
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

                    # 清空已有内容
                    await page.keyboard.press("Control+A")
                    await page.keyboard.press("Backspace")
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay
                        await random_delay(page, wait_ms(300), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(wait_ms(300))

                    full_text = (description or title or "").strip()

                    # 逐字输入
                    await edit_box.type(full_text, delay=desc_delay)
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay
                        await random_delay(page, wait_ms(800), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(wait_ms(800))

                    # 末尾 #话题 补空格确认
                    if full_text and re.search(r"#\S+$", full_text):
                        await page.keyboard.press("Space")
                        await page.wait_for_timeout(200)

                    desc_display = (full_text[:35] + "…") if len(full_text) > 35 else (full_text or "（空）")
                    tag_count = len(tags) if isinstance(tags, list) and tags else 0
                    USER_LOG.info(
                        f"[步骤4 作品描述] ✓ 正文已填写：{desc_display}，话题数={tag_count}"
                    )
                    logger.info("元数据填写完成")
                    return None
            except Exception as e:
                logger.warning(f"使用选择器 {selector} 填写失败: {e}")
                continue

        logger.warning("未能找到编辑器元素，跳过元数据填写")
        return None
