# -*- coding: utf-8 -*-
"""
步骤8：作者声明 / 作品申明
文件路径: src/plugins/community/kuaishou/steps/step_08_author_statement.py

按 OpenClaw DOM 分析报告（20260526）：Ant Design Select，
placeholder「为作品添加补充说明」→ role=option → 校验 selection-item。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Sequence, Tuple

from playwright.async_api import Page

from src.plugins.community.kuaishou.selectors import Selectors
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class AuthorStatementStep(BasePublishStep):
    """快手作品申明（Ant Design Select 下拉）。"""

    _FAILED_STEP = "AuthorStatementStep"

    def _fail(self, message: str) -> PublishResult:
        return PublishResult(
            success=False,
            error_message=message,
            failed_step=self._FAILED_STEP,
        )

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        privacy_settings = metadata.get("privacy_settings", {})
        if isinstance(privacy_settings, str):
            try:
                privacy_settings = json.loads(privacy_settings)
            except Exception:
                privacy_settings = {}

        from src.domain.publish.work_declaration import (
            KEY_KUAISHOU,
            KEY_KUAISHOU_AUTO,
            KUAISHOU_DECLARATION_PLACEHOLDER,
            declaration_auto_apply,
            kuaishou_declaration_click_texts,
            label_for_kuaishou_value,
        )

        prefix = self._step_prefix(metadata, "作者声明")

        if not declaration_auto_apply(privacy_settings, KEY_KUAISHOU_AUTO):
            USER_LOG.info("%s — 跳过（已关闭自动设置作品申明）", prefix)
            return None

        raw_key = privacy_settings.get(KEY_KUAISHOU) if isinstance(privacy_settings, dict) else None
        if not raw_key:
            USER_LOG.info("%s — 跳过（未配置作品申明）", prefix)
            return None

        decl_key = str(raw_key).strip()
        display_label = label_for_kuaishou_value(decl_key)
        click_texts = kuaishou_declaration_click_texts(decl_key)
        if not click_texts:
            msg = f"作品申明配置无效，无可用选项文案（枚举={decl_key}）"
            logger.warning(msg)
            USER_LOG.warning("%s ✗ %s", prefix, msg)
            return self._fail(msg)

        ok, matched = await self._apply_kuaishou_declaration(
            page, click_texts, metadata, prefix
        )
        if ok:
            USER_LOG.info("%s ✓ 已选择：%s", prefix, matched or display_label)
            return None

        msg = (
            f"作品申明：未能选中目标选项（期望「{display_label}」，"
            f"已尝试: {list(click_texts)}）"
        )
        logger.warning(msg)
        USER_LOG.warning("%s ✗ %s", prefix, msg)
        return self._fail(msg)

    async def _apply_kuaishou_declaration(
        self,
        page: Page,
        click_texts: Sequence[str],
        metadata: Dict[str, Any],
        prefix: str,
    ) -> Tuple[bool, str]:
        from src.infrastructure.anti_risk.delays import random_delay

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        for text in click_texts:
            if await self._verify_selection(page, text):
                return True, text

        try:
            from src.infrastructure.browser.human_behavior import HumanBehavior
            await HumanBehavior.scroll_to_bottom(page)
            await random_delay(page, wait_ms(400), metadata, config)
        except Exception:
            pass

        await self._scroll_declaration_into_view(page, metadata, wait_ms, config)

        if not await self._open_declaration_dropdown(page, metadata, wait_ms, config):
            logger.warning("%s 未能展开作者声明下拉", prefix)
            return False, ""

        for text in click_texts:
            if await self._select_option(page, text, metadata, wait_ms, config):
                await random_delay(page, wait_ms(300), metadata, config)
                if await self._verify_selection(page, text):
                    return True, text

        return False, ""

    async def _scroll_declaration_into_view(
        self,
        page: Page,
        metadata: Dict[str, Any],
        wait_ms,
        config: dict,
    ) -> None:
        from src.infrastructure.anti_risk.delays import random_delay

        label = Selectors.WORK_DECLARATION.get("LABEL_TEXT", "作者声明")
        label_text = label[0] if isinstance(label, list) else str(label)
        try:
            loc = page.get_by_text(label_text, exact=True).first
            if await loc.count() > 0:
                await loc.scroll_into_view_if_needed()
                await random_delay(page, wait_ms(150), metadata, config)
        except Exception:
            pass

    async def _locate_declaration_combobox(self, page: Page):
        from src.domain.publish.work_declaration import KUAISHOU_DECLARATION_PLACEHOLDER

        placeholder = (
            Selectors.WORK_DECLARATION.get("PLACEHOLDER")
            or KUAISHOU_DECLARATION_PLACEHOLDER
        )
        ph_text = placeholder[0] if isinstance(placeholder, list) else str(placeholder)
        combo = page.get_by_placeholder(ph_text)
        try:
            if await combo.count() > 0:
                return combo.first
        except Exception:
            pass

        label = Selectors.WORK_DECLARATION.get("LABEL_TEXT", "作者声明")
        try:
            form_item = page.locator(f'label:has-text("{label}")').locator("..")
            inner = form_item.get_by_role("combobox").first
            if await inner.count() > 0:
                return inner
        except Exception:
            pass

        return page.get_by_placeholder(ph_text).first

    async def _open_declaration_dropdown(
        self,
        page: Page,
        metadata: Dict[str, Any],
        wait_ms,
        config: dict,
    ) -> bool:
        from src.infrastructure.anti_risk.delays import random_delay

        combo = await self._locate_declaration_combobox(page)
        try:
            await combo.scroll_into_view_if_needed()
            await random_delay(page, wait_ms(150), metadata, config)
            await combo.click(timeout=5000)
            await random_delay(page, wait_ms(400), metadata, config)
        except Exception as e:
            logger.debug("点击作者声明 combobox 失败: %s", e)
            return False

        return await self._wait_dropdown_visible(page, timeout_ms=wait_ms(5000))

    async def _wait_dropdown_visible(self, page: Page, *, timeout_ms: int) -> bool:
        import asyncio

        deadline = max(0.5, timeout_ms / 1000.0)
        step_s = 0.12
        elapsed = 0.0
        while elapsed < deadline:
            for sel in Selectors.WORK_DECLARATION.get("DROPDOWN_VISIBLE", ()):
                try:
                    drop = page.locator(sel).first
                    if await drop.count() > 0 and await drop.is_visible():
                        return True
                except Exception:
                    continue
            try:
                opt = page.get_by_role("option").first
                if await opt.count() > 0 and await opt.is_visible():
                    return True
            except Exception:
                pass
            await asyncio.sleep(step_s)
            elapsed += step_s
        return False

    async def _select_option(
        self,
        page: Page,
        option_text: str,
        metadata: Dict[str, Any],
        wait_ms,
        config: dict,
    ) -> bool:
        from src.infrastructure.anti_risk.delays import random_delay

        try:
            opt = page.get_by_role("option", name=option_text, exact=True).first
            if await opt.count() > 0 and await opt.is_visible():
                await opt.click(timeout=5000)
                await random_delay(page, wait_ms(200), metadata, config)
                return True
        except Exception as e:
            logger.debug("role=option 点击失败 %s: %s", option_text, e)

        try:
            tpl = Selectors.WORK_DECLARATION.get("OPTION_BY_LABEL_ATTR", [""])[0]
            if tpl and "{text}" in tpl:
                loc = page.locator(tpl.format(text=option_text)).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=5000)
                    await random_delay(page, wait_ms(200), metadata, config)
                    return True
        except Exception as e:
            logger.debug("label 属性选项点击失败 %s: %s", option_text, e)

        try:
            drop = page.locator(
                ".ant-select-dropdown:not(.ant-select-dropdown-hidden)"
            ).first
            item = drop.get_by_text(option_text, exact=True).first
            if await item.count() > 0 and await item.is_visible():
                await item.click(timeout=5000)
                await random_delay(page, wait_ms(200), metadata, config)
                return True
        except Exception as e:
            logger.debug("dropdown 内文本点击失败 %s: %s", option_text, e)

        return False

    async def _verify_selection(self, page: Page, expected_text: str) -> bool:
        if not expected_text:
            return False

        for sel in Selectors.WORK_DECLARATION.get("SELECTION_ITEM", ()):
            try:
                item = page.locator(sel).first
                if await item.count() > 0 and await item.is_visible():
                    text = (await item.inner_text()).strip()
                    if expected_text in text:
                        return True
            except Exception:
                continue

        try:
            body = await page.locator("body").inner_text()
            if f"作者声明：{expected_text}" in body.replace("\n", ""):
                return True
            compact = " ".join(body.split())
            if expected_text in compact and "作者声明" in compact:
                return True
        except Exception:
            pass

        return False
