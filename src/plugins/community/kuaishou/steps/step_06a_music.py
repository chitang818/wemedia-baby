# -*- coding: utf-8 -*-
"""
步骤6a：图文发布 - 添加音乐
文件路径: src/plugins/community/kuaishou/steps/step_06a_music.py

依据：docs/03插件系统/OpenClaw 报告分析报告/快手_图文发布添加音乐功能 DOM 分析报告_20260403.md

触发条件：
  - metadata["music_random"] = True   → 从推荐列表随机选一首
  - metadata["music_keyword"] 有值    → 搜索后随机选一首
  - 两者均未配置                      → 跳过

DOM 报告关键 API（20260403）：
  - 添加音乐按钮：文案「添加音乐」，ref=e1236，cursor=pointer
  - 抽屉标题：「选择音乐」，ref=e285
  - 搜索框：placeholder=「搜索音乐」，ref=e1240
  - 音乐列表容器：class 含 music-list，ref=e1243
  - 音乐项：class 含 music-item，默认隐藏「添加」按钮，hover 后出现在右侧
  - 添加按钮：文案「添加」，ref=e1678，悬停后出现
  - 成功标志：「更换音乐」按钮出现，ref=e1690

报告推荐 Playwright API：
  # 悬停到目标曲目
  await page.get_by_text('春风何时来').first().hover()
  # 点击该行内的「添加」
  await page.get_by_text('春风何时来').locator('..').get_by_text('添加').click()
  # 验证
  await expect(page.get_by_role('button', name='更换音乐')).to_be_visible()
"""
import logging
import random
import re
from typing import Any, Dict, List, Optional, Union

from playwright.async_api import Locator, Page, TimeoutError as PlaywrightTimeoutError

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

# 超时常量（毫秒）
_BTN_TIMEOUT    = 8_000   # 「添加音乐」按钮
_DRAWER_TIMEOUT = 8_000   # 抽屉出现
_SEARCH_SETTLE  = 2_500   # 搜索稳定
_HOVER_WAIT     = 800     # hover 后等动画
_ADD_BTN_TIMEOUT = 5_000  # 「添加」按钮出现
_VERIFY_TIMEOUT  = 8_000  # 验证成功

# 曲目行文案必含时长（mm:ss）
_DURATION_RE = re.compile(r"\d{1,2}:\d{2}")

# 抽屉容器候选选择器（快速定位，1 秒超时，失败则退回整页）
_DRAWER_SCOPE_SELS = [
    "[class*='_music-drawer_']",
    "[class*='music-drawer']",
    ".ant-drawer-body",
]

# 音乐列表项选择器（DOM 报告：class 含 music-item）
_MUSIC_ITEM_SELS = [
    "[class*='music-item']",
    "[class*='_music-item_']",
    "[class*='musicItem']",
    "[class*='music-list'] > div",
    "[class*='_music-list_'] > div",
]


class MusicSettingStep(BasePublishStep):
    """快手图文发布：添加背景音乐（随机或关键词搜索）。"""

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)

        self._log_prefix = self._step_prefix(metadata, "添加音乐")
        is_random = bool(metadata.get("music_random"))
        keyword = (metadata.get("music_keyword") or "").strip()

        if not is_random and not keyword:
            USER_LOG.info("%s ✓ 未配置音乐，跳过", self._log_prefix)
            return None

        mode = "随机音乐" if is_random else f"搜索「{keyword}」"
        USER_LOG.info("%s ▶ 开始添加音乐（%s）", self._log_prefix, mode)
        try:
            return await self._run(page, keyword)
        except Exception as exc:
            logger.error("步骤6a 音乐异常: %s", exc, exc_info=True)
            USER_LOG.error("%s ✗ 异常: %s", self._log_prefix, str(exc)[:120])
            return PublishResult(
                success=False,
                error_message=f"音乐添加异常: {str(exc)[:120]}",
                failed_step="步骤6a/添加音乐",
            )

    # ──────────────────────────────────────────────
    # 主流程
    # ──────────────────────────────────────────────

    async def _run(self, page: Page, keyword: str) -> StepOutcome:
        # 1. 如果已有音乐直接跳过
        if await self._already_added(page):
            USER_LOG.info("%s ✓ 音乐已存在，跳过", self._log_prefix)
            return None

        # 2. 点击「添加音乐」按钮，打开侧边抽屉
        btn = await self._find_add_btn(page)
        if btn is None:
            return PublishResult(
                success=False,
                error_message="未找到「添加音乐」按钮，请确认当前为图文发布页",
                failed_step="步骤6a/添加音乐",
            )
        await btn.scroll_into_view_if_needed()
        await btn.click()
        logger.debug("步骤6a: 已点击「添加音乐」")

        # 3. 等待抽屉打开（以「选择音乐」文字出现为准）
        try:
            await page.get_by_text("选择音乐").first.wait_for(
                state="visible", timeout=_DRAWER_TIMEOUT
            )
            logger.debug("步骤6a: 抽屉已打开")
        except PlaywrightTimeoutError:
            return PublishResult(
                success=False,
                error_message="点击「添加音乐」后抽屉未出现（未检测到「选择音乐」标题）",
                failed_step="步骤6a/添加音乐",
            )

        # 4. 获取抽屉作用域
        scope = await self._get_drawer_scope(page)

        # 5. 有关键词则搜索
        if keyword:
            err = await self._search_music(scope, page, keyword)
            if err:
                return err

        # 6. 收集列表曲目行，随机取一行
        row = await self._pick_random_row(scope, page)
        if row is None:
            hint = f"（关键词：{keyword}）" if keyword else ""
            return PublishResult(
                success=False,
                error_message=f"音乐列表中未找到可点击的曲目行{hint}，请检查网络或页面",
                failed_step="步骤6a/添加音乐",
            )

        # 7. hover → 点击「添加」
        err = await self._hover_and_add(page, scope, row)
        if err:
            return err

        # 8. 抽屉不会自动关闭，按 Escape 收起
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

        # 9. 验证
        return await self._verify(page, keyword)

    # ──────────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────────

    async def _already_added(self, page: Page) -> bool:
        loc = page.get_by_text("更换音乐").first
        try:
            return await loc.is_visible()
        except Exception:
            return False

    async def _find_add_btn(self, page: Page) -> Optional[Locator]:
        """查找「添加音乐」按钮，按 DOM 报告优先用文案定位。"""
        candidates: List[Locator] = [
            # 报告：ref=e1236，cursor=pointer，文案「添加音乐」
            page.get_by_text("添加音乐", exact=True).last,
            page.get_by_role("button", name="添加音乐"),
            page.locator("[class*='_button_']:has-text('添加音乐')").last,
            page.locator("div[class*='music']:has-text('添加音乐')").last,
        ]
        for loc in candidates:
            try:
                await loc.wait_for(state="visible", timeout=_BTN_TIMEOUT)
                if await loc.is_visible():
                    return loc
            except PlaywrightTimeoutError:
                continue
        return None

    async def _get_drawer_scope(self, page: Page) -> Union[Locator, Page]:
        """
        定位抽屉内容区，后续列表查询限定在此范围。
        快速逐一尝试候选选择器（各等 1 秒），失败则退回整页。
        """
        for sel in _DRAWER_SCOPE_SELS:
            try:
                loc = page.locator(sel).last
                await loc.wait_for(state="visible", timeout=1_000)
                logger.debug("步骤6a: 抽屉作用域=%s", sel)
                return loc
            except Exception:
                continue

        # 含「搜索音乐」输入框的 div 块
        try:
            search_box = page.get_by_placeholder("搜索音乐").first
            scope = (
                page.locator("div")
                .filter(has_text="选择音乐")
                .filter(has=search_box)
                .last
            )
            await scope.wait_for(state="visible", timeout=1_500)
            logger.debug("步骤6a: 抽屉作用域=含搜索框的div")
            return scope
        except Exception:
            pass

        logger.debug("步骤6a: 未能定位抽屉容器，退回整页")
        return page

    async def _search_music(
        self, scope: Union[Locator, Page], page: Page, keyword: str
    ) -> StepOutcome:
        """在抽屉搜索框输入关键词。"""
        search_box = scope.get_by_placeholder("搜索音乐")
        try:
            await search_box.wait_for(state="visible", timeout=_DRAWER_TIMEOUT)
            await search_box.click()
            await search_box.fill(keyword)
            logger.debug("步骤6a: 已输入搜索词: %s", keyword)
            await page.wait_for_timeout(_SEARCH_SETTLE)
        except PlaywrightTimeoutError:
            return PublishResult(
                success=False,
                error_message="未找到抽屉内搜索框（placeholder=搜索音乐）",
                failed_step="步骤6a/添加音乐",
            )
        return None

    async def _collect_rows(self, scope: Union[Locator, Page]) -> List[Locator]:
        """
        收集抽屉内所有可见曲目行。

        策略按优先级：
          1. class 含 music-item（DOM 报告命名）
          2. 含封面 img 且文案带 mm:ss 的 div（快手通用行结构）
          3. 时长节点上溯 2 层（兜底）
        """
        seen: set[str] = set()
        rows: List[Locator] = []

        async def accept(item: Locator) -> bool:
            """可见 + 文案含时长 + 长度适中（排除大容器和纯时间戳）"""
            try:
                if not await item.is_visible():
                    return False
                text = (await item.inner_text(timeout=1_200) or "").strip()
                if not _DURATION_RE.search(text):
                    return False
                if len(text) < 4 or len(text) > 200:
                    return False
                if text in seen:
                    return False
                seen.add(text)
                return True
            except Exception:
                return False

        # 策略1：class 关键词
        for sel in _MUSIC_ITEM_SELS:
            try:
                items = scope.locator(sel)
                n = await items.count()
                if n == 0:
                    continue
                for i in range(min(n, 40)):
                    item = items.nth(i)
                    if await accept(item):
                        rows.append(item)
                if rows:
                    logger.debug("步骤6a: 策略1 命中 sel=%s，共 %d 行", sel, len(rows))
                    return rows
            except Exception:
                continue

        # 策略2：含 img 的 div（曲目行必有封面图）
        try:
            items = scope.locator("div:has(img)")
            n = await items.count()
            for i in range(min(n, 40)):
                item = items.nth(i)
                if await accept(item):
                    rows.append(item)
            if rows:
                logger.debug("步骤6a: 策略2 img行 命中，共 %d 行", len(rows))
                return rows
        except Exception as exc:
            logger.debug("步骤6a: 策略2 失败: %s", exc)

        # 策略3：找时长节点（≤5 字符含冒号），上溯 2 层
        try:
            xpath = (
                "xpath=.//(span|div)"
                "[string-length(normalize-space(.)) <= 5"
                " and contains(normalize-space(.), ':')]"
            )
            time_nodes = scope.locator(xpath)
            n = await time_nodes.count()
            for i in range(min(n, 40)):
                parent2 = time_nodes.nth(i).locator("xpath=../..").first
                if await accept(parent2):
                    rows.append(parent2)
            if rows:
                logger.debug("步骤6a: 策略3 时长上溯 命中，共 %d 行", len(rows))
        except Exception as exc:
            logger.debug("步骤6a: 策略3 失败: %s", exc)

        return rows

    async def _pick_random_row(
        self, scope: Union[Locator, Page], page: Page
    ) -> Optional[Locator]:
        """等待列表加载后随机取一行曲目。"""
        for attempt in range(4):
            rows = await self._collect_rows(scope)
            logger.debug("步骤6a: 第 %d 轮扫描，找到 %d 条曲目", attempt + 1, len(rows))
            if rows:
                choice = random.choice(rows)
                try:
                    await choice.scroll_into_view_if_needed()
                except Exception:
                    pass
                return choice
            await page.wait_for_timeout(1_500)
        return None

    async def _hover_and_add(
        self,
        page: Page,
        scope: Union[Locator, Page],
        row: Locator,
    ) -> StepOutcome:
        """
        hover 曲目行 → 等待「添加」出现 → 点击。

        DOM 报告：
          await page.get_by_text('春风何时来').locator('..').get_by_text('添加').click()
        本实现泛化为：row 就是已确定的行容器，hover 后在 row 或其父级中找「添加」。
        """
        # hover 曲目行
        try:
            await row.hover(force=True, timeout=5_000)
        except Exception as exc:
            logger.warning("步骤6a: hover 失败，尝试 click: %s", exc)
            try:
                await row.click(force=True, timeout=3_000)
            except Exception:
                pass

        logger.debug("步骤6a: 已 hover 曲目行，等待「添加」出现")
        await page.wait_for_timeout(_HOVER_WAIT)

        # 精确匹配「添加」（排除「添加音乐」）
        add_re = re.compile(r"^添加$")

        # 优先在行容器及其父级中找
        for container in (row, row.locator("..")):
            for locator in (
                container.get_by_text("添加", exact=True),
                container.get_by_text(add_re),
            ):
                try:
                    await locator.first.wait_for(state="visible", timeout=_ADD_BTN_TIMEOUT)
                    await locator.first.click()
                    logger.debug("步骤6a: 已点击行内「添加」")
                    return None
                except PlaywrightTimeoutError:
                    continue

        # 兜底：抽屉内最后一个可见的「添加」（hover 产生的按钮通常在 DOM 末尾）
        try:
            all_add = scope.get_by_text(add_re)
            n = await all_add.count()
            for i in range(n - 1, -1, -1):
                cand = all_add.nth(i)
                if await cand.is_visible():
                    await cand.click()
                    logger.debug("步骤6a: 兜底点击抽屉内第 %d 个「添加」", i)
                    return None
        except Exception as exc:
            logger.debug("步骤6a: 兜底「添加」查找失败: %s", exc)

        return PublishResult(
            success=False,
            error_message="hover 曲目行后「添加」按钮未出现，请确认页面与 DOM 报告一致",
            failed_step="步骤6a/添加音乐",
        )

    async def _verify(self, page: Page, keyword: str) -> StepOutcome:
        """验证音乐添加成功：「更换音乐」出现 或 music-info 区域存在。"""
        label = keyword or "随机音乐"

        # 主验证
        try:
            await page.get_by_text("更换音乐").first.wait_for(
                state="visible", timeout=_VERIFY_TIMEOUT
            )
            logger.info("步骤6a: 验证成功——「更换音乐」已出现")
            USER_LOG.info("%s ✓ 音乐添加成功：%s", self._log_prefix, label)
            return None
        except PlaywrightTimeoutError:
            pass

        # 备用验证
        music_info = page.locator("[class*='music-info']")
        try:
            if await music_info.count() > 0 and await music_info.first.is_visible():
                logger.info("步骤6a: 备用验证成功——music-info 区域存在")
                USER_LOG.info("%s ✓ 音乐添加成功（备用验证）：%s", self._log_prefix, label)
                return None
        except Exception:
            pass

        hint = f"（关键词：{keyword}）" if keyword else ""
        return PublishResult(
            success=False,
            error_message=f"点击「添加」后未检测到「更换音乐」{hint}，音乐可能未成功添加",
            failed_step="步骤6a/添加音乐",
        )
