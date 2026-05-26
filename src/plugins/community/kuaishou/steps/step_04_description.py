# -*- coding: utf-8 -*-
"""
步骤4：作品描述（简介、话题）
文件路径: src/plugins/community/kuaishou/steps/step_04_description.py

流程：
  1. 正文写入 #work-description-edit
  2. 每个话题：先触发话题编辑态（真 # 或「智能话题」）→ 门禁等待下拉 → 输入词名 → 空格收成
  3. 不点击话题下拉；收成以 .at-tag-item 数量增加为准
"""
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from playwright.async_api import Locator, Page

from src.domain.publish.work_description import (
    normalize_topics_for_paste,
    parse_topic_list,
    parse_topic_ranges,
)
from src.infrastructure.common.path_manager import PathManager
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors
from .wizard_utils import dismiss_kuaishou_publish_guides

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

_DROPDOWN_GATE_MS = 1200

_EXTRACT_TOPICS_JS = """(root) => {
    if (!root) return [];
    const seen = new Set();
    const out = [];
    const push = (raw) => {
        let t = (raw || '').trim();
        while (t.startsWith('#')) t = t.slice(1).trim();
        t = t.replace(/\\[话题\\]#?$/g, '').replace(/\\[话题\\]/g, '').trim();
        while (t.endsWith('#')) t = t.slice(0, -1).trim();
        if (t && t.length <= 50 && !seen.has(t)) {
            seen.add(t);
            out.push(t);
        }
    };
    root.querySelectorAll('.at-tag-item').forEach((el) => {
        if (root.contains(el)) push(el.textContent || '');
    });
    return out;
}"""

_COUNT_AT_TAG_JS = """(root) => {
    if (!root) return 0;
    return root.querySelectorAll('.at-tag-item').length;
}"""

_ENDS_WITH_STRAY_HASH_JS = """(root) => {
    if (!root) return false;
    const t = (root.innerText || root.textContent || '').trim();
    return t.endsWith('#') || /#\\s*$/.test(t);
}"""


def _topic_pause_ms(base_ms: int, speed_rate: float) -> int:
    return max(int(base_ms * max(0.5, speed_rate)), int(base_ms * 0.4))


def _topic_type_delay(speed_rate: float) -> int:
    return max(12, int(30 * max(0.5, speed_rate)))


def _body_type_delay(speed_rate: float) -> int:
    return max(18, int(40 * max(0.5, speed_rate)))


def _topic_label_for_type(tag: str) -> str:
    s = (tag or "").strip().replace("\uff03", "")
    while s.startswith("#"):
        s = s[1:].lstrip()
    return s


def _normalize_collected_topic(raw: str) -> str:
    return _topic_label_for_type(raw)


def _topic_in_collected(label: str, collected: List[str]) -> bool:
    want = _normalize_collected_topic(label)
    if not want:
        return False
    return want in {_normalize_collected_topic(c) for c in collected}


class MetadataFillStep(BasePublishStep):
    """填写作品描述与话题（快手发布页无独立标题框）。"""

    KS_MAX_TOPICS = 4

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        return _topic_label_for_type(tag)

    @classmethod
    def _ordered_topics_from_description(cls, text: str) -> List[str]:
        return parse_topic_list(text or "")

    def _build_description_with_topic_limit(
        self, description: str, tags: List[Any]
    ) -> tuple[str, List[str], int]:
        text = normalize_topics_for_paste(description or "")
        from_desc = self._ordered_topics_from_description(text)
        seen: Set[str] = set(from_desc)
        merged: List[str] = list(from_desc)
        for t in tags:
            nt = self._normalize_tag(str(t))
            if nt and nt not in seen:
                seen.add(nt)
                merged.append(nt)
        total_before_limit = len(merged)
        kept = merged[: self.KS_MAX_TOPICS]

        body = text
        for start, end in reversed(parse_topic_ranges(text)):
            body = body[:start] + " " + body[end:]
        body = re.sub(r"\s+", " ", body).strip()
        return body, kept, total_before_limit

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        _p = self._step_prefix(metadata, "添加作品描述")
        description = (metadata.get("description") or "").strip()
        tags = metadata.get("tags") or []
        if not isinstance(tags, list):
            tags = [t.strip() for t in str(tags).split(",") if t.strip()]

        logger.info(
            "开始填写元数据: 描述长度=%d, 任务话题数=%d",
            len(description),
            len(tags),
        )
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        config = metadata.get("anti_risk_config") or {}

        await dismiss_kuaishou_publish_guides(page, metadata)

        body_text, topics_kept, topic_total = self._build_description_with_topic_limit(
            description, tags
        )
        if topic_total > self.KS_MAX_TOPICS:
            logger.info(
                "话题数 %d 超过快手上限 %d，已截断为前 %d 个",
                topic_total,
                self.KS_MAX_TOPICS,
                self.KS_MAX_TOPICS,
            )

        if not body_text and not topics_kept:
            USER_LOG.info(f"{_p} ✓ 完成（无描述内容）")
            return None

        primary_sel = "#work-description-edit"
        desc_box = page.locator(primary_sel).first
        try:
            await desc_box.wait_for(state="visible", timeout=5000)
        except Exception:
            USER_LOG.error("%s ✗ 未找到描述编辑器（sel=%s），终止发布", _p, primary_sel)
            return PublishResult(
                success=False,
                error_message=f"未找到描述编辑器（sel={primary_sel}）",
                failed_step="步骤4/作品描述",
            )

        try:
            from src.infrastructure.anti_risk.human_like import human_click

            await human_click(page, desc_box, metadata, config, use_operation_delay=False)
        except Exception:
            await desc_box.click()

        await page.keyboard.press("Control+A")
        await page.keyboard.press("Delete")
        await page.wait_for_timeout(_topic_pause_ms(150, speed_rate))

        labels = [_topic_label_for_type(t) for t in topics_kept]
        labels = [x for x in labels if x]

        if labels:
            ok, formed = await self._fill_body_and_topics(
                page, desc_box, body_text, labels, speed_rate, metadata
            )
        elif body_text:
            await self._type_plain_body(page, desc_box, body_text, speed_rate)
            ok, formed = True, 0
        else:
            ok, formed = True, 0

        if labels and not ok:
            USER_LOG.error(
                "%s ✗ 话题未全部收成（期望 %d，实际 %d）：%s",
                _p,
                len(labels),
                formed,
                "、".join(labels[:5]),
            )
            return PublishResult(
                success=False,
                error_message=(
                    f"作品描述话题未生效：期望 {len(labels)} 个，编辑器仅识别 {formed} 个"
                ),
                failed_step="步骤4/作品描述",
            )

        try:
            actual = await self._get_editor_inner_text(page, desc_box)
            if not (actual or "").strip():
                USER_LOG.error("%s ✗ 作品描述写入验证失败（innerText 为空），终止发布", _p)
                return PublishResult(
                    success=False,
                    error_message="作品描述写入验证失败：innerText 为空",
                    failed_step="步骤4/作品描述",
                )
        except Exception as ve:
            logger.warning("innerText 验证异常（sel=%s）: %s", primary_sel, ve)

        USER_LOG.info(
            f"{_p} ✓ 作品简介已填写，话题数={len(labels)}"
            + (
                f"（已按平台上限保留前 {self.KS_MAX_TOPICS} 个）"
                if topic_total > self.KS_MAX_TOPICS
                else ""
            )
        )
        USER_LOG.info(f"{_p} ✓ 完成")
        return None

    async def _fill_body_and_topics(
        self,
        page: Page,
        desc_box: Locator,
        body_text: str,
        labels: List[str],
        speed_rate: float,
        metadata: Dict[str, Any],
    ) -> Tuple[bool, int]:
        if body_text:
            await self._type_plain_body(page, desc_box, body_text, speed_rate)

        for i, label in enumerate(labels):
            chip_before = await self._count_at_tag_items(page, desc_box)
            mode = await self._type_and_confirm_one_topic(
                page,
                desc_box,
                label,
                speed_rate,
                topic_index=i,
                has_body=bool(body_text),
                metadata=metadata,
            )
            chip_after = await self._count_at_tag_items(page, desc_box)
            if chip_after <= chip_before:
                logger.warning(
                    "话题 [%d] %s 未收成（%s, at-tag %d→%d），换智能话题重试",
                    i + 1,
                    label,
                    mode,
                    chip_before,
                    chip_after,
                )
                await self._cleanup_trailing_stray_hash(page, desc_box)
                chip_before = await self._count_at_tag_items(page, desc_box)
                mode2 = await self._type_and_confirm_one_topic(
                    page,
                    desc_box,
                    label,
                    speed_rate,
                    topic_index=i,
                    has_body=bool(body_text),
                    metadata=metadata,
                    force_topic_btn=True,
                )
                chip_after = await self._count_at_tag_items(page, desc_box)
                if chip_after > chip_before:
                    logger.info(
                        "话题 [%d] %s 重试收成（%s, at-tag=%d）",
                        i + 1,
                        label,
                        mode2,
                        chip_after,
                    )
                else:
                    await self._save_topic_trigger_debug(page, desc_box, label, metadata)
            else:
                logger.info(
                    "话题 [%d] %s 已收成（%s, at-tag %d→%d）",
                    i + 1,
                    label,
                    mode,
                    chip_before,
                    chip_after,
                )

        chip_count = await self._count_at_tag_items(page, desc_box)
        ok = chip_count >= len(labels)
        if not ok:
            formed = await self._extract_topics_from_editor(page, desc_box)
            logger.error(
                "话题收成不足：期望 %d 个芯片，实际 at-tag=%d，DOM 文案=%s",
                len(labels),
                chip_count,
                formed,
            )
        return ok, chip_count

    async def _type_plain_body(
        self, page: Page, desc_box: Locator, text: str, speed_rate: float
    ) -> None:
        await desc_box.click()
        await desc_box.type(text, delay=_body_type_delay(speed_rate))
        await page.wait_for_timeout(_topic_pause_ms(80, speed_rate))

    async def _focus_editor_end(self, page: Page, desc_box: Locator, speed_rate: float) -> None:
        await desc_box.click()
        await page.keyboard.press("Control+End")
        await page.wait_for_timeout(_topic_pause_ms(60, speed_rate))

    async def _press_hash_via_cdp(self, page: Page) -> bool:
        """CDP 发送 Shift+3 / # 真按键，避免 locator.press 走 insertText。"""
        cdp = None
        try:
            cdp = await page.context.new_cdp_session(page)
            for event_type, extra in (
                ("keyDown", {"modifiers": 8}),
                ("char", {"text": "#", "unmodifiedText": "#"}),
                ("keyUp", {"modifiers": 8}),
            ):
                payload: Dict[str, Any] = {
                    "type": event_type,
                    "key": "#",
                    "code": "Digit3",
                    "windowsVirtualKeyCode": 51,
                    "nativeVirtualKeyCode": 51,
                }
                payload.update(extra)
                await cdp.send("Input.dispatchKeyEvent", payload)
            return True
        except Exception as e:
            logger.debug("CDP 派发 # 失败: %s", e)
            return False
        finally:
            if cdp is not None:
                try:
                    await cdp.detach()
                except Exception:
                    pass

    async def _press_hash_keyboard(self, page: Page, desc_box: Locator) -> str:
        """页面级 keyboard 在编辑器已 focus 时发 #，返回实际使用的方式名。"""
        await self._focus_editor_end(page, desc_box, 1.0)
        try:
            await page.keyboard.press("#")
            return "keyboard_hash"
        except Exception:
            pass
        try:
            await page.keyboard.press("Shift+3")
            return "shift3"
        except Exception:
            pass
        return ""

    async def _click_topic_ai_button(self, page: Page) -> bool:
        for selector in Selectors.PUBLISH.get("TOPIC_AI_BUTTON") or []:
            try:
                btn = page.locator(selector).first
                if await btn.count() > 0 and await btn.is_visible():
                    await btn.click(timeout=800)
                    return True
            except Exception:
                continue
        try:
            btn = page.get_by_text("智能话题", exact=False).first
            if await btn.count() > 0 and await btn.is_visible():
                await btn.click(timeout=800)
                return True
        except Exception:
            pass
        return False

    async def _wait_desc_topic_dropdown(
        self, page: Page, *, speed_rate: float, max_ms: Optional[int] = None
    ) -> bool:
        budget = max_ms if max_ms is not None else _DROPDOWN_GATE_MS
        interval = max(25, _topic_pause_ms(35, speed_rate))
        spent = 0
        while spent < budget:
            if await self._is_desc_topic_dropdown_visible(page):
                return True
            await page.wait_for_timeout(interval)
            spent += interval
        return False

    async def _is_desc_topic_dropdown_visible(self, page: Page) -> bool:
        for selector in Selectors.PUBLISH.get("TOPIC_DROPDOWN") or []:
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                continue
        for selector in Selectors.PUBLISH.get("TOPIC_SUGGESTION") or []:
            try:
                loc = page.locator(selector).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _trigger_topic_mode(
        self,
        page: Page,
        desc_box: Locator,
        speed_rate: float,
        *,
        need_leading_space: bool,
        force_topic_btn: bool = False,
    ) -> Tuple[str, bool]:
        """
        阶段 A：仅触发话题编辑态，不输入词名。
        返回 (trigger_name, dropdown_visible)。
        """
        await self._focus_editor_end(page, desc_box, speed_rate)

        if need_leading_space:
            await page.keyboard.press(" ")
            await page.wait_for_timeout(_topic_pause_ms(50, speed_rate))

        if not force_topic_btn:
            if await self._press_hash_via_cdp(page):
                if await self._wait_desc_topic_dropdown(page, speed_rate=speed_rate):
                    logger.info("话题态触发成功: trigger=cdp, dropdown_visible=true")
                    return "cdp", True

            await self._cleanup_trailing_stray_hash(page, desc_box)
            await self._focus_editor_end(page, desc_box, speed_rate)
            if need_leading_space:
                await page.keyboard.press(" ")
                await page.wait_for_timeout(_topic_pause_ms(40, speed_rate))

            kb_mode = await self._press_hash_keyboard(page, desc_box)
            if kb_mode and await self._wait_desc_topic_dropdown(page, speed_rate=speed_rate):
                logger.info(
                    "话题态触发成功: trigger=%s, dropdown_visible=true", kb_mode
                )
                return kb_mode, True

        if await self._click_topic_ai_button(page):
            await self._focus_editor_end(page, desc_box, speed_rate)
            if await self._wait_desc_topic_dropdown(page, speed_rate=speed_rate):
                logger.info("话题态触发成功: trigger=topic_btn, dropdown_visible=true")
                return "topic_btn", True

        logger.warning("话题态触发失败: trigger=none, dropdown_visible=false")
        return "none", False

    async def _cleanup_trailing_stray_hash(self, page: Page, desc_box: Locator) -> None:
        try:
            handle = await desc_box.element_handle()
            if not handle:
                return
            if await page.evaluate(_ENDS_WITH_STRAY_HASH_JS, handle):
                await self._focus_editor_end(page, desc_box, 1.0)
                await page.keyboard.press("Backspace")
                await page.wait_for_timeout(80)
        except Exception as e:
            logger.debug("清理末尾 # 失败: %s", e)

    async def _type_and_confirm_one_topic(
        self,
        page: Page,
        desc_box: Locator,
        label: str,
        speed_rate: float,
        *,
        topic_index: int,
        has_body: bool,
        metadata: Dict[str, Any],
        force_topic_btn: bool = False,
    ) -> str:
        need_space = has_body or topic_index > 0
        trigger, dropdown_ok = await self._trigger_topic_mode(
            page,
            desc_box,
            speed_rate,
            need_leading_space=need_space,
            force_topic_btn=force_topic_btn,
        )

        if not dropdown_ok:
            return f"trigger_failed:{trigger}"

        # 阶段 B：输入完整词名后空格收成（不点下拉建议）
        chip_before = await self._count_at_tag_items(page, desc_box)
        delay = _topic_type_delay(speed_rate)
        await page.keyboard.type(label, delay=delay)
        await page.wait_for_timeout(_topic_pause_ms(80, speed_rate))

        confirm_mode = await self._confirm_topic_with_space(
            page, desc_box, chip_before=chip_before, speed_rate=speed_rate
        )
        return f"{trigger}+{confirm_mode}"

    async def _chip_increased(
        self, page: Page, desc_box: Locator, chip_before: int
    ) -> bool:
        return await self._count_at_tag_items(page, desc_box) > chip_before

    async def _confirm_topic_with_space(
        self,
        page: Page,
        desc_box: Locator,
        *,
        chip_before: int,
        speed_rate: float,
    ) -> str:
        """词名输入完成后按空格收成，与手动操作一致，不点话题弹窗。"""
        try:
            await page.keyboard.press("Space")
            await page.wait_for_timeout(_topic_pause_ms(120, speed_rate))
            if await self._chip_increased(page, desc_box, chip_before):
                return "space"
        except Exception as e:
            logger.debug("空格收成失败: %s", e)
        return "confirm_failed"

    async def _save_topic_trigger_debug(
        self,
        page: Page,
        desc_box: Locator,
        label: str,
        metadata: Dict[str, Any],
    ) -> None:
        try:
            root = PathManager.get_debug_dir() / "kuaishou" / "topic_trigger"
            root.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%H%M%S")
            path = root / f"topic_fail_{label}_{ts}.png"
            await page.screenshot(path=str(path), full_page=False)
            logger.info("话题触发失败截图: %s (label=%s)", path, label)
        except Exception as e:
            logger.debug("话题失败截图异常: %s", e)

    async def _get_editor_inner_text(self, page: Page, desc_box: Locator) -> str:
        try:
            handle = await desc_box.element_handle()
            if not handle:
                return ""
            return (await page.evaluate("el => el.innerText || ''", handle)) or ""
        except Exception:
            return ""

    async def _count_at_tag_items(self, page: Page, desc_box: Locator) -> int:
        try:
            handle = await desc_box.element_handle()
            if not handle:
                return 0
            n = await page.evaluate(_COUNT_AT_TAG_JS, handle)
            return int(n) if n is not None else 0
        except Exception:
            return 0

    async def _extract_topics_from_editor(self, page: Page, desc_box: Locator) -> List[str]:
        try:
            handle = await desc_box.element_handle()
            if not handle:
                return []
            dom_topics = await page.evaluate(_EXTRACT_TOPICS_JS, handle)
            if not isinstance(dom_topics, list):
                return []
            out: List[str] = []
            seen: Set[str] = set()
            for item in dom_topics:
                n = _normalize_collected_topic(str(item))
                if n and n not in seen:
                    seen.add(n)
                    out.append(n)
            return out
        except Exception as e:
            logger.debug("采集编辑器话题失败: %s", e)
            return []
