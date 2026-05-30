# -*- coding: utf-8 -*-
"""
步骤1：导航首页
文件路径: src/plugins/pro/xiaohongshu/steps/step_01_home.py

流程：
  1. 导航至小红书创作者服务平台首页
  2. 等待 DOM 加载完成及短暂延迟
  3. 执行风控拦截检查（RISK_MODAL）
  4. 执行登录态探测（LOGIN_EXPIRED_INDICATORS）
  5. 验证是否处于创作者平台域内（creator.xiaohongshu.com）
  6. 模拟首页自然浏览行为（随机滚动/鼠标移动/停顿），降低自动化特征

字段依赖：
  - metadata['speed_rate']: 等待延迟倍率（默认 1.0）
  - metadata['anti_risk_config']: 风控配置（影响浏览行为参数）
"""
import logging
import random
from typing import Dict, Any, Optional

from playwright.async_api import Page

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class NavigateHomeStep(BasePublishStep):
    """导航到小红书创作者服务平台首页，并做基础登录/风控检查。"""

    # ✅ 已确认：登录后首页 URL（来自 X-Ray 分析报告）
    CREATOR_HOME_URL = "https://creator.xiaohongshu.com/new/home"

    def __init__(self, home_url: Optional[str] = None):
        self.home_url = home_url or self.CREATOR_HOME_URL

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info(f"导航至小红书创作者服务平台: {self.home_url}")

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_after_nav = int(3000 * speed_rate)
        config = metadata.get("anti_risk_config") or {}

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
                login_keywords = ["登录已过期", "请重新登录", "扫码登录", "短信登录"]
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
            if "/login" in current_url:
                logger.error(f"页面被重定向到登录页: {current_url}")
                return PublishResult(
                    success=False,
                    error_message="Cookie失效，页面被重定向到登录页",
                )

            # 4. 确认在创作者平台域内
            if "creator.xiaohongshu.com" in current_url or "xiaohongshu.com" in current_url:
                logger.info("已确认处于小红书创作者平台域内")
                # 5. 模拟首页自然浏览（降低「进页面立即开始操作」的风控信号）
                await self._simulate_home_browsing(page, metadata, config, speed_rate)
                return None

            return PublishResult(
                success=False,
                error_message=f"无法确认已进入小红书创作者服务平台，当前 URL: {current_url}",
            )
        except Exception as e:
            logger.error(f"导航首页过程发生异常: {e}")
            return PublishResult(success=False, error_message=f"首页导航失败: {e}")

    async def _simulate_home_browsing(
        self,
        page: Page,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        speed_rate: float,
    ) -> None:
        """模拟真人在首页的自然浏览行为（进入发布页前的预热），降低自动化特征。

        随机执行 2-4 次操作（向下滚动/向上滚动/鼠标游荡/停顿思考），
        总停留时间约 5-20 秒，模拟用户进来先看一眼再去发布的自然行为。
        """
        try:
            from src.infrastructure.anti_risk.human_like import random_mouse_wander
            from src.infrastructure.anti_risk.delays import random_delay
        except ImportError:
            # 依赖不可用时静默跳过，不影响主流程
            logger.debug("human_like 模块不可用，跳过首页浏览预热")
            return

        actions_count = random.randint(2, 4)
        logger.info("步骤1 首页预热：模拟自然浏览 %d 次随机操作", actions_count)
        USER_LOG.info("[步骤1 首页] ▷ 模拟首页浏览预热中…")

        for i in range(actions_count):
            await self._await_pause(metadata)
            choice = random.choices(
                ["scroll_down", "scroll_up", "mouse", "pause"],
                weights=[35, 20, 25, 20],
                k=1,
            )[0]

            try:
                if choice == "scroll_down":
                    # 向下滚动 150-400px，模拟浏览内容流
                    scroll_px = random.uniform(150, 400)
                    await page.mouse.wheel(0, scroll_px)
                    logger.debug("首页预热：物理向下滚动 %.0fpx", scroll_px)
                elif choice == "scroll_up":
                    # 向上回滚 80-200px，模拟用户重新看刚才经过的内容
                    scroll_px = random.uniform(80, 200)
                    await page.mouse.wheel(0, -scroll_px)
                    logger.debug("首页预热：物理向上滚动 %.0fpx", scroll_px)
                elif choice == "mouse":
                    # 随机鼠标游荡（贝塞尔曲线移动）
                    await random_mouse_wander(page, metadata, config)
                    logger.debug("首页预热：随机鼠标游荡")
                # "pause"：仅等待，不做任何操作（模拟用户在思考/阅读）
                else:
                    logger.debug("首页预热：停顿思考")

            except Exception as e:
                logger.debug("首页预热操作 %d 异常（已忽略）: %s", i + 1, e)

            # 每次操作后随机等待 1.5-5 秒（受 speed_rate 影响）
            pause_ms = int(random.uniform(1500, 5000) * max(0.5, speed_rate))
            await random_delay(page, pause_ms, metadata, config)

        logger.info("步骤1 首页预热完成，准备进入发布流程")
