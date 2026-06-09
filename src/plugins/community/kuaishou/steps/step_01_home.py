# -*- coding: utf-8 -*-
"""
步骤1：导航首页
文件路径: src/plugins/community/kuaishou/steps/step_01_home.py

流程：
  1. 导航至快手创作者中心首页
  2. 等待 DOM 加载及短暂延迟
  3. 执行风控/登录态检查
  4. 验证是否处于 cp.kuaishou.com 域内
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
    """导航到快手创作者中心首页，并做基础登录/风控检查。"""

    def __init__(self, home_url: Optional[str] = None):
        self.home_url = home_url or "https://cp.kuaishou.com/profile"

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info(f"导航至快手创作者首页: {self.home_url}")
        _p = self._step_prefix(metadata, "进入创作者首页")
        USER_LOG.info(f"{_p} ▶ 地址={self.home_url}")

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

            redirect_keywords = Selectors.REDIRECT.get("LOGIN_URLS", ["login", "signin", "passport"])
            if any(kw in current_url.lower() for kw in redirect_keywords):
                return PublishResult(success=False, error_message="Cookie 已过期，被重定向到登录页")

            for selector in Selectors.SECURITY.get("RISK_MODAL", []):
                if await page.locator(selector).count() > 0:
                    try:
                        text = await page.locator(selector).inner_text()
                        logger.error(f"检测到风控或拦截提示: {text}")
                    except Exception:
                        pass
                    return PublishResult(
                        success=False,
                        error_message="检测到账号风控拦截或被强制要求重新登录，请关闭自动化后手动验证此账号",
                    )

            try:
                html = await page.content()
                if ("扫码登录" in html or "验证码" in html) and (
                    "passport" in current_url or "login" in current_url
                ):
                    return PublishResult(success=False, error_message="Cookie 失效，未登录或登录已过期")
            except Exception:
                pass

            if "cp.kuaishou.com" in current_url:
                logger.info("已确认处于快手创作者平台域内")
                USER_LOG.info(f"{_p} ✓ 已打开 ({current_url})")
                return None

            return PublishResult(
                success=False,
                error_message=f"无法确认已进入快手创作者中心，当前 URL: {current_url}",
            )
        except Exception as e:
            logger.error(f"导航首页过程发生异常: {e}")
            return PublishResult(success=False, error_message=f"首页导航失败: {e}")
