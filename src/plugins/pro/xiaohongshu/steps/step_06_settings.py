# -*- coding: utf-8 -*-
"""
步骤6：发布设置
文件路径: src/plugins/pro/xiaohongshu/steps/step_06_settings.py

流程（依次执行）：
  1. 页面滚动到底部暴露设置区
  2. 可见性设置：根据 privacy 字段选择"公开"或"私密"
  3. 发布时间：
     - 若 schedule_time 为空，则默认立即发布
     - 若有定时时间，设置定时发布

字段依赖：
  - metadata['privacy_settings']: 包含 privacy ("public"/"private")
  - metadata['schedule_time'] / metadata['scheduled_publish_time']: 定时发布时间
"""
import json
import logging
from typing import Dict, Any, Optional

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class PublishSettingsStep(BasePublishStep):
    """发布设置（权限、可见性、定时发布等）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        logger.info("===== 发布设置 =====")

        # 先滚动到底部确保设置区可见
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(300)
        except Exception as e:
            logger.debug(f"滚动到底部异常: {e}")

        # ── 1. 可见性设置 ──
        privacy_settings = metadata.get("privacy_settings", {})
        if isinstance(privacy_settings, str):
            try:
                privacy_settings = json.loads(privacy_settings)
            except Exception:
                privacy_settings = {}

        privacy = privacy_settings.get("privacy", "public")

        try:
            privacy_selectors = Selectors.SETTINGS.get("PRIVACY_PUBLIC", [])
            if privacy == "private":
                privacy_selectors = Selectors.SETTINGS.get("PRIVACY_PRIVATE", [])

            for sel in privacy_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        try:
                            await loc.scroll_into_view_if_needed()
                        except Exception:
                            pass
                        try:
                            from src.infrastructure.anti_risk.human_like import human_click
                            await human_click(page, loc, metadata, config)
                        except Exception:
                            await loc.click()

                        try:
                            from src.infrastructure.anti_risk.delays import random_delay
                            await random_delay(page, wait_ms(500), metadata, config)
                        except Exception:
                            await page.wait_for_timeout(wait_ms(500))

                        USER_LOG.info(f"[步骤6 发布设置] ▶ 已设置可见性: {privacy}")
                        logger.info(f"已设置可见性: {privacy}")
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"设置可见性异常: {e}")

        # ── 2. 定时发布 ──
        schedule_time = metadata.get("scheduled_publish_time") or metadata.get("schedule_time")

        try:
            if schedule_time:
                from src.utils.date_utils import format_schedule_time_st_str
                st_str = format_schedule_time_st_str(schedule_time) or ""

                logger.info(f"检测到定时发布时间: {st_str}")
                USER_LOG.info(f"[步骤6 发布设置] ▶ 尝试设置定时: {st_str}")

                # 勾选「定时发布」
                schedule_selectors = Selectors.SETTINGS.get("PUBLISH_SCHEDULE", [])
                clicked = False
                for sel in schedule_selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            try:
                                await loc.scroll_into_view_if_needed()
                            except Exception:
                                pass
                            try:
                                from src.infrastructure.anti_risk.human_like import human_click
                                await human_click(page, loc, metadata, config)
                            except Exception:
                                await loc.click()
                            clicked = True

                            try:
                                from src.infrastructure.anti_risk.delays import random_delay
                                await random_delay(page, wait_ms(500), metadata, config)
                            except Exception:
                                await page.wait_for_timeout(wait_ms(500))
                            break
                    except Exception:
                        continue

                if not clicked:
                    logger.warning("未找到定时发布选项")
                    USER_LOG.warning("[步骤6 发布设置] ✗ 未找到定时发布选项")
                    return PublishResult(
                        success=False,
                        error_message="未找到定时发布选项，定时发布设置失败",
                        failed_step="PublishSettingsStep",
                    )

                # 设置时间
                time_input_selectors = Selectors.SETTINGS.get("SCHEDULE_INPUT", [])
                time_set = False
                for sel in time_input_selectors:
                    try:
                        inp = page.locator(sel).first
                        if await inp.count() > 0 and await inp.is_visible():
                            await inp.click()
                            await page.keyboard.press("Control+A")
                            await page.keyboard.press("Backspace")
                            await inp.type(st_str, delay=max(10, int(30 * speed_rate)))
                            time_set = True
                            logger.info(f"已设置定时时间: {st_str}")
                            USER_LOG.info(f"[步骤6 发布设置] ▶ 已设置定时: {st_str}")
                            break
                    except Exception:
                        continue

                if not time_set:
                    logger.warning("未找到时间输入框")
                    USER_LOG.warning("[步骤6 发布设置] ✗ 未找到时间输入框")
                    return PublishResult(
                        success=False,
                        error_message="定时发布时间设置失败，未找到时间输入框",
                        failed_step="PublishSettingsStep",
                    )
            else:
                logger.info("未设置定时，将立即发布")
        except Exception as e:
            logger.warning(f"定时/立即发布设置异常: {e}")
            if schedule_time:
                return PublishResult(
                    success=False,
                    error_message=f"定时发布设置异常: {e}",
                    failed_step="PublishSettingsStep",
                )

        return None
