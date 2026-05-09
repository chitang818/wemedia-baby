# -*- coding: utf-8 -*-
"""
步骤2：进入视频/图文发布页
文件路径: src/plugins/pro/wechat_video/steps/step_02_entry.py

流程：
  1. 检测登录态（URL 含 login → Cookie 失效报错）
  2. 检测风控弹窗（Selectors.SECURITY.RISK_MODAL）
  3. 优先通过 JS 穿透 wujie-app Shadow DOM 点击「发表视频」/「发表图文」按钮：
     - 精确路径 → 文本匹配降级 → Playwright 原生选择器降级 → 直接 URL 导航兜底
  4. 等待 URL 跳转至发布页（URL 含 platform/post/create）
  5. 等待上传区域 DOM（div.upload-content）出现，确认页面加载完成

字段依赖：metadata['file_type']（video/image 决定点击哪个按钮）
                 metadata['_publish_btn_ready']（步骤1已确认按钮就绪时可快速点击）
"""
import logging
from typing import Dict, Any

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class EnterPublishEntryStep(BasePublishStep):
    """从创作者中心首页点击「发表视频」或「发表图文」，进入对应发布页。

    前置条件：浏览器打开后默认已在创作者中心首页（无需额外导航）。

    流程：
    1. 检测登录态（URL 是否跳转到登录页）
    2. 检测风控弹窗
    3. 根据 file_type 点击「发表视频」或「发表图文」按钮
    4. 等待页面跳转至发布页（URL 包含 /post/create）
    5. 等待上传区域 DOM 出现（div.upload-content），确认页面加载完成
    """

    # 发布页 URL 特征
    PUBLISH_PAGE_URL_PATTERN = "platform/post/create"
    # 页面加载超时（毫秒）
    PAGE_LOAD_TIMEOUT = 30000
    # 上传区域出现超时（毫秒）
    UPLOAD_AREA_TIMEOUT = 20000

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        file_type = metadata.get("file_type", "video")
        anti_risk_config = metadata.get("anti_risk_config")
        # 步骤1已确认按钮就绪时，快速进入点击流程（2秒内）
        btn_ready = metadata.get("_publish_btn_ready", False)
        logger.info(f"[视频号] 步骤2：正在进入{file_type}发布页 (按钮已就绪={btn_ready})")

        # ---- 1. 检测登录态 ----
        current_url = page.url
        if "login" in current_url:
            logger.warning("[视频号] 当前页面为登录页，Cookie 可能已失效")
            return PublishResult(
                success=False,
                error_message="Cookie 已失效，请重新登录",
                failed_step="EnterPublishEntryStep",
            )

        # ---- 2. 检测风控弹窗 ----
        try:
            risk_selectors = Selectors.SECURITY.get("RISK_MODAL", [])
            for sel in risk_selectors:
                if await page.locator(sel).count() > 0:
                    logger.warning(f"[视频号] 检测到风控弹窗: {sel}")
                    return PublishResult(
                        success=False,
                        error_message="检测到账号异常/风控弹窗",
                        failed_step="EnterPublishEntryStep",
                    )
        except Exception:
            pass

        # ---- 3. 点击发布入口按钮 ----
        # 确定按钮类型
        if file_type == "video":
            btn_selectors = Selectors.HOME.get("PUBLISH_VIDEO_BTN", [])
            btn_label = "发表视频"
        else:
            btn_selectors = Selectors.HOME.get("PUBLISH_IMAGE_BTN", [])
            btn_label = "发表图文"

        # 关键：「发表视频/图文」按钮位于 wujie-app 的 Shadow DOM 内部，
        # Playwright 虽然能定位但点击事件无效，必须通过 JS 穿透 shadowRoot 点击。
        # JS 路径：document.querySelector("...wujie-app").shadowRoot.querySelector("...button")

        clicked = False

        # 步骤1已确认按钮就绪，短暂等待后直接 JS 点击（不超过2秒）
        if btn_ready:
            logger.info("[视频号] 步骤1已确认按钮就绪，短暂等待后直接点击")
            await page.wait_for_timeout(500)  # 仅等 0.5 秒

        # 方案A（首选）：通过 JS 穿透 Shadow DOM 点击
        try:
            js_click_result = await page.evaluate(f"""() => {{
                // 查找 wujie-app 容器
                const wujieApp = document.querySelector(
                    '#container-wrap > div.container-center > div > div.main-body > div.third-line > div > wujie-app'
                );
                if (!wujieApp || !wujieApp.shadowRoot) {{
                    // 降级：尝试任意 wujie-app
                    const allWujie = document.querySelectorAll('wujie-app');
                    for (const w of allWujie) {{
                        if (w.shadowRoot) {{
                            const btn = w.shadowRoot.querySelector(
                                '#app > div.finder-card.wrap > div > div.post-list-header > div.post > div > button'
                            );
                            if (btn && btn.textContent.includes('{btn_label}')) {{
                                btn.click();
                                return 'clicked_via_fallback_wujie';
                            }}
                            // 再降级：在 shadowRoot 中通过文本匹配按钮
                            const buttons = w.shadowRoot.querySelectorAll('button.weui-desktop-btn_primary');
                            for (const b of buttons) {{
                                if (b.textContent.includes('{btn_label}')) {{
                                    b.click();
                                    return 'clicked_via_text_match';
                                }}
                            }}
                        }}
                    }}
                    return 'wujie_not_found';
                }}
                // 精确路径点击
                const btn = wujieApp.shadowRoot.querySelector(
                    '#app > div.finder-card.wrap > div > div.post-list-header > div.post > div > button'
                );
                if (btn && btn.textContent.includes('{btn_label}')) {{
                    btn.click();
                    return 'clicked_exact';
                }}
                // shadowRoot 内按文本匹配
                const buttons = wujieApp.shadowRoot.querySelectorAll('button.weui-desktop-btn_primary');
                for (const b of buttons) {{
                    if (b.textContent.includes('{btn_label}')) {{
                        b.click();
                        return 'clicked_via_class_text';
                    }}
                }}
                return 'button_not_found_in_shadow';
            }}""")

            if js_click_result and 'clicked' in js_click_result:
                clicked = True
                logger.info(f"[视频号] 通过 JS 穿透 Shadow DOM 点击「{btn_label}」成功 ({js_click_result})")
            else:
                logger.warning(f"[视频号] JS Shadow DOM 点击结果: {js_click_result}")
        except Exception as e:
            logger.warning(f"[视频号] JS Shadow DOM 点击异常: {e}")

        # 方案B（降级）：Playwright 选择器点击（可能对 open shadow DOM 有效）
        if not clicked:
            logger.info("[视频号] JS 方案失败，尝试 Playwright 选择器点击...")
            for sel in btn_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.wait_for(state="visible", timeout=10000)
                        logger.info(f"[视频号] Playwright 找到「{btn_label}」按钮: {sel}")
                        try:
                            from src.infrastructure.anti_risk.human_like import human_click
                            await human_click(page, btn, metadata, anti_risk_config)
                        except Exception:
                            await btn.click()
                        clicked = True
                        logger.info(f"[视频号] Playwright 已点击「{btn_label}」按钮")
                        break
                except Exception as e:
                    logger.debug(f"[视频号] Playwright 通过 {sel} 点击失败: {e}")
                    continue

        if not clicked:
            logger.error(f"[视频号] 未找到「{btn_label}」按钮（JS 与 Playwright 均未成功），终止发布")
            USER_LOG.error(f"[步骤2/11 进入发布页] ✗ 未找到「{btn_label}」按钮，终止发布")
            return PublishResult(
                success=False,
                error_message=f"未找到「{btn_label}」按钮，请检查页面状态或选择器配置",
                failed_step="EnterPublishEntryStep",
            )

        # ---- 4. 等待页面跳转到发布页 ----
        try:
            await page.wait_for_url(
                f"**/{self.PUBLISH_PAGE_URL_PATTERN}**",
                timeout=self.PAGE_LOAD_TIMEOUT,
            )
            logger.info(f"[视频号] 页面已跳转至发布页: {page.url}")
        except Exception:
            # 即使 URL 匹配超时，如果当前 URL 已包含特征也继续
            if self.PUBLISH_PAGE_URL_PATTERN not in page.url:
                if "login" in page.url:
                    return PublishResult(
                        success=False,
                        error_message="Cookie 已失效，请重新登录",
                        failed_step="EnterPublishEntryStep",
                    )
                return PublishResult(
                    success=False,
                    error_message=f"页面未跳转至发布页，当前 URL: {page.url}",
                    failed_step="EnterPublishEntryStep",
                )

        # ---- 5. 等待上传区域出现（确认页面加载完成） ----
        page_marker_selectors = Selectors.HOME.get("VIDEO_PUBLISH_PAGE_MARKER", [])
        marker_found = False

        for sel in page_marker_selectors:
            try:
                await page.locator(sel).first.wait_for(
                    state="visible", timeout=self.UPLOAD_AREA_TIMEOUT
                )
                marker_found = True
                logger.info(f"[视频号] 上传区域已出现: {sel}，发布页加载完成")
                break
            except Exception:
                continue

        if not marker_found:
            logger.error("[视频号] 上传区域标识未检测到，页面可能未正确加载，终止发布")
            USER_LOG.error("[步骤2/11 进入发布页] ✗ 上传区域未出现，终止发布")
            return PublishResult(
                success=False,
                error_message="进入发布页后上传区域（VIDEO_PUBLISH_PAGE_MARKER）未在超时内出现，请检查页面加载状态",
                failed_step="EnterPublishEntryStep",
            )

        logger.info(f"[视频号] 步骤2完成：已进入{file_type}发布页")
        return None
