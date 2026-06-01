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
from collections import deque
import logging
import random
import re
from typing import Any, Deque, Dict, List, Optional

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
# 随机选曲仅在当前视口内选，避免深行/虚拟列表导致行内无「使用」或 locator 失效。
_RANDOM_ROW_POOL_MAX = 10
_RECENT_MUSIC_MEMORY_MAX = 12
_ROW_SUMMARY_LOG_MAX = 80


class SelectMusicStep(BasePublishStep):
    """图文：三步法选择背景音乐。"""

    _recent_music_keys: Deque[str] = deque(maxlen=_RECENT_MUSIC_MEMORY_MAX)

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

        is_random_val = metadata.get("music_random")
        is_random = True if is_random_val is None else bool(is_random_val)
        has_config = is_random or bool(
            metadata.get("music_keyword")
            or metadata.get("music_name")
            or metadata.get("music_category")
        )
        if not has_config:
            logger.info("选择音乐：明确配置为不随机且未提供搜索条件，跳过")
            USER_LOG.info("选择音乐 ✓ 跳过（无需选择音乐）")
            return None

        # 已选过？
        if await self._is_modify_music_visible(page):
            USER_LOG.info("选择音乐 ✓ 已有音乐（跳过）")
            return None

        await self._scroll_to_music_entry(page)

        # ── 步骤1：打开抽屉 ──────────────────────────────────────────────────
        opened = False
        for attempt in range(1, 4):
            if await self._is_drawer_open(page):
                logger.info("选择音乐：[步骤1] 音乐抽屉已处于打开状态，复用当前抽屉")
                opened = True
                break
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
            await page.wait_for_timeout(500)

        if not opened:
            USER_LOG.error("选择音乐 ✗ 无法打开音乐抽屉")
            return PublishResult(success=False, error_message="选择音乐：无法打开音乐抽屉")

        # 切换分类 Tab（可选）
        category = (metadata.get("music_category") or "推荐").strip()
        if category != "推荐":
            await self._switch_tab(page, category)
            await self._wait_music_list_loaded(page, 3_000)

        # 搜索关键字（可选）。新版图文音乐抽屉默认不展示搜索框；
        # 指定音乐此时会在当前已加载列表里匹配，找不到则明确失败。
        keyword = (metadata.get("music_keyword") or "").strip()
        if keyword:
            if not await self._fill_search(page, keyword):
                logger.info("选择音乐：当前音乐面板未显示搜索框，将在已加载列表内匹配「%s」", keyword[:20])

        # ── 步骤2：选曲 + 点「使用」+ 等抽屉关闭 ──────────────────────────────
        logger.info("选择音乐：[步骤2] 等待推荐列表加载")
        if not await self._wait_music_list_loaded(page, _LIST_LOAD_TIMEOUT):
            return PublishResult(success=False, error_message="选择音乐：推荐列表未及时加载")

        music_name = (metadata.get("music_name") or "").strip()
        responses: List[str] = []

        def _capture_music_response(response) -> None:
            try:
                url = str(response.url or "")
                lowered = url.lower()
                if any(key in lowered for key in ("music", "sound", "audio", "song")):
                    responses.append(f"{response.status} {url[:180]}")
            except Exception:
                return

        page.on("response", _capture_music_response)
        try:
            use_clicked = await self._hover_random_music_and_click_use(
                page,
                metadata,
                is_random=is_random,
                name_filter=music_name,
            )
        finally:
            try:
                page.remove_listener("response", _capture_music_response)
            except Exception:
                pass
        if not use_clicked:
            await self._close_music_drawer_if_open(page)
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

        await self._log_music_post_apply_state(page, responses)
        if not responses and await self._is_music_module_absent(page):
            logger.warning("选择音乐：点击使用后页面移除了音乐模块，且未发起音乐保存请求，按平台当前状态跳过")
            USER_LOG.info("选择音乐 ✓ 跳过（当前发布条件下页面未保留音乐模块）")
            return None
        return PublishResult(success=False, error_message="选择音乐：点击使用后未出现「修改音乐」")

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤1：打开抽屉
    # ──────────────────────────────────────────────────────────────────────────

    async def _scroll_to_music_entry(self, page: Page) -> None:
        """将扩展信息里的音乐入口滚到可点击位置。"""
        entry = await self._music_entry_from_extension_card(page)
        if entry is not None:
            try:
                await entry.scroll_into_view_if_needed()
                await page.wait_for_timeout(250)
                return
            except Exception:
                pass

        placeholder = page.get_by_text("点击添加合适作品风格音乐", exact=False).first
        try:
            if await placeholder.count() > 0:
                await placeholder.evaluate(
                    "el => el.scrollIntoView({block: 'center', inline: 'nearest'})"
                )
                await page.wait_for_timeout(300)
                return
        except Exception:
            pass

        for query in ("扩展信息", "选择音乐"):
            try:
                anchor = page.get_by_text(query, exact=False).first
                if await anchor.count() > 0:
                    await anchor.evaluate(
                        "el => el.scrollIntoView({block: 'center', inline: 'nearest'})"
                    )
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
        返回音乐抽屉根。

        2026-05 图文页新版为右侧 Semi sidesheet，推荐列表默认没有「搜索音乐」
        输入框；旧版仍可能以搜索框为锚。这里优先识别 sidesheet，再兼容旧搜索框。
        """
        for sel in Selectors.PUBLISH.get("MUSIC_PANEL_ROOT", []) or []:
            try:
                roots = page.locator(sel)
                n = await roots.count()
                for i in range(min(n, 8)):
                    root = roots.nth(i)
                    if await self._is_music_drawer_candidate(root):
                        return root
            except Exception:
                continue

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

    async def _extension_card(self, page: Page) -> Optional[Locator]:
        """返回发布页主体里的「扩展信息」卡片，后续入口定位只限制在这个卡片内。"""
        try:
            title = page.get_by_text("扩展信息", exact=True).first
            if await title.count() == 0 or not await title.is_visible():
                return None
            for depth in range(1, 8):
                card = title.locator(f"xpath=ancestor::div[{depth}]")
                if await card.count() == 0:
                    break
                try:
                    box = await card.bounding_box()
                    if not box or box["width"] < 300 or box["height"] < 120:
                        continue
                    text = await card.inner_text(timeout=1500)
                    if "添加标签" in text and "关联热点" in text:
                        return card
                except Exception:
                    continue
        except Exception:
            return None
        return None

    async def _music_entry_from_extension_card(self, page: Page) -> Optional[Locator]:
        """在扩展信息卡片中定位右侧「选择音乐」按钮/动作区。"""
        card = await self._extension_card(page)
        if card is None:
            return None
        try:
            if await card.get_by_text("修改音乐", exact=True).count() > 0:
                return None
            placeholder = card.get_by_text("点击添加合适作品风格音乐", exact=False).first
            if await placeholder.count() > 0 and await placeholder.is_visible():
                for depth in range(1, 8):
                    row = placeholder.locator(f"xpath=ancestor::div[{depth}]")
                    if await row.count() == 0:
                        break
                    try:
                        row_text = await row.inner_text(timeout=1000)
                        if "选择音乐" not in row_text:
                            continue
                        action = row.get_by_text("选择音乐", exact=True).last
                        if await action.count() > 0 and await action.is_visible():
                            return action
                    except Exception:
                        continue
            action = card.get_by_text("选择音乐", exact=True).last
            if await action.count() > 0 and await action.is_visible():
                return action
        except Exception:
            return None
        return None

    async def _is_music_drawer_candidate(self, root: Locator) -> bool:
        """候选根需可见，且内部像音乐面板：标题 + Tab 或曲目行。"""
        try:
            if await root.count() == 0 or not await root.is_visible():
                return False
            if await root.get_by_text("选择音乐", exact=True).count() == 0:
                return False
            try:
                if await root.get_by_role("tab").count() >= 2:
                    return True
            except Exception:
                pass
            dur_re = re.compile(r"\d{1,2}:\d{2}")
            use_re = re.compile(r"\d+\.?\d*\s*万人使用|\d+\s*人使用")
            rows = (
                root.locator("div")
                .filter(has_text=dur_re)
                .filter(has_text=use_re)
            )
            return await rows.count() > 0
        except Exception:
            return False

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
        right_cell = await self._music_entry_from_extension_card(page)
        if right_cell is None:
            right_cell = await self._music_entry_right_cell_from_placeholder(page)
        if right_cell is None:
            logger.warning("选择音乐：未定位到灰条右侧入口（占位文案并列列中含「选择音乐」）")
            return
        logger.info(
            "选择音乐：点击音乐灰条内含「选择音乐」的列%s",
            "（force）" if force_only else "",
        )
        try:
            await right_cell.scroll_into_view_if_needed()
            await page.wait_for_timeout(200)
        except Exception:
            pass
        await right_cell.click(force=True, timeout=8000)

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
        """音乐抽屉根可见即视为打开；搜索框只是旧 DOM 的兼容信号。"""
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
                    logger.info("选择音乐：Tab 切换到「%s」（枚举）", category)
                    return
        except Exception:
            pass
        logger.warning("选择音乐：未找到分类 Tab「%s」，保持默认", category)

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤2b：搜索
    # ──────────────────────────────────────────────────────────────────────────

    async def _fill_search(self, page: Page, keyword: str) -> bool:
        try:
            inp = page.get_by_placeholder("搜索音乐").first
            if await inp.count() > 0 and await inp.is_visible():
                await inp.click()
                await inp.fill("")
                await page.wait_for_timeout(200)
                await inp.fill(keyword)
                await inp.press("Enter")
                await self._wait_music_list_loaded(page, 3_000)
                logger.info("选择音乐：已搜索「%s」", keyword[:20])
                return True
        except Exception as e:
            logger.warning("选择音乐：搜索框填写失败 %s", e)
        return False

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
        vh = float(vp["height"]) if vp else 900.0

        root = await self._music_drawer_root(page)
        scope = root if root is not None else page

        scored: List[tuple] = []

        async def _score_candidates(candidates: Locator, limit: int = 150) -> None:
            try:
                raw_n = await candidates.count()
            except Exception:
                return
            for i in range(min(raw_n, limit)):
                el = candidates.nth(i)
                try:
                    if not await el.is_visible():
                        continue
                    bb = await el.bounding_box()
                    if not bb:
                        continue
                    h, w = bb["height"], bb["width"]
                    y = float(bb["y"])
                    # 行高 30–200px，宽度 100px 以上且非整页宽
                    if h < 30 or h > 200 or w < 100 or w > vw * 0.97:
                        continue
                    # 仅使用当前视口内的曲目卡片。Semi 抽屉里的列表可能渲染出视口外
                    # 的节点，Playwright 仍认为 attached，但点击/读文本容易长时间卡住。
                    if y < 0 or y + min(h, 30) > vh:
                        continue
                    txt = (await el.inner_text()).strip()
                    if len(txt) > 500:  # 排除包含整个列表的父节点
                        continue
                    scored.append((y, h, el))
                except Exception:
                    continue

        for sel in Selectors.PUBLISH.get("MUSIC_ROW_CARD", []) or []:
            try:
                await _score_candidates(
                    scope.locator(sel)
                    .filter(has_text=dur_re)
                    .filter(has_text=use_re),
                    limit=80,
                )
                if scored:
                    break
            except Exception:
                continue

        if not scored:
            try:
                await _score_candidates(
                    scope.locator("div")
                    .filter(has_text=dur_re)
                    .filter(has_text=use_re)
                )
            except Exception:
                return []

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
                if not is_random:
                    logger.warning("选择音乐：未找到指定曲名「%s」", name_filter)
                    return None
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

    async def _get_music_row_infos(self, page: Page) -> List[Dict[str, Any]]:
        """
        在页面上下文一次性解析当前视口内曲目卡片。

        这比把 Playwright Locator 保存下来更稳：抖音音乐抽屉是 React/Semi
        滚动列表，选择曲目后 DOM 会局部重渲染，旧 locator 很容易在后续点击
        或读 inner_text 时卡住/失效。
        """
        try:
            rows = await page.evaluate(
                r"""
                () => {
                  const visible = (el) => {
                    const r = el.getBoundingClientRect();
                    const cs = getComputedStyle(el);
                    return r.width > 0 && r.height > 0
                      && cs.visibility !== 'hidden' && cs.display !== 'none';
                  };
                  const root = document.querySelector(".semi-sidesheet-inner[role='sidesheet']")
                    || document.querySelector(".semi-sidesheet[class*='music-side-sheet']")
                    || document.querySelector(".semi-sidesheet");
                  if (!root || !visible(root)) return [];
                  const dur = /\d{1,2}:\d{2}/;
                  const use = /\d+(\.\d+)?\s*万?人使用/;
                  const cards = Array.from(root.querySelectorAll(
                    ".card-container-tmocjc, div[class*='card-container']"
                  ));
                  const seenY = [];
                  const out = [];
                  for (const el of cards) {
                    if (!visible(el)) continue;
                    const text = (el.innerText || el.textContent || "").trim();
                    if (!dur.test(text) || !use.test(text)) continue;
                    if (text.length > 500) continue;
                    const r = el.getBoundingClientRect();
                    if (r.height < 30 || r.height > 200 || r.width < 100) continue;
                    if (r.y < 0 || r.y + Math.min(r.height, 30) > window.innerHeight) continue;
                    if (seenY.some((y) => Math.abs(y - r.y) < 8)) continue;
                    seenY.push(r.y);
                    out.push({
                      index: out.length,
                      text,
                      x: Math.round(r.x),
                      y: Math.round(r.y),
                      width: Math.round(r.width),
                      height: Math.round(r.height)
                    });
                  }
                  return out;
                }
                """
            )
            return rows if isinstance(rows, list) else []
        except Exception as e:
            logger.warning("选择音乐：解析曲目 DOM 失败 %s", e)
            return []

    async def _pick_row_info(
        self,
        page: Page,
        *,
        is_random: bool,
        name_filter: str = "",
        exclude_indices: Optional[set] = None,
    ) -> Optional[Dict[str, Any]]:
        rows = await self._get_music_row_infos(page)
        if not rows:
            logger.warning("选择音乐：当前视口未解析到可点击曲目")
            return None

        exclude_indices = exclude_indices or set()
        rows = [r for r in rows if int(r.get("index", -1)) not in exclude_indices]
        if not rows:
            return None

        if name_filter:
            named = [r for r in rows if name_filter in str(r.get("text") or "")]
            if named:
                rows = named
            elif not is_random:
                logger.warning("选择音乐：未找到指定曲名「%s」", name_filter)
                return None
            else:
                logger.warning("选择音乐：未找到曲名「%s」，使用全部行", name_filter)

        if is_random:
            pool = rows[:_RANDOM_ROW_POOL_MAX]
            chosen = random.choice(pool)
            logger.info(
                "选择音乐：随机选取候选池第 %d/%d 条（当前可见列表共解析 %d 条，候选上限=%d）",
                pool.index(chosen) + 1,
                len(pool),
                len(rows),
                _RANDOM_ROW_POOL_MAX,
            )
            return chosen

        logger.info("选择音乐：选取第 1 条（当前可见列表共 %d 条）", len(rows))
        return rows[0]

    async def _hover_random_music_and_click_use(
        self,
        page: Page,
        metadata: Dict[str, Any],
        *,
        is_random: bool,
        name_filter: str = "",
    ) -> bool:
        """
        当前抖音图文音乐抽屉的可靠交互：
        推荐列表中 hover 音乐卡片 -> 卡片右侧出现红色「使用」按钮 -> 点击按钮。
        """
        tried_y: List[float] = []
        for attempt in range(1, 4):
            rows = await self._get_music_rows(page)
            if not rows:
                logger.warning("选择音乐：推荐列表中未解析到音乐卡片")
                return False

            candidates = []
            for row in rows:
                try:
                    text = await row.inner_text(timeout=1200)
                    if name_filter:
                        if name_filter not in text:
                            continue
                    box = await row.bounding_box(timeout=1200)
                    if not box:
                        continue
                    if any(abs(float(box["y"]) - y) < 8 for y in tried_y):
                        continue
                    candidates.append((row, self._music_row_key(text), text))
                except Exception:
                    continue

            if not candidates:
                if name_filter:
                    logger.warning("选择音乐：未在当前推荐列表找到指定曲目「%s」", name_filter)
                return False

            pool = candidates[:_RANDOM_ROW_POOL_MAX] if is_random else candidates[:1]
            fresh_pool = [item for item in pool if item[1] not in self._recent_music_keys]
            selectable = fresh_pool or pool
            row, music_key, _music_text = random.SystemRandom().choice(selectable) if is_random else selectable[0]
            try:
                box = await row.bounding_box(timeout=1200)
                if box:
                    tried_y.append(float(box["y"]))
            except Exception:
                pass

            logger.info(
                "选择音乐：随机选取候选池第 %d/%d 条（当前可见列表共解析 %d 条，候选上限=%d，已避开近期=%d）",
                [item[0] for item in pool].index(row) + 1,
                len(pool),
                len(rows),
                _RANDOM_ROW_POOL_MAX,
                len(self._recent_music_keys),
            )
            if await self._hover_row_and_click_use(page, row, metadata, attempt):
                if music_key:
                    self._recent_music_keys.append(music_key)
                return True
            await page.wait_for_timeout(600)
        return False

    @staticmethod
    def _music_row_key(text: str) -> str:
        """用曲名/作者生成稳定 key，用于避免连续任务重复选同一首。"""
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        useful = []
        for line in lines:
            if re.fullmatch(r"\d{1,2}:\d{2}", line):
                continue
            if re.search(r"\d+(\.\d+)?\s*万?人使用", line):
                continue
            useful.append(line)
        return " ".join(useful[:2]).strip() or re.sub(r"\s+", " ", text or "").strip()

    async def _hover_row_and_click_use(
        self, page: Page, row: Locator, metadata: Dict[str, Any], attempt: int
    ) -> bool:
        """hover 当前音乐卡片，只在该卡片/抽屉内点击精确「使用」按钮。"""
        hover_ms = max(300, min(int(metadata.get("music_use_hover_ms") or 800), 4000))
        try:
            summary = (await row.inner_text(timeout=1500)).strip().replace("\n", " ")
            if len(summary) > _ROW_SUMMARY_LOG_MAX:
                summary = summary[:_ROW_SUMMARY_LOG_MAX] + "…"
            logger.info("选择音乐：[步骤2] 第 %d 次 hover 曲目卡片：%s", attempt, summary)
        except Exception:
            logger.info("选择音乐：[步骤2] 第 %d 次 hover 曲目卡片", attempt)

        try:
            await row.scroll_into_view_if_needed(timeout=3000)
            await page.wait_for_timeout(150)
            await row.hover(timeout=5000, force=True)
            await page.wait_for_timeout(hover_ms)
        except Exception as e:
            logger.warning("选择音乐：hover 曲目卡片失败 %s", e)
            return False

        btn = await self._find_use_btn(row)
        if btn is None:
            try:
                active = await self._active_music_row(page)
                if active is not None:
                    btn = await self._find_use_btn(active)
            except Exception:
                btn = None
        if btn is None:
            drawer = await self._music_drawer_root(page)
            if drawer is not None:
                btn = await self._find_use_btn(drawer)

        if btn is None:
            logger.warning("选择音乐：hover 后未出现「使用」按钮")
            return False

        try:
            box = await btn.bounding_box(timeout=3000)
            if not box:
                logger.warning("选择音乐：「使用」按钮无可用坐标")
                return False
            x = float(box["x"]) + float(box["width"]) / 2
            y = float(box["y"]) + float(box["height"]) / 2
            await page.mouse.move(x, y)
            await page.wait_for_timeout(120)
            await page.mouse.click(x, y)
            logger.info("选择音乐：已点击「使用」（真实鼠标点击卡片右侧按钮）")
            return True
        except Exception as e:
            logger.warning("选择音乐：「使用」按钮点击失败 %s", e)
            return False

    async def _active_music_row(self, page: Page) -> Optional[Locator]:
        root = await self._music_drawer_root(page)
        scope = root if root is not None else page
        for sel in Selectors.PUBLISH.get("MUSIC_ROW_ACTIVE", []) or []:
            try:
                loc = scope.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # 步骤2e：点击行 → 等待并点击「使用」
    # ──────────────────────────────────────────────────────────────────────────

    async def _click_row_index_and_use(
        self, page: Page, row_info: Dict[str, Any], metadata: Dict[str, Any]
    ) -> bool:
        """按当前可见列表索引在 DOM 内点击曲目，再点击同一抽屉内「使用」。"""
        idx = int(row_info.get("index", -1))
        summary = str(row_info.get("text") or "").replace("\n", " ")
        if len(summary) > _ROW_SUMMARY_LOG_MAX:
            summary = summary[:_ROW_SUMMARY_LOG_MAX] + "…"
        logger.info("选择音乐：准备点击曲目行摘要：%s", summary)

        if await self._activate_row_and_click_use_js(page, row_info, _USE_BTN_TIMEOUT):
            return True

        hover_ms = max(300, min(int(metadata.get("music_use_hover_ms") or 800), 6000))
        await page.wait_for_timeout(hover_ms)
        return await self._activate_row_and_click_use_js(page, row_info, 4000)

    async def _activate_row_and_click_use_js(
        self, page: Page, row_info: Dict[str, Any], timeout_ms: int
    ) -> bool:
        """
        只在音乐 sidesheet 内激活目标曲目并点击「使用」。

        之前用页面绝对坐标点击曲目行，在抖音页面缩放/抽屉动画/列表重排时可能落到
        页面主体扩展信息区域，触发“添加标签/位置”等字段切换，导致“选择音乐”入口消失。
        这里改为在浏览器上下文中重新查找当前曲目卡片，并把 mouse/pointer/click 事件派发到
        抽屉内元素，整个过程不触碰页面主体坐标。
        """
        target_index = int(row_info.get("index", -1))
        target_text = str(row_info.get("text") or "").strip()
        deadline = max(1000, timeout_ms)
        elapsed = 0
        interval = 250

        while elapsed < deadline:
            try:
                clicked = await page.evaluate(
                    r"""
                    ({ targetIndex, targetText }) => {
                      const visible = (el) => {
                        const r = el.getBoundingClientRect();
                        const cs = getComputedStyle(el);
                        return r.width > 0 && r.height > 0
                          && cs.visibility !== 'hidden'
                          && cs.display !== 'none'
                          && cs.pointerEvents !== 'none';
                      };
                      const textOf = (el) => (el.innerText || el.textContent || "").trim();
                      const root = document.querySelector(".semi-sidesheet-inner[role='sidesheet']")
                        || document.querySelector(".semi-sidesheet[class*='music-side-sheet']")
                        || document.querySelector(".semi-sidesheet");
                      if (!root || !visible(root)) return false;

                      const dur = /\d{1,2}:\d{2}/;
                      const useCount = /\d+(\.\d+)?\s*万?人使用/;
                      const cards = Array.from(root.querySelectorAll(
                        ".card-container-tmocjc, div[class*='card-container']"
                      )).filter((el) => {
                        if (!visible(el)) return false;
                        const text = textOf(el);
                        if (!dur.test(text) || !useCount.test(text) || text.length > 500) return false;
                        const r = el.getBoundingClientRect();
                        return r.height >= 30 && r.height <= 200 && r.width >= 100
                          && r.y >= 0 && r.y + Math.min(r.height, 30) <= window.innerHeight;
                      });
                      if (!cards.length) return false;

                      let card = null;
                      if (targetText) {
                        card = cards.find((el) => textOf(el) === targetText)
                          || cards.find((el) => textOf(el).includes(targetText.slice(0, 24)));
                      }
                      if (!card && targetIndex >= 0 && targetIndex < cards.length) {
                        card = cards[targetIndex];
                      }
                      if (!card) card = cards[0];

                      card.scrollIntoView({ block: "nearest", inline: "nearest" });
                      const r = card.getBoundingClientRect();
                      const eventInit = {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: r.left + Math.min(r.width * 0.55, r.width - 8),
                        clientY: r.top + r.height / 2,
                      };
                      for (const type of ["pointerover", "pointerenter", "mouseover", "mouseenter", "mousemove"]) {
                        card.dispatchEvent(new MouseEvent(type, eventInit));
                      }
                      card.click();

                      const buttonSelectors = [
                        "button.apply-btn-LUPP0D",
                        "button[class*='apply-btn']",
                        "button"
                      ];
                      const findUseButton = (scope) => {
                        for (const selector of buttonSelectors) {
                          for (const btn of Array.from(scope.querySelectorAll(selector))) {
                            const text = textOf(btn).replace(/\s+/g, "");
                            if (text === "使用") return btn;
                          }
                        }
                        return null;
                      };

                      const btn = findUseButton(card) || findUseButton(root);
                      if (!btn) return false;
                      btn.dispatchEvent(new MouseEvent("mouseover", eventInit));
                      btn.dispatchEvent(new MouseEvent("mouseenter", eventInit));
                      btn.click();
                      return true;
                    }
                    """,
                    {"targetIndex": target_index, "targetText": target_text},
                )
                if clicked:
                    logger.info("选择音乐：已点击「使用」（音乐抽屉 DOM 内精确激活）")
                    return True
            except Exception as e:
                logger.debug("选择音乐：DOM 激活曲目/点击使用失败：%s", e)

            await page.wait_for_timeout(interval)
            elapsed += interval
            await asyncio.sleep(0)

        return False

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

        # 音乐抽屉内曲目卡片是短距离 UI 操作，直接点击更稳定；
        # 拟人轨迹在虚拟/滚动列表里可能命中旧坐标并拖慢到几十秒。
        try:
            await row.click(force=True, timeout=3000)
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

    async def _wait_and_click_use_btn_js(self, page: Page, timeout_ms: int) -> bool:
        """在音乐抽屉 DOM 内直接点击精确文本「使用」按钮。"""
        elapsed = 0
        interval = 250
        deadline = max(1000, timeout_ms)
        while elapsed < deadline:
            try:
                rect = await page.evaluate(
                    r"""
                    () => {
                      const visible = (el) => {
                        const r = el.getBoundingClientRect();
                        const cs = getComputedStyle(el);
                        return r.width > 0 && r.height > 0
                          && cs.visibility !== 'hidden' && cs.display !== 'none';
                      };
                      const root = document.querySelector(".semi-sidesheet-inner[role='sidesheet']")
                        || document.querySelector(".semi-sidesheet[class*='music-side-sheet']")
                        || document.querySelector(".semi-sidesheet");
                      if (!root || !visible(root)) return false;
                      const buttons = Array.from(root.querySelectorAll(
                        "button.apply-btn-LUPP0D, button[class*='apply-btn'], button"
                      ));
                      for (const btn of buttons) {
                        if (!visible(btn)) continue;
                        const text = (btn.innerText || btn.textContent || "").trim().replace(/\s+/g, "");
                        if (text === "使用") {
                          const r = btn.getBoundingClientRect();
                          return {
                            x: Math.round(r.x),
                            y: Math.round(r.y),
                            width: Math.round(r.width),
                            height: Math.round(r.height)
                          };
                        }
                      }
                      return null;
                    }
                    """
                )
                if rect:
                    x = float(rect["x"]) + float(rect["width"]) / 2
                    y = float(rect["y"]) + float(rect["height"]) / 2
                    await page.mouse.move(x, y)
                    await page.wait_for_timeout(80)
                    await page.mouse.click(x, y)
                    logger.info("选择音乐：已点击「使用」（音乐抽屉 DOM）")
                    return True
            except Exception:
                pass
            await page.wait_for_timeout(interval)
            elapsed += interval
            await asyncio.sleep(0)
        return False

    async def _find_use_btn(self, scope) -> Optional[Locator]:
        """仅返回可点击且文本精确为「使用」的按钮，避免命中「万人使用」。"""
        selectors = Selectors.PUBLISH.get("MUSIC_USE_BTN") or ["button:has-text('使用')"]
        for sel in selectors:
            try:
                btns = scope.locator(sel) if hasattr(scope, "locator") else None
                if btns is None:
                    continue
                n = await btns.count()
                for i in range(min(n, 20)):
                    b = btns.nth(i)
                    if not await b.is_visible():
                        continue
                    txt = (await b.inner_text()).strip().replace("\n", "")
                    if txt == "使用":
                        return b
            except Exception:
                continue
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

    async def _close_music_drawer_if_open(self, page: Page) -> None:
        """失败退出前关闭音乐抽屉，避免 step_runner 重试时被打开的 sidesheet 遮挡入口。"""
        try:
            if not await self._is_drawer_open(page):
                return
            closed = await page.evaluate(
                r"""
                () => {
                  const root = document.querySelector(".semi-sidesheet-inner[role='sidesheet']")
                    || document.querySelector(".semi-sidesheet[class*='music-side-sheet']")
                    || document.querySelector(".semi-sidesheet");
                  if (!root) return true;
                  const buttons = Array.from(root.querySelectorAll("button, [role='button']"));
                  const closeBtn = buttons.find((btn) => {
                    const label = [
                      btn.getAttribute("aria-label"),
                      btn.getAttribute("title"),
                      btn.innerText,
                      btn.textContent,
                    ].filter(Boolean).join(" ");
                    return /关闭|取消|close/i.test(label);
                  }) || root.querySelector(".semi-sidesheet-close, [class*='close']");
                  if (!closeBtn) return false;
                  closeBtn.click();
                  return true;
                }
                """
            )
            if not closed:
                await page.keyboard.press("Escape")
            await self._wait_drawer_closed(page, 3000)
        except Exception:
            pass

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
        try:
            has_text = await page.evaluate("() => (document.body?.innerText || '').includes('修改音乐')")
            if has_text:
                return True
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

    async def _log_music_post_apply_state(self, page: Page, responses: List[str]) -> None:
        """记录点击「使用」后页面真实状态，帮助区分 UI 改版和平台未落库。"""
        try:
            card = await self._extension_card(page)
            card_text = ""
            if card is not None:
                card_text = re.sub(r"\s+", " ", (await card.inner_text(timeout=1500)).strip())
            logger.warning("选择音乐：点击使用后未见「修改音乐」，扩展卡片文本=%s", card_text[:240] or "<empty>")
        except Exception as e:
            logger.warning("选择音乐：读取点击使用后的扩展卡片状态失败 %s", e)
        try:
            toast_texts = await page.locator(
                ".semi-toast, .semi-toast-content, [class*='toast'], [class*='message']"
            ).all_inner_texts()
            toast_texts = [re.sub(r"\s+", " ", t).strip() for t in toast_texts if t.strip()]
            if toast_texts:
                logger.warning("选择音乐：点击使用后页面提示=%s", toast_texts[:5])
        except Exception:
            pass
        if responses:
            logger.warning("选择音乐：点击使用阶段捕获到疑似音乐接口响应=%s", responses[-8:])
        else:
            logger.warning("选择音乐：点击使用阶段未捕获到含 music/sound/audio/song 的接口响应")

    async def _is_music_module_absent(self, page: Page) -> bool:
        """扩展信息卡片内既无「选择音乐」也无「修改音乐」，视为音乐模块已被页面移除。"""
        try:
            card = await self._extension_card(page)
            if card is None:
                return False
            text = re.sub(r"\s+", " ", (await card.inner_text(timeout=1500)).strip())
            return "选择音乐" not in text and "修改音乐" not in text
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # 旧接口兼容（其它模块可能调用）
    # ──────────────────────────────────────────────────────────────────────────

    async def _already_has_music(self, page: Page) -> bool:
        return await self._is_modify_music_visible(page)

    async def _wait_modify_music_visible(self, page: Page, timeout_ms: int) -> bool:
        return await self._wait_modify_music(page, timeout_ms)
