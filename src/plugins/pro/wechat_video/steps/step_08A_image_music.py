# -*- coding: utf-8 -*-
"""
步骤8A：图文选择并设置背景音乐（占位）
文件路径：src/plugins/pro/wechat_video/steps/step_08A_image_music.py

说明：
  - 当前阶段只把该步骤加入图文发布步骤链中，用于占位与进度展示。
  - 具体的音乐选择与设置逻辑后续补充。
"""
import logging
from typing import Dict, Any

from src.infrastructure.browser.automation_api import Page

from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class ImageTextMusicStep(BasePublishStep):
    """图文选择并设置背景音乐（占位）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("[视频号] 图文步骤：选择并设置背景音乐（占位，暂不操作页面）")
        USER_LOG.info("图文：选择并设置背景音乐（占位）")
        return None

