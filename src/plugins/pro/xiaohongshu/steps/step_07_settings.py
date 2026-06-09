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
  - metadata['privacy_settings']: privacy ("public"/"private"/"friend")；
    图文 xiaohongshu_allow_co_create / xiaohongshu_allow_copy_content（bool，缺省为 True）
  - metadata['schedule_time'] / metadata['scheduled_publish_time']: 定时发布时间
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.infrastructure.browser.automation_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.wait_helper import PluginWaitHelper
from ._base import BasePublishStep, StepOutcome
from ._schedule_picker import blur_publish_form_focus, dismiss_schedule_date_picker_and_wait
from ..selectors import Selectors
from .step_06A_original_declaration import _scroll_locator_to_center

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

KEY_XHS_ALLOW_CO_CREATE = "xiaohongshu_allow_co_create"
KEY_XHS_ALLOW_COPY_CONTENT = "xiaohongshu_allow_copy_content"

# 定时发布 switch 交互（对齐 step_06A）
_SCHEDULE_SWITCH_RESPONSE_WAIT_MS = 2500
_SCHEDULE_SWITCH_POLL_MS = 200
_SCHEDULE_SWITCH_CLICK_MAX_ATTEMPTS = 3
_SCHEDULE_POST_CLICK_SETTLE_MS = 300
_SCHEDULE_PICKER_CLOSE_WAIT_MS = 3000
_SCHEDULE_PICKER_POLL_MS = 150
_SCHEDULE_TIME_VERIFY_RETRIES = 2
_RIGHT_BLANK_CLICK_SELECTORS: Sequence[str] = (
    "div[class*='preview']",
    "[class*='phone-preview']",
    "[class*='video-preview']",
    ".publish-preview",
    ".publish-page-container",
)

_PRIVACY_TO_XHS_LABEL: Dict[str, str] = {
    "public": "公开可见",
    "private": "仅自己可见",
    "friend": "仅互关好友可见",
}


def privacy_to_xhs_label(privacy: str) -> Optional[str]:
    """任务 privacy 字段 → 小红书可见范围下拉选项文案。"""
    return _PRIVACY_TO_XHS_LABEL.get((privacy or "").strip().lower())


def parse_schedule_st_str(st_str: str) -> Optional[Tuple[int, int, int, int, int]]:
    """解析 YYYY-MM-DD HH:mm 为 (year, month, day, hour, minute)。"""
    s = (st_str or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})$", s)
    if not m:
        return None
    return (
        int(m.group(1)),
        int(m.group(2)),
        int(m.group(3)),
        int(m.group(4)),
        int(m.group(5)),
    )


class PublishSettingsStep(BasePublishStep):
    """发布设置：视频/图文按类型应用可见性、定时及图文专属开关。"""

    _FAILED_STEP = "PublishSettingsStep"

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

    def _more_settings_root(self, page: Page) -> Locator:
        for sel in Selectors.SETTINGS.get("MORE_SETTINGS_SECTION", []):
            return page.locator(sel).first
        return page.locator(".publish-page-content-settings").first

    async def _scroll_to_settings_area(
        self, page: Page, wait_ms: Callable[[int], int],
    ) -> None:
        try:
            root = self._more_settings_root(page)
            if await root.count() > 0:
                await _scroll_locator_to_center(page, root, wait_ms=wait_ms(350))
                logger.debug("已滚入更多设置区")
                return
        except Exception:
            pass

        for hint in ("更多设置", "定时发布", "公开可见"):
            try:
                loc = page.locator("div").filter(has_text=hint).first
                if await loc.count() > 0:
                    await _scroll_locator_to_center(page, loc, wait_ms=wait_ms(350))
                    logger.debug("已滚入设置锚点: %s", hint)
                    return
            except Exception:
                continue

        try:
            from src.infrastructure.browser.human_behavior import HumanBehavior
            await HumanBehavior.scroll_to_bottom(page)
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

    async def _find_permission_select(self, page: Page) -> Optional[Locator]:
        root = self._more_settings_root(page)
        try:
            if await root.count() > 0:
                loc = root.locator(".permission-card-select").first
                if await loc.count() > 0:
                    return loc
        except Exception:
            pass

        for sel in Selectors.SETTINGS.get("PERMISSION_SELECT", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    async def _wait_permission_dropdown(self, page: Page, *, timeout_ms: int = 5000) -> Optional[Locator]:
        anchors = Selectors.SETTINGS.get("PERMISSION_DROPDOWN_ANCHOR", ["仅自己可见"])
        anchor = anchors[0] if anchors else "仅自己可见"
        for sel in Selectors.SETTINGS.get("PERMISSION_DROPDOWN", []):
            try:
                loc = page.locator(sel).first
                await loc.wait_for(state="visible", timeout=timeout_ms)
                if await loc.count() > 0:
                    return loc
            except Exception:
                continue
        try:
            loc = (
                page.locator("body > .d-popover.custom-dropdown-44")
                .filter(has_text=anchor)
                .first
            )
            await loc.wait_for(state="visible", timeout=timeout_ms)
            if await loc.count() > 0:
                return loc
        except Exception as e:
            logger.debug("等待权限浮层失败: %s", e)
        return None

    async def _apply_visibility_fallback_radio(
        self,
        page: Page,
        privacy: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> bool:
        """图文旧版 radio 兜底。"""
        from src.infrastructure.anti_risk.delays import random_delay
        from src.infrastructure.anti_risk.human_like import human_click

        privacy_selectors = list(Selectors.SETTINGS.get("PRIVACY_PUBLIC", []))
        if privacy == "private":
            privacy_selectors = list(Selectors.SETTINGS.get("PRIVACY_PRIVATE", []))

        for sel in privacy_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.scroll_into_view_if_needed()
                    try:
                        await human_click(page, loc, metadata, config)
                    except Exception:
                        await loc.click()
                    await random_delay(page, wait_ms(500), metadata, config)
                    return True
            except Exception:
                continue
        return False

    async def _apply_visibility(
        self,
        page: Page,
        privacy_settings: Dict[str, Any],
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> None:
        privacy = (privacy_settings.get("privacy") or "public").strip().lower()
        target_label = privacy_to_xhs_label(privacy)
        if not target_label:
            USER_LOG.warning(
                "[步骤7 发布设置] ▷ 未知可见性配置「%s」，跳过自动设置",
                privacy,
            )
            return

        try:
            entry = await self._find_permission_select(page)
            if entry is None:
                if await self._apply_visibility_fallback_radio(
                    page, privacy, metadata, config, wait_ms,
                ):
                    USER_LOG.info("[步骤7 发布设置] ▶ 已设置可见性（旧版控件）: %s", target_label)
                    return
                USER_LOG.warning("[步骤7 发布设置] ▷ 未找到可见性下拉，请人工核对")
                return

            await _scroll_locator_to_center(page, entry, wait_ms=wait_ms(200))
            try:
                entry_text = (await entry.inner_text() or "").strip()
            except Exception:
                entry_text = ""
            if target_label in entry_text:
                USER_LOG.info("[步骤7 发布设置] ▶ 可见性已是: %s", target_label)
                logger.info("可见性无需变更: %s", target_label)
                return

            from src.infrastructure.anti_risk.delays import random_delay
            from src.infrastructure.anti_risk.human_like import human_click

            try:
                await human_click(page, entry, metadata, config)
            except Exception:
                await entry.click()
            await random_delay(page, wait_ms(400), metadata, config)

            panel = await self._wait_permission_dropdown(page, timeout_ms=5000)
            if panel is None:
                USER_LOG.warning("[步骤7 发布设置] ▷ 可见性浮层未出现，请人工核对")
                return

            option = panel.get_by_text(target_label, exact=True).first
            if await option.count() == 0:
                option = panel.locator(f"div:has-text('{target_label}')").first
            if await option.count() == 0:
                USER_LOG.warning(
                    "[步骤7 发布设置] ▷ 浮层中未找到「%s」，请人工核对",
                    target_label,
                )
                return

            try:
                await human_click(page, option, metadata, config)
            except Exception:
                await option.click()
            await random_delay(page, wait_ms(400), metadata, config)
            await page.wait_for_timeout(wait_ms(200))

            USER_LOG.info("[步骤7 发布设置] ▶ 已设置可见性: %s", target_label)
            logger.info("已设置可见性: %s", target_label)
        except Exception as e:
            logger.warning("设置可见性异常: %s", e)
            USER_LOG.warning("[步骤7 发布设置] ▷ 设置可见性异常，请人工核对")

    def _schedule_wrapper(self, page: Page) -> Locator:
        """限定「更多设置」内带「定时发布」文案的卡片，避免误点其他 switch。"""
        for sel in Selectors.SETTINGS.get("SCHEDULE_WRAPPER", []):
            return page.locator(sel).filter(has_text="定时发布").first
        return page.locator(
            ".publish-page-content-settings .post-time-wrapper"
        ).filter(has_text="定时发布").first

    async def _scroll_to_schedule_area(
        self, page: Page, wait_ms: Callable[[int], int],
    ) -> None:
        """滚入定时发布区域（比整段更多设置更精确）。"""
        try:
            wrapper = self._schedule_wrapper(page)
            if await wrapper.count() > 0:
                await _scroll_locator_to_center(page, wrapper, wait_ms=wait_ms(350))
                logger.debug("已滚入定时发布区")
                return
        except Exception:
            pass
        for hint in ("定时发布", "更多设置"):
            try:
                loc = page.locator("div").filter(has_text=hint).first
                if await loc.count() > 0:
                    await _scroll_locator_to_center(page, loc, wait_ms=wait_ms(350))
                    return
            except Exception:
                continue

    async def _ensure_schedule_area_visible(
        self, page: Page, wait_ms: Callable[[int], int],
    ) -> None:
        await self._scroll_to_schedule_area(page, wait_ms)
        wrapper = self._schedule_wrapper(page)
        try:
            if await wrapper.count() > 0 and await wrapper.is_visible():
                return
        except Exception:
            pass
        try:
            root = self._more_settings_root(page)
            header = root.get_by_text("更多设置", exact=True).first
            if await header.count() > 0:
                await header.click()
                await page.wait_for_timeout(wait_ms(300))
                await self._scroll_to_schedule_area(page, wait_ms)
        except Exception as e:
            logger.debug("展开更多设置区失败: %s", e)

    async def _read_schedule_checkbox_state(self, checkbox: Locator) -> bool:
        try:
            return await checkbox.is_checked()
        except Exception:
            return False

    async def _read_schedule_switch_visual_on(self, wrapper: Locator) -> bool:
        """d-switch-simulator 无 unchecked 或含 checked 表示定时开关视觉为 ON。"""
        try:
            if await wrapper.count() == 0:
                return False
            sim = wrapper.locator(".d-switch-simulator").first
            if await sim.count() == 0:
                return False
            cls = (await sim.get_attribute("class")) or ""
            tokens = cls.split()
            if "unchecked" in tokens:
                return False
            if "checked" in tokens:
                return True
            box = wrapper.locator("input[type='checkbox']").first
            if await box.count() > 0:
                return await self._read_schedule_checkbox_state(box)
            return True
        except Exception:
            return False

    async def _schedule_switch_enabled(
        self,
        page: Page,
        wrapper: Locator,
        checkbox: Optional[Locator],
    ) -> bool:
        """视觉 ON、checkbox 勾选或时间输入框可见，任一即视为开关已开。"""
        if await self._read_schedule_switch_visual_on(wrapper):
            return True
        if checkbox is not None:
            if await self._read_schedule_checkbox_state(checkbox):
                return True
        display = await self._find_schedule_time_display(page)
        if display is not None:
            try:
                if await display.count() > 0 and await display.is_visible():
                    return True
            except Exception:
                pass
        return False

    @staticmethod
    def _schedule_input_value_matches(val: str, st_str: str) -> bool:
        v = (val or "").strip()
        s = (st_str or "").strip()
        return bool(v and s and (v == s or s in v))

    async def _read_schedule_input_value(self, inp: Locator) -> str:
        try:
            return (await inp.input_value() or "").strip()
        except Exception:
            return ""

    async def _ensure_schedule_switch_on(
        self,
        page: Page,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> bool:
        """选时失败后若开关被误关，仅在其为 OFF 时重新打开（避免重复点击关断）。"""
        wrapper = self._schedule_wrapper(page)
        checkbox = await self._find_schedule_checkbox(page)
        if await self._read_schedule_switch_visual_on(wrapper):
            return True
        if checkbox is not None and await self._read_schedule_checkbox_state(checkbox):
            return True
        logger.info("定时发布开关已关闭，尝试重新打开")
        USER_LOG.info("[步骤7 发布设置] ▶ 定时开关已关闭，正在重新打开")
        return await self._click_schedule_switch_to_open(page, metadata, config, wait_ms)

    async def _click_picker_item(
        self,
        page: Page,
        item: Locator,
        wait_ms: Callable[[int], int],
    ) -> bool:
        """仅在浮层子元素上点击，避免 human_click 偏移点到开关区域。"""
        try:
            if await item.count() == 0:
                return False
            await item.scroll_into_view_if_needed(timeout=4000)
            await page.wait_for_timeout(wait_ms(80))
            if await self._mouse_click_locator_center(page, item):
                return True
            await item.click(timeout=4000)
            return True
        except Exception as e:
            logger.debug("浮层内点击失败: %s", e)
            return False

    async def _set_schedule_time_via_input(
        self,
        page: Page,
        inp: Locator,
        st_str: str,
        wait_ms: Callable[[int], int],
        speed_rate: float,
    ) -> bool:
        """优先用输入框写入（模拟真实键盘行为，避免被平台识别）。"""
        import random

        try:
            await self._mouse_click_locator_center(page, inp)
            await page.wait_for_timeout(wait_ms(random.randint(100, 200)))
            
            await page.keyboard.press("Control+A")
            await page.wait_for_timeout(wait_ms(random.randint(80, 150)))
            await page.keyboard.press("Backspace")
            await page.wait_for_timeout(wait_ms(random.randint(100, 200)))

            for i, char in enumerate(st_str):
                if i > 0 and i % random.randint(3, 5) == 0:
                    await page.wait_for_timeout(wait_ms(random.randint(300, 600)))
                    
                if random.random() < 0.03 and char.isdigit():
                    wrong_char = str((int(char) + 1) % 10)
                    await page.keyboard.type(wrong_char)
                    await page.wait_for_timeout(wait_ms(random.randint(150, 300)))
                    await page.keyboard.press("Backspace")
                    await page.wait_for_timeout(wait_ms(random.randint(100, 200)))
                
                await page.keyboard.type(char)
                await page.wait_for_timeout(wait_ms(random.randint(80, 200)))

            await page.wait_for_timeout(wait_ms(random.randint(150, 300)))
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(wait_ms(250))
            
            if self._schedule_input_value_matches(
                await self._read_schedule_input_value(inp), st_str
            ):
                logger.info("成功通过键盘模拟写入定时时间: %s", st_str)
                return True
                
        except Exception as e:
            logger.debug("键盘模拟写入定时输入失败: %s", e)
            
        return False

    async def _mouse_click_locator_center(self, page: Page, locator: Locator) -> bool:
        try:
            box = await locator.bounding_box()
            if not box or box.get("width", 0) < 2 or box.get("height", 0) < 2:
                return False
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            await page.mouse.click(x, y)
            return True
        except Exception as e:
            logger.debug("定时发布 mouse.click 中心失败: %s", e)
            return False

    async def _try_click_schedule_switch_target(
        self,
        page: Page,
        target: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> None:
        from src.infrastructure.anti_risk.human_like import human_click

        await _scroll_locator_to_center(page, target, wait_ms=wait_ms(200))
        if await self._mouse_click_locator_center(page, target):
            return
        try:
            await target.click(timeout=4000, force=True)
            return
        except Exception as e:
            logger.debug("定时 switch locator.click(force) 失败: %s", e)
        await human_click(
            page,
            target,
            metadata,
            config,
            use_operation_delay=False,
        )

    @staticmethod
    def _schedule_sel_within_wrapper(selector: str) -> str:
        """将全局选择器转为 post-time-wrapper 内相对路径。"""
        for prefix in (
            ".publish-page-content-settings .post-time-wrapper ",
            ".post-time-wrapper ",
            ".post-time-switch-container ",
        ):
            if selector.startswith(prefix):
                return selector[len(prefix):]
        return selector

    async def _collect_schedule_switch_targets(self, wrapper: Locator) -> List[Locator]:
        ordered = (
            ".d-switch-simulator",
            ".d-clickable.d-switch",
            ".post-time-switch-container",
            ".custom-switch-card",
            ".custom-switch-wrapper",
        )
        targets: List[Locator] = []
        seen: set[str] = set()
        try:
            if await wrapper.count() == 0:
                return targets
            for sel in ordered:
                if sel in seen:
                    continue
                seen.add(sel)
                loc = wrapper.locator(sel).first
                if await loc.count() > 0:
                    targets.append(loc)
            for sel in Selectors.SETTINGS.get("SCHEDULE_SWITCH", []):
                rel = self._schedule_sel_within_wrapper(sel)
                if rel in seen:
                    continue
                seen.add(rel)
                loc = wrapper.locator(rel).first
                if await loc.count() > 0:
                    targets.append(loc)
        except Exception as e:
            logger.debug("收集定时 switch 目标失败: %s", e)
        return targets

    async def _wait_schedule_switch_response(
        self,
        page: Page,
        wrapper: Locator,
        checkbox: Optional[Locator],
        *,
        timeout_ms: int = _SCHEDULE_SWITCH_RESPONSE_WAIT_MS,
    ) -> bool:
        elapsed = 0
        while elapsed < timeout_ms:
            if await self._schedule_switch_enabled(page, wrapper, checkbox):
                return True
            await page.wait_for_timeout(_SCHEDULE_SWITCH_POLL_MS)
            elapsed += _SCHEDULE_SWITCH_POLL_MS
        return await self._schedule_switch_enabled(page, wrapper, checkbox)

    async def _find_schedule_checkbox_via_label(self, page: Page) -> Optional[Locator]:
        try:
            label = page.get_by_text("定时发布", exact=True).first
            if await label.count() == 0:
                return None
            for depth in range(1, 12):
                parent = label.locator(f"xpath=ancestor::div[{depth}]")
                box = parent.locator("input[type='checkbox']").first
                if await box.count() > 0:
                    return box
        except Exception:
            pass
        return None

    async def _click_schedule_switch_to_open(
        self,
        page: Page,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> bool:
        """打开定时发布 switch（对齐 06A：多目标点击 + 轮询 + 视觉/时间框判定）。"""
        await self._ensure_schedule_area_visible(page, wait_ms)

        wrapper = self._schedule_wrapper(page)
        checkbox = await self._find_schedule_checkbox(page)
        if checkbox is None:
            checkbox = await self._find_schedule_checkbox_via_label(page)

        if await self._read_schedule_switch_visual_on(wrapper):
            logger.info("定时发布开关已为开启状态（视觉 ON）")
            USER_LOG.info("[步骤7 发布设置] ▶ 定时发布开关已开启")
            return True
        if await self._schedule_switch_enabled(page, wrapper, checkbox):
            logger.info("定时发布开关已为开启状态")
            USER_LOG.info("[步骤7 发布设置] ▶ 定时发布开关已开启")
            return True

        targets = await self._collect_schedule_switch_targets(wrapper)
        if not targets:
            logger.warning("定时发布：未找到可点击的 switch 元素")
            return False

        for attempt in range(1, _SCHEDULE_SWITCH_CLICK_MAX_ATTEMPTS + 1):
            if await self._schedule_switch_enabled(page, wrapper, checkbox):
                return True

            for target in targets:
                try:
                    await self._try_click_schedule_switch_target(
                        page, target, metadata, config, wait_ms,
                    )
                    await page.wait_for_timeout(wait_ms(_SCHEDULE_POST_CLICK_SETTLE_MS))
                    if await self._wait_schedule_switch_response(page, wrapper, checkbox):
                        logger.info("定时发布开关点击有效（第 %s 次）", attempt)
                        USER_LOG.info("[步骤7 发布设置] ▶ 已打开定时发布开关")
                        return True
                except Exception as e:
                    logger.debug("定时 switch 点击失败 attempt=%s: %s", attempt, e)
                    continue

            logger.debug("定时发布：第 %s 次点击后无响应，准备重试", attempt)
            await page.wait_for_timeout(wait_ms(350))

        if checkbox is not None:
            try:
                await checkbox.check(force=True)
                await page.wait_for_timeout(wait_ms(200))
            except Exception as e:
                logger.debug("定时发布 checkbox.check 兜底失败: %s", e)

        enabled = await self._schedule_switch_enabled(page, wrapper, checkbox)
        if enabled:
            USER_LOG.info("[步骤7 发布设置] ▶ 已打开定时发布开关")
        return enabled

    @staticmethod
    def _schedule_time_display_selectors() -> List[str]:
        keys = ("SCHEDULE_TIME_DISPLAY", "SCHEDULE_TIME_INPUT", "SCHEDULE_INPUT")
        seen: set[str] = set()
        out: List[str] = []
        for key in keys:
            for sel in Selectors.SETTINGS.get(key, []):
                if sel and sel not in seen:
                    seen.add(sel)
                    out.append(sel)
        return out

    async def _find_schedule_time_display(self, page: Page) -> Optional[Locator]:
        """在定时发布区域内定位时间显示框（开关打开后出现，点击后呼出浮层）。"""
        wrapper = self._schedule_wrapper(page)
        scoped = (
            "input[type='text']",
            "input.d-text",
            ".d-datepicker-input input",
            ".d-datepicker-input",
        )
        try:
            if await wrapper.count() > 0:
                for sel in scoped:
                    loc = wrapper.locator(sel).first
                    if await loc.count() > 0:
                        return loc
        except Exception:
            pass

        for sel in self._schedule_time_display_selectors():
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    return loc
            except Exception:
                continue
        return None

    async def _click_schedule_time_display(
        self,
        page: Page,
        display: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> bool:
        """点击时间显示框，呼出 body 级日期时间选择浮层。"""
        from src.infrastructure.anti_risk.delays import random_delay
        from src.infrastructure.anti_risk.human_like import human_click

        picker_selectors = list(Selectors.SETTINGS.get("SCHEDULE_DATE_PICKER", []))
        if await PluginWaitHelper.first_visible_selector(page, picker_selectors):
            logger.info("日期时间浮层已打开，跳过重复点击时间框")
            return True

        await _scroll_locator_to_center(page, display, wait_ms=wait_ms(200))

        for attempt in range(1, 4):
            if await self._mouse_click_locator_center(page, display):
                pass
            else:
                try:
                    await human_click(page, display, metadata, config)
                except Exception:
                    try:
                        await display.click(force=True)
                    except Exception as e:
                        logger.debug("点击时间显示框失败 attempt=%s: %s", attempt, e)
                        continue
            await random_delay(page, wait_ms(300), metadata, config)
            matched = await PluginWaitHelper.first_visible_selector(page, picker_selectors)
            if matched:
                logger.info("定时时间浮层已打开（第 %s 次点击时间显示框）", attempt)
                USER_LOG.info("[步骤7 发布设置] ▶ 已点击时间显示框，日期时间选择器已打开")
                return True
            await page.wait_for_timeout(wait_ms(200))
        return False

    async def _find_schedule_checkbox(self, page: Page) -> Optional[Locator]:
        wrapper = self._schedule_wrapper(page)
        try:
            if await wrapper.count() > 0:
                box = wrapper.locator("input[type='checkbox']").first
                if await box.count() > 0:
                    return box
        except Exception:
            pass
        for sel in Selectors.SETTINGS.get("SCHEDULE_CHECKBOX", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    return loc
            except Exception:
                continue
        return None

    async def _is_schedule_picker_visible(self, page: Page) -> bool:
        for sel in Selectors.SETTINGS.get("SCHEDULE_DATE_PICKER", []) or []:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _find_visible_schedule_picker(self, page: Page) -> Optional[Locator]:
        for sel in Selectors.SETTINGS.get("SCHEDULE_DATE_PICKER", []) or []:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    async def _click_publish_page_right_blank(
        self, page: Page, wait_ms: Callable[[int], int]
    ) -> bool:
        """在页面右侧预览区空白处点击，用于关闭定时时间选择浮层。"""
        for sel in _RIGHT_BLANK_CLICK_SELECTORS:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                box = await loc.bounding_box()
                if not box or box.get("width", 0) < 40 or box.get("height", 0) < 40:
                    continue
                x = box["x"] + box["width"] * 0.55
                y = box["y"] + box["height"] * 0.35
                await page.mouse.click(x, y)
                await page.wait_for_timeout(wait_ms(150))
                logger.debug("已在右侧预览区空白点击: %s", sel)
                return True
            except Exception as e:
                logger.debug("右侧空白点击失败 %s: %s", sel, e)
                continue
        try:
            vp = await page.evaluate(
                "() => ({ w: window.innerWidth, h: window.innerHeight })"
            )
            w = float(vp.get("w") or 1200)
            h = float(vp.get("h") or 800)
            await page.mouse.click(w * 0.82, h * 0.4)
            await page.wait_for_timeout(wait_ms(150))
            logger.debug("已在视口右侧空白点击")
            return True
        except Exception as e:
            logger.debug("视口右侧空白点击失败: %s", e)
            return False

    async def _dismiss_schedule_date_picker_and_wait(
        self, page: Page, wait_ms: Callable[[int], int]
    ) -> bool:
        """设置完时间后：点右侧空白关浮层，并轮询直到浮层消失。"""
        if not await self._is_schedule_picker_visible(page):
            return True

        await self._click_publish_page_right_blank(page, wait_ms)
        elapsed = 0
        while elapsed < _SCHEDULE_PICKER_CLOSE_WAIT_MS:
            if not await self._is_schedule_picker_visible(page):
                logger.debug("定时日期浮层已关闭（右侧空白点击）")
                return True
            await page.wait_for_timeout(_SCHEDULE_PICKER_POLL_MS)
            elapsed += _SCHEDULE_PICKER_POLL_MS

        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(wait_ms(120))
        except Exception:
            pass
        await self._click_publish_page_right_blank(page, wait_ms)

        elapsed = 0
        while elapsed < _SCHEDULE_PICKER_CLOSE_WAIT_MS:
            if not await self._is_schedule_picker_visible(page):
                return True
            await page.wait_for_timeout(_SCHEDULE_PICKER_POLL_MS)
            elapsed += _SCHEDULE_PICKER_POLL_MS
        return not await self._is_schedule_picker_visible(page)

    async def _dismiss_schedule_date_picker(
        self, page: Page, wait_ms: Callable[[int], int]
    ) -> None:
        """兼容旧调用：关浮层并等待关闭。"""
        await self._dismiss_schedule_date_picker_and_wait(page, wait_ms)

    async def _verify_schedule_time_matches_task(
        self, page: Page, st_str: str
    ) -> Tuple[bool, str]:
        inp = await self._find_schedule_time_display(page)
        actual = (
            await self._read_schedule_input_value(inp) if inp is not None else ""
        )
        return self._schedule_input_value_matches(actual, st_str), actual

    async def _apply_schedule_time_with_verify(
        self,
        page: Page,
        inp: Locator,
        st_str: str,
        parts: Tuple[int, int, int, int, int],
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
        speed_rate: float,
    ) -> bool:
        """写入定时 → 右侧空白关浮层 → 校验与任务一致；不一致则重新设置。"""
        max_attempts = 1 + _SCHEDULE_TIME_VERIFY_RETRIES
        picker: Optional[Locator] = await self._find_visible_schedule_picker(page)

        for attempt in range(1, max_attempts + 1):
            if attempt > 1:
                logger.info("定时时间与任务不一致，第 %s 次重新设置", attempt)
                USER_LOG.info(
                    "[步骤7 发布设置] ▶ 定时校验未通过，正在第 %s 次重新设置",
                    attempt,
                )
                if not await self._click_schedule_time_display(
                    page, inp, metadata, config, wait_ms
                ):
                    logger.warning("重设定时：无法再次打开时间浮层")
                    continue
                picker = await self._find_visible_schedule_picker(page)

            filled = await self._set_schedule_time_via_input(
                page, inp, st_str, wait_ms, speed_rate,
            )
            if not filled and picker is not None:
                await self._pick_schedule_in_date_picker(
                    page, picker, parts, metadata, config, wait_ms,
                )
                await page.wait_for_timeout(wait_ms(300))

            closed = await self._dismiss_schedule_date_picker_and_wait(page, wait_ms)
            if not closed:
                USER_LOG.warning("[步骤7 发布设置] ▷ 定时浮层未能确认关闭")

            ok, actual = await self._verify_schedule_time_matches_task(page, st_str)
            if ok:
                logger.info(
                    "定时时间校验通过: 页面=%s 任务=%s", actual or st_str, st_str
                )
                USER_LOG.info(
                    "[步骤7 发布设置] ▶ 定时时间已校验一致: %s",
                    actual or st_str,
                )
                return True

            logger.warning(
                "定时时间校验未通过 (attempt=%s): 页面=%r 任务=%r",
                attempt,
                actual,
                st_str,
            )

        return False

    async def _pick_schedule_in_date_picker(
        self,
        page: Page,
        picker: Locator,
        parts: Tuple[int, int, int, int, int],
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        wait_ms: Callable[[int], int],
    ) -> bool:
        """在日期时间浮层内选择日、时、分（限定浮层作用域 + 中心点击，避免误触开关）。"""
        _year, _month, day, hour, minute = parts
        day_s = str(day)
        hour_s = f"{hour:02d}"
        minute_s = f"{minute:02d}"

        try:
            calendar = picker.locator(".d-datepicker-calendar").first
            if await calendar.count() > 0:
                day_cell = calendar.locator(
                    ".d-datepicker-cell:not(.disabled)"
                ).get_by_text(day_s, exact=True).first
                await self._click_picker_item(page, day_cell, wait_ms)
                await page.wait_for_timeout(wait_ms(150))
        except Exception as e:
            logger.debug("选择日期格失败: %s", e)

        minute_clicked = False
        try:
            time_body = picker.locator(".d-timepicker-body").first
            if await time_body.count() > 0:
                bars = time_body.locator(".d-timepicker-timebar")
                if await bars.count() >= 1:
                    hour_item = bars.nth(0).locator(".d-timepicker-time").get_by_text(
                        hour_s, exact=True
                    ).first
                    await self._click_picker_item(page, hour_item, wait_ms)
                    await page.wait_for_timeout(wait_ms(120))
                if await bars.count() >= 2:
                    minute_item = bars.nth(1).locator(".d-timepicker-time").get_by_text(
                        minute_s, exact=True
                    ).first
                    minute_clicked = await self._click_picker_item(
                        page, minute_item, wait_ms
                    )
                    await page.wait_for_timeout(wait_ms(250))
        except Exception as e:
            logger.debug("选择时分失败: %s", e)

        return minute_clicked

    async def _fill_schedule_input_fallback(
        self,
        page: Page,
        inp: Locator,
        st_str: str,
        wait_ms: Callable[[int], int],
        speed_rate: float,
    ) -> bool:
        return await self._set_schedule_time_via_input(
            page, inp, st_str, wait_ms, speed_rate,
        )

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
            if not st_str:
                return PublishResult(
                    success=False,
                    error_message="定时发布时间格式无效",
                    failed_step=self._FAILED_STEP,
                )

            parts = parse_schedule_st_str(st_str)
            if parts is None:
                return PublishResult(
                    success=False,
                    error_message=f"定时发布时间格式无效: {st_str}",
                    failed_step=self._FAILED_STEP,
                )

            logger.info("检测到定时发布时间: %s", st_str)
            USER_LOG.info("[步骤7 发布设置] ▶ 尝试设置定时: %s", st_str)

            await self._ensure_schedule_area_visible(page, wait_ms)

            wrapper = self._schedule_wrapper(page)
            if await wrapper.count() == 0:
                logger.warning("未找到定时发布区域")
                USER_LOG.warning("[步骤7 发布设置] ✗ 未找到定时发布选项")
                return PublishResult(
                    success=False,
                    error_message="未找到定时发布选项，定时发布设置失败",
                    failed_step=self._FAILED_STEP,
                )

            ok_switch = await self._click_schedule_switch_to_open(
                page, metadata, config, wait_ms,
            )
            if not ok_switch:
                logger.warning("未能打开定时发布开关")
                USER_LOG.warning("[步骤7 发布设置] ✗ 未能打开定时发布开关")
                return PublishResult(
                    success=False,
                    error_message="未能打开定时发布开关",
                    failed_step=self._FAILED_STEP,
                )

            await page.wait_for_timeout(wait_ms(400))

            display_selectors = self._schedule_time_display_selectors()
            matched_sel = await PluginWaitHelper.wait_for_any_attached(
                page,
                display_selectors,
                timeout_ms=10000,
                poll_interval_ms=250,
                pause_callback=lambda: self._await_pause(metadata),
            )
            inp = await self._find_schedule_time_display(page)
            if inp is None and matched_sel:
                inp = page.locator(matched_sel).first
            if inp is None:
                logger.warning("选中定时发布后，时间显示框未出现在 DOM 中")
                USER_LOG.warning("[步骤7 发布设置] ✗ 时间显示框未出现")
                return PublishResult(
                    success=False,
                    error_message="选中定时发布后未出现时间显示框",
                    failed_step=self._FAILED_STEP,
                )

            picker_opened = await self._click_schedule_time_display(
                page, inp, metadata, config, wait_ms,
            )
            if not picker_opened:
                logger.warning("已打开定时发布，但点击时间显示框后日期时间浮层未出现")
                USER_LOG.warning("[步骤7 发布设置] ✗ 点击时间显示框后选择器未打开")
                return PublishResult(
                    success=False,
                    error_message="点击时间显示框后未出现日期时间选择器",
                    failed_step=self._FAILED_STEP,
                )

            time_ok = await self._apply_schedule_time_with_verify(
                page,
                inp,
                st_str,
                parts,
                metadata,
                config,
                wait_ms,
                speed_rate,
            )
            if not time_ok:
                await self._ensure_schedule_switch_on(page, metadata, config, wait_ms)
                logger.warning("定时时间与任务不一致或未能写入")
                USER_LOG.warning(
                    "[步骤7 发布设置] ✗ 定时时间与任务不一致，设置失败"
                )
                return PublishResult(
                    success=False,
                    error_message=f"定时发布时间与任务不一致（期望 {st_str}）",
                    failed_step=self._FAILED_STEP,
                )

            await self._ensure_schedule_switch_on(
                page, metadata, config, wait_ms,
            )
            if not await self._read_schedule_switch_visual_on(
                self._schedule_wrapper(page)
            ):
                logger.warning("定时时间已校验通过但开关仍为关闭")
                USER_LOG.warning(
                    "[步骤7 发布设置] ✗ 定时时间已填但开关被关闭，请人工核对"
                )
                return PublishResult(
                    success=False,
                    error_message="定时时间已设置但定时发布开关被关闭",
                    failed_step=self._FAILED_STEP,
                )

            logger.info("已设置并校验定时时间: %s", st_str)
            USER_LOG.info("[步骤7 发布设置] ▶ 已设置定时: %s", st_str)
            await dismiss_schedule_date_picker_and_wait(page, wait_ms)
            await blur_publish_form_focus(page, wait_ms)
            return None
        except Exception as e:
            logger.warning("定时/立即发布设置异常: %s", e)
            if schedule_time:
                return PublishResult(
                    success=False,
                    error_message=f"定时发布设置异常: {e}",
                    failed_step=self._FAILED_STEP,
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

        checkbox: Optional[Locator] = None
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
                    trial = box.locator("input[type='checkbox']").first
                    if await trial.count() > 0:
                        checkbox = trial
                        break
                    trial = box.locator('[role="switch"]').first
                    if await trial.count() > 0 and await trial.is_visible():
                        checkbox = trial
                        break
                if checkbox is not None:
                    break

            if checkbox is None:
                for sel in anchor_selectors:
                    try:
                        anchor = page.locator(sel).first
                        if await anchor.count() > 0:
                            await anchor.scroll_into_view_if_needed()
                            await random_delay(page, wait_ms(150), metadata, config)
                            parent = anchor.locator("xpath=ancestor::div[position()<=14]")
                            trial = parent.locator("input[type='checkbox']").first
                            if await trial.count() > 0:
                                checkbox = trial
                                break
                            trial = parent.locator('[role="switch"]').first
                            if await trial.count() > 0:
                                checkbox = trial
                                break
                    except Exception:
                        continue

            if checkbox is None:
                return False

            try:
                tag = await checkbox.evaluate("el => el.tagName && el.tagName.toLowerCase()")
            except Exception:
                tag = ""
            if tag == "input":
                try:
                    is_on = await checkbox.is_checked()
                except Exception:
                    is_on = False
                if is_on != want_on:
                    if want_on:
                        await checkbox.check(force=True)
                    else:
                        await checkbox.uncheck(force=True)
                    await random_delay(page, wait_ms(280), metadata, config)
                return True

            cur = (await checkbox.get_attribute("aria-checked") or "").strip().lower()
            is_on = cur == "true"
            if is_on != want_on:
                await human_click(page, checkbox, metadata, config)
                await random_delay(page, wait_ms(280), metadata, config)
            return True
        except Exception as e:
            logger.debug("同步开关异常 hints=%s: %s", label_hints, e)
            return False
