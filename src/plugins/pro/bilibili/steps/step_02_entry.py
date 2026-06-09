# -*- coding: utf-8 -*-
"""
步骤2：进入投稿页
文件路径: src/plugins/pro/bilibili/steps/step_02_entry.py

流程：
  1. 优先尝试直接导航到投稿页 URL（/platform/upload/video/frame）
  2. 若直接导航失败或未检测到投稿页特征，回退到首页查找「投稿」按钮点击
  3. 检测投稿页面是否加载成功（上传区域出现）

字段依赖：
  - metadata['speed_rate']: 等待延迟倍率
  - metadata['anti_risk_config']: 风控相关配置
"""
import logging
from typing import Dict, Any

from src.infrastructure.browser.automation_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

PUBLISH_URL = "https://member.bilibili.com/platform/upload/video/frame"


class EnterPublishEntryStep(BasePublishStep):
    """进入B站视频投稿页面。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("===== 进入B站投稿页 =====")

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        config = metadata.get("anti_risk_config") or {}

        # 策略1：直接导航到投稿页 URL
        try:
            logger.info(f"尝试直接导航到投稿页: {PUBLISH_URL}")
            await page.goto(PUBLISH_URL, timeout=30000, wait_until="domcontentloaded")
            await PluginWaitHelper.wait_for_condition(
                page,
                lambda: self._check_publish_page_loaded(page),
                timeout_ms=int(3000 * speed_rate),
                poll_interval_ms=300,
                pause_callback=lambda: self._await_pause(metadata),
            )

            current_url = page.url
            logger.info(f"导航后 URL: {current_url}")

            if "passport.bilibili.com" in current_url or "/login" in current_url:
                return PublishResult(
                    success=False,
                    error_message="Cookie失效，进入投稿页时被重定向到登录页",
                )

            if await self._check_publish_page_loaded(page):
                logger.info("已确认进入投稿页面")
                return None
        except Exception as e:
            logger.warning(f"直接导航投稿页异常: {e}")

        # 策略2：从首页查找「投稿」按钮点击
        logger.info("直接导航失败，尝试从首页查找投稿入口…")
        for selector in Selectors.HOME["PUBLISH_BTN"]:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click
                        await human_click(page, btn, metadata, config)
                    except Exception:
                        await btn.click()

                    logger.info(f"已点击投稿入口: {selector}")
                    await PluginWaitHelper.wait_for_condition(

                        page,

                        lambda: self._check_publish_page_loaded(page),

                        timeout_ms=int(3000 * speed_rate),

                        poll_interval_ms=300,

                        pause_callback=lambda: self._await_pause(metadata),

                    )

                    if await self._check_publish_page_loaded(page):
                        logger.info("已确认进入投稿页面")
                        return None
                    break
            except Exception:
                continue

        # 策略3：通过链接点击进入
        for selector in Selectors.HOME["UPLOAD_ENTRY"]:
            try:
                link = page.locator(selector).first
                if await link.count() > 0:
                    await link.click()
                    await PluginWaitHelper.wait_for_condition(

                        page,

                        lambda: self._check_publish_page_loaded(page),

                        timeout_ms=int(3000 * speed_rate),

                        poll_interval_ms=300,

                        pause_callback=lambda: self._await_pause(metadata),

                    )

                    if await self._check_publish_page_loaded(page):
                        logger.info("已确认进入投稿页面")
                        return None
            except Exception:
                continue

        current_url = page.url
        return PublishResult(
            success=False,
            error_message=f"未能确认进入投稿页：未检测到投稿页特征元素（url={current_url}）",
        )

    async def _check_publish_page_loaded(self, page: Page) -> bool:
        """检测投稿页面是否已加载（有上传区域或 file input）。"""
        for selector in Selectors.HOME["PUBLISH_PAGE_MARKER"]:
            try:
                if await page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        try:
            if "upload" in page.url and "member.bilibili.com" in page.url:
                return True
        except Exception:
            pass

        return False
