# -*- coding: utf-8 -*-
"""
步骤1：导航首页
文件路径: src/plugins/pro/weibo/steps/step_01_home.py

流程：
  1. 导航至微博首页：https://weibo.com
  2. 等待 DOM 加载完成及短暂延迟
  3. 执行风控拦截检查（RISK_MODAL）
  4. 执行登录态探测（LOGIN_EXPIRED_INDICATORS）
  5. 验证是否处于微博域内（weibo.com）

字段依赖：
  - metadata['speed_rate']: 等待延迟倍率（默认 1.0）
"""
import logging
from typing import Dict, Any, Optional

from src.infrastructure.browser.automation_api import Page

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class NavigateHomeStep(BasePublishStep):
    """导航到微博首页，并做基础登录/风控检查。"""

    WEIBO_HOME_URL = "https://weibo.com"

    def __init__(self, home_url: Optional[str] = None):
        self.home_url = home_url or self.WEIBO_HOME_URL

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info(f"导航至微博首页: {self.home_url}")

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_after_nav = int(3000 * speed_rate)

        try:
            await page.goto(self.home_url, timeout=30000, wait_until="domcontentloaded")
            await PluginWaitHelper.wait_for_load_state_or_timeout(
                page,
                state="networkidle",
                timeout_ms=wait_after_nav,
                fallback_ms=300,
            )

            current_url = page.url
            logger.info(f"当前页面 URL: {current_url}")

            # 1. 检测风控拦截
            for selector in Selectors.SECURITY["RISK_MODAL"]:
                try:
                    if await page.locator(selector).count() > 0:
                        text = ""
                        try:
                            text = await page.locator(selector).inner_text()
                        except Exception:
                            pass
                        logger.error(f"检测到风控或拦截提示: {text}")
                        return PublishResult(
                            success=False,
                            error_message="检测到账号风控拦截，请手动验证此账号",
                        )
                except Exception:
                    continue

            # 2. 登录态探测
            try:
                html = await page.content()
                login_keywords = ["登录已过期", "请先登录", "请重新登录", "未登录"]
                for kw in login_keywords:
                    if kw in html:
                        logger.error(f"检测到登录组件文案: {kw}")
                        return PublishResult(
                            success=False,
                            error_message="Cookie失效，未登录或登录已过期",
                        )
            except Exception:
                pass

            # 3. URL 跳转到登录页检测
            if "passport.weibo" in current_url or "/sso/signin" in current_url:
                logger.error(f"页面被重定向到登录页: {current_url}")
                return PublishResult(
                    success=False,
                    error_message="Cookie失效，页面被重定向到登录页",
                )

            # 4. 确认在微博域内
            if "weibo.com" in current_url:
                logger.info("已确认处于微博域内")
                return None

            return PublishResult(
                success=False,
                error_message=f"无法确认已进入微博，当前 URL: {current_url}",
            )
        except Exception as e:
            logger.error(f"导航首页过程发生异常: {e}")
            return PublishResult(success=False, error_message=f"首页导航失败: {e}")
