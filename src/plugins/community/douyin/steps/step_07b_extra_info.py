# -*- coding: utf-8 -*-
"""
步骤7：扩展信息 － 添加标签（位置/团购/购物车/小程序）尽力填写
文件路径: src/plugins/community/douyin/steps/step_07b_extra_info.py

DOM 依据：
  - docs/03插件系统/OpenClaw 报告分析报告/抖音_视频发布DOM分析报告_20260325.md §3.3 添加标签
  - docs/03插件系统/OpenClaw 报告分析报告/抖音创作者中心视频发布页面购物车添加功能的DOM结构分析及操作流程验证.md
    （位置类 semi-select、粘贴商品链接、span 添加链接、弹窗短标题须 type、完成编辑待变红）

流程：
  1. 滚动「扩展信息」区域入视口。
  2. 若 metadata 含 poi_info / anchor_info / cart_info / micro_app_info，按优先级仅自动填一条：
     位置 > 团购 > 购物车 > 小程序（与单条任务页保存逻辑一致：页面上同时只操作一种标签类型）。
  3. 检测「补充信息」弹窗并点击确认类按钮，避免阻塞发布。

字段依赖（metadata，由发布管道从发布记录透传）：
  - poi_info, anchor_info, cart_info, micro_app_info: 与库中 publish_records 一致，可为 JSON 或纯文本
  - metadata['anti_risk_config']: 拟人点击 / 随机等待
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.infrastructure.browser.automation_api import Locator, Page

from src.domain.publish.location_settings import (
    LOCATION_MODE_CHOICES,
    parse_poi_info_storage,
)
from src.plugins.core.wait_helper import PluginWaitHelper

from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


def _parse_goods_storage(raw: str) -> Tuple[str, str]:
    s = (raw or "").strip()
    if not s:
        return "", ""
    if s.startswith("{"):
        try:
            d = json.loads(s)
            if isinstance(d, dict):
                link = str(d.get("cart") or d.get("link") or d.get("url") or "").strip()
                st = str(
                    d.get("short_title")
                    or d.get("cart_short_title")
                    or d.get("yellow_cart_short_title")
                    or d.get("promotion_title")
                    or ""
                ).strip()
                return link, st
        except (json.JSONDecodeError, TypeError):
            pass
    return s, ""


def _parse_anchor_storage(raw: str) -> Tuple[str, str]:
    s = (raw or "").strip()
    if not s:
        return "", ""
    if s.startswith("{"):
        try:
            d = json.loads(s)
            if isinstance(d, dict):
                main = str(d.get("tuan") or d.get("link") or d.get("url") or d.get("anchor") or "").strip()
                st = str(d.get("promotion_title") or d.get("short_title") or "").strip()
                return main, st
        except (json.JSONDecodeError, TypeError):
            pass
    return s, ""


class ExtraInfoCommonStep(BasePublishStep):
    """扩展信息：补充信息弹窗 + 添加标签（配置了标签时必须成功，否则终止发布）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        logger.info("===== 扩展信息（公共） =====")
        config = metadata.get("anti_risk_config") or {}

        await self._try_dismiss_supplement_modal(page, metadata, config)
        await self._scroll_extended_info_into_view(page)
        result = await self._try_fill_add_tag_row(page, metadata, config)
        if result is not None:
            return result
        await self._try_dismiss_supplement_modal(page, metadata, config)

        return None

    async def _scroll_extended_info_into_view(self, page: Page) -> None:
        try:
            anchor = page.locator("#DCPF").get_by_text("扩展信息", exact=False).first
            if await anchor.count() > 0:
                await anchor.scroll_into_view_if_needed()
                await page.wait_for_timeout(350)
        except Exception:
            pass

    async def _try_fill_add_tag_row(
        self, page: Page, metadata: Dict[str, Any], config: Dict[str, Any]
    ) -> Optional["PublishResult"]:
        """填写添加标签行。配置了标签时若失败则返回 PublishResult(False)，未配置时返回 None。"""
        from src.plugins.core.interfaces.publish_plugin import PublishResult

        poi_text, poi_mode = parse_poi_info_storage(metadata.get("poi_info") or "")
        # 仅有 location_mode、主输入为空：与单任务页一致，视为未使用位置标签
        has_poi = bool(poi_text)
        anchor = (metadata.get("anchor_info") or "").strip()
        goods = (metadata.get("cart_info") or "").strip()
        mini = (metadata.get("micro_app_info") or "").strip()
        if not any((has_poi, anchor, goods, mini)):
            return None

        # 确定当前要填写的标签类型（用于错误信息）
        tag_type = "位置" if has_poi else ("团购" if anchor else ("购物车" if goods else "小程序"))

        semi_chain = await self._semi_selects_after_add_tag(page)
        if semi_chain is None or await semi_chain.count() == 0:
            if goods and not (has_poi or anchor or mini):
                if await self._select_shopping_cart_via_openclaw_fallback(page, metadata, config):
                    link, promo = _parse_goods_storage(goods)
                    if link:
                        cart_ok = await self._fill_cart_link_and_confirm(page, link, promo, metadata, config)
                        if not cart_ok:
                            USER_LOG.error("[步骤7/9 扩展信息] ✗ 购物车商品未成功添加，终止发布")
                            return PublishResult(success=False, error_message="购物车商品添加失败，「已添加商品」区域未出现", failed_step="步骤7/扩展信息")
                    elif promo:
                        await self._fill_promotion_if_present(page, promo, metadata, config)
                    USER_LOG.info("[步骤7/9 扩展信息] ✓ 已填写「购物车」标签，商品已添加")
                    return None
                else:
                    USER_LOG.error("[步骤7/9 扩展信息] ✗ 未找到「添加标签」及购物车下拉，终止发布")
                    return PublishResult(success=False, error_message="未找到「添加标签」及购物车下拉", failed_step="步骤7/扩展信息")
            USER_LOG.error("[步骤7/9 扩展信息] ✗ 未找到「添加标签」行，终止发布（已配置%s标签）", tag_type)
            return PublishResult(
                success=False,
                error_message=f"未找到「添加标签」行，无法填写{tag_type}标签",
                failed_step="步骤7/扩展信息",
            )

        try:
            if has_poi:
                await self._select_tag_type(page, semi_chain, "位置", metadata, config)
                if poi_mode in LOCATION_MODE_CHOICES:
                    await self._select_second_mode(page, semi_chain, poi_mode, metadata, config)
                await self._fill_tag_main_input(page, poi_text, metadata, config)
                USER_LOG.info("[步骤7/9 扩展信息] ✓ 已填写「位置」标签")
                return None
            if anchor:
                main, promo = _parse_anchor_storage(anchor)
                await self._select_tag_type(page, semi_chain, "团购", metadata, config)
                if main:
                    await self._fill_tag_main_input(page, main, metadata, config)
                if promo:
                    await self._fill_promotion_if_present(page, promo, metadata, config)
                USER_LOG.info("[步骤7/9 扩展信息] ✓ 已填写「团购」标签")
                return None
            if goods:
                link, promo = _parse_goods_storage(goods)
                await self._select_tag_type(page, semi_chain, "购物车", metadata, config)
                if link:
                    cart_ok = await self._fill_cart_link_and_confirm(page, link, promo, metadata, config)
                    if not cart_ok:
                        USER_LOG.error("[步骤7/9 扩展信息] ✗ 购物车商品未成功添加，终止发布")
                        return PublishResult(success=False, error_message="购物车商品添加失败，「已添加商品」区域未出现", failed_step="步骤7/扩展信息")
                elif promo:
                    await self._fill_promotion_if_present(page, promo, metadata, config)
                USER_LOG.info("[步骤7/9 扩展信息] ✓ 已填写「购物车」标签，商品已添加")
                return None
            if mini:
                await self._select_tag_type(page, semi_chain, "小程序", metadata, config)
                await self._fill_tag_main_input(page, mini, metadata, config)
                USER_LOG.info("[步骤7/9 扩展信息] ✓ 已填写「小程序」标签")
                return None
        except Exception as e:
            logger.error(f"扩展信息：填写「{tag_type}」标签失败: {e}", exc_info=True)
            USER_LOG.error("[步骤7/9 扩展信息] ✗ 「%s」标签填写失败，终止发布: %s", tag_type, str(e)[:100])
            return PublishResult(
                success=False,
                error_message=f"「{tag_type}」标签填写失败: {str(e)[:100]}",
                failed_step="步骤7/扩展信息",
            )
        return None

    def _extended_info_scope(self, page: Page) -> Locator:
        """发布表单主容器：优先 #DCPF，否则整页。"""
        d = page.locator("#DCPF")
        return d

    async def _semi_selects_after_add_tag(self, page: Page) -> Optional[Locator]:
        """「添加标签」与类型下拉常为兄弟结构，同一 div 不一定同时含文案与 semi-select。

        使用 XPath：在文档顺序上位于「添加标签」之后的所有 ``div.semi-select``。
        参见 OpenClaw 购物车 DOM 报告（位置入口 semi-select + 后续锚点区）。
        """
        scope = self._extended_info_scope(page)
        if await scope.count() == 0:
            scope = page
        lbl = scope.get_by_text("添加标签", exact=False).first
        if await lbl.count() == 0:
            return None
        try:
            await lbl.scroll_into_view_if_needed()
        except Exception:
            pass
        return lbl.locator("xpath=following::div[contains(@class,'semi-select')]")

    async def _inputs_after_add_tag(self, page: Page) -> Optional[Locator]:
        scope = self._extended_info_scope(page)
        if await scope.count() == 0:
            scope = page
        lbl = scope.get_by_text("添加标签", exact=False).first
        if await lbl.count() == 0:
            return None
        return lbl.locator("xpath=following::input[@type='text']")

    async def _select_shopping_cart_via_openclaw_fallback(
        self, page: Page, metadata: Dict[str, Any], config: Dict[str, Any]
    ) -> bool:
        """无「添加标签」文案时的兜底：在 #DCPF 内点击报告中的类型 semi-select 并选「购物车」。"""
        scope = self._extended_info_scope(page)
        if await scope.count() == 0:
            scope = page
        try:
            await scope.get_by_text("扩展信息", exact=False).first.scroll_into_view_if_needed()
        except Exception:
            pass
        await page.wait_for_timeout(350)
        sels = list(Selectors.PUBLISH.get("EXTRA_TAG_TYPE_SEMI_SELECT") or [])
        for raw in sels:
            try:
                loc = scope.locator(raw).first
                if await loc.count() == 0 or not await loc.is_visible():
                    continue
                await loc.scroll_into_view_if_needed()
                await self._semi_click(page, loc, metadata, config)
                await page.wait_for_timeout(500)
                await self._click_dropdown_option(page, "购物车")
                await page.wait_for_timeout(400)
                return True
            except Exception:
                continue
        return False

    async def _semi_click(
        self,
        page: Page,
        loc: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        *,
        use_operation_delay: bool = True,
    ) -> None:
        try:
            from src.infrastructure.anti_risk.human_like import human_click

            await human_click(page, loc, metadata, config, use_operation_delay=use_operation_delay)
        except Exception:
            await loc.click(timeout=8000)

    async def _select_tag_type(
        self,
        page: Page,
        semi_chain: Locator,
        label: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> None:
        """类型下拉为「添加标签」之后在文档顺序上的第一个 semi-select。"""
        if await semi_chain.count() < 1:
            return
        first_sel = semi_chain.first
        trig = first_sel.locator(".semi-select-selection, [class*='selection']").first
        if await trig.count() == 0:
            trig = first_sel
        try:
            await trig.scroll_into_view_if_needed()
        except Exception:
            pass
        await self._semi_click(page, trig, metadata, config)
        await page.wait_for_timeout(500)
        await self._click_dropdown_option(page, label)

    async def _select_second_mode(
        self,
        page: Page,
        semi_chain: Locator,
        mode: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> None:
        """选「位置」时第二个下拉（打卡/带货模式等）。"""
        if await semi_chain.count() < 2:
            return
        second_sel = semi_chain.nth(1)
        trig = second_sel.locator(".semi-select-selection, [class*='selection']").first
        if await trig.count() == 0:
            trig = second_sel
        try:
            await trig.scroll_into_view_if_needed()
        except Exception:
            pass
        await self._semi_click(page, trig, metadata, config)
        await page.wait_for_timeout(400)
        await self._click_dropdown_option(page, mode)

    async def _click_dropdown_option(self, page: Page, text: str) -> None:
        """点击 Semi 浮层中的选项（挂载在 body）。"""
        escaped = re.escape(text)
        patterns: List[str] = list(Selectors.PUBLISH.get("SEMI_SELECT_OPTION") or [])
        for base in patterns:
            try:
                opt = page.locator(base).filter(has_text=re.compile(f"^{escaped}$")).first
                if await opt.count() > 0 and await opt.is_visible():
                    await opt.click(timeout=5000)
                    await page.wait_for_timeout(300)
                    return
            except Exception:
                continue
        # 兜底：全页精确文案
        try:
            await page.get_by_text(text, exact=True).first.click(timeout=4000)
            await page.wait_for_timeout(300)
        except Exception:
            pass

    async def _fill_tag_main_input(self, page: Page, text: str, metadata: Dict[str, Any], config: Dict[str, Any]) -> None:
        if not text:
            return
        sels = list(Selectors.PUBLISH.get("EXTRA_ADD_TAG_LOCATION_INPUT") or [])
        for sel in sels:
            try:
                inp = page.locator(sel).first
                if await inp.count() == 0 or not await inp.is_visible():
                    continue
                await inp.scroll_into_view_if_needed()
                await inp.click(timeout=3000)
                await inp.fill("")
                await inp.type(text, delay=max(15, int(25 * float(metadata.get("speed_rate", 1.0)))))
                try:
                    from src.infrastructure.anti_risk.delays import random_delay

                    await random_delay(page, 400, metadata, config)
                except Exception:
                    await page.wait_for_timeout(400)
                return
            except Exception:
                continue
        # 无「地理位置」占位时：取「添加标签」之后第一个可见 text input
        try:
            chain = await self._inputs_after_add_tag(page)
            if chain is None:
                return
            inp = chain.first
            if await inp.count() > 0 and await inp.is_visible():
                await inp.fill("")
                await inp.type(text, delay=max(15, int(25 * float(metadata.get("speed_rate", 1.0)))))
        except Exception:
            pass

    async def _fill_promotion_if_present(self, page: Page, promo: str, metadata: Dict[str, Any], config: Dict[str, Any]) -> None:
        """购物车/团购推广标题：页面若有第二个 text input 或占位含「推广」则填写。"""
        if not promo:
            return
        try:
            chain = await self._inputs_after_add_tag(page)
            if chain is None:
                return
            cnt = await chain.count()
            if cnt >= 2:
                second = chain.nth(1)
                if await second.is_visible():
                    await second.fill("")
                    await second.type(promo, delay=max(12, int(20 * float(metadata.get("speed_rate", 1.0)))))
                    return
            for ph in ("推广", "短标题", "标题"):
                loc = page.locator(f"input[placeholder*='{ph}']").first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.fill("")
                    await loc.type(promo, delay=max(12, int(20 * float(metadata.get("speed_rate", 1.0)))))
                    return
        except Exception:
            pass

    # 抖音「完成编辑」可点击时主色（OpenClaw 报告）
    _DOUYIN_PRIMARY_BTN_BG = "rgb(254, 44, 85)"

    async def _resolve_cart_link_input(self, page: Page) -> Optional[Locator]:
        # 1) placeholder 精确匹配（最稳定）
        for sel in list(Selectors.PUBLISH.get("EXTRA_CART_LINK_INPUT") or []):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        # 2) 在购物车锚点容器内查找 input（避免误匹配其他区域的输入框）
        for wrap_sel in list(Selectors.PUBLISH.get("EXTRA_CART_ANCHOR_WRAP") or []):
            try:
                wrap = page.locator(wrap_sel).first
                if await wrap.count() == 0:
                    continue
                inp = wrap.locator("input[type='text']").first
                if await inp.count() > 0 and await inp.is_visible():
                    return inp
            except Exception:
                continue
        # 3) 通过「添加链接」SPAN 的相邻 input 定位（购物车区域内）
        for add_link_sel in list(Selectors.PUBLISH.get("EXTRA_CART_ADD_LINK_SPAN") or []):
            try:
                span = page.locator(add_link_sel).first
                if await span.count() == 0:
                    continue
                # 查找同级或父级容器内的 input
                inp = span.locator("xpath=preceding::input[@type='text'][1]").first
                if await inp.count() > 0 and await inp.is_visible():
                    return inp
                # 兜底：查找父容器内的 input
                parent_inp = span.locator("xpath=ancestor::div[1]//input[@type='text']").first
                if await parent_inp.count() > 0 and await parent_inp.is_visible():
                    return parent_inp
            except Exception:
                continue
        # 注意：不再使用 _inputs_after_add_tag 兜底，该方法返回的是「添加标签」后的
        # 第一个 input，可能误匹配到「添加共创」等其他区域的输入框
        logger.warning("购物车：所有选择器均未找到「粘贴商品链接」输入框")
        return None

    async def _resolve_cart_add_link_span(self, page: Page) -> Optional[Locator]:
        """定位「添加链接」SPAN 元素（DOM报告：span.cart-mybtn-jPFx5X）。"""
        for sel in list(Selectors.PUBLISH.get("EXTRA_CART_ADD_LINK_SPAN") or []):
            try:
                loc = page.locator(sel).filter(has_text="添加链接").first
                if await loc.count() == 0:
                    loc = page.locator(sel).first
                if await loc.count() > 0:
                    return loc
            except Exception:
                continue
        # 兜底：文案精确匹配
        try:
            loc = page.get_by_text("添加链接", exact=True).first
            if await loc.count() > 0:
                return loc
        except Exception:
            pass
        return None

    # 「添加链接」SPAN 可点击时的主色（与「完成编辑」按钮相同）
    _DOUYIN_ADD_LINK_ACTIVE_BG = "rgb(254, 44, 85)"

    async def _wait_add_link_span_clickable(self, page: Page, timeout_ms: int = 600) -> Optional[Locator]:
        """等待「添加链接」SPAN 变红（可点击）后返回该元素，超时降级返回元素本身。
        DOM报告：粘贴链接后通常立即变红，最多等 600ms。
        """
        interval = 150
        deadline = max(1, timeout_ms // interval)
        for _ in range(deadline):
            span = await self._resolve_cart_add_link_span(page)
            if span is None:
                await page.wait_for_timeout(interval)
                continue
            try:
                bg = (await span.evaluate("el => window.getComputedStyle(el).backgroundColor")).strip()
                if bg == self._DOUYIN_ADD_LINK_ACTIVE_BG:
                    return span
            except Exception:
                pass
            await page.wait_for_timeout(interval)
        # 超时后降级：仍返回元素，让调用方尝试点击
        return await self._resolve_cart_add_link_span(page)

    async def _js_dispatch_click_cart_span(self, page: Page) -> bool:
        """用 dispatchEvent 触发「添加链接」SPAN 的点击事件，兼容 React/Vue 等前端框架。"""
        try:
            return bool(await page.evaluate(
                """() => {
                  const el = document.querySelector('span[class*="cart-mybtn"]')
                    || document.querySelector('span.cart-mybtn-jPFx5X');
                  if (!el) return false;
                  // 依次派发 mousedown / mouseup / click，确保框架监听器都能响应
                  ['mousedown', 'mouseup', 'click'].forEach(type => {
                    el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true}));
                  });
                  return true;
                }"""
            ))
        except Exception:
            return False

    async def _click_cart_add_link_span(self, page: Page, metadata: Dict[str, Any], config: Dict[str, Any]) -> bool:
        """等待「添加链接」SPAN 变红后，用多种方式尝试点击，每次点击后验证弹窗是否出现。"""

        async def _modal_appeared() -> bool:
            """检测「编辑商品」弹窗是否已出现。
            DOM报告：以「请输入商品短标题」输入框出现为判断依据（比检测弹窗容器更可靠）。
            同时兼容弹窗容器选择器作为双重保险。
            """
            try:
                # 优先：报告中建议的方式，短标题输入框出现即弹窗已就绪
                st_inp = page.locator('input[placeholder="请输入商品短标题"]').first
                if await st_inp.count() > 0 and await st_inp.is_visible():
                    return True
            except Exception:
                pass
            try:
                # 兜底：弹窗容器选择器
                m = await self._locate_edit_goods_modal(page)
                return await m.count() > 0 and await m.is_visible()
            except Exception:
                return False

        span = await self._wait_add_link_span_clickable(page, timeout_ms=600)

        # 按优先级逐一尝试：dispatchEvent 对 React 按钮最可靠，优先使用
        click_attempts = [
            # 1. dispatchEvent（兼容 React/Vue，跳过坐标命中检测）
            ("js_dispatch", None),
            # 2. Playwright 原生点击（兜底，去除 operation_delay 避免额外等待）
            ("playwright_click", None),
            # 3. 直接 JS .click()（最后兜底）
            ("js_click", None),
        ]

        for attempt_name, _ in click_attempts:
            try:
                if attempt_name == "playwright_click":
                    if span is None:
                        continue
                    await span.scroll_into_view_if_needed()
                    try:
                        await self._semi_click(page, span, metadata, config, use_operation_delay=False)
                    except Exception:
                        await span.click(timeout=5000)

                elif attempt_name == "js_dispatch":
                    if not await self._js_dispatch_click_cart_span(page):
                        continue

                elif attempt_name == "js_click":
                    result = await page.evaluate(
                        """() => {
                          const el = document.querySelector('span[class*="cart-mybtn"]');
                          if (el) { el.click(); return true; }
                          return false;
                        }"""
                    )
                    if not result:
                        continue

                logger.info("购物车：已用 %s 点击「添加链接」，等待弹窗...", attempt_name)
                # 轮询等待弹窗，最多 2 秒（页面响应通常在 1 秒内）
                import asyncio as _asyncio
                modal_found = False
                for _ in range(7):
                    await page.wait_for_timeout(300)
                    await _asyncio.sleep(0)  # 让出控制权防止 Qt UI 无响应
                    if await _modal_appeared():
                        modal_found = True
                        break
                if modal_found:
                    logger.info("购物车：弹窗已出现（%s 点击成功）", attempt_name)
                    return True
                logger.warning("购物车：%s 点击后 2 秒内弹窗未出现，尝试下一种方式", attempt_name)

            except Exception as e:
                logger.debug("购物车：%s 点击异常: %s", attempt_name, e)
                continue

        logger.warning("购物车：三种点击方式均未触发「编辑商品」弹窗")
        return False

    async def _locate_edit_goods_modal(self, page: Page) -> Locator:
        # 日志实测：弹窗容器为 div[role="modal"].semi-modal-wrap，内容区为 div.modal-body-*
        # 同时保留 role="dialog" 作为兜底（DOM报告中的结构）
        return page.locator(
            "div[role='modal'].semi-modal-wrap, "
            "div.semi-modal-wrap, "
            "div.semi-modal[role='dialog'], "
            "div[role='dialog'].semi-modal, "
            "div[role='dialog']"
        ).filter(has_text="编辑商品").first

    async def _wait_finish_edit_clickable(self, page: Page, finish_btn: Locator, timeout_ms: int = 2000) -> None:
        import asyncio as _asyncio
        deadline = timeout_ms // 200
        for _ in range(max(1, deadline)):
            try:
                bg = (await finish_btn.evaluate("el => window.getComputedStyle(el).backgroundColor")).strip()
                if bg == self._DOUYIN_PRIMARY_BTN_BG:
                    return
            except Exception:
                pass
            await page.wait_for_timeout(200)
            await _asyncio.sleep(0)  # 让出控制权防止 Qt UI 无响应

    async def _verify_cart_goods_added(self, page: Page) -> bool:
        """验证购物车商品已成功添加：检查页面出现「已添加商品」区域。
        图3实际样式：页面显示「已添加商品（1）」文字，商品行旁有「编辑」「移除」按钮。
        """
        # 方式1：「已添加商品」文字（含括号数字，用 has-text 包含匹配）
        try:
            loc = page.locator("*").filter(has_text=re.compile(r"已添加商品")).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            pass

        # 方式2：全页查找「编辑」+「移除」同时存在（只有商品添加成功后才会出现这两个操作按钮）
        try:
            edit_btns = page.get_by_text("编辑", exact=True)
            remove_btns = page.get_by_text("移除", exact=True)
            if await edit_btns.count() > 0 and await remove_btns.count() > 0:
                return True
        except Exception:
            pass

        # 方式3：class 名包含相关关键字
        for sel in ("[class*='added-goods']", "[class*='addedGoods']",
                    "[class*='cart-added']", "[class*='goods-list']",
                    "[class*='cart-part']"):
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                continue

        # 方式4：购物车锚点区域内有「编辑」或「移除」按钮
        for wrap_sel in list(Selectors.PUBLISH.get("EXTRA_CART_ANCHOR_WRAP") or []):
            try:
                wrap = page.locator(wrap_sel).first
                if await wrap.count() == 0:
                    continue
                for action_text in ("编辑", "移除"):
                    btn = wrap.get_by_text(action_text, exact=True).first
                    if await btn.count() > 0 and await btn.is_visible():
                        return True
            except Exception:
                continue
        return False

    async def _wait_cart_goods_added(self, page: Page, timeout_ms: int = 3000) -> bool:
        return bool(
            await PluginWaitHelper.wait_for_condition(
                page,
                lambda: self._verify_cart_goods_added(page),
                timeout_ms=timeout_ms,
                poll_interval_ms=300,
            )
        )

    async def _supplement_modal_closed(self, dialog: Locator) -> bool:
        try:
            return await dialog.count() == 0 or not await dialog.is_visible()
        except Exception:
            return True

    async def _fill_cart_link_and_confirm(
        self,
        page: Page,
        link: str,
        short_title: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        """
        购物车完整流程（对齐 OpenClaw DOM 报告）：
        1. input[placeholder="粘贴商品链接"] 直接 fill() 粘贴链接
        2. 等待 span.cart-mybtn-* 「添加链接」变红（rgb(254,44,85)）后点击
        3. 等待 semi-modal「编辑商品」弹出
        4. 短标题用 type() 模拟人工逐字输入（页面不识别直接赋值）
        5. 等待「完成编辑」按钮变红后点击
        6. 验证「已添加商品」区域出现，返回 True/False
        """
        from src.plugins.core.interfaces.publish_plugin import PublishResult  # noqa: F401

        try:
            # 重试进入时弹窗可能已存在（上次点击成功但检测超时），直接复用
            # DOM报告：以短标题输入框出现为判断弹窗是否就绪的依据
            st_inp_check = page.locator('input[placeholder="请输入商品短标题"]').first
            if await st_inp_check.count() > 0 and await st_inp_check.is_visible():
                logger.info("购物车：检测到「编辑商品」弹窗已存在（短标题输入框可见），跳过链接填写直接处理")
                edit_modal = await self._locate_edit_goods_modal(page)
                return await self._handle_edit_goods_modal(page, edit_modal, short_title, metadata, config)

            cart_input = await self._resolve_cart_link_input(page)
            if cart_input is None:
                logger.warning("购物车：未找到「粘贴商品链接」输入框")
                USER_LOG.warning("[步骤7/9 扩展信息] ✗ 购物车：未找到链接输入框")
                return False

            await cart_input.scroll_into_view_if_needed()
            await cart_input.click(timeout=3000)
            await cart_input.fill("")
            # 直接粘贴链接，无需逐字输入；页面收到 input 事件后「添加链接」SPAN 会变红
            await cart_input.fill(link)
            logger.info("购物车：已粘贴商品链接，等待「添加链接」变红...")

            # 等待「添加链接」SPAN 变红后点击，内部会验证弹窗是否出现
            if not await self._click_cart_add_link_span(page, metadata, config):
                logger.warning("购物车：点击「添加链接」后弹窗未出现，链接可能无效或点击未生效")
                USER_LOG.warning("[步骤7/9 扩展信息] ✗ 购物车「编辑商品」弹窗未出现（链接可能无效）")
                return False

            # 弹窗已出现（_click_cart_add_link_span 内部已验证），直接获取引用
            edit_modal = await self._locate_edit_goods_modal(page)
            logger.info("购物车：「编辑商品」弹窗已出现")
            return await self._handle_edit_goods_modal(page, edit_modal, short_title, metadata, config)

        except Exception as e:
            logger.warning(f"购物车设置失败: {e}")
            USER_LOG.warning("[步骤7/9 扩展信息] ✗ 购物车设置未完成（可手动检查）: %s", str(e)[:80])
            return False

    async def _handle_edit_goods_modal(
        self,
        page: Page,
        edit_modal: Locator,
        short_title: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> bool:
        """处理「编辑商品」弹窗：填写短标题 → 等待「完成编辑」变红 → 点击 → 验证已添加商品。
        DOM报告：
          - 短标题输入框: input[placeholder="请输入商品短标题"] (ref: e596)，必填，最多10个汉字
          - 完成编辑按钮: button (ref: e602)，需变红 rgb(254,44,85) 后点击
        """
        # 定位短标题输入框（DOM报告：精确 placeholder 最稳定）
        st_inp = page.locator('input[placeholder="请输入商品短标题"]').first
        if await st_inp.count() == 0:
            st_inp = edit_modal.locator('input[placeholder="请输入商品短标题"]').first
        if await st_inp.count() == 0:
            st_inp = edit_modal.locator("input[placeholder*='短标题']").first
        if await st_inp.count() == 0:
            st_inp = edit_modal.locator("input[type='text']").first

        if await st_inp.count() > 0 and await st_inp.is_visible():
            title_to_fill = (short_title or "").strip()
            if not title_to_fill:
                logger.warning("购物车：未配置商品短标题（请在「购物车推广」商品库中填写「商品短标题」列），「完成编辑」按钮可能无法变红")

            if title_to_fill:
                await st_inp.scroll_into_view_if_needed()
                await st_inp.click(timeout=3000)
                await st_inp.fill("")
                # DOM报告：必须用模拟人工键盘输入，JS 直接赋值不被页面识别
                await st_inp.type(
                    title_to_fill,
                    delay=max(15, int(25 * float(metadata.get("speed_rate", 1.0)))),
                )
                logger.info("购物车：已输入商品短标题: %s", title_to_fill)
                try:
                    from src.infrastructure.anti_risk.delays import random_delay

                    await random_delay(page, 500, metadata, config)
                except Exception:
                    await page.wait_for_timeout(500)
        else:
            logger.warning("购物车：未找到「商品短标题」输入框，跳过短标题填写")

        # DOM报告：完成编辑按钮为 button，ref: e602；弹窗可能用 portal 渲染在 body 下需全页查找
        finish_btn = page.locator("button").filter(has_text="完成编辑").first
        if await finish_btn.count() == 0:
            finish_btn = edit_modal.get_by_role("button", name="完成编辑").first
        if await finish_btn.count() == 0:
            finish_btn = edit_modal.locator("button").filter(has_text="完成编辑").first
        if await finish_btn.count() == 0:
            logger.warning("购物车：未找到「完成编辑」按钮")
            USER_LOG.warning("[步骤7/9 扩展信息] ✗ 购物车：未找到「完成编辑」按钮")
            return False

        await self._wait_finish_edit_clickable(page, finish_btn)
        await self._semi_click(page, finish_btn, metadata, config, use_operation_delay=False)

        import asyncio as _asyncio
        for _ in range(12):
            if await edit_modal.count() == 0 or not await edit_modal.is_visible():
                break
            await page.wait_for_timeout(400)
            await _asyncio.sleep(0)  # 让出控制权防止 Qt UI 无响应
        logger.info("购物车：已点击「完成编辑」，等待弹窗关闭")

        if await self._wait_cart_goods_added(page, timeout_ms=3_000):
            logger.info("购物车：已确认「已添加商品」区域出现，商品添加成功")
            return True
        else:
            logger.warning("购物车：弹窗已关闭但未检测到「已添加商品」区域，可能添加失败")
            USER_LOG.warning("[步骤7/9 扩展信息] ✗ 购物车：未检测到「已添加商品」，商品可能未成功添加")
            return False

    async def _try_dismiss_supplement_modal(self, page: Page, metadata: Dict[str, Any], config: Dict[str, Any]) -> None:
        supplement_selector = ", ".join(Selectors.SECURITY.get("PUBLISH_MODAL_SUPPLEMENT", []))
        if not supplement_selector:
            return
        try:
            dialog = page.locator(supplement_selector).first
            if await dialog.count() > 0 and await dialog.is_visible():
                logger.info("检测到补充信息弹窗，尝试自动处理（公共部分）")
                USER_LOG.info("[步骤7/9 扩展信息] ▶ 检测到补充信息弹窗，尝试处理")
                btn_candidates = [
                    "button:has-text('确定')",
                    "button:has-text('确认')",
                    "button:has-text('完成')",
                    "button:has-text('下一步')",
                    "button:has-text('知道了')",
                    "button:has-text('跳过')",
                ]
                for btn_sel in btn_candidates:
                    btn = dialog.locator(btn_sel).first
                    if await btn.count() > 0 and await btn.is_visible():
                        try:
                            from src.infrastructure.anti_risk.human_like import human_click

                            await human_click(page, btn, metadata, config)
                        except Exception:
                            await btn.click()
                        await PluginWaitHelper.wait_for_condition(
                            page,
                            lambda: self._supplement_modal_closed(dialog),
                            timeout_ms=2_000,
                            poll_interval_ms=250,
                            pause_callback=lambda: self._await_pause(metadata),
                        )
                        logger.info(f"已点击补充信息弹窗按钮: {btn_sel}")
                        USER_LOG.info("[步骤7/9 扩展信息] ✓ 已处理补充信息弹窗")
                        break
        except Exception as e:
            logger.warning(f"处理补充信息弹窗失败: {e}")
            USER_LOG.warning("[步骤7/9 扩展信息] ✗ 处理弹窗失败（不阻断）")
