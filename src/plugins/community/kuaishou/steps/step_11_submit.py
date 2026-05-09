# -*- coding: utf-8 -*-
"""
步骤11：点击发布并验证结果
文件路径: src/plugins/community/kuaishou/steps/step_11_submit.py

流程：
  1. 若已在作品管理页，直接成功（避免重试时重复点击）
  2. 关闭新手引导/向导弹层，防止遮挡点击
  3. 定位发布按钮
  4. 等待按钮可见，滚动到视口
  5. 点击（evaluate el.click() 最可靠，逐级降级）
  6. 点击后立即检测 Toast；再以 200ms 间隔轮询约 4.5 秒（Toast 仅持续约 3 秒）
  7. 探测窗口内无响应则补点一次；最终进入结果验证

DOM 参考（快手_发布按钮 DOM 分析报告_20260405.md）：
  视频发布页（/article/publish/video?tabType=1）与图文发布页（/article/publish/article）
  发布按钮结构完全一致：
    - 标签类型：generic (div)，cursor=pointer
    - 视频页 ref=e253，图文页 ref=e293
    - 建议 API：page.get_by_role('button', name='发布')
    - 两套页面复用同一套选择器逻辑
"""
import logging
import time
from typing import Any, Dict, Optional, Tuple

from playwright.async_api import Locator, Page

from src.plugins.core.interfaces.publish_plugin import PublishResult
from ._base import BasePublishStep, NeedsAction, StepOutcome
from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")

# 发布成功后作品管理路径
PUBLISH_SUCCESS_URL_PATTERN = "**/article/manage**"

# 视频/图文发布页通用选择器（DOM 报告 20260405 + probe 实测）
# 按钮为 <div>，无 role 属性，get_by_role 不可用
# 实测文案：图文页为「发布作品」，视频页为「发布」，故不带文案限制用类名定位
_SUBMIT_SELECTORS = [
    # probe 实测精确类名（最稳定）
    "div._button_3a3lq_1._button-primary_3a3lq_60",
    # 容器内 primary 按钮（哈希变更时仍可命中）
    "[class*='_edit-section-btns_'] [class*='_button-primary_']",
    # 完整精确路径（probe 日志直接给出）
    "#joyride-wrapper > main > div._edit-container_ql0z6_7 > div._edit-section_ql0z6_20._last_ql0z6_26 > div._edit-section-form_ql0z6_100 > div._edit-section-btns_ql0z6_118 > div._button_3a3lq_1._button-primary_3a3lq_60",
]


def _is_success_url(url: str) -> bool:
    """URL 是否已进入作品管理页（含 article/manage）。"""
    return bool(url) and "kuaishou.com" in url and "article/manage" in url.lower()


class SubmitStep(BasePublishStep):
    """点击发布按钮并验证最终结果。"""

    # ── 按钮定位 ──────────────────────────────────────────────────────────────

    async def _resolve_submit_button(self, page: Page) -> Tuple[Optional[Locator], str]:
        """定位发布按钮（视频/图文通用）。
        按钮为 <div>，无 role 属性，直接用 CSS 类名定位。
        probe 实测：div._button_3a3lq_1._button-primary_3a3lq_60 可稳定命中。
        """
        for sel in _SUBMIT_SELECTORS:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                if await loc.is_visible():
                    return loc, sel
            except Exception:
                continue

        return None, ""

    async def _find_success_url_in_context(self, page: Page) -> Optional[str]:
        """在当前页及同一 browser context 内查找作品管理 URL。"""
        try:
            pages = page.context.pages
        except Exception:
            pages = [page]
        for p in pages:
            try:
                u = p.url or ""
                if _is_success_url(u):
                    return u
            except Exception:
                continue
        return None

    # ── 点击 ──────────────────────────────────────────────────────────────────

    async def _click_submit_button(
        self,
        page: Page,
        target_btn: Locator,
        metadata: Dict[str, Any],
        config: Dict[str, Any],
    ) -> None:
        """统一点击发布按钮（视频/图文通用）。
        evaluate el.click() 对 div 和 button 均能穿透 React 事件绑定，最可靠。
        """
        # 1. evaluate el.click()
        try:
            await target_btn.evaluate("el => el.click()")
            logger.info("发布按钮 evaluate el.click() 成功")
            return
        except Exception as e:
            logger.info("evaluate el.click() 失败，降级 human_click: %s", e)

        # 2. human_click（防风控；外层已有 operation_delay，跳过内部重复等待）
        try:
            from src.infrastructure.anti_risk.human_like import human_click
            await human_click(page, target_btn, metadata, config, use_operation_delay=False)
            logger.info("发布按钮 human_click 成功")
            return
        except Exception as e:
            logger.info("human_click 失败，降级 click: %s", e)

        # 3. Playwright 普通 click
        try:
            await target_btn.click(timeout=10000)
            logger.info("发布按钮 click() 成功")
            return
        except Exception as e:
            logger.info("普通 click 失败，降级 force: %s", e)

        # 4. force click
        try:
            await target_btn.click(timeout=10000, force=True)
            return
        except Exception as e:
            logger.info("force click 失败，降级 mouse.click: %s", e)

        # 5. mouse.click
        box = await target_btn.bounding_box()
        if not box:
            raise RuntimeError("发布按钮无 bounding_box，所有点击方式均失败")
        await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

    # ── Toast 检测 ────────────────────────────────────────────────────────────

    async def _toast_success_visible(self, page: Page) -> bool:
        """检测发布成功 Toast（精确匹配，避免误命中非 Toast 元素）。"""
        phrases = Selectors.VERIFY.get("SUCCESS_TOAST_PHRASES") or [
            "内容发布成功",
            "视频发布成功",
            "发布成功",
        ]
        containers = Selectors.VERIFY.get("SUCCESS_TOAST_CONTAINERS") or []
        for csel in containers:
            try:
                group = page.locator((csel or "").strip())
                n = await group.count()
                for i in range(n):
                    node = group.nth(i)
                    if not await node.is_visible():
                        continue
                    try:
                        inner = await node.inner_text()
                    except Exception:
                        inner = ""
                    for phrase in phrases:
                        p = (phrase or "").strip()
                        if not p:
                            continue
                        if p in inner and "失败" not in inner and "未发布" not in inner:
                            return True
            except Exception:
                continue
        return False

    # ── 主流程 ────────────────────────────────────────────────────────────────

    async def execute(self, page: Page, file_path: str, metadata: Dict[str, Any]) -> StepOutcome:
        await self._await_pause(metadata)
        _p = self._step_prefix(metadata, "点击发布")
        config = metadata.get("anti_risk_config") or {}
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
        publish_type = metadata.get("publish_type", "video")

        logger.info("发布类型=%s，使用统一发布按钮策略（DOM 报告 20260405：视频/图文按钮结构一致）",
                    publish_type)

        # 重试进入时可能已跳转成功，避免再次点击
        pre_ok = await self._find_success_url_in_context(page)
        if pre_ok:
            logger.info("已在作品列表相关页，跳过点击发布: %s", pre_ok)
            USER_LOG.info("%s ✓ 已在作品列表页，视为成功 (%s)", _p, pre_ok)
            return PublishResult(success=True, publish_url=pre_ok)

        logger.info("===== 寻找并点击发布按钮 =====")

        # 关闭新手引导/向导弹层（防止遮挡发布按钮导致点击失效）
        try:
            from .wizard_utils import dismiss_kuaishou_publish_guides
            await dismiss_kuaishou_publish_guides(page, metadata, max_rounds=4)
        except Exception as e:
            logger.debug("步骤11 关闭新手引导时异常（已忽略）: %s", e)

        # 定位发布按钮
        target_btn, submit_sel = await self._resolve_submit_button(page)
        if target_btn is None:
            logger.warning("未找到发布按钮，当前页 URL: %s", page.url)
            logger.warning("尝试的选择器列表: %s", _SUBMIT_SELECTORS)
            return PublishResult(
                success=False,
                error_message="未找到发布按钮，可能页面结构已变更",
            )
        logger.info("发布按钮命中选择器: %s", submit_sel)

        # 等待按钮可见
        try:
            await target_btn.wait_for(state="visible", timeout=10000)
        except Exception as e:
            return PublishResult(success=False, error_message=f"发布按钮未在超时内变为可见: {e}")

        # 滚动到视口中央，确保按钮可点击
        try:
            await target_btn.evaluate(
                "el => el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' })"
            )
            await page.wait_for_timeout(300)
        except Exception:
            pass

        # 操作前随机等待（防风控）
        try:
            from src.infrastructure.anti_risk.delays import operation_delay
            await operation_delay(page, metadata, config)
        except Exception:
            await page.wait_for_timeout(int(500 * speed_rate))

        # ── 第一次点击 ────────────────────────────────────────────────────────
        try:
            # 点击前重新解析按钮，避免 DOM 刷新后节点失效
            target_btn, submit_sel = await self._resolve_submit_button(page)
            if target_btn is None:
                return PublishResult(success=False, error_message="点击前按钮消失，可能页面已刷新")
            await self._click_submit_button(page, target_btn, metadata, config)
        except Exception as e:
            logger.warning("发布按钮点击失败: %s", e)
            return PublishResult(success=False, error_message=f"发布按钮点击失败: {e}")

        USER_LOG.info("%s ▶ 已点击发布按钮", _p)

        # 检测操作频繁/风控弹窗
        for sel in Selectors.SECURITY.get("PUBLISH_TOAST_FREQ", []):
            try:
                if await page.locator(sel).count() > 0:
                    sec = (config or {}).get("cooldown_after_frequent_seconds", 180)
                    try:
                        from src.infrastructure.anti_risk.delays import cooldown_before_retry
                        await cooldown_before_retry(float(sec), reason="操作频繁")
                        return NeedsAction(action="need_retry", message="操作频繁，已冷却后重试")
                    except Exception:
                        pass
                    return PublishResult(success=False, error_message="检测到操作频繁或风控提示")
            except Exception:
                continue

        # ── 立即检测 Toast（Toast 最多持续约 3 秒，必须尽快捕获）────────────
        if await self._toast_success_visible(page):
            logger.info("点击后即时检测到「发布成功」Toast")
            USER_LOG.info("%s ✓ 发布成功！", _p)
            return PublishResult(success=True, publish_url=page.url)

        # 已在成功页？
        ok_url = await self._find_success_url_in_context(page)
        if ok_url:
            USER_LOG.info("%s ✓ 发布成功，已检测到作品列表 (%s)", _p, ok_url)
            return PublishResult(success=True, publish_url=ok_url)

        # ── 探测窗口（200ms 轮询，约 4.5 秒）────────────────────────────────
        probe_ms = int(4500 * speed_rate)
        steps = max(15, probe_ms // 200)
        for _ in range(steps):
            await page.wait_for_timeout(200)
            if await self._toast_success_visible(page):
                logger.info("探测窗口内检测到「发布成功」Toast")
                USER_LOG.info("%s ✓ 发布成功！", _p)
                return PublishResult(success=True, publish_url=page.url)
            ok_url = await self._find_success_url_in_context(page)
            if ok_url:
                logger.info("探测窗口内检测到作品列表 URL: %s", ok_url)
                USER_LOG.info("%s ✓ 发布成功 (%s)", _p, ok_url)
                return PublishResult(success=True, publish_url=ok_url)

        # ── 补点一次（探测窗口无响应，重新找按钮点击）────────────────────────
        logger.info("探测窗口内未确认响应，执行补充点击…")
        try:
            btn2, _ = await self._resolve_submit_button(page)
            if btn2 is not None and await btn2.is_visible():
                await btn2.evaluate("el => el.click()")
                logger.info("补充点击已执行")
                await page.wait_for_timeout(500)
                if await self._toast_success_visible(page):
                    USER_LOG.info("%s ✓ 发布成功（补充点击后检测到 Toast）", _p)
                    return PublishResult(success=True, publish_url=page.url)
        except Exception as e:
            logger.warning("补充点击异常（已忽略）: %s", e)

        # ── 最终验证 ─────────────────────────────────────────────────────────
        return await self._verify_publish_result(page, metadata, _p)

    # ── 兜底验证 ──────────────────────────────────────────────────────────────

    async def _verify_publish_result(self, page: Page, metadata: Dict[str, Any], _p: str = "") -> PublishResult:
        """验证发布结果：作品管理页 URL 或 Toast（超时随 speed_rate）。"""
        logger.info("===== 验证发布结果（兜底）=====")
        speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))

        # 立即检查是否已在成功页
        ok_url = await self._find_success_url_in_context(page)
        if ok_url:
            USER_LOG.info("%s ✓ 发布成功，已检测到作品列表 (%s)", _p, ok_url)
            return PublishResult(success=True, publish_url=ok_url)

        # 等待 URL 跳转（最长 10 秒）
        try:
            await page.wait_for_url(PUBLISH_SUCCESS_URL_PATTERN, timeout=int(10000 * speed_rate))
            final = page.url
            USER_LOG.info("%s ✓ 发布成功，跳转至 %s", _p, final)
            return PublishResult(success=True, publish_url=final)
        except Exception:
            pass

        # Toast 轮询（150ms 间隔，最长 5 秒）
        t0 = time.monotonic()
        while (time.monotonic() - t0) < 5.0:
            if await self._toast_success_visible(page):
                USER_LOG.info("%s ✓ 检测到「内容发布成功」提示", _p)
                try:
                    await page.wait_for_url(PUBLISH_SUCCESS_URL_PATTERN, timeout=8000)
                except Exception:
                    pass
                return PublishResult(success=True, publish_url=page.url)
            ok_url = await self._find_success_url_in_context(page)
            if ok_url:
                USER_LOG.info("%s ✓ 发布成功 (%s)", _p, ok_url)
                return PublishResult(success=True, publish_url=ok_url)
            await page.wait_for_timeout(150)

        current_url = page.url or ""
        all_urls = [p.url for p in page.context.pages] if page.context else [current_url]
        logger.warning(
            "发布后未检测到作品列表页或成功提示；当前页 URL=%s；context 内全部 URL=%s",
            current_url,
            all_urls,
        )
        return PublishResult(
            success=False,
            error_message=(
                "发布后未检测到成功（未跳转至作品管理 article/manage 且未见成功提示）。"
                f"当前页: {current_url or '未知'}"
            ),
        )
