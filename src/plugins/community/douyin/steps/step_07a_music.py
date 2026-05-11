# -*- coding: utf-8 -*-
"""
步骤7：图文 — 选择音乐（三步法重构版）
文件路径: src/plugins/community/douyin/steps/step_07a_music.py

Playwright MCP 实测（图文发布 /content/post/image，2026-04）要点：
  · 入口：占位「点击添加合适作品风格音乐」与操作区为同一父级下并列子节点，仅点击**内含 exact「选择音乐」的那一列**（快照 e300），无其它兜底路径。
  · 抽屉：含「搜索音乐」输入、多枚 role=tab、列表项含时长与「万人使用」；Tab/列表在「搜索音乐」祖先容器内查找。

流程：
  步骤1  点击扩展信息卡片中「选择音乐」入口 → 等待音乐抽屉出现
          判定：搜索框可见且可解析音乐抽屉根（含多 Tab）；第 2 次起 force 点击入口
  步骤2  在列表前 N 条中随机选一首（或按名）→ 点击行 → 仅在行内/抽屉内点「使用」（禁止全页）
          判定：点击「使用」后 input[placeholder="搜索音乐"] 不再可见（抽屉已关）
  步骤3  检测扩展信息区出现「修改音乐」文案 → 整步完成

metadata 字段：
  music_random      : True → 随机选推荐列表中任意一首（默认也是如此）
  music_keyword     : 可选，搜索关键字
  music_name        : 可选，指定曲名（模糊匹配）
  music_category    : 可选，分类 Tab，默认「推荐」
  skip_select_music : True → 整步跳过
  music_use_hover_ms: hover 后等待「使用」出现的毫秒数，默认 800
"""
import asyncio
import logging
import random
import re
from typing import Any, Dict, List, Optional

from playwright.async_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

# 最长等待时间（单位：ms）
_DRAWER_OPEN_TIMEOUT = 12_000
_DRAWER_OPEN_INITIAL_WAIT_MS = 450  # 点击入口后稍候再轮询，减少动画期误判
_LIST_LOAD_TIMEOUT = 15_000
_USE_BTN_TIMEOUT = 10_000
_DRAWER_CLOSE_TIMEOUT = 8_000
_MODIFY_VISIBLE_TIMEOUT = 15_000
# 随机选曲仅在列表前 N 条中选，避免深行/虚拟列表导致行内无「使用」
_RANDOM_ROW_POOL_MAX = 15
_ROW_SUMMARY_LOG_MAX = 80


class SelectMusicStep(BasePublishStep):
    """图文：三步法选择背景音乐。"""

    # ──────────────────────────────────────────────────────────────────────────
    # 主流程
    # ──────────────────────────────────────────────────────────────────────────

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        config = metadata.get("anti_risk_config") or {}

        if metadata.get("skip_select_music") is True:
            logger.info("选择音乐：skip_select_music=True，跳过")
            USER_LOG.info("选择音乐 ✓ 跳过（任务设置跳过）")
            return None

        is_random = bool(metadata.get("music_random"))
        has_config = is_random or bool(
            metadata.get("music_keyword")
            or metadata.get("music_name")
            or metadata.get("music_category")
        )
        if not has_config:
            logger.info("选择音乐：未配置任何音乐字段，跳过")
            USER_LOG.info("选择音乐 ✓ 跳过（任务未配置音乐）")
            return None

        # 已选过？
        if await self._is_modify_music_visible(page):
            USER_LOG.info("选择音乐 ✓ 已有音乐（跳过）")
            return None

        await self._scroll_to_music_entry(page)

        # ── 步骤1：打开抽屉 ──────────────────────────────────────────────────
        opened = False
        for attempt in range(1, 4):
            logger.info("选择音乐：[步骤1] 尝试打开抽屉（第 %d/3 次）", attempt)
            # 第 2 次起仅用 force 点击同一入口，减少拟人首击未命中
            await self._click_music_entry(
                page, metadata, config, force_only=(attempt >= 2)
            )
            if await self._wait_drawer_open(page, _DRAWER_OPEN_TIMEOUT):
                logger.info("选择音乐：[步骤1] 抽屉已打开（第 %d 次）", attempt)
                opened = True
                break
            logger.warning("选择音乐：[步骤1] 第 %d 次抽屉未出现，等待后重试", attempt)
            await page.wait_for_timeout(1500)

        if not opened:
            USER_LOG.error("选择音乐 ✗ 无法打开音乐抽屉")
            return PublishResult(success=False, error_message="选择音乐：无法打开音乐抽屉")

        # 切换分类 Tab（可选）
        category = (metadata.get("music_category") or "推荐").strip()
        if category != "推荐":
            await self._switch_tab(page, category)
            await page.wait_for_timeout(800)

        # 搜索关键字（可选）
        keyword = (metadata.get("music_keyword") or "").strip()
        if keyword:
            await self._fill_search(page, keyword)

        # ── 步骤2：选曲 + 点「使用」+ 等抽屉关闭 ──────────────────────────────
        logger.info("选择音乐：[步骤2] 等待推荐列表加载")
        if not await self._wait_music_list_loaded(page, _LIST_LOAD_TIMEOUT):
            return PublishResult(success=False, error_message="选择音乐：推荐列表未及时加载")

        music_name = (metadata.get("music_name") or "").strip()
        row = await self._pick_row(page, is_random=is_random, name_filter=music_name)
        if row is None:
            return PublishResult(success=False, error_message="选择音乐：未在列表中找到可用曲目")

        use_clicked = False
        for try_idx in range(1, 4):
            logger.info("选择音乐：[步骤2] 第 %d 次点击曲目行并寻找「使用」", try_idx)
            use_clicked = await self._click_row_and_use(page, row, metadata)
            if use_clicked:
                break
            if try_idx < 3:
                next_row = await self._pick_row(page, is_random=True, exclude=row)
                if next_row:
                    row = next_row
            await page.wait_for_timeout(600)

        if not use_clicked:
            return PublishResult(success=False, error_message="选择音乐：未出现或未点到「使用」按钮")

        # 等抽屉关闭（搜索框消失）
        logger.info("选择音乐：[步骤2] 等待抽屉关闭")
        await self._wait_drawer_closed(page, _DRAWER_CLOSE_TIMEOUT)

        # ── 步骤3：确认「修改音乐」出现 ──────────────────────────────────────
        logger.info("选择音乐：[步骤3] 等待「修改音乐」标签")
        if await self._wait_modify_music(page, _MODIFY_VISIBLE_TIMEOUT):
            name = await self._read_selected_name(page)
            USER_LOG.info("选择音乐 ✓ 完成%s", f"（已选：{name}）" if name else "")
            return None

        return PublishResult(success=False, error_message="选择音乐：点击使用后未出现「修改音乐」")

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤1：打开抽屉
    # ──────────────────────────────────────────────────────────────────────────

    async def _scroll_to_music_entry(self, page: Page) -> None:
        """将扩展信息区滚动到视口内。优先锚定音乐灰条占位文案，避免「选择音乐」.first 落到错误区域。"""
        for query in ("点击添加合适作品风格音乐", "扩展信息", "选择音乐"):
            try:
                anchor = page.get_by_text(query, exact=False).first
                if await anchor.count() > 0:
                    await anchor.scroll_into_view_if_needed()
                    await page.wait_for_timeout(300)
                    return
            except Exception:
                continue

    async def _music_entry_right_cell_from_placeholder(self, page: Page) -> Optional[Locator]:
        """
        从占位文案上溯父级，找到「同一容器下多列子节点」中含 exact「选择音乐」的那一列（通常为第二列，快照 e295+e300）。
        比单纯 XPath 兄弟节点更耐中间多包一层 wrapper。
        """
        try:
            ph = page.get_by_text("点击添加合适作品风格音乐", exact=False).first
            if await ph.count() == 0 or not await ph.is_visible():
                return None
            for depth in range(1, 12):
                anc = ph.locator(f"xpath=ancestor::div[{depth}]")
                if await anc.count() == 0:
                    break
                kids = anc.locator(":scope > *")
                nk = await kids.count()
                if nk < 2:
                    continue
                for idx in range(1, nk):
                    cell = kids.nth(idx)
                    try:
                        if not await cell.is_visible():
                            continue
                        if await cell.get_by_text("选择音乐", exact=True).count() > 0:
                            return cell
                    except Exception:
                        continue
            return None
        except Exception:
            return None

    async def _music_drawer_root(self, page: Page) -> Optional[Locator]:
        """
        以「搜索音乐」输入为锚，上溯到同时包含多个分类 Tab 的容器，作为抽屉内操作作用域。
        避免 page.get_by_role('tab') 命中页面其它区域（若 a11y 树异常时）。
        """
        try:
            inp = page.get_by_placeholder("搜索音乐").first
            if await inp.count() == 0 or not await inp.is_visible():
                return None
            for depth in range(2, 28):
                anc = inp.locator(f"xpath=ancestor::div[{depth}]")
                if await anc.count() == 0:
                    break
                try:
                    tabs = anc.get_by_role("tab")
                    tc = await tabs.count()
                    if tc >= 3:
                        return anc
                except Exception:
                    continue
            return None
        except Exception:
            return None

    async def _click_music_entry(
        self,
        page: Page,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        *,
        force_only: bool = False,
    ) -> None:
        """
        唯一方案：从占位「点击添加合适作品风格音乐」上溯父级，在并列子节点中找到
        内含 exact「选择音乐」的那一列并点击（灰条右侧入口，勿点整条灰条）。
        force_only=True 时跳过拟人轨迹，直接 force 点击（用于重试打开抽屉）。
        """
        async def _do_click(loc: Locator) -> None:
            try:
                await loc.scroll_into_view_if_needed()
                await page.wait_for_timeout(200)
            except Exception:
                pass
            if force_only:
                await loc.click(force=True, timeout=8000)
                return
            try:
                from src.infrastructure.anti_risk.human_like import human_click
                await human_click(page, loc, metadata, config, use_operation_delay=False)
            except Exception:
                await loc.click(force=True, timeout=8000)

        right_cell = await self._music_entry_right_cell_from_placeholder(page)
        if right_cell is None:
            logger.warning("选择音乐：未定位到灰条右侧入口（占位文案并列列中含「选择音乐」）")
            return
        logger.info(
            "选择音乐：点击音乐灰条内含「选择音乐」的列%s",
            "（force）" if force_only else "",
        )
        await _do_click(right_cell)

    async def _wait_drawer_open(self, page: Page, timeout_ms: int) -> bool:
        """抽屉已打开：搜索框可见且能解析到含多 Tab 的抽屉根（与 _music_drawer_root 一致）。"""
        await page.wait_for_timeout(_DRAWER_OPEN_INITIAL_WAIT_MS)
        deadline = timeout_ms
        interval = 300
        elapsed = 0
        while elapsed < deadline:
            if await self._is_drawer_open(page):
                return True
            await page.wait_for_timeout(interval)
            elapsed += interval
            await asyncio.sleep(0)
        return False

    async def _is_drawer_open(self, page: Page) -> bool:
        """搜索框可见且存在音乐抽屉根（多 Tab 祖先），避免仅命中无关 input。"""
        try:
            inp = page.get_by_placeholder("搜索音乐").first
            if await inp.count() == 0 or not await inp.is_visible():
                return False
        except Exception:
            return False
        try:
            return await self._music_drawer_root(page) is not None
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤2a：切换分类 Tab
    # ──────────────────────────────────────────────────────────────────────────

    async def _switch_tab(self, page: Page, category: str) -> None:
        root = await self._music_drawer_root(page)
        scope = root if root is not None else page
        try:
            tab = scope.get_by_role("tab", name=category).first
            if await tab.count() > 0 and await tab.is_visible():
                selected = (await tab.get_attribute("aria-selected")) or ""
                if selected != "true":
                    await tab.click()
                    await page.wait_for_timeout(800)
                logger.info("选择音乐：Tab 切换到「%s」", category)
                return
        except Exception:
            pass
        # 枚举所有 tab 匹配（仍在抽屉作用域内）
        try:
            tabs = scope.get_by_role("tab")
            n = await tabs.count()
            for i in range(n):
                tab = tabs.nth(i)
                raw = (await tab.text_content()) or ""
                if re.sub(r"\s+", "", raw) == re.sub(r"\s+", "", category):
                    selected = (await tab.get_attribute("aria-selected")) or ""
                    if selected != "true":
                        await tab.click()
                        await page.wait_for_timeout(800)
                    logger.info("选择音乐：Tab 切换到「%s」（枚举）", category)
                    return
        except Exception:
            pass
        logger.warning("选择音乐：未找到分类 Tab「%s」，保持默认", category)

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤2b：搜索
    # ──────────────────────────────────────────────────────────────────────────

    async def _fill_search(self, page: Page, keyword: str) -> None:
        try:
            inp = page.get_by_placeholder("搜索音乐").first
            if await inp.count() > 0 and await inp.is_visible():
                await inp.click()
                await inp.fill("")
                await page.wait_for_timeout(200)
                await inp.fill(keyword)
                await inp.press("Enter")
                await page.wait_for_timeout(1500)
                logger.info("选择音乐：已搜索「%s」", keyword[:20])
        except Exception as e:
            logger.warning("选择音乐：搜索框填写失败 %s", e)

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤2c：等待列表加载
    # ──────────────────────────────────────────────────────────────────────────

    async def _wait_music_list_loaded(self, page: Page, timeout_ms: int) -> bool:
        """在抽屉内等待曲目行出现（含时长 + 使用量的 div 可见即算加载完成）。"""
        dur_re = re.compile(r"\d{1,2}:\d{2}")
        use_re = re.compile(r"\d+\.?\d*\s*万人使用|\d+\s*人使用")
        elapsed = 0
        interval = 400
        while elapsed < timeout_ms:
            try:
                rows = await self._get_music_rows(page)
                if rows:
                    logger.info("选择音乐：列表已加载，共 %d 条", len(rows))
                    return True
            except Exception:
                pass
            # 次选：抽屉内是否已出现使用量文案（避免全页误匹配）
            try:
                root = await self._music_drawer_root(page)
                s = root if root is not None else page
                loc = s.get_by_text(use_re).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                pass
            await page.wait_for_timeout(interval)
            elapsed += interval
            await asyncio.sleep(0)

        # 超时兜底：抽屉仍开着就继续
        if await self._is_drawer_open(page):
            logger.warning("选择音乐：列表信号超时但抽屉仍开，直接尝试定位行")
            return True
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤2d：获取曲目行 / 选行
    # ──────────────────────────────────────────────────────────────────────────

    async def _get_music_rows(self, page: Page) -> List[Locator]:
        """
        在音乐抽屉作用域内查找曲目行（MCP：每行 generic[cursor=pointer]，多渲染为 div）。
        同时含「时长（MM:SS）」与「使用量」；按 y 去重。
        """
        dur_re = re.compile(r"\d{1,2}:\d{2}")
        use_re = re.compile(r"\d+\.?\d*\s*万人使用|\d+\s*人使用")
        vp = page.viewport_size
        vw = float(vp["width"]) if vp else 1280.0

        root = await self._music_drawer_root(page)
        scope = root if root is not None else page

        try:
            candidates = (
                scope.locator("div")
                .filter(has_text=dur_re)
                .filter(has_text=use_re)
            )
            raw_n = await candidates.count()
        except Exception:
            return []

        scored: List[tuple] = []
        for i in range(min(raw_n, 150)):
            el = candidates.nth(i)
            try:
                if not await el.is_visible():
                    continue
                bb = await el.bounding_box()
                if not bb:
                    continue
                h, w = bb["height"], bb["width"]
                # 行高 30–200px，宽度 100px 以上且非整页宽
                if h < 30 or h > 200 or w < 100 or w > vw * 0.97:
                    continue
                txt = (await el.inner_text()).strip()
                if len(txt) > 500:  # 排除包含整个列表的父节点
                    continue
                scored.append((bb["y"], h, el))
            except Exception:
                continue

        scored.sort(key=lambda x: x[0])
        rows: List[Locator] = []
        last_y = -9999.0
        for y, _h, el in scored:
            if y - last_y < 8:  # 同一行去重
                continue
            last_y = y
            rows.append(el)
        return rows

    async def _pick_row(
        self,
        page: Page,
        is_random: bool = True,
        name_filter: str = "",
        exclude: Optional[Locator] = None,
    ) -> Optional[Locator]:
        rows = await self._get_music_rows(page)
        if not rows:
            logger.warning("选择音乐：_get_music_rows 返回空列表")
            return None

        # 排除已试过的行
        if exclude is not None:
            try:
                ex_bb = await exclude.bounding_box()
                if ex_bb:
                    rows = [r for r in rows if abs((await r.bounding_box() or {}).get("y", -1) - ex_bb["y"]) > 8]
            except Exception:
                pass

        # 按名称过滤
        if name_filter:
            named = []
            for r in rows:
                try:
                    if name_filter in (await r.inner_text()):
                        named.append(r)
                except Exception:
                    pass
            if named:
                rows = named
            else:
                logger.warning("选择音乐：未找到曲名「%s」，使用全部行", name_filter)

        if not rows:
            return None
        if is_random:
            pool = rows[:_RANDOM_ROW_POOL_MAX]
            chosen = random.choice(pool)
            logger.info(
                "选择音乐：随机选取候选池第 %d/%d 条（列表共解析 %d 条，候选上限=%d）",
                pool.index(chosen) + 1,
                len(pool),
                len(rows),
                _RANDOM_ROW_POOL_MAX,
            )
            return chosen
        logger.info("选择音乐：选取第 1 条（共 %d 条）", len(rows))
        return rows[0]

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤2e：点击行 → 等待并点击「使用」
    # ──────────────────────────────────────────────────────────────────────────

    async def _click_row_and_use(
        self, page: Page, row: Locator, metadata: Dict[str, Any]
    ) -> bool:
        """点击曲目行，再等「使用」按钮出现并点击。返回 True 表示成功。"""
        hover_ms = max(300, min(int(metadata.get("music_use_hover_ms") or 800), 6000))

        try:
            await row.scroll_into_view_if_needed()
            await page.wait_for_timeout(200)
        except Exception:
            pass

        # 点击行（优先拟人，失败退化）
        clicked = False
        try:
            config = metadata.get("anti_risk_config") or {}
            from src.infrastructure.anti_risk.human_like import human_click
            await human_click(page, row, metadata, config, use_operation_delay=False)
            clicked = True
        except Exception:
            pass
        if not clicked:
            try:
                await row.click(force=True, timeout=5000)
                clicked = True
            except Exception as e:
                logger.warning("选择音乐：曲目行点击失败 %s", e)
                return False

        await page.wait_for_timeout(500)

        try:
            summary = (await row.inner_text()).strip().replace("\n", " ")
            if len(summary) > _ROW_SUMMARY_LOG_MAX:
                summary = summary[:_ROW_SUMMARY_LOG_MAX] + "…"
            logger.info("选择音乐：等待「使用」前曲目行摘要：%s", summary)
        except Exception:
            logger.info("选择音乐：等待「使用」前无法读取曲目行摘要")

        # 等「使用」按钮出现并点击（禁止全页查找，避免误点）
        if await self._wait_and_click_use_btn(page, row, _USE_BTN_TIMEOUT):
            return True

        # 再 hover 一次（部分版本需悬停才显示）
        try:
            await row.hover(timeout=5000)
            await page.wait_for_timeout(hover_ms)
        except Exception:
            pass
        return await self._wait_and_click_use_btn(page, row, 4000)

    async def _wait_and_click_use_btn(
        self, page: Page, row: Optional[Locator], timeout_ms: int
    ) -> bool:
        """仅在当前行与音乐抽屉根内查找「使用」按钮并点击（禁止 page 全表扫描）。"""
        elapsed = 0
        interval = 300
        deadline = max(2000, timeout_ms)

        while elapsed < deadline:
            drawer = await self._music_drawer_root(page)

            if row is not None:
                btn = await self._find_use_btn(row)
                if btn is not None:
                    try:
                        await btn.click(force=True)
                        logger.info("选择音乐：已点击「使用」（曲目行内）")
                        return True
                    except Exception:
                        pass

            if drawer is not None:
                btn = await self._find_use_btn(drawer)
                if btn is not None:
                    try:
                        await btn.click(force=True)
                        logger.info("选择音乐：已点击「使用」（音乐抽屉内，非全页）")
                        return True
                    except Exception:
                        pass

            await page.wait_for_timeout(interval)
            elapsed += interval
            await asyncio.sleep(0)
        return False

    async def _find_use_btn(self, scope) -> Optional[Locator]:
        """仅 role=button 且可访问名「使用」，避免 span 等宽泛匹配误点。"""
        try:
            btns = scope.get_by_role("button", name="使用")
            n = await btns.count()
            for i in range(n):
                b = btns.nth(i)
                if not await b.is_visible():
                    continue
                txt = (await b.inner_text()).strip().replace("\n", "")
                if txt == "使用":
                    return b
        except Exception:
            pass
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤2f：等待抽屉关闭
    # ──────────────────────────────────────────────────────────────────────────

    async def _wait_drawer_closed(self, page: Page, timeout_ms: int) -> None:
        """等待「搜索音乐」输入框消失（即抽屉已关闭）。"""
        elapsed = 0
        interval = 300
        while elapsed < timeout_ms:
            if not await self._is_drawer_open(page):
                logger.info("选择音乐：抽屉已关闭")
                return
            await page.wait_for_timeout(interval)
            elapsed += interval
            await asyncio.sleep(0)
        logger.warning("选择音乐：抽屉关闭等待超时（可能已选好但抽屉仍开着）")

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤3：检测「修改音乐」
    # ──────────────────────────────────────────────────────────────────────────

    async def _wait_modify_music(self, page: Page, timeout_ms: int) -> bool:
        elapsed = 0
        interval = 400
        while elapsed < timeout_ms:
            if await self._is_modify_music_visible(page):
                return True
            await page.wait_for_timeout(interval)
            elapsed += interval
            await asyncio.sleep(0)
        return False

    async def _is_modify_music_visible(self, page: Page) -> bool:
        """「修改音乐」文案可见即视为已选。"""
        try:
            loc = page.get_by_text("修改音乐", exact=True)
            n = await loc.count()
            for i in range(n):
                el = loc.nth(i)
                try:
                    if await el.is_visible():
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        for sel in Selectors.PUBLISH.get("MUSIC_ENTRY_MODIFY") or []:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0 or not await loc.is_visible():
                    continue
                if (await loc.inner_text()).strip() == "修改音乐":
                    return True
            except Exception:
                continue
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # 已选音乐名称（仅用于日志）
    # ──────────────────────────────────────────────────────────────────────────

    async def _read_selected_name(self, page: Page) -> str:
        for sel in Selectors.PUBLISH.get("MUSIC_SELECTED_NAME") or []:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return (await loc.inner_text()).strip()
            except Exception:
                continue
        # 从「修改音乐」周围提取歌名
        try:
            loc = page.get_by_text("修改音乐", exact=True).first
            if await loc.count() > 0:
                parent = loc.locator("xpath=ancestor::*[3]").first
                if await parent.count() > 0:
                    txt = (await parent.inner_text()).strip()
                    lines = [
                        l.strip() for l in txt.splitlines()
                        if l.strip()
                        and l.strip() != "修改音乐"
                        and not re.match(r"^\d{1,2}:\d{2}$", l.strip())
                    ]
                    if lines:
                        return lines[0]
        except Exception:
            pass
        return ""

    # ──────────────────────────────────────────────────────────────────────────
    # 旧接口兼容（其它模块可能调用）
    # ──────────────────────────────────────────────────────────────────────────

    async def _already_has_music(self, page: Page) -> bool:
        return await self._is_modify_music_visible(page)

    async def _wait_modify_music_visible(self, page: Page, timeout_ms: int) -> bool:
        return await self._wait_modify_music(page, timeout_ms)
