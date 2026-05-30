# -*- coding: utf-8 -*-
"""
步骤6：作者服务（含购物车/关联商品挂载）
文件路径: src/plugins/community/kuaishou/steps/step_06_author_service.py

依据：docs/03插件系统/OpenClaw 报告分析报告/快手_购物车功能DOM分析报告_20260402.md

流程（均在主文档内，无 iframe / Shadow DOM）：
  若 metadata["kuaishou_goods_name"] 有值，则：
    1. 点击「选择服务类型」combobox，展开服务类型菜单
    2. 选择「关联商品」选项，等待商品输入框变为可用
    3. 点击「关联商品获得更多收入」combobox，激活商品搜索
    4. 输入商品名称，等待即时过滤完成
    5. 点击第一个商品选项，完成挂载
    6. 验证 combobox 显示已选择的商品名称（collapsed 状态）
    任一关键步骤失败则返回 PublishResult(success=False)，终止发布任务。
  未配置商品时直接跳过（return None）。
"""
import logging
from typing import Dict, Any, Optional

from playwright.async_api import Page, Locator, TimeoutError as PlaywrightTimeoutError

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

# 各等待阶段超时（毫秒）
_DROPDOWN_APPEAR_MS = 5_000   # 下拉菜单出现
_GOODS_INPUT_ENABLE_MS = 6_000  # 商品输入框从 disabled 变为 enabled
_FILTER_SETTLE_MS = 2_500      # 输入后等待即时过滤
_ITEM_APPEAR_MS = 6_000        # 商品列表项出现
_COLLAPSE_MS = 3_000           # 选择后下拉收起


class AuthorServiceStep(BasePublishStep):
    """作者服务：若任务配置了快手商品名称则自动挂载关联商品（尽力而为，失败不阻断）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        _p = self._step_prefix(metadata, "作者服务")
        goods_name = (metadata.get("kuaishou_goods_name") or "").strip()
        if not goods_name:
            logger.debug("步骤6: kuaishou_goods_name 为空，跳过作者服务商品挂载")
            USER_LOG.info("%s ✓ 无需挂载商品，跳过", _p)
            return None

        USER_LOG.info("%s ▶ 尝试挂载关联商品：%s", _p, goods_name)

        try:
            result = await self._mount_goods(page, goods_name, _p)
            return result
        except Exception as e:
            logger.error("步骤6: 关联商品挂载异常: %s", e, exc_info=True)
            USER_LOG.error("%s ✗ 关联商品挂载异常，终止发布: %s", _p, str(e)[:120])
            return PublishResult(success=False, error_message=f"关联商品挂载异常: {str(e)[:120]}", failed_step="步骤6/作者服务")

    # ------------------------------------------------------------------
    # 核心流程
    # ------------------------------------------------------------------

    async def _mount_goods(self, page: Page, goods_name: str, _p: str = "") -> StepOutcome:
        """关联商品挂载完整流程（共6步）。任一步骤失败返回 PublishResult(False)。"""

        # 滚动到作者服务区域，确保元素可见
        from src.infrastructure.browser.human_behavior import HumanBehavior
        await HumanBehavior.scroll_to_bottom(page)
        await page.wait_for_timeout(500)

        # ── 重试快速检测：若上一次实际已成功挂载（验证误判），直接返回成功 ──────────
        # 场景：第1次 card.click() 成功但 _verify_goods_selected 误报失败，导致重试；
        # 重试时 combobox 已处于"已选中"状态，selection-item 里有商品名即可视为成功
        if await self._is_goods_already_mounted(page, goods_name):
            logger.debug("步骤6: 检测到商品已挂载（重试快速退出）")
            USER_LOG.info("%s ✓ 关联商品已挂载（重试检测确认）：%s", _p, goods_name)
            return None

        # ── 步骤1&2：选择「关联商品」服务类型 ─────────────────────────
        # 先检测是否已经选择了「关联商品」（重试时页面已是选中状态），避免重复点击
        already_selected = await self._is_goods_type_already_selected(page)
        if already_selected:
            logger.debug("步骤6: 「关联商品」已为当前选中状态，跳过触发器点击")
        else:
            trigger = await self._get_service_type_trigger(page)
            if trigger is None:
                USER_LOG.error("%s ✗ 未找到「选择服务类型」下拉框，终止发布", _p)
                return PublishResult(success=False, error_message="未找到「选择服务类型」下拉框", failed_step="步骤6/作者服务")
            await trigger.scroll_into_view_if_needed()
            await trigger.click()
            logger.debug("步骤6: 已点击「选择服务类型」，等待下拉菜单出现")

            option = await self._wait_for_goods_option(page)
            if option is None:
                await page.keyboard.press("Escape")
                USER_LOG.error("%s ✗ 未找到「关联商品」选项，终止发布", _p)
                return PublishResult(success=False, error_message="未找到「关联商品」选项", failed_step="步骤6/作者服务")
            await option.click()
            logger.debug("步骤6: 已选择「关联商品」")

        # ── 等待并定位商品搜索输入框（变为 enabled 状态） ──────────────
        goods_input = await self._wait_for_goods_input_enabled(page)
        if goods_input is None:
            USER_LOG.error("%s ✗ 商品输入框未变为可用状态，终止发布", _p)
            return PublishResult(success=False, error_message="关联商品输入框未变为可用状态", failed_step="步骤6/作者服务")

        # ── 步骤3：点击商品输入框，激活搜索 ───────────────────────────
        # 将输入框滚动到视口中央（而非仅确保可见），保证上下均有足够空间；
        # 否则输入框贴底时 Ant Design 会把商品卡片弹窗向上翻转，影响点击兜底
        try:
            from src.infrastructure.browser.human_behavior import HumanBehavior
            await HumanBehavior.scroll_to_locator(page, goods_input, target_ratio=0.5)
        except Exception:
            await goods_input.scroll_into_view_if_needed()
        await page.wait_for_timeout(300)
        await goods_input.click()
        await page.wait_for_timeout(500)

        # ── 步骤4：逐字输入商品名称，触发即时搜索过滤 ───────────────────
        # 使用 page.keyboard 确保键盘事件发给当前焦点元素（combobox 内部 input），
        # 避免在容器 div 上调用 .type() 导致 React 合成事件未触发
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Delete")
        await page.keyboard.type(goods_name, delay=80)
        logger.debug("步骤6: 已输入商品名称「%s」，等待即时过滤", goods_name)
        await page.wait_for_timeout(_FILTER_SETTLE_MS)

        # ── 步骤5：选择商品结果项（键盘优先，降级为 DOM 点击）──────────────────
        item_selected = await self._select_goods_item(page, goods_name)
        if not item_selected:
            await page.keyboard.press("Escape")
            USER_LOG.error(
                "%s ✗ 搜索「%s」无结果或无法选中商品卡片，终止发布", _p, goods_name
            )
            return PublishResult(
                success=False,
                error_message=f"搜索商品「{goods_name}」无结果，未能选中商品卡片",
                failed_step="步骤6/作者服务",
            )

        # ── 步骤6：验证挂载成功 ────────────────────────────────────────────
        success = await self._verify_goods_selected(page, goods_name)
        if success:
            USER_LOG.info("%s ✓ 关联商品挂载完成：%s", _p, goods_name)
        else:
            USER_LOG.error("%s ✗ 商品挂载后验证失败（下拉未收起），终止发布", _p)
            return PublishResult(
                success=False,
                error_message="关联商品挂载后验证失败，下拉未收起",
                failed_step="步骤6/作者服务",
            )
        return None

    # ------------------------------------------------------------------
    # 定位辅助
    # ------------------------------------------------------------------

    async def _is_goods_type_already_selected(self, page: Page) -> bool:
        """
        检测「选择服务类型」下拉框当前是否已显示「关联商品」。
        重试时页面可能已选好，直接跳过触发器点击，避免将已选状态重置为初始。
        """
        try:
            # 查找作者服务区域内显示「关联商品」文案的已选 combobox
            loc = page.locator(
                ".ant-select-selection-item:has-text('关联商品'), "
                "[class*='ant-select'] [title='关联商品'], "
                "[class*='_author-service_'] .ant-select-selection-item"
            ).first
            if await loc.count() > 0:
                text = (await loc.inner_text()).strip()
                if "关联商品" in text:
                    return True
        except Exception as e:
            logger.debug("步骤6: 检测已选状态异常: %s", e)
        return False

    async def _is_goods_already_mounted(self, page: Page, goods_name: str) -> bool:
        """
        检测商品是否已经成功挂载（combobox 处于"已选中"状态，selection-item 含商品名关键字）。
        用于重试时快速判断上一次是否实际成功（验证误判场景）。
        """
        if not goods_name:
            return False
        key = goods_name[:8]
        try:
            items = page.locator(".ant-select-selection-item")
            count = await items.count()
            for i in range(count):
                try:
                    text = (await items.nth(i).inner_text()).strip()
                    if key in text:
                        logger.debug("步骤6: 检测到 selection-item 含商品关键字「%s」，已挂载", key)
                        return True
                except Exception:
                    continue
        except Exception as e:
            logger.debug("步骤6: _is_goods_already_mounted 检测异常: %s", e)
        return False

    async def _get_service_type_trigger(self, page: Page) -> Optional[Locator]:
        """
        定位「选择服务类型」combobox 触发器。
        优先用角色+名称（DOM 报告推荐），降级到 CSS 选择器列表。
        """
        # 首选：role=combobox + 名称（最稳定）
        try:
            loc = page.get_by_role("combobox", name="选择服务类型")
            if await loc.count() > 0:
                logger.debug("步骤6: [选择服务类型] 命中 get_by_role combobox")
                return loc.first
        except Exception as e:
            logger.debug("步骤6: [选择服务类型] role 定位异常: %s", e)

        # 降级：CSS 选择器备用列表
        return await self._find_first_css(
            page,
            Selectors.AUTHOR_SERVICE.get("SERVICE_TYPE_TRIGGER", []),
            "选择服务类型下拉框",
        )

    async def _wait_for_goods_option(self, page: Page) -> Optional[Locator]:
        """等待并返回「关联商品」选项（下拉展开后才可见）。"""
        # 首选：role=option + 名称（DOM 报告：关联商品选项 role=option）
        try:
            loc = page.get_by_role("option", name="关联商品")
            await loc.first.wait_for(state="visible", timeout=_DROPDOWN_APPEAR_MS)
            logger.debug("步骤6: [关联商品选项] 命中 get_by_role option")
            return loc.first
        except (PlaywrightTimeoutError, Exception) as e:
            logger.debug("步骤6: [关联商品选项] role 定位失败: %s，尝试 CSS 降级", e)

        # 降级：CSS 选择器备用
        return await self._find_first_css(
            page,
            Selectors.AUTHOR_SERVICE.get("OPTION_GOODS", []),
            "关联商品选项",
        )

    async def _wait_for_goods_input_enabled(self, page: Page) -> Optional[Locator]:
        """
        等待「关联商品获得更多收入」combobox 变为可用（非 disabled）。

        DOM 报告确认：Ant Design Select 占位符文案在 <span> 而非 <input> 的 placeholder
        属性上，因此不能用 input[placeholder*=...] 定位；需要通过以下三层策略查找：
          1. get_by_role('combobox', name=...) — Ant Design 在 input 上设置 role=combobox，
             并通过 aria-label 传递可访问名称（DOM 报告 §步骤3 推荐，最稳定）
          2. 通过 placeholder-span 文案定位父 .ant-select 容器，再查找其内部 input
          3. CSS 兜底：作者服务区域内第二个 .ant-select 或不含 disabled 类的 show-search
        """
        deadline_ms = _GOODS_INPUT_ENABLE_MS
        poll_interval = 300

        for _ in range(int(deadline_ms / poll_interval)):

            # ── 策略1：role=combobox + name（DOM 报告 §步骤3 推荐）──────────────
            try:
                cb = page.get_by_role("combobox", name="关联商品获得更多收入")
                if await cb.count() > 0:
                    el = cb.first
                    aria_disabled = await el.get_attribute("aria-disabled")
                    disabled_attr = await el.get_attribute("disabled")
                    if await el.is_visible() and aria_disabled != "true" and disabled_attr is None:
                        logger.debug("步骤6: [商品combobox] 策略1(role) enabled")
                        return el
            except Exception as e:
                logger.debug("步骤6: 策略1异常: %s", e)

            # ── 策略2：通过 placeholder span 文案找父容器再取内部 input ──────────
            try:
                container = page.locator(
                    ".ant-select:has(.ant-select-selection-placeholder:has-text('关联商品获得更多收入'))"
                ).first
                if await container.count() > 0:
                    cls_val = await container.get_attribute("class") or ""
                    if "ant-select-disabled" not in cls_val:
                        inner = container.locator("input.ant-select-selection-search-input").first
                        if await inner.count() == 0:
                            inner = container.locator("input").first
                        if await inner.count() > 0:
                            logger.debug("步骤6: [商品combobox] 策略2(placeholder-span) enabled")
                            return inner
            except Exception as e:
                logger.debug("步骤6: 策略2异常: %s", e)

            # ── 策略3：CSS 兜底（作者服务区内第二个 select 或未禁用的 show-search）──
            fallback_selectors = [
                "div[class*='_author-service_'] .ant-select:nth-of-type(2) input",
                "div[class*='_author-service_'] .ant-select-show-search:not(.ant-select-disabled) input",
            ] + list(Selectors.AUTHOR_SERVICE.get("GOODS_INPUT", []))
            for sel in fallback_selectors:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        disabled_attr = await loc.get_attribute("disabled")
                        aria_disabled = await loc.get_attribute("aria-disabled")
                        if disabled_attr is None and aria_disabled != "true":
                            logger.debug("步骤6: [商品输入框] 策略3(CSS) enabled: %s", sel)
                            return loc
                except Exception:
                    pass

            await page.wait_for_timeout(poll_interval)

        logger.debug("步骤6: [商品输入框] 等待 enabled 超时，所有策略均未命中")
        return None

    async def _select_goods_item(self, page: Page, goods_name: str) -> bool:
        """
        选中商品搜索结果中的第一个商品卡片。

        快手商品卡片是自定义 div（非标准 role=option），Ant Design autocomplete 标准行为：
        输入后按 ArrowDown 高亮第一项，再按 Enter 确认选中。此方法以键盘操作为主路，
        DOM 点击为备路，避免因类名随机哈希或浮层容器选择器不匹配导致点击失败。
        """
        # ── 主路：键盘 ArrowDown + Enter（Ant Design autocomplete 标准方式）────────
        try:
            await page.keyboard.press("ArrowDown")
            await page.wait_for_timeout(400)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(600)
            if await self._is_goods_already_mounted(page, goods_name):
                logger.debug("步骤6: [商品选中] 键盘方式成功")
                return True
            logger.debug("步骤6: [商品选中] 键盘方式后未检测到挂载，尝试 DOM 点击")
        except Exception as e:
            logger.debug("步骤6: [商品选中] 键盘方式异常: %s", e)

        # ── 备路：DOM 点击（多策略定位卡片）────────────────────────────────────
        card = await self._wait_for_first_goods_item(page, goods_name)
        if card is None:
            return False
        try:
            # 点击前先把卡片滚到视口中央，避免因视口边缘导致点击坐标计算偏差
            try:
                from src.infrastructure.browser.human_behavior import HumanBehavior
                await HumanBehavior.scroll_to_locator(page, card, target_ratio=0.5)
            except Exception:
                await card.scroll_into_view_if_needed()
            await page.wait_for_timeout(200)
            await card.click()
            logger.debug("步骤6: [商品选中] DOM 点击方式执行")
            await page.wait_for_timeout(600)
            return True
        except Exception as e:
            logger.debug("步骤6: [商品选中] DOM 点击异常: %s", e)
            return False

    async def _wait_for_first_goods_item(self, page: Page, goods_name: str = "") -> Optional[Locator]:
        """
        等待商品搜索结果列表出现，返回第一个商品项的可点击 Locator。

        DOM 报告确认：快手商品卡片为自定义 div（非 role=option），浮层挂在 body 末位；
        采用多策略逐级定位，任一命中立即返回。
        """
        _timeout = _ITEM_APPEAR_MS

        # ── 候选下拉容器选择器（快手/Ant Design 浮层，按可能性从高到低）──────────
        dropdown_selectors = [
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden)",
            ".ant-select-dropdown",
            "[class*='ant-select-dropdown']",
            "[class*='_dropdown_']",
            "[class*='popup']",
        ]

        # ── 策略1：在可见下拉容器内用文本定位（DOM 报告 §步骤6 推荐方式）──────────
        if goods_name:
            snippet = goods_name[:15]   # 取前15字，不被截断标记...影响
            for dd_sel in dropdown_selectors:
                try:
                    dd = page.locator(dd_sel).first
                    if await dd.count() == 0:
                        continue
                    await dd.wait_for(state="visible", timeout=_timeout)
                    text_loc = dd.get_by_text(snippet, exact=False).first
                    if await text_loc.count() > 0 and await text_loc.is_visible():
                        logger.debug("步骤6: [商品卡片] 策略1(文本+容器 %s) 命中", dd_sel)
                        return text_loc
                except (PlaywrightTimeoutError, Exception) as e:
                    logger.debug("步骤6: [商品卡片] 策略1 容器=%s 失败: %s", dd_sel, e)

        # ── 策略2：role=option（全局，无父容器限制）──────────────────────────────
        try:
            loc = page.get_by_role("option").first
            await loc.wait_for(state="visible", timeout=_timeout)
            logger.debug("步骤6: [商品卡片] 策略2(role=option) 命中")
            return loc
        except (PlaywrightTimeoutError, Exception) as e:
            logger.debug("步骤6: [商品卡片] 策略2 失败: %s", e)

        # ── 策略3：标准 antd listbox > item 结构 ─────────────────────────────────
        try:
            loc = page.get_by_role("listbox").locator("[role='option'], .ant-select-item").first
            await loc.wait_for(state="visible", timeout=_timeout)
            logger.debug("步骤6: [商品卡片] 策略3(listbox>item) 命中")
            return loc
        except (PlaywrightTimeoutError, Exception) as e:
            logger.debug("步骤6: [商品卡片] 策略3 失败: %s", e)

        # ── 策略4：CSS 选择器兜底（GOODS_RESULT_CARD 配置 + 通用条目）──────────────
        css_fallbacks = list(Selectors.AUTHOR_SERVICE.get("GOODS_RESULT_CARD", [])) + [
            ".ant-select-item",
            ".ant-select-item-option",
            "[class*='ant-select-item']",
        ]
        for sel in css_fallbacks:
            try:
                loc = page.locator(sel).first
                await loc.wait_for(state="visible", timeout=_timeout)
                logger.debug("步骤6: [商品卡片] 策略4(CSS %s) 命中", sel)
                return loc
            except (PlaywrightTimeoutError, Exception) as e:
                logger.debug("步骤6: [商品卡片] 策略4 CSS=%s 失败: %s", sel, e)

        logger.debug("步骤6: [商品卡片] 所有策略均未命中")
        return None

    async def _verify_goods_selected(self, page: Page, goods_name: str = "") -> bool:
        """
        验证商品挂载成功：依次使用三种策略，任一命中即返回 True。

        注意：不再依赖 aria-expanded 属性——选中后 Ant Design 会将 combobox 的内部 input
        隐藏并用 selection-item 替换，此时 get_by_role("combobox", name=...) 可能找不到元素，
        导致原有验证逻辑误判为失败。
        """
        await page.wait_for_timeout(_COLLAPSE_MS)

        # ── 策略1：selection-item 显示商品名关键字（最直接的成功标志）────────────
        if goods_name:
            key = goods_name[:8]
            try:
                items = page.locator(".ant-select-selection-item")
                count = await items.count()
                for i in range(count):
                    text = (await items.nth(i).inner_text()).strip()
                    if key in text:
                        logger.debug("步骤6: 验证成功(策略1)：selection-item 含「%s」", key)
                        return True
            except Exception as e:
                logger.debug("步骤6: 策略1 selection-item 检测异常: %s", e)

        # ── 策略2：商品下拉弹窗已收起（无可见 dropdown） ────────────────────────
        try:
            visible_dropdown = page.locator(".ant-select-dropdown:not(.ant-select-dropdown-hidden)")
            if await visible_dropdown.count() == 0:
                logger.debug("步骤6: 验证成功(策略2)：商品下拉弹窗已收起")
                return True
        except Exception as e:
            logger.debug("步骤6: 策略2 dropdown 可见性检测异常: %s", e)

        # ── 策略3：combobox aria-expanded=false（兜底）──────────────────────────
        try:
            combobox = page.get_by_role("combobox", name="关联商品获得更多收入")
            if await combobox.count() > 0:
                aria_expanded = await combobox.first.get_attribute("aria-expanded")
                if aria_expanded != "true":
                    logger.debug("步骤6: 验证成功(策略3)：combobox aria-expanded=%s", aria_expanded)
                    return True
        except Exception as e:
            logger.debug("步骤6: 策略3 aria-expanded 检测异常: %s", e)

        logger.debug("步骤6: 三种验证策略均未通过，视为挂载失败")
        return False

    # ------------------------------------------------------------------
    # 通用工具
    # ------------------------------------------------------------------

    async def _find_first_css(
        self, page: Page, selectors: list, label: str
    ) -> Optional[Locator]:
        """依次尝试 CSS 选择器列表，返回第一个 count>0 的 Locator.first，全部失败返回 None。"""
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    logger.debug("步骤6: [%s] CSS 命中: %s", label, sel)
                    return loc
            except Exception as e:
                logger.debug("步骤6: [%s] CSS 选择器异常 %s → %s", label, sel, e)
        logger.debug("步骤6: [%s] 所有 CSS 选择器均未命中", label)
        return None
