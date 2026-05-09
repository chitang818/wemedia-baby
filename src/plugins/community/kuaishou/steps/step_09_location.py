# -*- coding: utf-8 -*-
"""
步骤9：位置添加
文件路径: src/plugins/community/kuaishou/steps/step_09_location.py

流程：
  位置信息（POI）添加。可根据 metadata 的 poi_info 填写。当前为占位，待根据页面 DOM 补充。
"""
import logging
from typing import Dict, Any

from playwright.async_api import Page

from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class LocationStep(BasePublishStep):
    """位置添加。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("步骤9: 位置添加（当前占位）")
        # TODO: 若 metadata.get("poi_info") 有值，可在此步填写位置
        USER_LOG.info("%s ✓ 完成", self._step_prefix(metadata, "位置添加"))
        return None
