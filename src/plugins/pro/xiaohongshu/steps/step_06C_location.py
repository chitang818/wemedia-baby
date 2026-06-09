# -*- coding: utf-8 -*-
"""
步骤6C：添加地点
文件路径: src/plugins/pro/xiaohongshu/steps/step_06C_location.py

流程：
  根据 metadata 的 poi_info / location 等在发布页添加地点（POI）。
  当前为占位步骤，待根据小红书创作者中心实际 DOM 补充选择器与逻辑。
"""
import logging
from typing import Dict, Any

from src.infrastructure.browser.automation_api import Page

from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class LocationStep(BasePublishStep):
    """添加地点（占位）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("步骤6C: 添加地点（当前占位，待补充 DOM）")
        # TODO: 若 metadata.get("poi_info") 或 location 有值，定位地点入口并选择 POI
        USER_LOG.info("[步骤6C 添加地点] ✓ 跳过（占位）")
        return None
