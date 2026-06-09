# -*- coding: utf-8 -*-
"""
步骤9：点击发布
文件路径: src/plugins/community/douyin/steps/step_09_submit.py

流程：
  1. 定位发布按钮：优先 OpenClaw L1「role=button name=发布」，再按 SUBMIT_BTN 候选；每次轮询重新解析避免 Semi 刷新后节点失效
  2. 就绪判定：is_enabled + disabled 属性 + aria-disabled（避免仅看 disabled 属性时 Semi 仍不可点）
  3. 等待解除不可用（转码等），最长约 3 分钟
  4. 点击：human_click → 普通 click → force → 视口中心 mouse.click
  5. 首次点击后拉长探测窗口（随 speed_rate），仍无 Toast/跳转则再点一次
  6. 拦截弹窗与验证：URL 含 content/manage、作品数据/作品管理、发布成功 Toast（含 STEP_EXTRAS 备选）

字段依赖：
  - metadata['speed_rate']: 影响等待重试与延时
  - metadata['anti_risk_config']: 风控冷却重试等配置
"""
import logging
import time
from typing import Any, Dict, Optional, Tuple

from src.infrastructure.browser.automation_api import Page, Locator

from src.plugins.core.wait_helper import PluginWaitHelper
from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, NeedsAction, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


def _is_publish_edit_url(url: str) -> bool:
    """判断当前是否仍在发布编辑页（视频/图文上传/发布表单页）。
    注意：不能包含 enter_from=publish 参数判断，因为发布成功后跳转到
    /content/manage?enter_from=publish 时该参数也会出现。
    """
    u = (url or "").lower()
    # /content/manage 优先排除：即使带 enter_from=publish 也是管理页而非编辑页
    if "content/manage" in u:
        return False
    return any(k in u for k in ("/post/video", "/post/image", "/publish/video", "/upload"))


def _is_manage_url(url: str) -> bool:
    """发布后跳转的作品管理页判定：URL 必须含 /content/manage 且不在发布编辑页。
    注意：不能只看 /manage，因为左侧导航项文案也含"作品管理"，
    必须结合 URL 路径排除发布编辑页的误判。
    特殊说明：发布成功后抖音会跳转到 /content/manage?enter_from=publish，
    这里的 enter_from=publish 只是来源参数，并非发布编辑页，需优先匹配 /content/manage。
    """
    u = (url or "").lower()
    if "creator.douyin.com" not in u:
        return False
    # /content/manage 路径明确代表作品管理页，即使带 enter_from=publish 参数也认为是管理页
    if "content/manage" in u:
        return True
    if _is_publish_edit_url(u):
        return False
    return "/manage" in u


async def _submit_control_ready(loc: Locator) -> bool:
    """Semi 主按钮可能仅用 aria-disabled 或 class，不全写原生 disabled。"""
    try:
        if not await loc.is_visible():
            return False
        if not await loc.is_enabled():
            return False
        dis = await loc.get_attribute("disabled")
        if dis is not None and str(dis).lower() not in ("", "false"):
            return False
        aria = (await loc.get_attribute("aria-disabled") or "").lower()
        if aria == "true":
            return False
        cls = (await loc.get_attribute("class") or "").lower()
        if "semi-button-disabled" in cls:
            return False
        return True
    except Exception:
        return False


async def _is_btn_actionable(loc: Locator) -> bool:
    """判断按钮是否真正可操作（可见、未禁用、且未被遮盖）。
    用 Playwright 内置的 actionability 检查（超时极短），遮盖/禁用时返回 False。
    """
    try:
        # check_actionability 会检查 visible + enabled + not obscured
        await loc.wait_for(state="visible", timeout=300)
        # 尝试用 Playwright 原生 actionable 检测：hover 会触发遮盖检查
        box = await loc.bounding_box()
        if not box or box["width"] < 1 or box["height"] < 1:
            return False
        if not await loc.is_enabled():
            return False
        # 检查是否被其他元素遮盖：用 JS 查询该坐标最顶层的元素
        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2
        top_el = await loc.page.evaluate(
            "(args) => { const el = document.elementFromPoint(args.x, args.y); return el ? el.outerHTML.slice(0, 200) : null; }",
            {"x": cx, "y": cy},
        )
        if top_el is None:
            return False
        # 只要最顶层元素包含「发布」文字，或是按钮本身的子元素，就认为可操作
        if "发布" in (top_el or ""):
            return True
        # 如果最顶层是完全无关的元素（如遮罩），认为被遮盖
        btn_html = await loc.evaluate("el => el.outerHTML.slice(0, 300)")
        # 顶层元素在按钮内部（子元素）→ 可操作
        if top_el and len(top_el) < len(btn_html) and any(kw in top_el for kw in ("button", "span", "发布")):
            return True
        # fallback：顶层就是按钮本身
        return top_el == btn_html
    except Exception:
        # 检测失败时保守返回 True，让后续点击逻辑自行处理
        return True


async def _resolve_submit_button(page: Page) -> Tuple[Optional[Locator], str]:
    """找到真正可操作的发布按钮。
    当页面存在多个「发布」按钮（如 SPA 残留旧 DOM）时，优先选取通过遮盖检测的那个。
    策略：遍历所有候选，用 _is_btn_actionable 过滤，取第一个真正可操作的。
    """
    candidates: list[Tuple[Locator, str]] = []

    # L1：get_by_role 语义查找，收集所有可见候选
    try:
        by_role = page.get_by_role("button", name="发布", exact=True)
        cnt = await by_role.count()
        for i in range(cnt):
            loc = by_role.nth(i)
            try:
                if await loc.is_visible():
                    candidates.append((loc, f"get_by_role(button, name=发布)[{i}]"))
            except Exception:
                continue
    except Exception:
        pass

    # L2：备用 CSS 选择器
    if not candidates:
        for sel in Selectors.PUBLISH.get("SUBMIT_BTN", []) or []:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                if await loc.is_visible():
                    candidates.append((loc, sel))
                    break
            except Exception:
                continue

    if not candidates:
        return None, ""

    # 只有一个候选直接返回
    if len(candidates) == 1:
        return candidates[0]

    # 多个候选：用遮盖检测筛选，取第一个真正可操作的
    logger.info("发现 %d 个「发布」按钮候选，执行遮盖检测筛选…", len(candidates))
    for loc, desc in candidates:
        if await _is_btn_actionable(loc):
            logger.info("遮盖检测通过，选定按钮: %s", desc)
            return loc, desc
        else:
            logger.info("按钮被遮盖或不可操作，跳过: %s", desc)

    # 全部检测失败时退化：返回第一个
    logger.warning("所有候选均未通过遮盖检测，退化使用第一个")
    return candidates[0]


async def _click_submit_with_fallback(
    page: Page,
    target_btn: Locator,
    metadata: Dict[str, Any],
    config: Dict[str, Any],
) -> None:
    """发表按钮点击策略（优先级从高到低）：
    1. Playwright locator.click()：内置 actionability 检查（含遮盖检测），最可靠
    2. 拟人贝塞尔曲线移动 + locator.click()：防风控外观，但保留 Playwright 遮盖检测
    3. locator.click(force=True)：强制穿透，仅在前两步均异常时使用
    4. page.mouse.click(坐标)：最后兜底，绕过所有检测

    注意：human_click 内部用 mouse.down/up 打坐标，会绕过 Playwright 遮盖检测，
    因此将其降级为第二步（先移动鼠标制造轨迹，再交还给 locator.click 完成实际点击）。
    """
    # 第一步：先尝试 Playwright 标准 click（带 actionability 检查）
    try:
        await target_btn.click(timeout=8000)
        logger.info("发布按钮标准 click 成功")
        return
    except Exception as e:
        logger.info("发布按钮标准 click 失败，尝试拟人移动后再 click: %s", e)

    # 第二步：拟人鼠标移动（制造自然轨迹），然后用 locator.click 完成点击
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
        import random as _random
        box = await target_btn.bounding_box()
        if box:
            vp = await page.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
            vw, vh = vp.get("w") or 800, vp.get("h") or 600
            from_x = _random.uniform(0, max(1, vw))
            from_y = _random.uniform(0, max(1, vh))
            to_x = box["x"] + box["width"] * _random.uniform(0.3, 0.7)
            to_y = box["y"] + box["height"] * _random.uniform(0.3, 0.7)
            await HumanBehavior.mouse_move(page, from_x, from_y, to_x, to_y, steps=_random.randint(18, 30))
            await page.wait_for_timeout(_random.randint(80, 200))
        await target_btn.click(timeout=8000)
        logger.info("发布按钮拟人移动后 click 成功")
        return
    except Exception as e:
        logger.info("拟人移动后 click 失败，尝试 force: %s", e)

    # 第三步：force click（跳过遮盖检测，仍走 Playwright 事件派发）
    try:
        await target_btn.click(timeout=8000, force=True)
        logger.info("发布按钮 force click 成功")
        return
    except Exception as e:
        logger.info("force click 失败，最后兜底 mouse.click: %s", e)

    # 第四步：坐标兜底（绕过所有检测，失败时直接抛出）
    box = await target_btn.bounding_box()
    if not box:
        raise RuntimeError("发布按钮无 bounding_box，无法 mouse.click")
    await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    logger.info("发布按钮坐标兜底 click 执行完毕")


async def _any_toast_success_visible(page: Page) -> bool:
    """检测「发布成功」Toast，主选择器优先，备用选择器兜底。Toast 消失极快，多候选可提高捕获率。"""
    primary = Selectors.VERIFY.get("SUCCESS_TOAST")
    if primary:
        try:
            loc = page.locator(primary).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            pass

    # 备用：VERIFY.SUCCESS_TOAST_ALT 及 STEP_EXTRAS.TOAST_SUCCESS_ALT
    for alt_key in ("SUCCESS_TOAST_ALT",):
        candidates = Selectors.VERIFY.get(alt_key) or []
        if isinstance(candidates, str):
            candidates = [candidates]
        for sel in candidates:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                continue

    for sel in Selectors.STEP_EXTRAS.get("TOAST_SUCCESS_ALT") or []:
        try:
            loc = page.locator(sel).first
            if await loc.count() > 0 and await loc.is_visible():
                return True
        except Exception:
            continue

    return False


async def _manage_page_content_visible(page: Page) -> bool:
    """发布后落地页特征检测。
    关键约束：发布编辑页（左侧导航栏）本身也含「作品数据」「作品管理」文案，
    因此必须同时排除仍在发布编辑页的情况，避免误判。
    """
    try:
        current_url = page.url or ""
        # 仍在发布编辑页，不认为是管理页
        if _is_publish_edit_url(current_url):
            return False
    except Exception:
        pass
    for sel in Selectors.VERIFY.get("MANAGE_PAGE_INDICATOR", []) or []:
        try:
            if await page.locator(sel).first.count() > 0 and await page.locator(sel).first.is_visible():
                return True
        except Exception:
            continue
    for sel in Selectors.VERIFY.get("MANAGE_PAGE_TITLE", []) or []:
        try:
            if await page.locator(sel).first.count() > 0 and await page.locator(sel).first.is_visible():
                return True
        except Exception:
            continue
    return False


class SubmitStep(BasePublishStep):
    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        """点击发布按钮并验证最终结果"""
        await self._await_pause(metadata)
        logger.info("===== 寻找并点击发布按钮 =====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        wait_ms = lambda ms: int(ms * speed_rate)

        config = metadata.get("anti_risk_config") or {}
        target_selector = ""
        target_btn: Optional[Locator] = None

        # ── 阶段1：找到发布按钮（最多约 10 秒）──────────────────────────────
        # 找不到按钮说明页面结构异常或未进入发布页，快速失败而非盲目等待3分钟
        async def _find_submit_button():
            loc, selector = await _resolve_submit_button(page)
            if loc:
                return loc, selector
            return None

        def _log_find_attempt(attempt: int) -> None:
            logger.info("发布按钮尚未可见，第 %d 次...", attempt + 1)

        found = await PluginWaitHelper.wait_for_condition(
            page,
            _find_submit_button,
            timeout_ms=wait_ms(10_000),
            poll_interval_ms=wait_ms(1_000),
            pause_callback=lambda: self._await_pause(metadata),
            on_poll=_log_find_attempt,
        )
        if found:
            target_btn, target_selector = found
        else:
            return PublishResult(
                success=False,
                error_message="未找到发布按钮（已等待约 10 秒），页面结构可能已变更",
            )

        # ── 阶段2：等发布按钮可点（最长 90 秒，用于等视频转码完成）────────────
        # 按钮存在但不可点通常是视频仍在转码，给足时间等转码，但有上限避免无限阻塞
        MAX_TRANSCODE_WAIT_SEC = 90
        async def _wait_ready_submit_button():
            # 每轮重新解析按钮，防止 Semi UI 刷新后节点失效
            loc, selector = await _resolve_submit_button(page)
            if loc:
                try:
                    await loc.scroll_into_view_if_needed(timeout=3000)
                except Exception:
                    pass
                if await _submit_control_ready(loc):
                    return loc, selector
                return None
            return None

        def _log_transcode_wait(_attempt: int) -> None:
            logger.info("发布按钮已出现但转码中，继续等待...")

        ready = await PluginWaitHelper.wait_for_condition(
            page,
            _wait_ready_submit_button,
            timeout_ms=MAX_TRANSCODE_WAIT_SEC * 1000,
            poll_interval_ms=wait_ms(500),
            pause_callback=lambda: self._await_pause(metadata),
            on_poll=_log_transcode_wait,
        )
        if ready:
            target_btn, target_selector = ready
        else:
            try:
                target_btn, target_selector = await _resolve_submit_button(page)
            except Exception:
                target_btn, target_selector = None, ""
            if target_btn:
                logger.info("发布按钮已出现但转码中，等待超时")
            else:
                logger.info("发布按钮消失，等待超时")
            return PublishResult(
                success=False,
                error_message=f"等待视频转码超时（{MAX_TRANSCODE_WAIT_SEC} 秒），发布按钮始终不可点",
            )

        if not target_btn or not await _submit_control_ready(target_btn):
            return PublishResult(
                success=False,
                error_message="发布按钮状态异常，无法点击",
            )

        logger.info("发布按钮已就绪（%s），准备点击…", target_selector)
        try:
            await self._await_pause(metadata)
            try:
                from src.infrastructure.anti_risk.delays import random_delay

                await random_delay(page, wait_ms(200), metadata, config)
            except Exception:
                await page.wait_for_timeout(wait_ms(200))

            target_btn, target_selector = await _resolve_submit_button(page)
            if not target_btn or not await _submit_control_ready(target_btn):
                return PublishResult(success=False, error_message="发布前按钮状态异常，请重试")
            await target_btn.wait_for(state="visible", timeout=5000)
            await target_btn.scroll_into_view_if_needed(timeout=5000)
            await page.wait_for_timeout(wait_ms(200))
            box = await target_btn.bounding_box()
            if box:
                logger.info(
                    "发布按钮位置: x=%.0f y=%.0f w=%.0f h=%.0f",
                    box["x"],
                    box["y"],
                    box["width"],
                    box["height"],
                )
            await _click_submit_with_fallback(page, target_btn, metadata, config)
            logger.info("已执行第一次点击")
            USER_LOG.info("[步骤9/9 点击发布] ▶ 已点击发布按钮")

            # Toast 消失极快（约 3 秒），点击后立即先检测一次，再进入轮询；一旦检测到则直接返回成功
            if await _any_toast_success_visible(page):
                logger.info("点击后即时检测到「发布成功」Toast")
                USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功！")
                return PublishResult(success=True, publish_url=page.url)

            probe_ms = wait_ms(4500)
            steps = max(12, probe_ms // 200)
            for _ in range(steps):
                await page.wait_for_timeout(200)
                if await _any_toast_success_visible(page):
                    logger.info("探测窗口内检测到「发布成功」Toast")
                    USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功！")
                    return PublishResult(success=True, publish_url=page.url)
                try:
                    u = page.url or ""
                    if _is_manage_url(u):
                        logger.info("探测窗口内检测到已跳转作品管理页: %s", u)
                        USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", u)
                        return PublishResult(success=True, publish_url=u)
                    if await _manage_page_content_visible(page):
                        logger.info("探测窗口内检测到作品管理页特征元素")
                        USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", page.url)
                        return PublishResult(success=True, publish_url=page.url)
                except Exception:
                    pass

            logger.info("探测窗口内未确认响应，执行第二次点击…")
            try:
                target_btn, _ = await _resolve_submit_button(page)
                if target_btn and await _submit_control_ready(target_btn):
                    await target_btn.wait_for(state="visible", timeout=3000)
                    await target_btn.scroll_into_view_if_needed(timeout=5000)
                    await page.wait_for_timeout(wait_ms(150))
                    await _click_submit_with_fallback(page, target_btn, metadata, config)
                    logger.info("已执行第二次点击")
            except Exception as e:
                logger.warning("第二次点击异常: %s", e)
        except Exception as e:
            return PublishResult(success=False, error_message=f"点击发布按钮失败: {str(e)}")

        logger.info("检查发布后是否存在弹窗或错误提示…")
        try:
            from src.infrastructure.anti_risk.delays import random_delay

            await random_delay(page, wait_ms(200), metadata, config)
        except Exception:
            await page.wait_for_timeout(wait_ms(200))

        try:
            error_selectors = [
                (", ".join(Selectors.SECURITY["PUBLISH_TOAST_ERROR"]), "发布失败/错误"),
                (", ".join(Selectors.SECURITY["PUBLISH_MODAL_COVER"]), "需要选择封面"),
                (", ".join(Selectors.SECURITY["PUBLISH_MODAL_SUPPLEMENT"]), "需要补充额外信息"),
                (", ".join(Selectors.SECURITY["PUBLISH_TOAST_FREQ"]), "操作频繁，风控拦截"),
            ]

            for selector, desc in error_selectors:
                if await page.locator(selector).count() > 0:
                    logger.warning("检测到异常弹窗/提示: %s", desc)
                    try:
                        text = await page.locator(selector).inner_text()
                        desc = f"{desc}: {text}"
                    except Exception:
                        pass
                    if "封面" in desc:
                        return NeedsAction(action="need_cover", message=f"点击发布后受阻: {desc}")
                    if "补充信息" in desc:
                        return NeedsAction(action="need_supplement", message=f"点击发布后受阻: {desc}")
                    if "操作频繁" in desc or "风控" in desc:
                        try:
                            from src.infrastructure.anti_risk.delays import cooldown_before_retry

                            sec = (metadata.get("anti_risk_config") or {}).get("cooldown_after_frequent_seconds", 180)
                            await cooldown_before_retry(float(sec), reason="操作频繁")
                            return NeedsAction(action="need_retry", message="操作频繁，已冷却后重试")
                        except Exception:
                            pass
                    return PublishResult(success=False, error_message=f"点击发布后受阻: {desc}")
        except Exception as e:
            logger.debug("检查弹窗出现异常（不影响主流程）: %s", e)

        return await self._verify_publish_result(page, metadata)

    async def _verify_publish_result(self, page: Page, metadata: Dict[str, Any]) -> PublishResult:
        """验证发布结果：manage URL、落地文案、Toast（超时随 speed_rate）。"""
        logger.info("===== 验证发布结果 =====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        # 抖音发布后跳转可能需要较长时间（网络慢/转码中），适当延长等待窗口
        t_url = int(15000 * speed_rate)
        t_toast = int(8000 * speed_rate)
        t_fallback = int(10000 * speed_rate)

        try:
            current_url = page.url or ""
            if _is_manage_url(current_url):
                logger.info("页面已在作品管理页: %s，视为发布成功", current_url)
                USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", current_url)
                return PublishResult(success=True, publish_url=current_url)
        except Exception:
            pass

        if await _manage_page_content_visible(page):
            logger.info("已检测到作品管理页特征元素，视为发布成功 | url=%s", page.url)
            USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", page.url)
            return PublishResult(success=True, publish_url=page.url)

        try:
            await page.wait_for_url(lambda u: _is_manage_url(str(u)), timeout=t_url)
            logger.info("点击后检测到跳转: %s", page.url)
            USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", page.url)
            return PublishResult(success=True, publish_url=page.url)
        except Exception:
            pass

        poll_interval_ms = max(100, int(150 * speed_rate))
        logger.info("检测「发布成功」Toast（最长约 %d ms）…", t_toast)
        t0 = time.time()
        while (time.time() - t0) * 1000 < t_toast:
            try:
                if await _any_toast_success_visible(page):
                    logger.info("✓ 检测到「发布成功」Toast")
                    USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功！")
                    try:
                        await page.wait_for_url(lambda u: _is_manage_url(str(u)), timeout=int(6000 * speed_rate))
                        logger.info("页面已跳转到作品管理页: %s", page.url)
                    except Exception:
                        pass
                    return PublishResult(success=True, publish_url=page.url)
            except Exception:
                pass
            await page.wait_for_timeout(poll_interval_ms)
            try:
                u = page.url or ""
                if _is_manage_url(u):
                    logger.info("轮询中检测到已跳转: %s", u)
                    USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", u)
                    return PublishResult(success=True, publish_url=u)
                if await _manage_page_content_visible(page):
                    logger.info("轮询中检测到管理页特征: %s", u)
                    USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", u)
                    return PublishResult(success=True, publish_url=u)
            except Exception:
                pass

        logger.info("未捕获到 Toast，尝试跳转与落地特征兜底校验…")

        try:
            await page.wait_for_url(lambda u: _is_manage_url(str(u)), timeout=t_fallback)
            logger.info("页面已跳转到作品管理页: %s，视为发布成功", page.url)
            USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", page.url)
            return PublishResult(success=True, publish_url=page.url)
        except Exception:
            pass

        if await _manage_page_content_visible(page):
            logger.info("兜底：作品管理页特征可见 | url=%s", page.url)
            USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", page.url)
            return PublishResult(success=True, publish_url=page.url)

        current_url = page.url or ""
        if _is_manage_url(current_url):
            logger.info("页面已进入作品管理页: %s，视为发布成功", current_url)
            USER_LOG.info("[步骤9/9 点击发布] ✓ 发布成功 (%s)", current_url)
            return PublishResult(success=True, publish_url=current_url)

        if _is_publish_edit_url(current_url):
            logger.warning("页面仍在发布编辑页，发布未生效（可能未选封面、被风控拦截等）: %s", current_url)
        elif "creator.douyin.com" in current_url.lower():
            logger.warning(
                "未检测到发布成功 Toast 且 URL 未进入作品管理，当前: %s",
                current_url,
            )

        logger.warning("未能确认发布成功，请手动检查")
        return PublishResult(
            success=False,
            error_message="发布后未能确认成功（未检测到'发布成功'提示或页面跳转），请手动检测",
        )
