# -*- coding: utf-8 -*-
"""
步骤9：发布后停留/预热 (防风控策略)
文件路径: src/plugins/pro/xiaohongshu/steps/step_09_post_publish.py

功能：
发布成功后，不立即关闭浏览器窗口，而是模拟真人在发布成功页停留、滑动，
查看笔记详情或进入笔记管理页的自然行为，以降低被风控系统识别为自动化脚本的概率。
"""
import logging
import random
from typing import Dict, Any

from src.infrastructure.browser.automation_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.infrastructure.anti_risk.delays import random_delay
from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

class PostPublishBrowseStep(BasePublishStep):
    """小红书发布后驻留查看步骤"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        try:
            logger.info("===== 执行发布后停留行为 =====")
            USER_LOG.info("[步骤9 停留] ▷ 模拟真实用户发布后查看行为…")
            
            config = metadata.get("anti_risk_config") or {}
            speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
            
            actions_count = random.randint(2, 5)
            for i in range(actions_count):
                await self._await_pause(metadata)
                
                choice = random.choices(
                    ["scroll_down", "scroll_up", "mouse", "pause"],
                    weights=[30, 20, 25, 25],
                    k=1,
                )[0]
                
                try:
                    if choice == "scroll_down":
                        await page.mouse.wheel(0, random.uniform(200, 500))
                    elif choice == "scroll_up":
                        await page.mouse.wheel(0, -random.uniform(100, 300))
                    elif choice == "mouse":
                        from src.infrastructure.anti_risk.human_like import random_mouse_wander
                        await random_mouse_wander(page, metadata, config)
                except Exception as e:
                    logger.debug(f"停留操作 {i} 失败: {e}")
                
                pause_ms = int(random.uniform(3000, 8000) * speed_rate)
                await random_delay(page, pause_ms, metadata, config)
                
            logger.info("发布后停留行为执行完毕")
            USER_LOG.info("[步骤9 停留] ▶ 停留行为完成")
            
            return None
        except Exception as e:
            logger.warning(f"发布后停留行为异常(已忽略): {e}")
            return None
