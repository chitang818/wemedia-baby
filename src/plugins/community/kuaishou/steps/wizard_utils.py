# -*- coding: utf-8 -*-
"""
快手发布页新手引导 / 使用向导关闭工具
文件路径: src/plugins/community/kuaishou/steps/wizard_utils.py

新号首次发布常见：作品信息 1/4 向导、react-joyride 遮罩、Ant 弹窗类引导。
高发时机：进入发布页（步骤2）、上传完成瞬间（步骤3末尾）；步骤4 填表前再兜底一次。步骤5 之后一般不再弹新手引导，不必每步调用。
策略：检测须 await；优先关 X，再点「下一步/知道了/跳过」等，并辅以 Escape 与 Joyride 气泡内按钮。
"""
import logging
from typing import Dict, Any, List

from src.infrastructure.browser.automation_api import Page

from ..selectors import Selectors

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


async def _is_kuaishou_onboarding_blocking(page: Page) -> bool:
    """当前页是否存在可能遮挡操作的引导层（向导弹窗、joyride、Ant Tour 等）。"""
    for sel in (Selectors.WIZARD.get("WORK_INFO_MODAL") or []):
        try:
            el = page.locator(sel).first
            if await el.count() > 0 and await el.is_visible():
                return True
        except Exception:
            continue
    try:
        overlay = page.locator(".react-joyride__overlay").first
        if await overlay.count() > 0 and await overlay.is_visible():
            return True
    except Exception:
        pass
    try:
        tip = page.locator(".react-joyride__tooltip").first
        if await tip.count() > 0 and await tip.is_visible():
            return True
    except Exception:
        pass
    for tip_sel in (Selectors.WIZARD.get("JOYRIDE_TOOLTIP_ROOT") or []):
        if tip_sel == ".react-joyride__tooltip":
            continue
        try:
            el = page.locator(tip_sel).first
            if await el.count() > 0 and await el.is_visible():
                return True
        except Exception:
            continue
    try:
        tour = page.locator(".ant-tour, [class*='ant-tour']").first
        if await tour.count() > 0 and await tour.is_visible():
            return True
    except Exception:
        pass
    # 可见的 Ant Modal 且文案像新手引导（避免误伤仅含「确定」的普通弹窗）
    for phrase in ("新手指引", "发布引导", "新手教程", "创作者"):
        try:
            m = page.locator(f".ant-modal-wrap:not(.ant-modal-wrap-hidden) .ant-modal-content:has-text('{phrase}')").first
            if await m.count() > 0 and await m.is_visible():
                return True
        except Exception:
            continue
    return False


async def _try_press_escape(page: Page, metadata: Dict[str, Any], times: int = 2) -> None:
    speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
    for _ in range(max(1, times)):
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(int(350 * speed_rate))
        except Exception:
            break


async def _click_first_visible(
    page: Page, selectors: List[str], metadata: Dict[str, Any], config: Dict[str, Any]
) -> bool:
    """按选择器列表点击第一个可见元素，成功返回 True。"""
    speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
    for sel in selectors or []:
        try:
            btn = page.locator(sel).first
            if await btn.count() == 0 or not await btn.is_visible():
                continue
            try:
                from src.infrastructure.anti_risk.human_like import human_click

                await human_click(page, btn, metadata, config)
            except Exception:
                await btn.click(timeout=5000)
            await page.wait_for_timeout(int(400 * speed_rate))
            return True
        except Exception:
            continue
    return False


async def _click_joyride_tooltip_buttons(page: Page, metadata: Dict[str, Any], config: Dict[str, Any]) -> bool:
    """在 react-joyride 气泡内点击主操作按钮（下一步/知道了等）。"""
    speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
    clicked = False
    for root_sel in Selectors.WIZARD.get("JOYRIDE_TOOLTIP_ROOT") or [".react-joyride__tooltip"]:
        try:
            root = page.locator(root_sel).first
            if await root.count() == 0 or not await root.is_visible():
                continue
            inner_selectors = [
                "button:has-text('下一步')",
                "button:has-text('知道了')",
                "button:has-text('跳过')",
                "button:has-text('完成')",
                "button:has-text('好的')",
                "[role='button']:has-text('下一步')",
                "[role='button']:has-text('知道了')",
                "button[type='button']",
            ]
            for inner in inner_selectors:
                try:
                    loc = root.locator(inner).first
                    if await loc.count() == 0 or not await loc.is_visible():
                        continue
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click

                        await human_click(page, loc, metadata, config)
                    except Exception:
                        await loc.click(timeout=5000)
                    await page.wait_for_timeout(int(400 * speed_rate))
                    clicked = True
                    break
                except Exception:
                    continue
        except Exception:
            continue
    return clicked


async def dismiss_work_info_wizard_if_present(
    page: Page, metadata: Dict[str, Any], max_clicks: int = 8
) -> bool:
    """
    关闭「作品信息」类向导弹窗：优先 X，再多次点击「下一步/知道了/…」。
    返回是否执行过至少一次关闭尝试（不一定表示层已完全消失，由上层可再调 dismiss_kuaishou_publish_guides）。
    """
    if not await _is_kuaishou_onboarding_blocking(page):
        return False

    config = metadata.get("anti_risk_config") or {}
    speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
    did_close = False

    for sel in (Selectors.WIZARD.get("WIZARD_CLOSE_X") or []):
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0 and await btn.is_visible():
                try:
                    from src.infrastructure.anti_risk.human_like import human_click

                    await human_click(page, btn, metadata, config)
                except Exception:
                    await btn.click()
                await page.wait_for_timeout(int(400 * speed_rate))
                did_close = True
                logger.info("已点击向导弹窗关闭按钮(X)")
                USER_LOG.info("[快手] 已关闭引导弹窗（关闭按钮）")
                if not await _is_kuaishou_onboarding_blocking(page):
                    return True
        except Exception:
            continue

    for _ in range(max_clicks):
        if not await _is_kuaishou_onboarding_blocking(page):
            return True
        for sel in (Selectors.WIZARD.get("WIZARD_NEXT_OR_DONE") or []):
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0 and await btn.is_visible():
                    try:
                        from src.infrastructure.anti_risk.human_like import human_click

                        await human_click(page, btn, metadata, config)
                    except Exception:
                        await btn.click()
                    await page.wait_for_timeout(int(400 * speed_rate))
                    did_close = True
                    if not await _is_kuaishou_onboarding_blocking(page):
                        logger.info("向导已通过主按钮关闭")
                        USER_LOG.info("[快手] 已关闭发布引导向导")
                        return True
                    break
            except Exception:
                continue

    await _click_joyride_tooltip_buttons(page, metadata, config)
    return did_close


async def dismiss_kuaishou_publish_guides(page: Page, metadata: Dict[str, Any], max_rounds: int = 6) -> bool:
    """
    统一关闭发布页各类新手引导（多轮：Escape + 关 X + 主按钮 + Joyride 气泡）。
    建议在步骤 2（进页）、3（上传成功后）、4（填元数据前）调用。
    返回是否至少进行过一轮处理。
    """
    config = metadata.get("anti_risk_config") or {}
    speed_rate = max(0.5, float(metadata.get("speed_rate", 1.0)))
    any_action = False

    for round_i in range(max_rounds):
        if not await _is_kuaishou_onboarding_blocking(page):
            break
        any_action = True
        if round_i == 0:
            logger.info("检测到快手发布页新手引导/向导弹层，开始关闭")
            USER_LOG.info("[快手] 检测到新手引导，正在关闭…")

        await _try_press_escape(page, metadata, times=2)
        if not await _is_kuaishou_onboarding_blocking(page):
            USER_LOG.info("[快手] 已通过 Esc 关闭引导层")
            break

        await dismiss_work_info_wizard_if_present(page, metadata, max_clicks=4)
        if not await _is_kuaishou_onboarding_blocking(page):
            break

        if await _click_joyride_tooltip_buttons(page, metadata, config):
            if not await _is_kuaishou_onboarding_blocking(page):
                break

        # Ant Tour「下一步」
        for sel in (
            ".ant-tour button:has-text('下一步')",
            ".ant-tour button:has-text('知道了')",
            ".ant-tour button:has-text('跳过')",
            "[class*='ant-tour'] button:has-text('下一步')",
        ):
            if await _click_first_visible(page, [sel], metadata, config):
                break
        await page.wait_for_timeout(int(300 * speed_rate))

    return any_action
