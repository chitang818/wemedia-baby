# -*- coding: utf-8 -*-
"""
步骤7c：扩展信息 — 关联热点
文件路径: src/plugins/community/douyin/steps/step_07c_trending.py

TODO：功能待实现。
  当前为占位步骤，execute() 直接跳过，不影响正常发布流程。

流程（规划）：
  1. 滚动「扩展信息」区域中的「关联热点」模块入视口。
  2. 点击热点输入框，输入 metadata['trending_keyword'] 关键词。
  3. 从下拉结果中选择匹配的热点条目。
  4. 等待已关联热点标签出现，确认成功。

字段依赖（待实现后生效）：
  - metadata['trending_keyword'] : 可选，热点关键词，不填则跳过
  - metadata['skip_trending']    : 为 True 时整步跳过

DOM 参考（来自抖音_图文发布DOM分析报告 §8）：
  - 关联热点标题 : e364
  - 热点输入框   : e370 / e373（placeholder='点击输入热点词'）
"""
import logging
from typing import Any, Dict

from src.infrastructure.browser.automation_api import Page

from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class TrendingStep(BasePublishStep):
    """扩展信息：关联热点（占位，功能待实现）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        # 占位：功能未实现，直接跳过
        logger.info("关联热点：功能尚未实现，跳过此步骤")
        USER_LOG.info("关联热点 ✓ 跳过（功能待实现）")
        return None
