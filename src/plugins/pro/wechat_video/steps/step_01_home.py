# -*- coding: utf-8 -*-
"""
步骤1：导航至创作者服务中心
文件路径: src/plugins/pro/wechat_video/steps/step_01_home.py

流程：
  1. page.goto() 导航至 https://channels.weixin.qq.com/platform
  2. 检测 URL 是否跳转到登录页（login） → 若是则报 Cookie 失效
  3. 检测风控弹窗（Selectors.SECURITY.RISK_MODAL）
  4. 等待 networkidle，确保页面加载完成
  5. 穿透 wujie-app Shadow DOM 检测「发表视频」按钮：
     - 最多轮询 10 次（每次间隔 1s）
     - 找到后写入 metadata['_publish_btn_ready'] = True，供步骤2快速点击

字段依赖：无（由 metadata 携带的平台参数支撑）
"""
import logging
from typing import Dict, Any

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class NavigateHomeStep(BasePublishStep):
    """导航至视频号创作者服务中心，检测登录态和风控。

    浏览器打开后可能不在创作者中心页面（如上次会话停留在其他页面），
    本步骤确保页面位于创作者服务中心首页，为后续点击发布入口做准备。
    """

    HOME_URL = "https://channels.weixin.qq.com/platform"

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        logger.info(f"[视频号] 步骤1：正在导航至创作者服务中心")

        # ---- 1. 导航至创作者中心 ----
        try:
            await page.goto(self.HOME_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            logger.error(f"[视频号] 导航失败: {e}")
            return PublishResult(
                success=False,
                error_message=f"导航至创作者服务中心失败: {e}",
                failed_step="NavigateHomeStep",
            )

        # ---- 2. 检测是否跳转到登录页 ----
        current_url = page.url
        if "login" in current_url:
            logger.warning("[视频号] 页面跳转到登录页，Cookie 可能已失效")
            return PublishResult(
                success=False,
                error_message="Cookie 已失效，请重新登录",
                failed_step="NavigateHomeStep",
            )

        # ---- 3. 检测风控弹窗 ----
        try:
            risk_selectors = Selectors.SECURITY.get("RISK_MODAL", [])
            for sel in risk_selectors:
                if await page.locator(sel).count() > 0:
                    logger.warning(f"[视频号] 检测到风控弹窗: {sel}")
                    return PublishResult(
                        success=False,
                        error_message="检测到账号异常/风控弹窗",
                        failed_step="NavigateHomeStep",
                    )
        except Exception:
            pass

        # ---- 4. 等待页面加载完成 ----
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            logger.debug("[视频号] networkidle 等待超时，继续执行")

        # ---- 5. 通过 JS 穿透 Shadow DOM 检测「发表视频」按钮 ----
        # 按钮在 wujie-app 的 shadowRoot 内，必须用 JS 检测
        btn_found = False
        max_attempts = 10  # 最多等 10 秒（每次间隔 1 秒）

        for attempt in range(max_attempts):
            try:
                result = await page.evaluate("""() => {
                    // 精确路径
                    const wujieApp = document.querySelector(
                        '#container-wrap > div.container-center > div > div.main-body > div.third-line > div > wujie-app'
                    );
                    if (wujieApp && wujieApp.shadowRoot) {
                        const btn = wujieApp.shadowRoot.querySelector(
                            '#app > div.finder-card.wrap > div > div.post-list-header > div.post > div > button'
                        );
                        if (btn && btn.textContent.includes('发表视频')) {
                            return 'found_exact';
                        }
                    }
                    // 降级：遍历所有 wujie-app
                    const allWujie = document.querySelectorAll('wujie-app');
                    for (const w of allWujie) {
                        if (w.shadowRoot) {
                            const buttons = w.shadowRoot.querySelectorAll('button.weui-desktop-btn_primary');
                            for (const b of buttons) {
                                if (b.textContent.includes('发表视频')) {
                                    return 'found_fallback';
                                }
                            }
                        }
                    }
                    return 'not_found';
                }""")

                if result and 'found' in result:
                    btn_found = True
                    # 将结果存入 metadata，步骤2可直接点击无需重新等待
                    metadata["_publish_btn_ready"] = True
                    logger.info(f"[视频号] Shadow DOM 内检测到「发表视频」按钮 ({result})")
                    break
                else:
                    logger.debug(f"[视频号] 第 {attempt + 1} 次检测：按钮未出现，等待 1 秒...")
                    await page.wait_for_timeout(1000)
            except Exception as e:
                logger.debug(f"[视频号] JS 检测异常: {e}")
                await page.wait_for_timeout(1000)

        if not btn_found:
            logger.error("[视频号] 未在 Shadow DOM 中找到「发表视频」按钮，终止发布")
            USER_LOG.error(
                "%s ✗ 未找到「发表视频」按钮，终止发布",
                self._step_prefix(metadata, "导航首页"),
            )
            return PublishResult(
                success=False,
                error_message="未在 Shadow DOM 中找到「发表视频」按钮，请检查页面加载状态或按钮选择器",
                failed_step="NavigateHomeStep",
            )

        logger.info(f"[视频号] 步骤1完成：已进入创作者服务中心 ({page.url})")
        return None
