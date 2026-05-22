# -*- coding: utf-8 -*-
"""
步骤6A：原创申明
文件路径: src/plugins/pro/xiaohongshu/steps/step_06A_original_declaration.py

流程：
  根据 metadata 的 privacy_settings 在发布页勾选「原创申明」等选项。
  当前为占位步骤，待根据小红书创作者中心实际 DOM 补充选择器与逻辑。
"""
import logging
from typing import Dict, Any

from playwright.async_api import Page

from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class OriginalDeclarationStep(BasePublishStep):
    """原创申明（占位）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("步骤6A: 原创申明（当前占位，待补充 DOM）")
        # TODO: 根据小红书 DOM 定位原创申明开关/弹窗，按 privacy_settings 配置操作
        USER_LOG.info("[步骤6A 原创申明] ✓ 跳过（占位）")
        return None
