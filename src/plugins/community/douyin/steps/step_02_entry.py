# -*- coding: utf-8 -*-
"""
步骤2：进入发布页
文件路径: src/plugins/community/douyin/steps/step_02_entry.py

流程：
  1. 根据 file_type 判断进入"发布视频"或"发布图文"
  2. 查找首页左侧卡片入口（见 Selectors.HOME），拟人点击，等待进入 /content/post/ 路由
  3. 综合判断跳转成功：轮询 VIDEO_PUBLISH_PAGE_MARKERS / IMAGE_PUBLISH_PAGE_MARKERS 全部候选；
     标题/按钮等用 is_visible()；file input 常以隐藏控件存在，仅要求 DOM 上可 locate

字段依赖：
  - metadata['file_type']: "video" 或 "image"
  - metadata['speed_rate']: 等待延迟倍率
  - metadata['anti_risk_config']: 风控相关配置
"""
import logging
import time
from typing import Any, Dict, Tuple

from src.infrastructure.browser.automation_api import Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


def _selector_targets_file_input(sel: str) -> bool:
    """拖拽区里的 file input 常被 opacity/clip 隐藏，is_visible() 易误判，需单独判定。"""
    s = (sel or "").lower().replace('"', "'")
    return "input[type='file']" in s or "[type=file]" in s


def _url_matches_publish_route(url: str, file_type: str) -> bool:
    u = (url or "").lower()
    if file_type == "video":
        return any(s in u for s in ("/post/video", "/content/post/video", "/content/post/article", "/content/upload"))
    return any(s in u for s in ("/post/image", "/content/post/image", "/content/post/article", "/content/upload"))


def _is_video_publish_url(url: str) -> bool:
    u = (url or "").lower()
    return any(s in u for s in ("/post/video", "/content/post/video", "/content/upload"))


def _is_image_publish_url(url: str) -> bool:
    u = (url or "").lower()
    return any(s in u for s in ("/post/image", "/content/post/image", "/content/upload"))


class EnterPublishEntryStep(BasePublishStep):
    """从首页点击"发布视频/发布图文"入口，进入对应发布页。"""

    async def _wait_publish_route(
        self,
        page: Page,
        file_type: str,
        url_before: str,
        timeout_ms: int,
    ) -> Tuple[bool, str]:
        """等待 URL 进入发布域且与 file_type 一致。"""

        def predicate(u: object) -> bool:
            s = str(u) if u is not None else ""
            if not s or s == url_before:
                return False
            return _url_matches_publish_route(s, file_type)

        try:
            await page.wait_for_url(predicate, timeout=timeout_ms)
            return True, page.url or ""
        except Exception:
            return _url_matches_publish_route(page.url or "", file_type), page.url or ""

    async def _switch_publish_tab_if_needed(
        self,
        page: Page,
        file_type: str,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
        speed_rate: float,
    ) -> bool:
        """已在发布域但类型不符时，点击 Tab「视频」/「图文」。"""
        u = page.url or ""
        if file_type == "video" and _is_image_publish_url(u):
            tabs = Selectors.PUBLISH.get("TAB_VIDEO") or []
            label = "视频"
        elif file_type == "image" and _is_video_publish_url(u):
            tabs = Selectors.PUBLISH.get("TAB_IMAGE") or []
            label = "图文"
        else:
            return True

        from src.infrastructure.anti_risk.human_like import human_click

        timeout_ms = int(12000 * speed_rate)
        for sel in tabs:
            try:
                t = page.locator(sel).first
                if await t.count() == 0:
                    continue
                await t.scroll_into_view_if_needed(timeout=5000)
                if not await t.is_visible():
                    continue
                url_before = page.url or ""
                try:
                    await human_click(page, t, metadata, config)
                except Exception:
                    await t.click()
                try:
                    await page.wait_for_url(
                        lambda url: str(url) != url_before
                        and _url_matches_publish_route(str(url), file_type),
                        timeout=timeout_ms,
                    )
                except Exception:
                    await page.wait_for_timeout(int(600 * speed_rate))
                if file_type == "video" and _is_video_publish_url(page.url or ""):
                    logger.info("已切换到发布页「视频」Tab（候选=%s）", sel)
                    USER_LOG.info("[步骤2/9 进入发布页] ▶ 已切换到「视频」发布")
                    return True
                if file_type == "image" and _is_image_publish_url(page.url or ""):
                    logger.info("已切换到发布页「图文」Tab（候选=%s）", sel)
                    USER_LOG.info("[步骤2/9 进入发布页] ▶ 已切换到「图文」发布")
                    return True
            except Exception:
                continue
        logger.warning("发布页类型与任务不符（需%s），且 Tab 切换未成功 | url=%s", label, page.url)
        return False

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        file_type = (metadata.get("file_type") or "video").lower()
        logger.info(f"===== 进入发布入口: file_type={file_type} =====")

        if file_type not in ("video", "image"):
            logger.warning(f"未知 file_type={file_type}，按视频处理")
            file_type = "video"

        config = metadata.get("anti_risk_config") or {}
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_route_ms = int(12000 * speed_rate)

        # 已在目标发布页则跳过点击（重试步骤时减少无效操作）
        cur = page.url or ""
        if file_type == "video" and _is_video_publish_url(cur):
            logger.info("当前已在视频发布页 URL，跳过入口点击 | url=%s", cur)
        elif file_type == "image" and _is_image_publish_url(cur):
            logger.info("当前已在图文发布页 URL，跳过入口点击 | url=%s", cur)
        else:
            if file_type == "video":
                selectors = Selectors.HOME["PUBLISH_VIDEO_BTN"]
                action_text = "发布视频"
            else:
                selectors = Selectors.HOME["PUBLISH_IMAGE_BTN"]
                action_text = "发布图文"

            entered = False
            url_before_click = page.url or ""

            for sel in selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() == 0:
                        continue
                    await btn.scroll_into_view_if_needed(timeout=5000)
                    if not await btn.is_visible():
                        continue
                    from src.infrastructure.anti_risk.human_like import human_click

                    try:
                        await human_click(page, btn, metadata, config)
                    except Exception:
                        await btn.click()

                    ok_route, url_after_click = await self._wait_publish_route(
                        page, file_type, url_before_click, wait_route_ms
                    )
                    if not ok_route:
                        url_after_click = page.url or ""
                        ok_route = _url_matches_publish_route(url_after_click, file_type)

                    if ok_route:
                        entered = True
                        logger.info(
                            "已点击发布入口并进入发布路由: %s | %s -> %s",
                            sel,
                            url_before_click,
                            url_after_click,
                        )
                        USER_LOG.info(f"[步骤2/9 进入发布页] ▶ 点击「{action_text}」（已进入发布路由）")
                        break

                    if url_after_click and url_after_click != url_before_click:
                        logger.warning(
                            "点击发布入口后进入非预期页面：候选=%s | url=%s（将继续尝试下一候选）",
                            sel,
                            url_after_click,
                        )
                    else:
                        logger.warning(
                            "点击发布入口但 URL 未变化：候选=%s | url=%s",
                            sel,
                            url_before_click,
                        )
                except Exception:
                    continue

            if not entered:
                # 兜底：尝试「高清发布」统一入口（抖音新版首页将视频/图文合并为一个入口，进入后再切 Tab）
                logger.info("普通发布入口未找到，尝试「高清发布」统一入口…")
                hd_selectors = Selectors.HOME.get("PUBLISH_HD_ENTRY_BTN") or []
                url_before_hd = page.url or ""
                for hd_sel in hd_selectors:
                    try:
                        hd_btn = page.locator(hd_sel).first
                        if await hd_btn.count() == 0:
                            continue
                        await hd_btn.scroll_into_view_if_needed(timeout=5000)
                        if not await hd_btn.is_visible():
                            continue
                        from src.infrastructure.anti_risk.human_like import human_click
                        try:
                            await human_click(page, hd_btn, metadata, config)
                        except Exception:
                            await hd_btn.click()
                        # 高清发布进入后需等待页面跳转（进入任意发布域即可，后续 Tab 切换）
                        await self._wait_publish_route(
                            page, file_type, url_before_hd, wait_route_ms
                        )
                        cur_after_hd = page.url or ""
                        if cur_after_hd and cur_after_hd != url_before_hd:
                            logger.info("已通过「高清发布」入口进入: %s", cur_after_hd)
                            # 若类型不匹配，尝试 Tab 切换
                            if not _url_matches_publish_route(cur_after_hd, file_type):
                                await self._switch_publish_tab_if_needed(
                                    page, file_type, metadata, config, speed_rate
                                )
                            entered = True
                            USER_LOG.info("[步骤2/9 进入发布页] ▶ 通过「高清发布」入口进入（已切换 Tab）")
                            break
                    except Exception:
                        continue

            if not entered:
                return PublishResult(
                    success=False,
                    error_message=f"未找到发布入口按钮（file_type={file_type}），请检查首页布局或选择器配置",
                )

        # 等待跳转到对应发布页，记录当前 URL
        wait_ms = int(2000 * speed_rate)
        try:
            try:
                from src.infrastructure.anti_risk.delays import random_delay
                await random_delay(page, wait_ms, metadata, config)
            except Exception:
                await page.wait_for_timeout(wait_ms)
            current_url = page.url
            logger.info(f"点击发布入口后 URL: {current_url}")
            USER_LOG.info(f"[步骤2/9 进入发布页] ▶ 进入 {current_url}")
        except Exception:
            current_url = ""

        # 依次尝试 VIDEO/IMAGE_PUBLISH_PAGE_MARKERS 中全部候选（DOM 改版时 placeholder、accept 可能变）
        markers = (
            Selectors.HOME.get("VIDEO_PUBLISH_PAGE_MARKERS", [])
            if file_type == "video"
            else Selectors.HOME.get("IMAGE_PUBLISH_PAGE_MARKERS", [])
        )
        markers = [m for m in markers if isinstance(m, str) and m.strip()]
        if not markers:
            return PublishResult(
                success=False,
                error_message=f"发布页特征元素选择器未配置（file_type={file_type}），请检查 selectors.py",
            )

        ok = False
        start_ts = time.time()
        timeout_s = 12.0 * speed_rate
        while (time.time() - start_ts) < timeout_s:
            try:
                for marker in markers:
                    try:
                        loc = page.locator(marker).first
                        if await loc.count() == 0:
                            continue
                        if _selector_targets_file_input(marker):
                            ok = True
                            logger.info("已检测到发布页特征元素（file input 已挂载 DOM）: %s", marker)
                            break
                        if await loc.is_visible():
                            ok = True
                            logger.info("已检测到发布页特征元素（is_visible）: %s", marker)
                            break
                    except Exception:
                        continue
                if ok:
                    break
            except Exception:
                pass
            await page.wait_for_timeout(500)
            # 每轮让出控制权，防止长等待期间 Qt UI 无响应
            import asyncio as _asyncio
            await _asyncio.sleep(0)

        if not ok:
            return PublishResult(
                success=False,
                error_message=(
                    f"未能确认进入发布页：以下特征均未就绪（url={page.url}）；"
                    f"候选数={len(markers)}，示例={markers[0]!r}"
                ),
            )

        return None
