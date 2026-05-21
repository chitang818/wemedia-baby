# -*- coding: utf-8 -*-
"""
步骤2：进入发布页
文件路径: src/plugins/pro/xiaohongshu/steps/step_02_entry.py

流程：
  1. 优先尝试直接导航到发布页 URL（/publish/publish）
  2. 若直接导航失败或未检测到发布页特征，回退到首页查找「发布笔记」按钮点击
  3. 检测发布页面是否加载成功（上传区域出现）

字段依赖：
  - metadata['speed_rate']: 等待延迟倍率
  - metadata['anti_risk_config']: 风控相关配置
"""
import logging
from typing import Dict, Any

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"


class EnterPublishEntryStep(BasePublishStep):
    """进入小红书发布页面。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("===== 进入小红书发布页 =====")

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        config = metadata.get("anti_risk_config") or {}

        # 策略1：直接导航到发布页 URL
        try:
            logger.info(f"尝试直接导航到发布页: {PUBLISH_URL}")
            await page.goto(PUBLISH_URL, timeout=30000, wait_until="domcontentloaded")
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, int(3000 * speed_rate), metadata, config)
            except Exception:
                await page.wait_for_timeout(int(3000 * speed_rate))

            current_url = page.url
            logger.info(f"导航后 URL: {current_url}")

            # 检查是否被重定向到登录页
            if "/login" in current_url:
                return PublishResult(
                    success=False,
                    error_message="Cookie失效，进入发布页时被重定向到登录页",
                )

            # 检测发布页特征元素
            if await self._check_publish_page_loaded(page):
                logger.info("已确认进入发布页面")
                return None
        except Exception as e:
            logger.warning(f"直接导航发布页异常: {e}")

        # 策略2：从首页查找对应类型的发布入口卡片（来自 X-Ray 实际 DOM）
        file_type = (metadata.get("file_type") or "video").lower()
        logger.info(f"直接导航失败，尝试从首页查找发布入口 (file_type={file_type})…")

        # 优先点击具体类型卡片（X-Ray 确认: div.publish-card）
        type_selectors = (
            Selectors.HOME.get("PUBLISH_IMAGE_CARD", [])
            if file_type == "image"
            else Selectors.HOME.get("PUBLISH_VIDEO_CARD", [])
        )
        # 兜底：通用「发布笔记」按钮
        entry_selectors = type_selectors + Selectors.HOME["PUBLISH_BTN"]

        for selector in entry_selectors:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click
                        await human_click(page, btn, metadata, config)
                    except Exception:
                        await btn.click()

                    logger.info(f"已点击发布入口: {selector}")
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay
                        await random_delay(page, int(3000 * speed_rate), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(int(3000 * speed_rate))

                    if await self._check_publish_page_loaded(page):
                        logger.info("已确认进入发布页面")
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
                    try:
                        from src.infrastructure.anti_risk.delays import random_delay
                        await random_delay(page, int(3000 * speed_rate), metadata, config)
                    except Exception:
                        await page.wait_for_timeout(int(3000 * speed_rate))

                    if await self._check_publish_page_loaded(page):
                        logger.info("已确认进入发布页面")
                        return None
            except Exception:
                continue

        current_url = page.url
        return PublishResult(
            success=False,
            error_message=f"未能确认进入发布页：未检测到发布页特征元素（url={current_url}）",
        )

    async def _check_publish_page_loaded(self, page: Page) -> bool:
        """检测发布页面是否已加载（有上传区域或 file input）。"""
        for selector in Selectors.HOME["PUBLISH_PAGE_MARKER"]:
            try:
                if await page.locator(selector).count() > 0:
                    return True
            except Exception:
                continue

        # 兜底：检查 URL 是否包含 publish 关键字
        try:
            if "publish" in page.url:
                return True
        except Exception:
            pass

        return False
