# -*- coding: utf-8 -*-
"""
步骤8：作者声明 / 作品申明
文件路径: src/plugins/community/kuaishou/steps/step_08_author_statement.py

根据 metadata privacy_settings.kuaishou_work_declaration 在发布页选择对应选项（best-effort）。
"""
import json
import logging
from typing import Any, Dict

from playwright.async_api import Page

from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


class AuthorStatementStep(BasePublishStep):
    """快手作品申明（原创/来源类选项）。"""

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
            declaration_auto_apply,
            label_for_kuaishou_value,
        )

        if not declaration_auto_apply(privacy_settings, KEY_KUAISHOU_AUTO):
            USER_LOG.info(
                "%s — 跳过（已关闭自动设置作品申明）",
                self._step_prefix(metadata, "作者声明"),
            )
            return None

        raw_key = privacy_settings.get(KEY_KUAISHOU) if isinstance(privacy_settings, dict) else None
        if not raw_key:
            USER_LOG.info("%s — 跳过（未配置作品申明）", self._step_prefix(metadata, "作者声明"))
            return None

        cn_label = label_for_kuaishou_value(str(raw_key))
        ok = await self._click_kuaishou_declaration(page, cn_label, metadata)
        if ok:
            USER_LOG.info("%s ✓ 已选择：%s", self._step_prefix(metadata, "作者声明"), cn_label)
        else:
            USER_LOG.warning(
                "%s ▷ 未命中控件，请人工核对：%s",
                self._step_prefix(metadata, "作者声明"),
                cn_label,
            )
        return None

    async def _click_kuaishou_declaration(
        self, page: Page, cn_label: str, metadata: Dict[str, Any],
    ) -> bool:
        from src.infrastructure.anti_risk.delays import random_delay

        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)
        config = metadata.get("anti_risk_config") or {}

        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await random_delay(page, wait_ms(400), metadata, config)
        except Exception:
            pass

        for tip in ("作者声明", "原创声明", "来源声明", "声明"):
            try:
                hint = page.locator(f"text={tip}").first
                if await hint.count() > 0:
                    try:
                        await hint.scroll_into_view_if_needed()
                        await hint.click(timeout=3000)
                        await random_delay(page, wait_ms(250), metadata, config)
                    except Exception:
                        pass
                    break
            except Exception:
                continue

        try:
            opt = page.get_by_text(cn_label, exact=True).first
            if await opt.count() > 0:
                await opt.scroll_into_view_if_needed()
                await random_delay(page, wait_ms(150), metadata, config)
                await opt.click(timeout=5000)
                return True
        except Exception:
            pass

        try:
            trig = page.locator(
                "div[class*='select'], .semi-select, button:has-text('请选择'), "
                "[role='listbox'], [role='combobox']"
            ).first
            if await trig.count() > 0 and await trig.is_visible():
                await trig.click(timeout=4000)
                await random_delay(page, wait_ms(350), metadata, config)
                opt2 = page.get_by_text(cn_label, exact=True).first
                if await opt2.count() > 0:
                    await opt2.click(timeout=5000)
                    return True
        except Exception:
            pass

        return False
