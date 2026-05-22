# -*- coding: utf-8 -*-
"""
步骤7：发布设置
文件路径: src/plugins/pro/xiaohongshu/steps/step_07_settings.py

按发布类型执行不同设置项：
  - 视频：公开可见、定时发布
  - 图文：允许合拍、允许正文复制、公开可见、定时发布

原创申明、作品申明、地点由步骤 6A/6B/6C 负责。

字段依赖：
  - metadata['file_type']: "video" / "image"
  - metadata['privacy_settings']: privacy ("public"/"private")；
    图文 xiaohongshu_allow_co_create / xiaohongshu_allow_copy_content（bool，缺省为 True）
  - metadata['schedule_time'] / metadata['scheduled_publish_time']: 定时发布时间
"""
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

from playwright.async_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

KEY_XHS_ALLOW_CO_CREATE = "xiaohongshu_allow_co_create"
KEY_XHS_ALLOW_COPY_CONTENT = "xiaohongshu_allow_copy_content"


class PublishSettingsStep(BasePublishStep):
    """发布设置：视频/图文按类型应用可见性、定时及图文专属开关。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms: Callable[[int], int] = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}
        file_type = (metadata.get("file_type") or "video").lower()
        is_image = file_type == "image"
        privacy_settings = self._parse_privacy_settings(metadata)

        logger.info("===== 发布设置 (%s) =====", "图文" if is_image else "视频")
        USER_LOG.info(
            "[步骤7 发布设置] ▶ 开始（%s）",
            "图文：合拍+正文复制+可见性+定时" if is_image else "视频：可见性+定时",
        )

        await self._scroll_to_settings_area(page, wait_ms)

        if is_image:
            await self._apply_image_only_switches(
                page, privacy_settings, metadata, config, wait_ms,
            )

        await self._apply_visibility(
            page, privacy_settings, metadata, config, wait_ms,
        )

        schedule_outcome = await self._apply_scheduled_publish(
            page, metadata, config, wait_ms, speed_rate,
        )
        if schedule_outcome is not None:
            return schedule_outcome

        return None

    @staticmethod
    def _parse_privacy_settings(metadata: Dict[str, Any]) -> Dict[str, Any]:
        privacy_settings = metadata.get("privacy_settings", {})
        if isinstance(privacy_settings, str):
            try:
                privacy_settings = json.loads(privacy_settings)
            except Exception:
                privacy_settings = {}
        elif not isinstance(privacy_settings, dict):
            privacy_settings = {}
        return privacy_settings

    async def _scroll_to_settings_area(
        self, page: Page, wait_ms: Callable[[int], int],
    ) -> None:
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(wait_ms(300))
        except Exception as e:
            logger.debug("滚动到底部异常: %s", e)

    async def _apply_image_only_switches(
        self,
        page: Page,
        privacy_settings: Dict[str, Any],
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> None:
        """图文专属：允许合拍、允许正文复制（best-effort，失败不阻断）。"""
        want_co_create = bool(privacy_settings.get(KEY_XHS_ALLOW_CO_CREATE, True))
        ok_co = await self._sync_switch_near_label(
            page,
            want_on=want_co_create,
            label_hints=("允许合拍", "合拍"),
            anchor_selectors=Selectors.SETTINGS.get("ALLOW_CO_CREATE_LABEL", []),
            metadata=metadata,
            config=config,
            wait_ms=wait_ms,
        )
        self._log_switch_result("允许合拍", want_co_create, ok_co)

        want_copy = bool(privacy_settings.get(KEY_XHS_ALLOW_COPY_CONTENT, True))
        ok_copy = await self._sync_switch_near_label(
            page,
            want_on=want_copy,
            label_hints=("允许正文复制", "正文复制", "复制正文"),
            anchor_selectors=Selectors.SETTINGS.get("ALLOW_COPY_CONTENT_LABEL", []),
            metadata=metadata,
            config=config,
            wait_ms=wait_ms,
        )
        self._log_switch_result("允许正文复制", want_copy, ok_copy)

    def _log_switch_result(self, name: str, want_on: bool, ok: bool) -> None:
        target = "开启" if want_on else "关闭"
        if ok:
            USER_LOG.info("[步骤7 发布设置] ▶ 已设置%s：%s", name, target)
        else:
            USER_LOG.warning(
                "[步骤7 发布设置] ▷ 未能自动设置「%s」为%s，请人工核对",
                name,
                target,
            )

    async def _apply_visibility(
        self,
        page: Page,
        privacy_settings: Dict[str, Any],
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> None:
        privacy = privacy_settings.get("privacy", "public")
        try:
            privacy_selectors = list(Selectors.SETTINGS.get("PRIVACY_PUBLIC", []))
            if privacy == "private":
                privacy_selectors = list(Selectors.SETTINGS.get("PRIVACY_PRIVATE", []))

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

                        label = "私密" if privacy == "private" else "公开可见"
                        USER_LOG.info(f"[步骤7 发布设置] ▶ 已设置可见性: {label}")
                        logger.info("已设置可见性: %s", privacy)
                        return
                except Exception:
                    continue
            USER_LOG.warning("[步骤7 发布设置] ▷ 未找到可见性选项，请人工核对")
        except Exception as e:
            logger.warning("设置可见性异常: %s", e)

    async def _apply_scheduled_publish(
        self,
        page: Page,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
        speed_rate: float,
    ) -> Optional[PublishResult]:
        schedule_time = metadata.get("scheduled_publish_time") or metadata.get("schedule_time")

        try:
            if not schedule_time:
                logger.info("未设置定时，将立即发布")
                return None

            from src.utils.date_utils import format_schedule_time_st_str
            st_str = format_schedule_time_st_str(schedule_time) or ""

            logger.info("检测到定时发布时间: %s", st_str)
            USER_LOG.info(f"[步骤7 发布设置] ▶ 尝试设置定时: {st_str}")

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
                USER_LOG.warning("[步骤7 发布设置] ✗ 未找到定时发布选项")
                return PublishResult(
                    success=False,
                    error_message="未找到定时发布选项，定时发布设置失败",
                    failed_step="PublishSettingsStep",
                )

            time_input_selectors = Selectors.SETTINGS.get("SCHEDULE_INPUT", [])
            for sel in time_input_selectors:
                try:
                    inp = page.locator(sel).first
                    if await inp.count() > 0 and await inp.is_visible():
                        await inp.click()
                        await page.keyboard.press("Control+A")
                        await page.keyboard.press("Backspace")
                        await inp.type(st_str, delay=max(10, int(30 * speed_rate)))
                        logger.info("已设置定时时间: %s", st_str)
                        USER_LOG.info(f"[步骤7 发布设置] ▶ 已设置定时: {st_str}")
                        return None
                except Exception:
                    continue

            logger.warning("未找到时间输入框")
            USER_LOG.warning("[步骤7 发布设置] ✗ 未找到时间输入框")
            return PublishResult(
                success=False,
                error_message="定时发布时间设置失败，未找到时间输入框",
                failed_step="PublishSettingsStep",
            )
        except Exception as e:
            logger.warning("定时/立即发布设置异常: %s", e)
            if schedule_time:
                return PublishResult(
                    success=False,
                    error_message=f"定时发布设置异常: {e}",
                    failed_step="PublishSettingsStep",
                )
        return None

    async def _sync_switch_near_label(
        self,
        page: Page,
        *,
        want_on: bool,
        label_hints: Sequence[str],
        anchor_selectors: Sequence[str],
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> bool:
        from src.infrastructure.anti_risk.delays import random_delay
        from src.infrastructure.anti_risk.human_like import human_click

        sw: Optional[Locator] = None
        try:
            for hint in label_hints:
                if not hint:
                    continue
                cands = page.locator("div").filter(has_text=hint)
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
                if sw is not None:
                    break

            if sw is None:
                for sel in anchor_selectors:
                    try:
                        anchor = page.locator(sel).first
                        if await anchor.count() > 0:
                            await anchor.scroll_into_view_if_needed()
                            await random_delay(page, wait_ms(150), metadata, config)
                            parent = anchor.locator("xpath=ancestor::div[position()<=14]")
                            trial = parent.locator('[role="switch"]').first
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
            logger.debug("同步开关异常 hints=%s: %s", label_hints, e)
            return False
