# -*- coding: utf-8 -*-
"""
步骤2：进入发布页
文件路径: src/plugins/pro/xiaohongshu/steps/step_02_entry.py

流程：
  1. 优先尝试直接导航到发布页 URL（/publish/publish，不含 openFilePicker）
  2. 若直接导航失败或未检测到发布页特征，回退到首页查找「发布笔记」按钮点击
  3. 进入成功后净化 URL（去掉 openFilePicker）并关闭系统自动文件对话框
  4. 检测发布页面是否加载成功（上传区域出现）

字段依赖：
  - metadata['speed_rate']: 等待延迟倍率
  - metadata['anti_risk_config']: 风控相关配置
"""
import logging
from typing import Dict, Any

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from ..browser_environment_diagnostics import attach_xhs_environment_snapshot
from .publish_page_guard import (
    PUBLISH_TARGET_URLS,
    clean_publish_url,
    ensure_publish_page_without_file_picker,
)

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

HOME_URL = "https://creator.xiaohongshu.com/new/home"


async def _safe_attach_environment_snapshot(
    page: Page,
    metadata: Dict[str, Any],
    stage: str,
) -> None:
    try:
        await attach_xhs_environment_snapshot(metadata, page, stage=stage)
    except Exception as exc:
        logger.debug("XHS environment snapshot failed at %s: %s", stage, exc)


class EnterPublishEntryStep(BasePublishStep):
    """进入小红书发布页面。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("===== 进入小红书发布页 =====")

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        config = metadata.get("anti_risk_config") or {}
        file_type = (metadata.get("file_type") or "video").lower()
        pause_cb = lambda: self._await_pause(metadata)

        strict_real_browser = bool(metadata.get("xhs_strict_real_browser", True))
        if strict_real_browser:
            logger.info("小红书 strict_real_browser：优先从创作者首页自然进入发布页")
            if await self._enter_from_home_card(page, file_type, metadata, config, speed_rate):
                metadata["xhs_entry_strategy"] = "home_card"
                guard_err = await self._finalize_publish_entry(page, file_type, metadata)
                if guard_err is not None:
                    return guard_err
                await _safe_attach_environment_snapshot(page, metadata, "publish_page_loaded_home_card")
                return None
            logger.warning("小红书首页入口未成功，降级使用发布页直达兜底")
            metadata["xhs_entry_strategy"] = "direct_url_fallback"

        # 策略1：直接进入对应类型发布页。首页卡片点击后的真实 URL 会带
        # openFilePicker=true 并弹出系统文件选择器；自动化入口这里去掉该参数，
        # 让后续上传步骤统一接管 input[type=file]。
        try:
            target_url = clean_publish_url(file_type)
            logger.info("尝试直接导航到小红书%s发布页: %s", file_type, target_url)
            await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
            await PluginWaitHelper.wait_for_condition(
                page,
                lambda: self._check_publish_page_loaded(page, file_type),
                timeout_ms=int(3000 * speed_rate),
                poll_interval_ms=300,
                pause_callback=pause_cb,
            )

            current_url = page.url
            logger.info(f"导航后 URL: {current_url}")

            if "/login" in current_url:
                return PublishResult(
                    success=False,
                    error_message="Cookie失效，进入发布页时被重定向到登录页",
                )

            if await self._check_publish_page_loaded(page, file_type):
                guard_err = await self._finalize_publish_entry(page, file_type, metadata)
                if guard_err is not None:
                    return guard_err
                logger.info("已确认进入小红书%s发布页面", file_type)
                return None
        except Exception as e:
            logger.warning(f"直接导航发布页异常: {e}")

        # 策略2：从首页查找对应类型的发布入口卡片（来自 X-Ray 实际 DOM）
        if await self._enter_from_home_card(page, file_type, metadata, config, speed_rate):
            guard_err = await self._finalize_publish_entry(page, file_type, metadata)
            if guard_err is not None:
                return guard_err
            return None

        logger.info(f"直接导航失败，尝试从首页查找发布入口 (file_type={file_type})…")

        type_selectors = (
            Selectors.HOME.get("PUBLISH_IMAGE_CARD", [])
            if file_type == "image"
            else Selectors.HOME.get("PUBLISH_VIDEO_CARD", [])
        )
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
                    await self._wait_publish_navigation(page, file_type, metadata, speed_rate)
                    if await self._check_publish_page_loaded(page, file_type):
                        guard_err = await self._finalize_publish_entry(page, file_type, metadata)
                        if guard_err is not None:
                            return guard_err
                        logger.info("已确认进入发布页面")
                        return None
                    break
            except Exception:
                continue

        for selector in Selectors.HOME["UPLOAD_ENTRY"]:
            try:
                link = page.locator(selector).first
                if await link.count() > 0:
                    await link.click()
                    await self._wait_publish_navigation(page, file_type, metadata, speed_rate)
                    if await self._check_publish_page_loaded(page, file_type):
                        guard_err = await self._finalize_publish_entry(page, file_type, metadata)
                        if guard_err is not None:
                            return guard_err
                        logger.info("已确认进入发布页面")
                        return None
            except Exception:
                continue

        current_url = page.url
        return PublishResult(
            success=False,
            error_message=f"未能确认进入发布页：未检测到发布页特征元素（url={current_url}）",
        )

    async def _finalize_publish_entry(
        self, page: Page, file_type: str, metadata: Dict[str, Any]
    ) -> StepOutcome:
        """净化 openFilePicker URL 并再次确认发布页类型就绪。"""
        guard_err = await ensure_publish_page_without_file_picker(
            page,
            file_type,
            metadata,
            pause_callback=lambda: self._await_pause(metadata),
        )
        if guard_err is not None:
            return guard_err
        if not await self._check_publish_page_loaded(page, file_type):
            return PublishResult(
                success=False,
                error_message="页面自动弹出文件选择器，未能切换到自动化上传模式（发布页未就绪）",
            )
        return None

    async def _publish_url_ready(self, page: Page) -> bool:
        return "publish" in (page.url or "")


    async def _wait_publish_navigation(
        self,
        page: Page,
        file_type: str,
        metadata: Dict[str, Any],
        speed_rate: float,
    ) -> None:
        """点击首页入口后等待跳转到发布页（短超时）。"""
        await PluginWaitHelper.wait_for_condition(
            page,
            lambda: self._publish_url_ready(page),
            timeout_ms=int(8000 * speed_rate),
            poll_interval_ms=300,
            pause_callback=lambda: self._await_pause(metadata),
        )
        await PluginWaitHelper.wait_for_condition(
            page,
            lambda: self._check_publish_page_loaded(page, file_type),
            timeout_ms=int(5000 * speed_rate),
            poll_interval_ms=300,
            pause_callback=lambda: self._await_pause(metadata),
        )

    async def _enter_from_home_card(
        self,
        page: Page,
        file_type: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        speed_rate: float,
    ) -> bool:
        try:
            if "/new/home" not in page.url:
                logger.info("导航到小红书创作者首页，准备点击发布入口卡片: %s", HOME_URL)
                await page.goto(HOME_URL, timeout=30000, wait_until="domcontentloaded")
                await self._delay(page, metadata, config, 2000, speed_rate)
        except Exception as e:
            logger.warning("导航小红书首页失败: %s", e)

        target_name = "图文" if file_type == "image" else "视频"
        logger.info("尝试从首页点击发布%s笔记卡片", target_name)
        clicked = await self._click_first_visible(
            page, self._entry_card_selectors(file_type), metadata, config
        )
        if not clicked:
            logger.info("未找到发布%s笔记卡片", target_name)
            return False

        await self._wait_publish_navigation(page, file_type, metadata, speed_rate)
        if await self._check_publish_page_loaded(page, file_type):
            logger.info("已通过首页发布%s笔记卡片进入发布页", target_name)
            return True

        logger.info("点击发布%s笔记卡片后未确认发布页: url=%s", target_name, page.url)
        return False

    def _entry_card_selectors(self, file_type: str) -> list[str]:
        return (
            Selectors.HOME.get("PUBLISH_IMAGE_CARD", [])
            if file_type == "image"
            else Selectors.HOME.get("PUBLISH_VIDEO_CARD", [])
        )

    async def _click_first_visible(
        self,
        page: Page,
        selectors: list[str],
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        for selector in selectors:
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click
                        await human_click(page, loc, metadata, config)
                    except Exception:
                        await loc.click()
                    logger.info("已点击小红书发布入口: %s", selector)
                    return True
            except Exception as e:
                logger.debug("小红书发布入口选择器不可用: %s (%s)", selector, e)
        return False

    async def _delay(
        self,
        page: Page,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        base_ms: int,
        speed_rate: float,
    ) -> None:
        try:
            from src.infrastructure.anti_risk.delays import random_delay
            await random_delay(page, int(base_ms * speed_rate), metadata, config)
        except Exception:
            await page.wait_for_timeout(int(base_ms * speed_rate))

    async def _check_publish_page_loaded(self, page: Page, file_type: str = "video") -> bool:
        """检测发布页面是否已加载，并确认进入了对应的图文/视频发布态。"""
        for selector in Selectors.HOME["PUBLISH_PAGE_MARKER"]:
            try:
                if await page.locator(selector).count() > 0:
                    return await self._check_publish_type_ready(page, file_type)
            except Exception:
                continue

        try:
            if "publish" in page.url:
                return await self._check_publish_type_ready(page, file_type)
        except Exception:
            pass

        return False

    async def _check_publish_type_ready(self, page: Page, file_type: str) -> bool:
        """根据真实 DOM 确认当前发布页类型。

        2026-05 实测：
        - 图文卡片跳转 target=image，active tab 为「上传图文」，
          input accept=".jpg,.jpeg,.png,.webp"，multiple=true。
        - 视频卡片跳转 target=video，active tab 为「上传视频」，
          input accept 含 .mp4/.mov，multiple=false。
        """
        expected = "image" if file_type == "image" else "video"
        url_matches = False
        try:
            url = page.url
            if expected == "image" and "target=image" in url:
                url_matches = True
            if expected == "video" and "target=video" in url:
                url_matches = True
        except Exception:
            pass

        try:
            active_text = await page.locator(".creator-tab.active").first.inner_text(timeout=1500)
            active_text = (active_text or "").strip()
            if expected == "image" and "上传图文" in active_text:
                return True
            if expected == "video" and "上传视频" in active_text:
                return True
        except Exception:
            pass

        try:
            inputs = page.locator("input[type='file']")
            count = await inputs.count()
            for i in range(count):
                accept = (await inputs.nth(i).get_attribute("accept") or "").lower()
                if expected == "image" and any(k in accept for k in (".jpg", ".jpeg", ".png", ".webp", "image")):
                    return True
                if expected == "video" and any(k in accept for k in (".mp4", ".mov", "video")):
                    return True
        except Exception:
            pass

        try:
            body_text = await page.locator("body").inner_text(timeout=1500)
            if expected == "image" and all(k in body_text for k in ("上传图片", "图片格式")):
                return True
            if expected == "video" and all(k in body_text for k in ("上传视频", "视频格式")):
                return True
            if url_matches:
                logger.debug("小红书发布页 URL 类型匹配，但 DOM 类型标记尚未出现: expected=%s", expected)
        except Exception:
            pass

        logger.warning("小红书发布页已加载但类型未匹配: expected=%s url=%s", expected, getattr(page, "url", ""))
        return False
