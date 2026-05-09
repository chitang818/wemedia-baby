# -*- coding: utf-8 -*-
"""
步骤7：点击投稿
文件路径: src/plugins/pro/bilibili/steps/step_07_submit.py

流程：
  1. 定位投稿按钮（SUBMIT_BTN），等待其可用
  2. 模拟点击投稿按钮
  3. 若未响应则进行第二次强点击兜底
  4. 检查拦截弹窗（错误提示、操作频繁等）
  5. 多重轮询验证投稿是否成功：
     a. 检测「投稿成功」Toast 或成功提示
     b. 检测 URL 跳转（success/manage）
     c. 兜底等待

字段依赖：
  - metadata['speed_rate']: 影响等待与延时
  - metadata['anti_risk_config']: 风控配置
"""
import logging
from typing import Dict, Any

from playwright.async_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, NeedsAction, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class SubmitStep(BasePublishStep):
    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """点击投稿按钮并验证最终结果。"""
        await self._await_pause(metadata)
        logger.info("===== 寻找并点击投稿按钮 =====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        # 先滚动到底部确保按钮可见
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(300)
        except Exception:
            pass

        # 查找投稿按钮
        target_btn = None
        target_selector = ""
        for selector in Selectors.PUBLISH["SUBMIT_BTN"]:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0:
                    await btn.wait_for(state="visible", timeout=5000)
                    target_btn = btn
                    target_selector = selector
                    break
            except Exception:
                continue

        if not target_btn:
            return PublishResult(
                success=False,
                error_message="未找到投稿按钮，可能页面结构已变更",
            )

        logger.info(f"找到投稿按钮: {target_selector}，检查是否就绪…")

        # 等待按钮可用（disabled 消失）
        max_wait_seconds = 120
        is_ready = False
        for i in range(max_wait_seconds // 3):
            await self._await_pause(metadata)
            is_disabled = await target_btn.get_attribute("disabled")
            if is_disabled is None or is_disabled == "false":
                is_ready = True
                break
            logger.info("投稿按钮当前不可用（可能仍在处理中），继续等待…")
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, wait_ms(3000), metadata, config)
            except Exception:
                await page.wait_for_timeout(wait_ms(3000))

        if not is_ready:
            return PublishResult(
                success=False,
                error_message="等待处理超时，投稿按钮始终不可用",
            )

        # 点击投稿
        logger.info("投稿按钮已就绪，执行点击…")
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
            USER_LOG.info("[步骤7 点击投稿] ▶ 已点击投稿按钮")

            # 短暂等待后检测反馈
            success_selectors = ", ".join(Selectors.VERIFY["SUCCESS_TOAST"])
            detected = False
            for _ in range(10):
                await page.wait_for_timeout(200)
                try:
                    if await page.locator(success_selectors).first.count() > 0:
                        detected = True
                        logger.info("检测到投稿成功提示")
                        break
                except Exception:
                    pass
                try:
                    url = page.url
                    for kw in Selectors.VERIFY["SUCCESS_URL_KEYWORDS"]:
                        if kw in url:
                            detected = True
                            logger.info(f"检测到页面跳转: {url}")
                            break
                    if detected:
                        break
                except Exception:
                    pass

            if not detected:
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
            return PublishResult(success=False, error_message=f"点击投稿按钮失败: {str(e)}")

        # 检查错误弹窗
        logger.info("检查是否存在错误弹窗…")
        try:
            from src.infrastructure.anti_risk.delays import random_delay
            await random_delay(page, wait_ms(300), metadata, config)
        except Exception:
            await page.wait_for_timeout(wait_ms(300))

        try:
            error_checks = [
                (Selectors.SECURITY["PUBLISH_TOAST_ERROR"], "投稿失败/错误"),
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
                        return NeedsAction(action="need_retry", message=f"投稿受阻: {desc}")
                    return PublishResult(success=False, error_message=f"投稿受阻: {desc}")
        except Exception as e:
            logger.debug(f"检查弹窗异常: {e}")

        return await self._verify_publish_result(page, metadata)

    async def _verify_publish_result(self, page: Page, metadata: Dict[str, Any]) -> PublishResult:
        """验证投稿结果。"""
        logger.info("===== 验证投稿结果 =====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        # 0. 快速检查 URL（B站投稿成功后通常跳转到成功页面）
        try:
            current_url = page.url
            for kw in Selectors.VERIFY["SUCCESS_URL_KEYWORDS"]:
                if kw in current_url:
                    logger.info(f"页面已跳转: {current_url}，视为投稿成功")
                    USER_LOG.info(f"[步骤7 点击投稿] ✓ 投稿成功 ({current_url})")
                    return PublishResult(success=True, publish_url=current_url)
        except Exception:
            pass

        # 1. 轮询检测 Toast 和 URL
        success_selectors = ", ".join(Selectors.VERIFY["SUCCESS_TOAST"])
        poll_interval_ms = 200
        total_wait_ms = 10000

        logger.info("轮询检测投稿结果…")
        for _ in range(0, total_wait_ms, poll_interval_ms):
            try:
                loc = page.locator(success_selectors).first
                if await loc.count() > 0 and await loc.is_visible():
                    logger.info("✓ 检测到投稿成功提示")
                    USER_LOG.info("[步骤7 点击投稿] ✓ 投稿成功！")
                    return PublishResult(success=True, publish_url=page.url)
            except Exception:
                pass

            try:
                current_url = page.url
                for kw in Selectors.VERIFY["SUCCESS_URL_KEYWORDS"]:
                    if kw in current_url:
                        logger.info(f"轮询中检测到跳转: {current_url}")
                        USER_LOG.info(f"[步骤7 点击投稿] ✓ 投稿成功 ({current_url})")
                        return PublishResult(success=True, publish_url=current_url)
            except Exception:
                pass

            await page.wait_for_timeout(poll_interval_ms)

        # 2. 兜底：等待 URL 变化
        try:
            await page.wait_for_timeout(int(5000 * speed_rate))
            current_url = page.url
            if "upload/video/frame" not in current_url and "member.bilibili.com" in current_url:
                logger.info(f"页面已离开投稿页: {current_url}，视为投稿成功")
                USER_LOG.info(f"[步骤7 点击投稿] ✓ 投稿成功 ({current_url})")
                return PublishResult(success=True, publish_url=current_url)
        except Exception:
            pass

        logger.warning("未能确认投稿成功，请手动检查")
        return PublishResult(
            success=False,
            error_message="投稿后未能确认成功（未检测到'投稿成功'提示或页面跳转），请手动检查",
        )
