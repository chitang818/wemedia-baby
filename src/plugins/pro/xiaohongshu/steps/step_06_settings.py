# -*- coding: utf-8 -*-
"""
步骤6：发布设置
文件路径: src/plugins/pro/xiaohongshu/steps/step_06_settings.py

流程（依次执行）：
  1. 页面滚动到底部暴露设置区
  2. 可见性设置：根据 privacy 字段选择"公开"或"私密"
  3. 作品申明（best-effort）：原创声明开关、内容属性下拉（受 privacy_settings 控制）
  4. 发布时间：
     - 若 schedule_time 为空，则默认立即发布
     - 若有定时时间，设置定时发布

字段依赖：
  - metadata['privacy_settings']: 包含 privacy ("public"/"private")；
    以及 xiaohongshu_is_original / xiaohongshu_content_attribute / xiaohongshu_content_attribute_auto
  - metadata['schedule_time'] / metadata['scheduled_publish_time']: 定时发布时间
"""
import json
import logging
from typing import Any, Dict, Optional

from playwright.async_api import Page, Locator

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class PublishSettingsStep(BasePublishStep):
    """发布设置（权限、可见性、定时发布等）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        logger.info("===== 发布设置 =====")

        # 先滚动到底部确保设置区可见
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(300)
        except Exception as e:
            logger.debug(f"滚动到底部异常: {e}")

        privacy_settings = metadata.get("privacy_settings", {})
        if isinstance(privacy_settings, str):
            try:
                privacy_settings = json.loads(privacy_settings)
            except Exception:
                privacy_settings = {}
        elif not isinstance(privacy_settings, dict):
            privacy_settings = {}

        # ── 1. 可见性设置 ──
        privacy = privacy_settings.get("privacy", "public")

        try:
            privacy_selectors = Selectors.SETTINGS.get("PRIVACY_PUBLIC", [])
            if privacy == "private":
                privacy_selectors = Selectors.SETTINGS.get("PRIVACY_PRIVATE", [])

            for sel in privacy_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        try:
                            await loc.scroll_into_view_if_needed()
                        except Exception:
                            pass
                        try:
                            from src.infrastructure.anti_risk.human_like import human_click
                            await human_click(page, loc, metadata, config)
                        except Exception:
                            await loc.click()

                        try:
                            from src.infrastructure.anti_risk.delays import random_delay
                            await random_delay(page, wait_ms(500), metadata, config)
                        except Exception:
                            await page.wait_for_timeout(wait_ms(500))

                        USER_LOG.info(f"[步骤6 发布设置] ▶ 已设置可见性: {privacy}")
                        logger.info(f"已设置可见性: {privacy}")
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"设置可见性异常: {e}")

        await self._apply_xiaohongshu_work_declaration(
            page, privacy_settings, metadata, config, wait_ms,
        )

        # ── 2. 定时发布 ──
        schedule_time = metadata.get("scheduled_publish_time") or metadata.get("schedule_time")

        try:
            if schedule_time:
                from src.utils.date_utils import format_schedule_time_st_str
                st_str = format_schedule_time_st_str(schedule_time) or ""

                logger.info(f"检测到定时发布时间: {st_str}")
                USER_LOG.info(f"[步骤6 发布设置] ▶ 尝试设置定时: {st_str}")

                # 勾选「定时发布」
                schedule_selectors = Selectors.SETTINGS.get("PUBLISH_SCHEDULE", [])
                clicked = False
                for sel in schedule_selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            try:
                                await loc.scroll_into_view_if_needed()
                            except Exception:
                                pass
                            try:
                                from src.infrastructure.anti_risk.human_like import human_click
                                await human_click(page, loc, metadata, config)
                            except Exception:
                                await loc.click()
                            clicked = True

                            try:
                                from src.infrastructure.anti_risk.delays import random_delay
                                await random_delay(page, wait_ms(500), metadata, config)
                            except Exception:
                                await page.wait_for_timeout(wait_ms(500))
                            break
                    except Exception:
                        continue

                if not clicked:
                    logger.warning("未找到定时发布选项")
                    USER_LOG.warning("[步骤6 发布设置] ✗ 未找到定时发布选项")
                    return PublishResult(
                        success=False,
                        error_message="未找到定时发布选项，定时发布设置失败",
                        failed_step="PublishSettingsStep",
                    )

                # 设置时间
                time_input_selectors = Selectors.SETTINGS.get("SCHEDULE_INPUT", [])
                time_set = False
                for sel in time_input_selectors:
                    try:
                        inp = page.locator(sel).first
                        if await inp.count() > 0 and await inp.is_visible():
                            await inp.click()
                            await page.keyboard.press("Control+A")
                            await page.keyboard.press("Backspace")
                            await inp.type(st_str, delay=max(10, int(30 * speed_rate)))
                            time_set = True
                            logger.info(f"已设置定时时间: {st_str}")
                            USER_LOG.info(f"[步骤6 发布设置] ▶ 已设置定时: {st_str}")
                            break
                    except Exception:
                        continue

                if not time_set:
                    logger.warning("未找到时间输入框")
                    USER_LOG.warning("[步骤6 发布设置] ✗ 未找到时间输入框")
                    return PublishResult(
                        success=False,
                        error_message="定时发布时间设置失败，未找到时间输入框",
                        failed_step="PublishSettingsStep",
                    )
            else:
                logger.info("未设置定时，将立即发布")
        except Exception as e:
            logger.warning(f"定时/立即发布设置异常: {e}")
            if schedule_time:
                return PublishResult(
                    success=False,
                    error_message=f"定时发布设置异常: {e}",
                    failed_step="PublishSettingsStep",
                )

        return None

    async def _apply_xiaohongshu_work_declaration(
        self,
        page: Page,
        privacy_settings: Dict[str, Any],
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms,
    ) -> None:
        """小红书原创声明 + 内容属性（失败不阻断发布）。"""
        from src.domain.publish.work_declaration import (
            KEY_XHS_CONTENT_ATTR,
            KEY_XHS_CONTENT_ATTR_AUTO,
            KEY_XHS_ORIGINAL,
            declaration_auto_apply,
            label_for_xhs_content_attr,
            normalize_xhs_content_attr,
        )
        from src.infrastructure.anti_risk.delays import random_delay

        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await random_delay(page, wait_ms(350), metadata, config)
        except Exception:
            pass

        want_orig = bool(privacy_settings.get(KEY_XHS_ORIGINAL, False))
        ok_orig = await self._sync_xhs_original_switch(
            page, want_orig, metadata, config, wait_ms,
        )
        if ok_orig:
            USER_LOG.info(
                "[步骤6 发布设置] ▶ 原创声明目标：%s",
                "申明原创" if want_orig else "不申明原创",
            )
        else:
            USER_LOG.warning(
                "[步骤6 发布设置] ▷ 未能自动切换「原创声明」，请人工核对页面开关",
            )

        if not declaration_auto_apply(privacy_settings, KEY_XHS_CONTENT_ATTR_AUTO):
            USER_LOG.info("[步骤6 发布设置] — 跳过内容属性（已关闭自动设置）")
            return

        raw_attr = privacy_settings.get(KEY_XHS_CONTENT_ATTR)
        attr = normalize_xhs_content_attr(
            str(raw_attr) if raw_attr is not None else None,
        )
        if not attr:
            USER_LOG.info("[步骤6 发布设置] — 跳过内容属性（未选择）")
            return

        cn_label = label_for_xhs_content_attr(attr)
        if not cn_label:
            return

        ok_attr = await self._pick_xhs_content_attribute_option(
            page, cn_label, metadata, config, wait_ms,
        )
        if ok_attr:
            USER_LOG.info("[步骤6 发布设置] ▶ 内容属性：%s", cn_label)
        else:
            USER_LOG.warning(
                "[步骤6 发布设置] ▷ 未能自动选择内容属性「%s」，请人工核对",
                cn_label,
            )

    async def _sync_xhs_original_switch(
        self,
        page: Page,
        want_on: bool,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms,
    ) -> bool:
        from src.infrastructure.anti_risk.delays import random_delay
        from src.infrastructure.anti_risk.human_like import human_click

        sw: Optional[Locator] = None
        try:
            cands = page.locator("div").filter(has_text="原创声明")
            n = await cands.count()
            for i in range(n):
                box = cands.nth(i)
                try:
                    await box.scroll_into_view_if_needed()
                except Exception:
                    pass
                trial = box.locator('[role="switch"]').first
                if await trial.count() > 0 and await trial.is_visible():
                    sw = trial
                    break
            if sw is None:
                for sel in Selectors.SETTINGS.get("WORK_ORIGINAL_LABEL", []):
                    try:
                        anchor = page.locator(sel).first
                        if await anchor.count() > 0:
                            await anchor.scroll_into_view_if_needed()
                            await random_delay(page, wait_ms(150), metadata, config)
                            p = anchor.locator("xpath=ancestor::div[position()<=14]")
                            trial = p.locator('[role="switch"]').first
                            if await trial.count() > 0:
                                sw = trial
                                break
                    except Exception:
                        continue
            if sw is None:
                return False

            cur = (await sw.get_attribute("aria-checked") or "").strip().lower()
            is_on = cur == "true"
            if is_on != want_on:
                await human_click(page, sw, metadata, config)
                await random_delay(page, wait_ms(280), metadata, config)
            return True
        except Exception as e:
            logger.debug(f"同步小红书原创声明开关异常: {e}")
            return False

    async def _pick_xhs_content_attribute_option(
        self,
        page: Page,
        cn_label: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms,
    ) -> bool:
        from src.infrastructure.anti_risk.delays import random_delay
        from src.infrastructure.anti_risk.human_like import human_click

        try:
            for hint in ("内容属性", "笔记类型", "添加声明"):
                try:
                    h = page.get_by_text(hint, exact=False).first
                    if await h.count() > 0 and await h.is_visible():
                        await h.scroll_into_view_if_needed()
                        await random_delay(page, wait_ms(120), metadata, config)
                        try:
                            await human_click(page, h, metadata, config)
                        except Exception:
                            await h.click()
                        await random_delay(page, wait_ms(220), metadata, config)
                        break
                except Exception:
                    continue

            opt = page.get_by_text(cn_label, exact=True).first
            if await opt.count() > 0 and await opt.is_visible():
                await opt.scroll_into_view_if_needed()
                await random_delay(page, wait_ms(120), metadata, config)
                try:
                    await human_click(page, opt, metadata, config)
                except Exception:
                    await opt.click()
                return True

            opt2 = page.get_by_text(cn_label, exact=False).first
            if await opt2.count() > 0:
                await opt2.scroll_into_view_if_needed()
                await random_delay(page, wait_ms(120), metadata, config)
                try:
                    await human_click(page, opt2, metadata, config)
                except Exception:
                    await opt2.click()
                return True
        except Exception as e:
            logger.debug(f"选择小红书内容属性异常: {e}")
        return False
