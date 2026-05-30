# -*- coding: utf-8 -*-
"""
步骤6B：内容类型声明
文件路径: src/plugins/pro/xiaohongshu/steps/step_06B_work_declaration.py

流程：
  根据 metadata.privacy_settings 的小红书内容属性配置，打开「添加内容类型声明」并选择目标选项。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from playwright.async_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_CONTENT_PANEL_ANCHOR = "虚构演绎，仅供娱乐"
_SOURCE_DECLARATION_LABEL = "内容来源声明"
_ORIGINAL_DIALOG_FEATURE = "笔记完成原创声明后"

_PANEL_WAIT_MS = 6_000
_PANEL_POLL_MS = 150
_ENTRY_CLICK_RETRIES = 3
_POST_6A_SETTLE_MS = 250
_ENTRY_VERIFY_MS = 4_000
_ENTRY_VERIFY_POLL_MS = 150
_SELECTION_RETRY_MAX = 2
_SCROLL_SETTLE_MS = 180


async def _scroll_locator_to_center(page: Page, locator: Locator, *, wait_ms: int = _SCROLL_SETTLE_MS) -> None:
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
        await HumanBehavior.scroll_to_locator(page, locator, target_ratio=0.5)
        await page.wait_for_timeout(wait_ms)
    except Exception as e:
        logger.debug("滚入视口中部失败: %s", e)


class WorkDeclarationStep(BasePublishStep):
    """小红书内容类型声明。"""

    _FAILED_STEP = "WorkDeclarationStep"

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        from src.domain.publish.work_declaration import (
            KEY_XHS_CONTENT_ATTR,
            KEY_XHS_CONTENT_ATTR_AUTO,
            declaration_auto_apply,
            label_for_xhs_content_attr,
            normalize_xhs_content_attr,
            parse_privacy_settings_dict,
        )

        privacy_settings = parse_privacy_settings_dict(metadata.get("privacy_settings"))
        for key in (KEY_XHS_CONTENT_ATTR, KEY_XHS_CONTENT_ATTR_AUTO):
            if key in metadata and metadata[key] is not None:
                privacy_settings[key] = metadata[key]

        prefix = self._step_prefix(metadata, "内容类型声明")
        if KEY_XHS_CONTENT_ATTR_AUTO not in privacy_settings:
            USER_LOG.info("%s — 跳过（任务未包含小红书内容类型声明配置）", prefix)
            return None

        if not declaration_auto_apply(privacy_settings, KEY_XHS_CONTENT_ATTR_AUTO):
            USER_LOG.info("%s — 跳过（已关闭发布时自动设置内容类型声明）", prefix)
            return None

        attr_value = normalize_xhs_content_attr(
            str(privacy_settings.get(KEY_XHS_CONTENT_ATTR) or "") or None
        )
        target_label = label_for_xhs_content_attr(attr_value)
        if not target_label:
            msg = f"小红书内容类型声明配置无效: {attr_value}"
            logger.warning(msg)
            USER_LOG.warning("%s ✗ %s", prefix, msg)
            return PublishResult(success=False, error_message=msg, failed_step=self._FAILED_STEP)

        logger.info("===== 小红书内容类型声明：目标=%s =====", target_label)

        await self._ensure_no_blocking_dialog(page)
        await page.wait_for_timeout(_POST_6A_SETTLE_MS)
        await self._scroll_content_settings_into_view(page)

        if await self._target_label_visible_in_settings(page, target_label):
            USER_LOG.info("%s ✓ 页面已显示目标选项：%s", prefix, target_label)
            return None

        entry = await self._find_entry(page)
        if entry is None:
            msg = "小红书内容类型声明：未找到「添加内容类型声明」入口"
            logger.warning(msg)
            USER_LOG.warning("%s ✗ %s", prefix, msg)
            return PublishResult(success=False, error_message=msg, failed_step=self._FAILED_STEP)

        config = metadata.get("anti_risk_config") or {}
        applied = await self._apply_content_type_selection(
            page, entry, target_label, metadata, config
        )
        if not applied:
            msg = f"小红书内容类型声明：选择后入口未显示「{target_label}」"
            logger.warning(msg)
            USER_LOG.warning("%s ✗ %s", prefix, msg)
            return PublishResult(success=False, error_message=msg, failed_step=self._FAILED_STEP)

        USER_LOG.info("%s ✓ 已选择：%s", prefix, target_label)
        return None

    def _content_settings_root(self, page: Page) -> Locator:
        for sel in Selectors.SETTINGS.get("CONTENT_SETTINGS_SECTION", []):
            return page.locator(sel).first
        return page.locator(".publish-page-content-content-extra").first

    async def _ensure_no_blocking_dialog(self, page: Page) -> None:
        """6A 若遗留原创权益弹窗，会挡住内容类型入口。"""
        for sel in Selectors.SETTINGS.get("ORIGINAL_DECLARATION_DIALOG", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0 or not await loc.is_visible():
                    continue
                try:
                    close_btn = loc.locator(
                        "button[aria-label='关闭'], .d-modal-close, .close"
                    ).first
                    if await close_btn.count() > 0 and await close_btn.is_visible():
                        await close_btn.click(timeout=2000)
                        await page.wait_for_timeout(300)
                        logger.info("已关闭残留的原创权益弹窗")
                        return
                except Exception:
                    pass
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(300)
                logger.info("已尝试 Escape 关闭原创权益弹窗")
                return
            except Exception:
                continue

        try:
            feat = page.get_by_text(_ORIGINAL_DIALOG_FEATURE, exact=False).first
            if await feat.count() > 0 and await feat.is_visible():
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(300)
        except Exception:
            pass

    async def _scroll_content_settings_into_view(self, page: Page) -> None:
        try:
            root = self._content_settings_root(page)
            if await root.count() > 0:
                await _scroll_locator_to_center(page, root)
                return
        except Exception:
            pass
        for hint in ("添加内容类型声明", "内容设置", "原创声明"):
            try:
                loc = page.locator("div").filter(has_text=hint).first
                if await loc.count() > 0:
                    await _scroll_locator_to_center(page, loc)
                    return
            except Exception:
                continue

    async def _find_entry(self, page: Page) -> Optional[Locator]:
        root = self._content_settings_root(page)
        try:
            if await root.count() > 0:
                scoped = root.locator(".d-select-wrapper").filter(
                    has_text="添加内容类型声明"
                ).first
                if await scoped.count() > 0 and await scoped.is_visible():
                    return scoped
        except Exception:
            pass

        for sel in Selectors.SETTINGS.get("CONTENT_TYPE_DECLARATION_ENTRY", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    async def _target_label_visible_in_settings(self, page: Page, target_label: str) -> bool:
        if await self._target_label_visible_via_evaluate(page, target_label):
            return True

        root = self._content_settings_root(page)
        try:
            if await root.count() > 0:
                entry = root.locator(".d-select-wrapper").filter(has_text=target_label).first
                if await entry.count() > 0 and await entry.is_visible():
                    return True
        except Exception:
            pass

        for hint in ("内容设置", "内容类型声明", "添加内容类型声明"):
            try:
                scoped = (
                    page.locator(".publish-page-content-content-extra")
                    .locator(".d-select-wrapper")
                    .filter(has_text=hint)
                    .filter(has_text=target_label)
                    .first
                )
                if await scoped.count() > 0 and await scoped.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _target_label_visible_via_evaluate(self, page: Page, target_label: str) -> bool:
        try:
            return bool(
                await page.evaluate(
                    """(label) => {
                        const root = document.querySelector(
                            '.publish-page-content-content-extra'
                        );
                        if (!root) return false;
                        const wrappers = root.querySelectorAll('.d-select-wrapper');
                        for (const w of wrappers) {
                            const t = (w.innerText || '').trim();
                            if (t.includes(label)) return true;
                        }
                        return false;
                    }""",
                    target_label,
                )
            )
        except Exception as e:
            logger.debug("evaluate 检测入口文案失败: %s", e)
            return False

    async def _wait_target_label_in_settings(
        self,
        page: Page,
        target_label: str,
        *,
        timeout_ms: int = _ENTRY_VERIFY_MS,
    ) -> bool:
        elapsed = 0
        while elapsed < timeout_ms:
            if await self._target_label_visible_in_settings(page, target_label):
                return True
            await page.wait_for_timeout(_ENTRY_VERIFY_POLL_MS)
            elapsed += _ENTRY_VERIFY_POLL_MS
        return await self._target_label_visible_in_settings(page, target_label)

    async def _wait_content_panel_closed(
        self, page: Page, *, timeout_ms: int = 2_000
    ) -> None:
        elapsed = 0
        while elapsed < timeout_ms:
            if not await self._is_content_panel_visible(page):
                return
            await page.wait_for_timeout(_PANEL_POLL_MS)
            elapsed += _PANEL_POLL_MS

    async def _apply_content_type_selection(
        self,
        page: Page,
        entry: Locator,
        target_label: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        for attempt in range(1, _SELECTION_RETRY_MAX + 1):
            panel = await self._open_content_type_panel(page, entry, metadata, config)
            if panel is None:
                if attempt >= _SELECTION_RETRY_MAX:
                    logger.warning("小红书内容类型声明：未出现内容类型下拉浮层")
                    return False
                await page.wait_for_timeout(200)
                continue

            if not await self._click_target_option(
                page, panel, target_label, metadata, config
            ):
                await self._dismiss_open_content_panel(page)
                if attempt >= _SELECTION_RETRY_MAX:
                    logger.warning(
                        "小红书内容类型声明：未找到目标选项「%s」", target_label
                    )
                    return False
                await page.wait_for_timeout(200)
                continue

            await self._click_confirm_if_present(page)
            await self._wait_content_panel_closed(page)

            if target_label == _SOURCE_DECLARATION_LABEL:
                sub_panel = await self._wait_content_type_panel(page, timeout_ms=3000)
                if sub_panel is not None:
                    logger.info("小红书内容类型声明：已展开「内容来源声明」子项浮层")
                    await self._click_confirm_if_present(page)
                    await self._wait_content_panel_closed(page)

            if await self._wait_target_label_in_settings(page, target_label):
                return True

            logger.debug(
                "小红书内容类型声明：第 %s 次选择后入口未刷新，准备重试",
                attempt,
            )
            await self._dismiss_open_content_panel(page)
            await page.wait_for_timeout(200)

        return False

    def _panel_anchor_text(self) -> str:
        anchors = Selectors.SETTINGS.get("CONTENT_TYPE_DECLARATION_PANEL_ANCHOR", [])
        return anchors[0] if anchors else _CONTENT_PANEL_ANCHOR

    async def _is_content_panel_visible(self, page: Page) -> bool:
        anchor = self._panel_anchor_text()
        try:
            loc = (
                page.locator("body > .d-popover.d-dropdown")
                .filter(has_text=anchor)
                .first
            )
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            pass
        try:
            loc = page.get_by_text(anchor, exact=True).first
            if await loc.count() > 0 and await loc.is_visible():
                parent = loc.locator("xpath=ancestor::div[contains(@class,'d-popover')]").first
                if await parent.count() > 0 and await parent.is_visible():
                    return True
        except Exception:
            pass
        return False

    async def _find_content_panel_locator(self, page: Page) -> Optional[Locator]:
        anchor = self._panel_anchor_text()
        try:
            loc = (
                page.locator("body > .d-popover.d-dropdown")
                .filter(has_text=anchor)
                .first
            )
            if await loc.count() > 0 and await loc.is_visible():
                return loc
        except Exception:
            pass

        for sel in Selectors.SETTINGS.get("CONTENT_TYPE_DECLARATION_PANEL", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    async def _wait_content_type_panel(
        self, page: Page, *, timeout_ms: int = _PANEL_WAIT_MS
    ) -> Optional[Locator]:
        elapsed = 0
        while elapsed < timeout_ms:
            panel = await self._find_content_panel_locator(page)
            if panel is not None:
                return panel
            await page.wait_for_timeout(_PANEL_POLL_MS)
            elapsed += _PANEL_POLL_MS
        return None

    async def _dismiss_open_content_panel(self, page: Page) -> None:
        if not await self._is_content_panel_visible(page):
            return
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(250)
        except Exception:
            pass

    async def _open_content_type_panel(
        self,
        page: Page,
        entry: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Optional[Locator]:
        from src.infrastructure.anti_risk.human_like import human_click

        await self._dismiss_open_content_panel(page)

        for attempt in range(_ENTRY_CLICK_RETRIES):
            try:
                await _scroll_locator_to_center(page, entry)
                await human_click(page, entry, metadata, config)
            except Exception as e:
                logger.debug("内容类型入口点击失败 (attempt=%s): %s", attempt + 1, e)
                if attempt + 1 >= _ENTRY_CLICK_RETRIES:
                    return None
                continue

            panel = await self._wait_content_type_panel(
                page, timeout_ms=3000 if attempt == 0 else _PANEL_WAIT_MS
            )
            if panel is not None:
                return panel

            await page.wait_for_timeout(150)

        return None

    async def _visible_option_containers(self, page: Page) -> Sequence[Locator]:
        panel = await self._find_content_panel_locator(page)
        if panel is not None:
            return [panel]

        out: list[Locator] = []
        for sel in Selectors.SETTINGS.get("CONTENT_TYPE_DECLARATION_PANEL", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    out.append(loc)
            except Exception:
                continue
        return out

    async def _click_target_option(
        self,
        page: Page,
        panel: Locator,
        target_label: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        containers = [panel]
        extra = await self._visible_option_containers(page)
        for c in extra:
            if c not in containers:
                containers.append(c)

        for container in containers:
            if await self._click_text_inside(container, target_label, page, metadata, config):
                return True
        return False

    async def _click_text_inside(
        self,
        root: Locator,
        text: str,
        page: Page,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        from src.infrastructure.anti_risk.human_like import human_click

        candidates = [
            root.get_by_text(text, exact=True).first,
            root.locator(f"label:has-text('{text}')").first,
            root.locator(f"div.d-grid-item:has-text('{text}')").first,
            root.locator(f"div:has-text('{text}')").first,
            root.locator(f"span:has-text('{text}')").first,
        ]
        for loc in candidates:
            try:
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.scroll_into_view_if_needed()
                    try:
                        await human_click(
                            page,
                            loc,
                            metadata,
                            config,
                            use_operation_delay=False,
                        )
                    except Exception:
                        await loc.click(timeout=3000)
                    await page.wait_for_timeout(80)
                    return True
            except Exception:
                continue
        return False

    async def _click_confirm_if_present(self, page: Page) -> None:
        for sel in Selectors.SETTINGS.get("CONTENT_TYPE_DECLARATION_CONFIRM", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=3000)
                    return
            except Exception:
                continue
