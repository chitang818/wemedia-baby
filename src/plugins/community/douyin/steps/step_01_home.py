# -*- coding: utf-8 -*-
"""
步骤1：导航首页
文件路径: src/plugins/community/douyin/steps/step_01_home.py

流程：
  1. 导航至抖音创作者中心首页：https://creator.douyin.com/creator-micro/home
  2. 等待 DOM 加载完成及短暂延迟
  3. 执行风控拦截检查（RISK_MODAL）
  4. 执行登录态弹窗文本探测（扫码登录、短信登录等）
  5. 验证是否处于创作者平台域内（creator.douyin.com）

字段依赖：
  - metadata['speed_rate']: 等待延迟倍率（默认 1.0）
"""
import logging
from typing import Dict, Any, Optional

from playwright.async_api import Page

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class NavigateHomeStep(BasePublishStep):
    """导航到抖音创作者中心首页，并做基础登录/风控检查。"""

    def __init__(self, home_url: Optional[str] = None):
        self.home_url = home_url or "https://creator.douyin.com/creator-micro/home"

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info(f"导航至抖音创作者首页: {self.home_url}")
        USER_LOG.info(f"[步骤1/9 导航首页] ▶ 地址={self.home_url}")

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
            USER_LOG.info(f"[步骤1/9 导航首页] ✓ 已打开 ({current_url})")

            # 1. 检测风控拦截和登录弹窗
            for selector in Selectors.SECURITY["RISK_MODAL"]:
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

            # 2. 简单登录文案探测（有时 URL 不含 login 但弹出登录层）
            try:
                html = await page.content()
                for kw in ["扫码登录", "短信登录", "密码登录", "验证码登录"]:
                    if kw in html:
                        logger.error(f"检测到登录组件文案: {kw}")
                        return PublishResult(success=False, error_message="Cookie失效，未登录或登录已过期")
            except Exception as e:
                logger.debug("inner_text/content extraction failed: %s", e)

            if "creator.douyin.com" in current_url:
                logger.info("已确认处于抖音创作者平台域内")
                return None

            return PublishResult(
                success=False,
                error_message=f"无法确认已进入抖音创作者中心首页，当前 URL: {current_url}",
            )
        except Exception as e:
            logger.error(f"导航首页过程发生异常: {e}")
            return PublishResult(success=False, error_message=f"首页导航失败: {e}")
