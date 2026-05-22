# -*- coding: utf-8 -*-
"""
步骤8：点击发布
文件路径: src/plugins/pro/xiaohongshu/steps/step_08_submit.py

流程：
  1. 定位发布按钮（SUBMIT_BTN），等待其可用
  2. 模拟点击发布按钮
  3. 若未响应则进行第二次强点击兜底
  4. 检查拦截弹窗（错误提示、操作频繁等）
  5. 多重轮询验证发布是否成功：
     a. 检测「发布成功」Toast
     b. 检测 URL 跳转（manage/success）
     c. 兜底等待

字段依赖：
  - metadata['speed_rate']: 影响等待与延时
  - metadata['anti_risk_config']: 风控配置
"""
import logging
from typing import Dict, Any

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, NeedsAction, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class SubmitStep(BasePublishStep):
    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """点击发布按钮并验证最终结果。"""
        await self._await_pause(metadata)
        logger.info("===== 寻找并点击发布按钮 =====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        async def _submit_button_ready() -> bool:
            await self._await_pause(metadata)
            try:
                is_disabled = await target_btn.get_attribute("disabled")
                return is_disabled is None or is_disabled == "false"
            except Exception:
                return False

        is_ready = bool(
            await PluginWaitHelper.wait_for_condition(
                page,
                _submit_button_ready,
                timeout_ms=120_000,
                poll_interval_ms=700,
                pause_callback=lambda: self._await_pause(metadata),
                on_poll=lambda _attempt: logger.info(
                    "????????????????????????"
                ),
            )
        )

        if not is_ready:
            return PublishResult(
                success=False,
                error_message="等待处理超时，发布按钮始终不可用",
            )

        # 点击发布
        logger.info("发布按钮已就绪，执行点击…")
        try:
            await self._await_pause(metadata)
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, wait_ms(200), metadata, config)
            except Exception:
                await page.wait_for_timeout(wait_ms(200))

            target_btn = page.locator(target_selector).first
            await target_btn.wait_for(state="visible", timeout=5000)
            try:
                await target_btn.scroll_into_view_if_needed()
                await page.wait_for_timeout(150)
            except Exception:
                pass

            # 第一次点击
            await target_btn.click(force=True)
            logger.info("已执行第一次点击")
            USER_LOG.info("[步骤8 点击发布] ▶ 已点击发布按钮")

            # 短暂等待后检测反馈
            success_selectors = ", ".join(Selectors.VERIFY["SUCCESS_TOAST"])
            detected = False
            for _ in range(10):
                await page.wait_for_timeout(200)
                try:
                    if await page.locator(success_selectors).first.count() > 0:
                        detected = True
                        logger.info("检测到「发布成功」提示")
                        break
                except Exception:
                    pass
                try:
                    url = page.url
                    for kw in Selectors.VERIFY["SUCCESS_URL_KEYWORDS"]:
                        if kw in url and "publish" not in url.split("/")[-1]:
                            detected = True
                            logger.info(f"检测到页面跳转: {url}")
                            break
                    if detected:
                        break
                except Exception:
                    pass

            if not detected:
                # 第二次点击兜底
                logger.info("未检测到反馈，执行第二次点击…")
                try:
                    target_btn = page.locator(target_selector).first
                    if await target_btn.count() > 0:
                        await target_btn.wait_for(state="visible", timeout=3000)
                        await target_btn.click(force=True)
                        logger.info("已执行第二次点击")
                except Exception as e:
                    logger.warning(f"第二次点击异常: {e}")

        except Exception as e:
            return PublishResult(success=False, error_message=f"点击发布按钮失败: {str(e)}")

        # 检查错误弹窗
        logger.info("检查是否存在错误弹窗…")
        try:
            from src.infrastructure.anti_risk.delays import random_delay
            await random_delay(page, wait_ms(300), metadata, config)
        except Exception:
            await page.wait_for_timeout(wait_ms(300))

        try:
            error_checks = [
                (Selectors.SECURITY["PUBLISH_TOAST_ERROR"], "发布失败/错误"),
                (Selectors.SECURITY["PUBLISH_TOAST_FREQ"], "操作频繁"),
            ]
            for selector_list, desc in error_checks:
                selector = ", ".join(selector_list)
                if await page.locator(selector).count() > 0:
                    logger.warning(f"检测到异常: {desc}")
                    try:
                        text = await page.locator(selector).inner_text()
                        desc = f"{desc}: {text}"
                    except Exception:
                        pass
                    if "频繁" in desc:
                        return NeedsAction(action="need_retry", message=f"发布受阻: {desc}")
                    return PublishResult(success=False, error_message=f"发布受阻: {desc}")
        except Exception as e:
            logger.debug(f"检查弹窗异常: {e}")

        return await self._verify_publish_result(page, metadata)

    async def _verify_publish_result(self, page: Page, metadata: Dict[str, Any]) -> PublishResult:
        """验证发布结果。"""
        logger.info("===== 验证发布结果 =====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        # 0. 快速检查 URL
        try:
            current_url = page.url
            for kw in Selectors.VERIFY["SUCCESS_URL_KEYWORDS"]:
                if kw in current_url and "/publish/publish" not in current_url:
                    logger.info(f"页面已跳转: {current_url}，视为发布成功")
                    USER_LOG.info(f"[步骤8 点击发布] ✓ 发布成功 ({current_url})")
                    return PublishResult(success=True, publish_url=current_url)
        except Exception:
            pass

        # 1. 轮询检测 Toast 和 URL
        success_selectors = ", ".join(Selectors.VERIFY["SUCCESS_TOAST"])
        poll_interval_ms = 200
        total_wait_ms = 8000

        logger.info("轮询检测发布结果…")
        for _ in range(0, total_wait_ms, poll_interval_ms):
            try:
                loc = page.locator(success_selectors).first
                if await loc.count() > 0 and await loc.is_visible():
                    logger.info("✓ 检测到「发布成功」Toast")
                    USER_LOG.info("[步骤8 点击发布] ✓ 发布成功！")
                    return PublishResult(success=True, publish_url=page.url)
            except Exception:
                pass

            try:
                current_url = page.url
                for kw in Selectors.VERIFY["SUCCESS_URL_KEYWORDS"]:
                    if kw in current_url and "/publish/publish" not in current_url:
                        logger.info(f"轮询中检测到跳转: {current_url}")
                        USER_LOG.info(f"[步骤8 点击发布] ✓ 发布成功 ({current_url})")
                        return PublishResult(success=True, publish_url=current_url)
            except Exception:
                pass

            await page.wait_for_timeout(poll_interval_ms)

        # 2. 兜底：等待 URL 变化
        try:
            await PluginWaitHelper.wait_for_url_or_selectors(
                page,
                initial_url=page.url,
                timeout_ms=int(5000 * speed_rate),
                poll_interval_ms=300,
                pause_callback=lambda: self._await_pause(metadata),
            )
            current_url = page.url
            if "/publish/publish" not in current_url and "xiaohongshu.com" in current_url:
                logger.info(f"页面已离开发布页: {current_url}，视为发布成功")
                USER_LOG.info(f"[步骤8 点击发布] ✓ 发布成功 ({current_url})")
                return PublishResult(success=True, publish_url=current_url)
        except Exception:
            pass

        logger.warning("未能确认发布成功，请手动检查")
        return PublishResult(
            success=False,
            error_message="发布后未能确认成功（未检测到'发布成功'提示或页面跳转），请手动检查",
        )
