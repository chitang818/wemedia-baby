# -*- coding: utf-8 -*-
"""
步骤1：导航首页
文件路径: src/plugins/pro/qiehao/steps/step_01_home.py

流程：
  1. 导航至企鹅号后台首页：https://om.qq.com/
  2. 等待 DOM 加载完成及短暂延迟
  3. 执行风控拦截检查（RISK_MODAL）
  4. 执行登录态探测（LOGIN_EXPIRED_INDICATORS）
  5. 验证是否处于后台域内（om.qq.com）

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
    """导航到企鹅号后台首页，并做基础登录/风控检查。"""

    CREATOR_HOME_URL = "https://om.qq.com/"

    def __init__(self, home_url: Optional[str] = None):
        self.home_url = home_url or self.CREATOR_HOME_URL

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info(f"导航至企鹅号后台: {self.home_url}")

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
                login_keywords = ["登录已过期", "请先登录", "请重新登录", "登录失效", "会话已过期"]
                for kw in login_keywords:
                    if kw in html:
                        logger.error(f"检测到登录组件文案: {kw}")
                        return PublishResult(
                            success=False,
                            error_message="Cookie失效，未登录或登录已过期",
                        )
            except Exception:
                pass

            # 3. 登录页检测（企鹅号未登录时显示首页而非跳转，需检测是否有后台元素）
            for selector in Selectors.HOME["CREATOR_CENTER_MARKER"]:
                try:
                    if await page.locator(selector).count() > 0:
                        logger.info("已确认处于企鹅号后台管理区域")
                        return None
                except Exception:
                    continue

            # 4. 检查页面是否包含登录/注册入口（说明未登录）
            try:
                login_btns = await page.locator("a:has-text('登录'), button:has-text('登录')").count()
                register_btns = await page.locator("a:has-text('注册')").count()
                if login_btns > 0 and register_btns > 0:
                    logger.error("页面存在登录/注册按钮，账号未登录")
                    return PublishResult(
                        success=False,
                        error_message="Cookie失效，未登录",
                    )
            except Exception:
                pass

            # 5. 确认在企鹅号域内
            if "om.qq.com" in current_url:
                logger.info("已确认处于企鹅号域内")
                return None

            return PublishResult(
                success=False,
                error_message=f"无法确认已进入企鹅号后台，当前 URL: {current_url}",
            )
        except Exception as e:
            logger.error(f"导航首页过程发生异常: {e}")
            return PublishResult(success=False, error_message=f"首页导航失败: {e}")
