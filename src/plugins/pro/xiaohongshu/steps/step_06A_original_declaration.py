# -*- coding: utf-8 -*-
"""
步骤6A：原创申明
文件路径: src/plugins/pro/xiaohongshu/steps/step_06A_original_declaration.py

流程：
  根据 metadata.privacy_settings.xiaohongshu_is_original 同步发布页「原创声明」开关。
  开启时优先点击开关；若出现权益弹窗则勾选协议并确认；若开关已变红且无弹窗则视为已完成。
"""
import logging
from typing import Any, Dict, Optional, Sequence

from src.infrastructure.browser.automation_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_SETTINGS_SECTION_HINTS: Sequence[str] = (
    "原创声明",
    "内容设置",
    "添加内容类型声明",
)

_DIALOG_FEATURE_TEXTS: Sequence[str] = (
    "笔记完成原创声明后",
    "原创声明须知",
    "获得原创笔记标记",
    "我已阅读并同意",
)
_DIALOG_WAIT_MS = 5_000
_DIALOG_POLL_MS = 150
_DIALOG_CLOSE_WAIT_MS = 4_000
_DIALOG_AFTER_ENABLE_WAIT_MS = 3_000
_POST_CLICK_SETTLE_MS = 150
_SWITCH_CLICK_MAX_ATTEMPTS = 3
_SWITCH_RESPONSE_WAIT_MS = 1_500
_CONFIRM_ENABLE_POLL_MS = 100
_CONFIRM_ENABLE_MAX_MS = 2_500
_SCROLL_SETTLE_MS = 180


async def _scroll_locator_to_center(page: Page, locator: Locator, *, wait_ms: int = _SCROLL_SETTLE_MS) -> None:
    """将元素滚到视口中部（比 scroll_into_view_if_needed 更适合长页表单）。"""
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
        await HumanBehavior.scroll_to_locator(page, locator, target_ratio=0.5)
        await page.wait_for_timeout(wait_ms)
    except Exception as e:
        logger.debug("滚入视口中部失败: %s", e)


class OriginalDeclarationStep(BasePublishStep):
    """小红书原创声明。"""

    _FAILED_STEP = "OriginalDeclarationStep"

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        from src.domain.publish.work_declaration import (
            KEY_XHS_ORIGINAL,
            parse_privacy_settings_dict,
        )

        privacy_settings = parse_privacy_settings_dict(metadata.get("privacy_settings"))
        if KEY_XHS_ORIGINAL in metadata and metadata[KEY_XHS_ORIGINAL] is not None:
            privacy_settings[KEY_XHS_ORIGINAL] = metadata[KEY_XHS_ORIGINAL]
        prefix = self._step_prefix(metadata, "原创声明")

        if KEY_XHS_ORIGINAL not in privacy_settings:
            USER_LOG.info("%s — 跳过（任务未包含小红书原创声明配置）", prefix)
            return None

        want_checked = bool(privacy_settings.get(KEY_XHS_ORIGINAL, False))
        logger.info("===== 小红书原创声明：目标=%s =====", "勾选" if want_checked else "不勾选")

        await self._scroll_settings_section_into_view(page)

        checkbox = await self._find_original_checkbox(page)
        if checkbox is None:
            msg = "小红书原创声明：未找到「原创声明」邻近复选框"
            logger.warning(msg)
            USER_LOG.warning("%s ✗ %s", prefix, msg)
            return PublishResult(success=False, error_message=msg, failed_step=self._FAILED_STEP)

        config = metadata.get("anti_risk_config") or {}

        if want_checked and await self._verify_original_enabled(page, checkbox):
            USER_LOG.info("%s ✓ 已是目标状态：申明原创", prefix)
            return None

        if not want_checked:
            try:
                is_checked = await checkbox.is_checked()
            except Exception:
                is_checked = False
            visual_on = await self._read_switch_visual_on(page)
            if not is_checked and not visual_on:
                USER_LOG.info("%s ✓ 已是目标状态：不申明原创", prefix)
                return None

        ok = await self._set_original_checked(
            page, checkbox, want_checked, metadata, config
        )
        if not ok:
            msg = (
                "小红书原创声明：权益弹窗流程未完成"
                if want_checked
                else "小红书原创声明：关闭开关失败"
            )
            logger.warning(msg)
            USER_LOG.warning("%s ✗ %s", prefix, msg)
            return PublishResult(success=False, error_message=msg, failed_step=self._FAILED_STEP)

        await page.wait_for_timeout(150)

        if want_checked:
            if not await self._verify_original_enabled(page, checkbox):
                msg = "小红书原创声明：弹窗流程后开关未处于开启状态（需红色 ON）"
                logger.warning(msg)
                USER_LOG.warning("%s ✗ %s", prefix, msg)
                return PublishResult(success=False, error_message=msg, failed_step=self._FAILED_STEP)
        else:
            try:
                verified = await checkbox.is_checked()
            except Exception:
                verified = True
            visual_on = await self._read_switch_visual_on(page)
            if verified or visual_on:
                msg = "小红书原创声明：点击后开关仍未关闭"
                logger.warning(msg)
                USER_LOG.warning("%s ✗ %s", prefix, msg)
                return PublishResult(success=False, error_message=msg, failed_step=self._FAILED_STEP)

        USER_LOG.info("%s ✓ 已设置：%s", prefix, "申明原创" if want_checked else "不申明原创")
        return None

    def _content_settings_root(self, page: Page) -> Locator:
        for sel in Selectors.SETTINGS.get("CONTENT_SETTINGS_SECTION", []):
            loc = page.locator(sel).first
            return loc
        return page.locator(".publish-page-content-content-extra").first

    def _original_wrapper(self, page: Page) -> Locator:
        return page.locator(".original-wrapper").first

    async def _scroll_settings_section_into_view(self, page: Page) -> None:
        """步骤5 常把视口停在描述区，先滚到「内容设置/原创声明」区域。"""
        try:
            root = self._content_settings_root(page)
            if await root.count() > 0:
                await _scroll_locator_to_center(page, root)
                logger.debug("已滚入内容设置区: publish-page-content-content-extra")
                return
        except Exception:
            pass

        wrapper = self._original_wrapper(page)
        try:
            if await wrapper.count() > 0:
                await _scroll_locator_to_center(page, wrapper)
                logger.debug("已滚入原创声明卡片: original-wrapper")
                return
        except Exception:
            pass

        for hint in _SETTINGS_SECTION_HINTS:
            try:
                loc = page.locator("div").filter(has_text=hint).first
                if await loc.count() > 0:
                    await _scroll_locator_to_center(page, loc)
                    logger.debug("已滚入设置区锚点: %s", hint)
                    return
            except Exception:
                continue

    async def _find_original_label(self, page: Page) -> Optional[Locator]:
        wrapper = self._original_wrapper(page)
        try:
            if await wrapper.count() > 0:
                return wrapper
        except Exception:
            pass

        for sel in Selectors.SETTINGS.get("WORK_ORIGINAL_LABEL", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    return loc
            except Exception:
                continue
        return None

    async def _find_original_checkbox(self, page: Page) -> Optional[Locator]:
        wrapper = self._original_wrapper(page)
        try:
            if await wrapper.count() > 0:
                box = wrapper.locator("input[type='checkbox']").first
                if await box.count() > 0:
                    return box
        except Exception:
            pass

        for sel in Selectors.SETTINGS.get("ORIGINAL_DECLARATION_CHECKBOX", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    return loc
            except Exception:
                continue

        label = await self._find_original_label(page)
        if label is None:
            return None
        return await self._find_switch_near_anchor(page, label)

    async def _find_switch_near_anchor(self, page: Page, anchor: Locator) -> Optional[Locator]:
        """图文等旧版可能为 role=switch；视频页多为 d-switch 内 checkbox。"""
        for depth in range(1, 15):
            try:
                parent = anchor.locator(f"xpath=ancestor::div[{depth}]")
                sw = parent.locator('[role="switch"]').first
                if await sw.count() > 0:
                    return sw
                box = parent.locator("input[type='checkbox']").first
                if await box.count() > 0:
                    return box
            except Exception:
                continue
        return None

    async def _read_switch_visual_on(self, page: Page) -> bool:
        """d-switch-simulator 不含 unchecked 类，或含 checked 类，表示开关视觉为 ON。"""
        try:
            result = await page.evaluate(
                """() => {
                    const wrap = document.querySelector('.original-wrapper');
                    if (!wrap) return false;
                    const sim = wrap.querySelector('.d-switch-simulator');
                    if (!sim) return false;
                    const cls = sim.className || '';
                    if (cls.includes('unchecked')) return false;
                    if (cls.includes('checked')) return true;
                    const cb = wrap.querySelector('input[type="checkbox"]');
                    return !!(cb && cb.checked);
                }"""
            )
            return bool(result)
        except Exception:
            pass
        wrapper = self._original_wrapper(page)
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
            return True
        except Exception:
            return False

    async def _dialog_open_via_evaluate(self, page: Page) -> bool:
        try:
            return bool(
                await page.evaluate(
                    """() => {
                    const texts = [
                        '笔记完成原创声明后',
                        '原创声明须知',
                        '获得原创笔记标记',
                    ];
                    const hasConfirmBtn = (root) => {
                        const buttons = root.querySelectorAll('button');
                        for (const b of buttons) {
                            const t = (b.textContent || '').trim();
                            if (t === '声明原创' || t === '申明原创') {
                                const st = window.getComputedStyle(b);
                                if (st.display !== 'none' && st.visibility !== 'hidden') {
                                    const r = b.getBoundingClientRect();
                                    if (r.width > 2 && r.height > 2) return true;
                                }
                            }
                        }
                        return false;
                    };
                    const walk = (el) => {
                        if (!el || el.nodeType !== 1) return false;
                        const tx = (el.innerText || '').slice(0, 800);
                        const hit = texts.some((t) => tx.includes(t));
                        const agree = tx.includes('我已阅读并同意');
                        if ((hit || agree) && hasConfirmBtn(el)) {
                            const st = window.getComputedStyle(el);
                            if (st.display === 'none' || st.visibility === 'hidden') return false;
                            const r = el.getBoundingClientRect();
                            if (r.width > 80 && r.height > 80) return true;
                        }
                        for (const ch of el.children || []) {
                            if (walk(ch)) return true;
                        }
                        return false;
                    };
                    const roots = document.querySelectorAll(
                        'div[role="dialog"], div.d-modal, div.d-modal-wrapper, body > div'
                    );
                    for (const root of roots) {
                        if (walk(root)) return true;
                    }
                    return walk(document.body);
                }"""
                )
            )
        except Exception as e:
            logger.debug("evaluate 检测原创弹窗失败: %s", e)
            return False

    async def _find_dialog_locator(self, page: Page) -> Optional[Locator]:
        for sel in Selectors.SETTINGS.get("ORIGINAL_DECLARATION_DIALOG", []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        for text in _DIALOG_FEATURE_TEXTS:
            try:
                loc = page.get_by_text(text, exact=False).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    async def _is_original_dialog_open(self, page: Page) -> bool:
        if await self._dialog_open_via_evaluate(page):
            return True
        dialog = await self._find_dialog_locator(page)
        if dialog is not None:
            return True
        try:
            agree = page.get_by_text("我已阅读并同意", exact=False).first
            confirm = page.locator("button:has-text('声明原创'), button:has-text('申明原创')").first
            if (
                await agree.count() > 0
                and await agree.is_visible()
                and await confirm.count() > 0
                and await confirm.is_visible()
            ):
                return True
        except Exception:
            pass
        return False

    async def _wait_original_dialog(self, page: Page, *, timeout_ms: int = _DIALOG_WAIT_MS) -> bool:
        elapsed = 0
        while elapsed < timeout_ms:
            if await self._is_original_dialog_open(page):
                return True
            await page.wait_for_timeout(_DIALOG_POLL_MS)
            elapsed += _DIALOG_POLL_MS
        return False

    async def _wait_dialog_closed(self, page: Page, *, timeout_ms: int = _DIALOG_CLOSE_WAIT_MS) -> bool:
        elapsed = 0
        while elapsed < timeout_ms:
            if not await self._is_original_dialog_open(page):
                return True
            await page.wait_for_timeout(_DIALOG_POLL_MS)
            elapsed += _DIALOG_POLL_MS
        return False

    async def _find_agreement_target(self, page: Page) -> Optional[Locator]:
        dialog = await self._find_dialog_locator(page)
        scopes: list[Locator | Page] = []
        if dialog is not None:
            scopes.append(dialog)
        scopes.append(page)

        for scope in scopes:
            for sel in Selectors.SETTINGS.get("ORIGINAL_DECLARATION_AGREEMENT", []):
                try:
                    loc = scope.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        return loc
                except Exception:
                    continue
            try:
                loc = scope.get_by_text("我已阅读并同意", exact=False).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    async def _find_confirm_button(self, page: Page) -> Optional[Locator]:
        dialog = await self._find_dialog_locator(page)
        scopes: list[Locator | Page] = []
        if dialog is not None:
            scopes.append(dialog)
        scopes.append(page)

        for scope in scopes:
            for sel in Selectors.SETTINGS.get("ORIGINAL_DECLARATION_CONFIRM_BTN", []):
                try:
                    loc = scope.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        return loc
                except Exception:
                    continue
        return None

    async def _is_confirm_button_enabled(self, button: Locator) -> bool:
        try:
            if await button.is_disabled():
                return False
        except Exception:
            pass
        try:
            disabled = await button.get_attribute("disabled")
            if disabled is not None:
                return False
            aria = (await button.get_attribute("aria-disabled") or "").strip().lower()
            if aria in ("true", "1"):
                return False
        except Exception:
            pass
        try:
            cls = (await button.get_attribute("class")) or ""
            if "disabled" in cls.lower():
                return False
        except Exception:
            pass
        return True

    async def _click_agreement_in_dialog(
        self,
        page: Page,
        agreement: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        from src.infrastructure.anti_risk.human_like import human_click

        try:
            await _scroll_locator_to_center(page, agreement, wait_ms=100)
            if await self._mouse_click_locator_center(page, agreement):
                await page.wait_for_timeout(120)
                logger.info("已通过中心坐标点击勾选协议")
                return True
            await human_click(
                page,
                agreement,
                metadata,
                config,
                use_operation_delay=False,
            )
            await page.wait_for_timeout(120)
            return True
        except Exception as e:
            logger.debug("点击协议区域失败: %s", e)
            return False

    async def _wait_confirm_button_enabled(
        self,
        page: Page,
        confirm: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        from src.infrastructure.anti_risk.human_like import human_click

        elapsed = 0
        while elapsed < _CONFIRM_ENABLE_MAX_MS:
            if await self._is_confirm_button_enabled(confirm):
                return True
            agreement = await self._find_agreement_target(page)
            if agreement is not None:
                await self._click_agreement_in_dialog(page, agreement, metadata, config)
            await page.wait_for_timeout(_CONFIRM_ENABLE_POLL_MS)
            elapsed += _CONFIRM_ENABLE_POLL_MS
            confirm = await self._find_confirm_button(page)
            if confirm is None:
                return False
        return await self._is_confirm_button_enabled(confirm)

    async def _complete_original_dialog(
        self,
        page: Page,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        agreement = await self._find_agreement_target(page)
        if agreement is None:
            logger.warning("小红书原创声明：弹窗内未找到协议勾选区域")
            return False

        if not await self._click_agreement_in_dialog(page, agreement, metadata, config):
            logger.warning("小红书原创声明：勾选协议失败")
            return False
        USER_LOG.info(
            "%s ▶ 已勾选「我已阅读并同意」",
            self._step_prefix(metadata, "原创声明"),
        )

        new_confirm = await self._find_confirm_button(page)
        if new_confirm is None:
            logger.warning("小红书原创声明：弹窗内未找到「声明原创」按钮")
            return False
        confirm_btn = new_confirm

        if not await self._wait_confirm_button_enabled(page, confirm_btn, metadata, config):
            logger.warning("小红书原创声明：「声明原创」按钮仍不可用")
            return False

        try:
            await _scroll_locator_to_center(page, confirm_btn, wait_ms=100)
            if not await self._mouse_click_locator_center(page, confirm_btn):
                from src.infrastructure.anti_risk.human_like import human_click
                await human_click(
                    page,
                    confirm_btn,
                    metadata,
                    config,
                    use_operation_delay=False,
                )
            USER_LOG.info(
                "%s ▶ 已点击弹窗「声明原创」",
                self._step_prefix(metadata, "原创声明"),
            )
        except Exception as e:
            logger.warning("小红书原创声明：点击「声明原创」失败: %s", e)
            return False

        if not await self._wait_dialog_closed(page):
            logger.warning("小红书原创声明：确认后弹窗未关闭")
            return False

        return True

    async def _switch_interaction_detected(self, page: Page, checkbox: Locator) -> bool:
        """点击开关后期望：弹窗出现或开关变为 ON。"""
        if await self._is_original_dialog_open(page):
            return True
        if await self._read_switch_visual_on(page):
            return True
        return await self._read_checkbox_state(checkbox)

    async def _mouse_click_locator_center(self, page: Page, locator: Locator) -> bool:
        """在元素中心用真实鼠标点击（Vue switch 比随机边缘点更稳）。"""
        try:
            box = await locator.bounding_box()
            if not box or box.get("width", 0) < 2 or box.get("height", 0) < 2:
                return False
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            await page.mouse.click(x, y)
            return True
        except Exception as e:
            logger.debug("中心 mouse.click 失败: %s", e)
            return False

    async def _try_click_switch_target(
        self,
        page: Page,
        target: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> None:
        from src.infrastructure.anti_risk.human_like import human_click

        await _scroll_locator_to_center(page, target, wait_ms=120)
        if await self._mouse_click_locator_center(page, target):
            return
        try:
            await target.click(timeout=4000, force=True)
            return
        except Exception as e:
            logger.debug("locator.click(force) 失败: %s", e)
        await human_click(
            page,
            target,
            metadata,
            config,
            use_operation_delay=False,
        )

    async def _wait_switch_response(
        self,
        page: Page,
        checkbox: Locator,
        *,
        timeout_ms: int = _SWITCH_RESPONSE_WAIT_MS,
    ) -> bool:
        elapsed = 0
        while elapsed < timeout_ms:
            if await self._switch_interaction_detected(page, checkbox):
                return True
            await page.wait_for_timeout(_DIALOG_POLL_MS)
            elapsed += _DIALOG_POLL_MS
        return await self._switch_interaction_detected(page, checkbox)

    async def _collect_switch_click_targets(
        self, wrapper: Locator
    ) -> list[Locator]:
        """优先点可见 switch 区域，避免只命中整块卡片未触发 Vue。"""
        ordered_selectors = (
            ".d-switch-simulator",
            ".d-clickable.d-switch",
            ".custom-switch-card",
            ".custom-switch-wrapper",
        )
        targets: list[Locator] = []
        seen: set[str] = set()
        try:
            if await wrapper.count() == 0:
                return targets
            for sel in ordered_selectors:
                if sel in seen:
                    continue
                seen.add(sel)
                loc = wrapper.locator(sel).first
                if await loc.count() > 0:
                    targets.append(loc)
            for sel in Selectors.SETTINGS.get("ORIGINAL_DECLARATION_SWITCH", []):
                if sel in seen:
                    continue
                seen.add(sel)
                loc = wrapper.locator(sel).first
                if await loc.count() > 0:
                    targets.append(loc)
        except Exception as e:
            logger.debug("收集 switch 点击目标失败: %s", e)
        return targets

    async def _verify_original_enabled(self, page: Page, checkbox: Locator) -> bool:
        if await self._is_original_dialog_open(page):
            return False
        visual_on = await self._read_switch_visual_on(page)
        if not visual_on:
            return False
        checked = await self._read_checkbox_state(checkbox)
        if not checked:
            logger.info(
                "小红书原创声明：开关视觉已为 ON，checkbox 未同步勾选，按已开启处理"
            )
        return True

    async def _click_switch_to_open(
        self,
        page: Page,
        wrapper: Locator,
        checkbox: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        """点击开关并确认页面有响应（弹窗或变红）；已开启则不重复点。"""
        if await self._verify_original_enabled(page, checkbox):
            return True
        if await self._is_original_dialog_open(page):
            return True
        if await self._read_switch_visual_on(page):
            logger.info("小红书原创声明：开关已为 ON，跳过重复点击")
            return True

        label = await self._find_original_label(page)
        if label is not None:
            await _scroll_locator_to_center(page, label)

        targets = await self._collect_switch_click_targets(wrapper)
        if not targets:
            logger.warning("小红书原创声明：未找到可点击的 switch 元素")
            return False

        prefix = self._step_prefix(metadata, "原创声明")

        for attempt in range(1, _SWITCH_CLICK_MAX_ATTEMPTS + 1):
            if await self._switch_interaction_detected(page, checkbox):
                return True

            for target in targets:
                try:
                    if not await target.is_visible():
                        continue
                    await self._try_click_switch_target(
                        page, target, metadata, config
                    )
                    await page.wait_for_timeout(_POST_CLICK_SETTLE_MS)
                    if await self._wait_switch_response(page, checkbox):
                        logger.info(
                            "小红书原创声明：开关点击有效（第 %s 次）",
                            attempt,
                        )
                        USER_LOG.info(
                            "%s ▶ 已点击「原创声明」开关并收到页面响应",
                            prefix,
                        )
                        return True
                except Exception as e:
                    logger.debug(
                        "开关点击失败 attempt=%s: %s", attempt, e
                    )
                    continue

            logger.debug(
                "小红书原创声明：第 %s 次点击后无响应，准备重试",
                attempt,
            )
            await page.wait_for_timeout(350)

        return await self._switch_interaction_detected(page, checkbox)

    async def _wait_dialog_or_enabled(
        self,
        page: Page,
        checkbox: Locator,
        *,
        timeout_ms: int = _DIALOG_WAIT_MS,
    ) -> str:
        """轮询直到弹窗出现、开关已开启或超时。返回 dialog / enabled / timeout。"""
        elapsed = 0
        while elapsed < timeout_ms:
            if await self._is_original_dialog_open(page):
                return "dialog"
            if await self._verify_original_enabled(page, checkbox):
                return "enabled"
            await page.wait_for_timeout(_DIALOG_POLL_MS)
            elapsed += _DIALOG_POLL_MS
        if await self._is_original_dialog_open(page):
            return "dialog"
        if await self._verify_original_enabled(page, checkbox):
            return "enabled"
        return "timeout"

    async def _set_original_checked(
        self,
        page: Page,
        checkbox: Locator,
        want_checked: bool,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        wrapper = self._original_wrapper(page)
        await _scroll_locator_to_center(page, checkbox)

        if want_checked:
            return await self._enable_original(page, wrapper, checkbox, metadata, config)

        return await self._disable_original(page, wrapper, checkbox, metadata, config)

    async def _enable_original(
        self,
        page: Page,
        wrapper: Locator,
        checkbox: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        prefix = self._step_prefix(metadata, "原创声明")

        if await self._verify_original_enabled(page, checkbox):
            return True

        if await self._is_original_dialog_open(page):
            USER_LOG.info("%s ▶ 检测到未完成的原创权益弹窗，继续确认流程", prefix)
            outcome = "dialog"
        elif await self._verify_original_enabled(page, checkbox):
            outcome = "enabled"
        else:
            switch_ok = await self._click_switch_to_open(
                page, wrapper, checkbox, metadata, config
            )
            if not switch_ok:
                logger.warning(
                    "小红书原创声明：多次点击开关后仍无弹窗且未变红"
                )
                return False
            if await self._is_original_dialog_open(page):
                outcome = "dialog"
            elif await self._verify_original_enabled(page, checkbox):
                outcome = "enabled"
            else:
                outcome = await self._wait_dialog_or_enabled(
                    page,
                    checkbox,
                    timeout_ms=_DIALOG_AFTER_ENABLE_WAIT_MS,
                )
        if outcome == "enabled":
            USER_LOG.info(
                "%s ✓ 开关已开启（未出现或未等待权益弹窗）",
                prefix,
            )
            return True
        if outcome == "timeout":
            if await self._verify_original_enabled(page, checkbox):
                USER_LOG.info(
                    "%s ✓ 等待超时但开关已为 ON，按成功处理",
                    prefix,
                )
                return True
            logger.warning(
                "小红书原创声明：点击后既未出现权益弹窗，开关也未变为开启"
            )
            return False

        USER_LOG.info("%s ▶ 原创权益弹窗已出现", prefix)
        if not await self._complete_original_dialog(page, metadata, config):
            return False

        await page.wait_for_timeout(150)
        return await self._verify_original_enabled(page, checkbox)

    async def _disable_original(
        self,
        page: Page,
        wrapper: Locator,
        checkbox: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        if not await self._read_checkbox_state(checkbox) and not await self._read_switch_visual_on(page):
            return True

        from src.infrastructure.anti_risk.human_like import human_click

        targets: list[Locator] = []
        try:
            if await wrapper.count() > 0:
                for sel in Selectors.SETTINGS.get("ORIGINAL_DECLARATION_SWITCH", []):
                    loc = wrapper.locator(sel).first
                    if await loc.count() > 0:
                        targets.append(loc)
        except Exception:
            pass

        for target in targets:
            try:
                if not await target.is_visible():
                    continue
                await _scroll_locator_to_center(page, target, wait_ms=120)
                await human_click(page, target, metadata, config)
                await page.wait_for_timeout(400)
                if not await self._read_checkbox_state(checkbox) and not await self._read_switch_visual_on(page):
                    return True
            except Exception as e:
                logger.debug("关闭 d-switch 失败: %s", e)
                continue

        label = await self._find_original_label(page)
        if label is not None:
            control = await self._find_switch_near_anchor(page, label)
            if control is not None:
                try:
                    role = (await control.get_attribute("role") or "").lower()
                    if role == "switch" and await control.is_visible():
                        await _scroll_locator_to_center(page, control, wait_ms=200)
                        await human_click(page, control, metadata, config)
                        await page.wait_for_timeout(400)
                        if not await self._read_switch_on(control):
                            return True
                except Exception:
                    pass

        return not await self._read_checkbox_state(checkbox) and not await self._read_switch_visual_on(page)

    async def _read_checkbox_state(self, checkbox: Locator) -> bool:
        try:
            return await checkbox.is_checked()
        except Exception:
            return False

    async def _read_switch_on(self, control: Locator) -> bool:
        try:
            role = (await control.get_attribute("role") or "").lower()
            if role == "switch":
                cur = (await control.get_attribute("aria-checked") or "").strip().lower()
                return cur == "true"
            return await control.is_checked()
        except Exception:
            return False
