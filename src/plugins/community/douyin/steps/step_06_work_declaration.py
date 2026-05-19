# -*- coding: utf-8 -*-
"""
步骤6：作品申明（自主声明）
文件路径: src/plugins/community/douyin/steps/step_06_work_declaration.py

**当前线上成功路径（与日志一致）**
1. `#DCPF` 内滚动到「自主声明」行；
2. 入口：`div[class*=selectText]` 占位/已选文案 → 优先点文案节点，必要时 `controlWrapper` + `force`；
3. 弹窗：Semi `div.semi-portal div[role=modal]`（或 `role=modal` / `dialog`）且含标题「对作品内容添加声明」；
4. 选项：`modal.get_by_role("radio", name=<枚举中文>)`（来自 `douyin_declaration_click_texts`），失败再 `label.semi-radio`；
5. 确定：`get_by_role("button", name="确定")` + `expect(...).to_be_enabled()`，再 `click`（必要时 `force`）；
6. 校验：弹窗关闭后入口区文案包含所选枚举。

若弹窗已打开：不重复点底层入口，直接 4→5→6。

**无入口（旧版/未灰度）**：在已配置且需自动设置时，若页面未找到占位「请选择自主声明」或等价入口，
视为当前发布页无自主声明能力，不打开弹窗，记录说明日志后本步直接完成（不阻断后续发布）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from playwright.async_api import Page, Locator, expect

from src.plugins.community.douyin.selectors import Selectors
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class WorkDeclarationStep(BasePublishStep):
    """抖音发布页自主声明（作品申明）——Semi 弹窗 + radio + 确定。"""

    _FAILED_STEP = "WorkDeclarationStep"

    def _dialog_title(self) -> str:
        return str(
            Selectors.PUBLISH.get("WORK_DECLARATION_DIALOG_TITLE")
            or "对作品内容添加声明"
        )

    def _placeholder_variants(self) -> Tuple[str, ...]:
        pub = Selectors.PUBLISH
        raw = pub.get("WORK_DECLARATION_PLACEHOLDER_VARIANTS")
        if isinstance(raw, (tuple, list)) and raw:
            return tuple(str(x) for x in raw)
        ph = pub.get("WORK_DECLARATION_ROW_PLACEHOLDER") or "请选择自主声明"
        return (str(ph),)

    def _entry_hint_strings(self) -> List[str]:
        from src.domain.publish.work_declaration import douyin_declaration_trigger_label_hints

        hints: List[str] = []
        hints.extend(self._placeholder_variants())
        hints.extend(douyin_declaration_trigger_label_hints())
        seen: set[str] = set()
        out: List[str] = []
        for h in hints:
            if h and h not in seen:
                seen.add(h)
                out.append(h)
        return out

    @staticmethod
    def _compact_text(s: str) -> str:
        return " ".join(s.split())

    def _text_contains_any_choice(self, visible: str, click_texts: Sequence[str]) -> bool:
        compact = self._compact_text(visible)
        for t in click_texts:
            tt = (t or "").strip()
            if tt and tt in compact:
                return True
        return False

    async def _resolve_publish_root(self, page: Page) -> Locator:
        d = page.locator("#DCPF")
        try:
            if await d.count() > 0:
                return d
        except Exception:
            pass
        return page.locator("body")

    async def _scroll_to_declaration_row(self, root: Locator) -> None:
        """把「自主声明」表单项滚进视口，减少被顶栏/侧栏遮挡。"""
        for loc in (
            root.get_by_text("自主声明", exact=True).first,
            root.locator("section").filter(has_text="自主声明").first,
        ):
            try:
                if await loc.count() > 0:
                    await loc.scroll_into_view_if_needed()
                    return
            except Exception:
                continue

    def _declaration_modal_locators(self, page: Page, title: str) -> List[Locator]:
        """抖音/Semi：优先 portal 内 role=modal；兼容标准 dialog。"""
        return [
            page.locator("div.semi-portal div[role='modal']").filter(has_text=title).first,
            page.locator("div[role='modal']").filter(has_text=title).first,
            page.get_by_role("dialog").filter(has_text=title).first,
        ]

    async def _first_visible_declaration_modal(
        self, page: Page, title: str,
    ) -> Optional[Locator]:
        for loc in self._declaration_modal_locators(page, title):
            try:
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    async def _wait_declaration_modal(
        self, page: Page, title: str, timeout_ms: int,
    ) -> Locator:
        deadline = time.monotonic() + max(1000, timeout_ms) / 1000.0
        while time.monotonic() < deadline:
            m = await self._first_visible_declaration_modal(page, title)
            if m is not None:
                return m
            await asyncio.sleep(0.12)
        raise TimeoutError(f"等待声明弹窗超时（{timeout_ms}ms），标题应含「{title}」")

    async def _locate_select_text_pair(
        self, root: Locator, hints: Sequence[str],
    ) -> Tuple[Optional[Locator], Optional[Locator]]:
        """一次遍历 hints：返回 (文案节点 selectText, 优先点击的祖先 controlWrapper 等)。无命中返回 (None, None)。"""
        pub = Selectors.PUBLISH
        txt_sub = str(
            pub.get("WORK_DECLARATION_ENTRY_SELECT_TEXT_CLASS_SUBSTR") or "selectText"
        )
        wrap_sub = str(
            pub.get("WORK_DECLARATION_ENTRY_CONTROL_WRAPPER_CLASS_SUBSTR")
            or "controlWrapper"
        )
        for h in hints:
            if not h:
                continue
            inner = root.locator(f"div[class*='{txt_sub}']").filter(has_text=h).first
            try:
                if await inner.count() == 0:
                    continue
            except Exception:
                continue
            for xpath in (
                f"xpath=ancestor::div[contains(@class,'{wrap_sub}')][1]",
                "xpath=ancestor::div[contains(@class,'semi-select')][1]",
                "xpath=ancestor::div[@role='button'][1]",
            ):
                try:
                    wrap = inner.locator(xpath)
                    if await wrap.count() > 0:
                        return inner, wrap.first
                except Exception:
                    continue
            return inner, inner
        return None, None

    async def _find_declaration_entry_via_select_text_row(
        self, root: Locator, hints: Sequence[str],
    ) -> Optional[Locator]:
        _inner, wrap = await self._locate_select_text_pair(root, hints)
        return wrap

    async def _find_select_text_inner(
        self, root: Locator, hints: Sequence[str],
    ) -> Optional[Locator]:
        inner, _w = await self._locate_select_text_pair(root, hints)
        return inner

    async def _find_declaration_entry_button(self, page: Page) -> Optional[Locator]:
        root = await self._resolve_publish_root(page)
        hints = self._entry_hint_strings()

        via_row = await self._find_declaration_entry_via_select_text_row(root, hints)
        if via_row is not None:
            return via_row

        candidates: List[Locator] = [
            root.get_by_role("button"),
            root.locator("div[role='button']"),
            root.locator("span[role='button']"),
            root.locator("div.semi-select"),
        ]
        for cand in candidates:
            try:
                n = await cand.count()
            except Exception:
                continue
            for i in range(n):
                el = cand.nth(i)
                try:
                    txt = self._compact_text(await el.inner_text())
                except Exception:
                    continue
                if not txt:
                    continue
                for h in hints:
                    if h in txt:
                        return el
        return None

    async def _click_open_declaration_modal(
        self,
        page: Page,
        root: Locator,
        hints: Sequence[str],
        wait_ms,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> None:
        """点击入口打开弹窗：优先点 `selectText` 文案区（命中用户 DOM），失败再点 controlWrapper，必要时 force。"""
        from src.infrastructure.anti_risk.delays import random_delay

        inner, wrap = await self._locate_select_text_pair(root, hints)

        if inner is not None:
            await inner.scroll_into_view_if_needed()
            await random_delay(page, wait_ms(200), metadata, config)
            for force in (False, True):
                try:
                    await inner.click(timeout=8000, force=force)
                    return
                except Exception as e:
                    logger.debug("作品申明：点击 selectText(force=%s) 失败: %s", force, e)
        if wrap is not None and wrap != inner:
            await wrap.scroll_into_view_if_needed()
            await random_delay(page, wait_ms(200), metadata, config)
            for force in (False, True):
                try:
                    await wrap.click(timeout=8000, force=force)
                    return
                except Exception as e:
                    logger.debug("作品申明：点击 controlWrapper(force=%s) 失败: %s", force, e)
        raise RuntimeError("无法点击自主声明入口（selectText / controlWrapper 均失败）")

    async def _click_radio_in_modal(self, modal: Locator, cand: str, prefix: str) -> bool:
        c = (cand or "").strip()
        if not c:
            return False
        try:
            radio = modal.get_by_role("radio", name=c)
            if await radio.count() > 0:
                await radio.first.click(timeout=8000)
                USER_LOG.info("%s ▶ 已点选声明类型(radio): %s", prefix, c)
                return True
        except Exception as e:
            logger.debug("作品申明：radio name=%r 失败: %s", c, e)
        try:
            lab = modal.locator("label.semi-radio").filter(has_text=c).first
            if await lab.count() > 0:
                await lab.click(timeout=8000)
                USER_LOG.info("%s ▶ 已点选声明类型(label): %s", prefix, c)
                return True
        except Exception as e:
            logger.debug("作品申明：label.semi-radio %r 失败: %s", c, e)
        return False

    async def _resolve_confirm_button(self, modal: Locator, confirm_name: str) -> Locator:
        """弹窗底部「确定」：优先 role+name，其次主按钮样式（Semi 可能未暴露 enabled 状态到 wait_for）。"""
        by_role = modal.get_by_role("button", name=confirm_name)
        try:
            n = await by_role.count()
            if n > 1:
                return by_role.last
            if n == 1:
                return by_role.first
        except Exception:
            pass
        primary = modal.locator("button.semi-button-primary").filter(has_text=confirm_name).first
        if await primary.count() > 0:
            return primary
        return modal.locator("button").filter(has_text=confirm_name).last

    async def _wait_confirm_enabled_and_click(
        self,
        modal: Locator,
        confirm_name: str,
        timeout_ms: int,
        prefix: str,
    ) -> None:
        """Playwright 的 locator.wait_for 不支持 state=enabled，须用 expect().to_be_enabled() 或轮询 is_enabled。"""
        btn = await self._resolve_confirm_button(modal, confirm_name)
        try:
            await btn.wait_for(state="visible", timeout=min(5000, timeout_ms))
        except Exception:
            pass
        try:
            await expect(btn).to_be_enabled(timeout=timeout_ms)
        except Exception as ex_expect:
            logger.debug("作品申明：expect.to_be_enabled 未满足: %s，尝试轮询 is_enabled", ex_expect)
            deadline = time.monotonic() + timeout_ms / 1000.0
            ok = False
            while time.monotonic() < deadline:
                try:
                    if await btn.is_enabled():
                        ok = True
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.15)
            if not ok:
                USER_LOG.info(
                    "%s ▶ 未检测到「确定」变为 enabled，尝试 force 点击（界面已红时 DOM 可能未同步）",
                    prefix,
                )
                try:
                    await btn.click(timeout=5000, force=True)
                    return
                except Exception as ex_force:
                    raise TimeoutError(
                        f"「确定」在 {timeout_ms}ms 内未变为可点击，且 force 点击失败"
                    ) from ex_force
        try:
            await btn.click(timeout=8000)
        except Exception as e_click:
            USER_LOG.info("%s ▶ 常规点击确定失败，尝试 force 点击…", prefix)
            await btn.click(timeout=8000, force=True)
            logger.debug("作品申明：常规点击异常(已 force): %s", e_click)

    def _fail(self, message: str) -> PublishResult:
        return PublishResult(
            success=False,
            error_message=message,
            failed_step=self._FAILED_STEP,
        )

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}
        prefix = self._step_prefix(metadata, "作品申明")
        title = self._dialog_title()

        logger.info("===== 作品申明 =====")

        from src.domain.publish.work_declaration import (
            KEY_DOUYIN,
            KEY_DOUYIN_AUTO,
            declaration_auto_apply,
            douyin_declaration_click_texts,
            label_for_douyin_value,
            normalize_douyin_value,
            parse_privacy_settings_dict,
        )

        _parsed = parse_privacy_settings_dict(metadata.get("privacy_settings"))
        _flat = {
            k: metadata[k]
            for k in (KEY_DOUYIN, KEY_DOUYIN_AUTO)
            if k in metadata and metadata[k] is not None
        }
        privacy_settings: Dict[str, Any] = {**_flat, **_parsed}

        if KEY_DOUYIN not in privacy_settings:
            USER_LOG.info("%s — 跳过（任务未包含作品申明配置）", prefix)
            return None
        _raw_decl = privacy_settings.get(KEY_DOUYIN)
        if _raw_decl is None or (isinstance(_raw_decl, str) and _raw_decl.strip() == ""):
            USER_LOG.info("%s — 跳过（任务作品申明为空）", prefix)
            return None

        if not declaration_auto_apply(privacy_settings, KEY_DOUYIN_AUTO):
            USER_LOG.info("%s — 跳过（已关闭发布时自动设置）", prefix)
            return None

        decl_key = normalize_douyin_value(str(_raw_decl).strip())
        display_label = label_for_douyin_value(decl_key)
        click_texts = douyin_declaration_click_texts(decl_key)
        if not click_texts:
            msg = f"作品申明配置无效，无可用选项文案（枚举={decl_key}）"
            logger.warning(msg)
            USER_LOG.warning("%s ✗ %s", prefix, msg)
            return self._fail(msg)

        confirm_name = (
            Selectors.PUBLISH.get("WORK_DECLARATION_DIALOG_CONFIRM_BTN") or "确定"
        )

        try:
            from src.infrastructure.anti_risk.delays import random_delay

            try:
                await page.locator("#DCPF").wait_for(state="attached", timeout=8000)
            except Exception:
                pass

            root = await self._resolve_publish_root(page)
            hints = self._entry_hint_strings()
            await self._scroll_to_declaration_row(root)
            await random_delay(page, wait_ms(180), metadata, config)

            entry = await self._find_declaration_entry_button(page)
            if entry is None:
                msg = (
                    "作品申明：未找到自主声明入口（占位「请选择自主声明」或已选声明文案），"
                    "按旧版发布页或未开放该功能处理，跳过自动设置，发布继续。"
                )
                logger.info(msg)
                USER_LOG.info("%s — %s", prefix, msg)
                return None

            await entry.scroll_into_view_if_needed()
            await random_delay(page, wait_ms(200), metadata, config)

            try:
                entry_visible = self._compact_text(await entry.inner_text())
            except Exception:
                entry_visible = ""

            modal_pre = await self._first_visible_declaration_modal(page, title)
            if self._text_contains_any_choice(entry_visible, click_texts) and modal_pre is None:
                USER_LOG.info(
                    "%s ▶ 页面已显示目标选项「%s」且无声明弹窗，跳过",
                    prefix,
                    display_label,
                )
                return None

            if modal_pre is not None:
                modal = modal_pre
                USER_LOG.info(
                    "%s ▶ 声明弹窗已打开，继续完成选择与点击确定（不重复点底层入口）",
                    prefix,
                )
            else:
                USER_LOG.info("%s ▶ 打开自主声明面板…", prefix)
                await self._click_open_declaration_modal(
                    page, root, hints, wait_ms, metadata, config,
                )
                await random_delay(page, wait_ms(280), metadata, config)
                try:
                    modal = await self._wait_declaration_modal(
                        page, title, wait_ms(15000),
                    )
                except Exception as e:
                    msg = f"作品申明：点击后未检测到声明弹窗（Semi modal / dialog，标题「{title}」）: {e}"
                    logger.warning(msg)
                    USER_LOG.warning("%s ✗ %s", prefix, msg)
                    return self._fail(msg)

            radio_clicked = False
            for cand in click_texts:
                if await self._click_radio_in_modal(modal, cand, prefix):
                    radio_clicked = True
                    break

            if not radio_clicked:
                msg = (
                    f"作品申明：弹窗内未能选中任一声明项（已尝试: {list(click_texts)}）。"
                    "请核对页面文案与 domain 枚举。"
                )
                logger.warning(msg)
                USER_LOG.warning("%s ✗ %s", prefix, msg)
                return self._fail(msg)

            await random_delay(page, wait_ms(220), metadata, config)

            try:
                await self._wait_confirm_enabled_and_click(
                    modal, confirm_name, wait_ms(12000), prefix,
                )
            except Exception as e:
                msg = f"作品申明：等待或点击「确定」失败: {e}"
                logger.warning(msg)
                USER_LOG.warning("%s ✗ %s", prefix, msg)
                return self._fail(msg)

            await random_delay(page, wait_ms(320), metadata, config)

            try:
                await modal.wait_for(state="hidden", timeout=wait_ms(12000))
            except Exception:
                pass

            entry2 = await self._find_declaration_entry_button(page)
            if entry2 is None:
                msg = "作品申明：关闭弹窗后未再找到自主声明入口，无法校验成功"
                logger.warning(msg)
                USER_LOG.warning("%s ✗ %s", prefix, msg)
                return self._fail(msg)

            try:
                after = self._compact_text(await entry2.inner_text())
            except Exception:
                after = ""

            if not self._text_contains_any_choice(after, click_texts):
                msg = (
                    f"作品申明：确定后入口未显示目标文案（当前: {after[:80]}…），"
                    f"期望其一: {list(click_texts)}"
                )
                logger.warning(msg)
                USER_LOG.warning("%s ✗ %s", prefix, msg)
                return self._fail(msg)

            USER_LOG.info("%s ▶ 已选择: %s", prefix, display_label)
            logger.info(
                "作品申明链路: selectText→Semi(role=modal)→radio(name)→expect(确定).enabled→click→入口校验"
            )
            return None

        except Exception as e:
            msg = f"作品申明执行异常: {e}"
            logger.warning(msg, exc_info=True)
            USER_LOG.warning("%s ✗ %s", prefix, msg)
            return self._fail(str(e))
