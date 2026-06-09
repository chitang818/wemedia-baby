# -*- coding: utf-8 -*-
"""
步骤7：关联热点
文件路径: src/plugins/community/kuaishou/steps/step_07_manage_hotspot.py

流程：
  关联热点相关选项。当前为占位，待根据页面 DOM 补充。
"""
import logging
from typing import Dict, Any

from src.infrastructure.browser.automation_api import Page

from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class ManageHotspotStep(BasePublishStep):
    """关联热点。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("步骤7: 关联热点（当前占位）")
        USER_LOG.info("%s ✓ 完成", self._step_prefix(metadata, "关联热点"))
        return None
