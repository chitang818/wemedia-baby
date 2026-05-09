"""
发布层防风控：拟人行为（随机鼠标移动、步骤前随机浏览、拟人点击、拟人输入）
文件路径：src/infrastructure/anti_risk/human_like.py
依赖 HumanBehavior，在关键步骤前/间插入随机移动、滚动、悬停；点击时区域内随机坐标+贝塞尔移动；输入时逐字节奏。
"""

import random
import asyncio
import logging
from typing import Dict, Any, Optional, Union

from playwright.async_api import Page, Locator

logger = logging.getLogger(__name__)


def _is_human_like_enabled(metadata: Optional[Dict[str, Any]], config: Optional[Dict[str, Any]]) -> bool:
    """是否启用拟人行为（可由平台配置或 metadata 关闭）。"""
    if config is not None and config.get("enable_human_like") is False:
        return False
    if metadata is not None and metadata.get("anti_risk_human_like") is False:
        return False
    return True


async def random_mouse_wander(
    page: Page,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """在可视区内做一次随机鼠标移动（贝塞尔曲线），模拟用户无目的移动。

    若未启用拟人或 HumanBehavior 不可用则直接返回。
    """
    if not _is_human_like_enabled(metadata, config):
        return
    if config is not None and config.get("enable_mouse_wander") is False:
        return
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
    except ImportError:
        logger.debug("HumanBehavior 未找到，跳过随机鼠标移动")
        return
    try:
        viewport = await page.evaluate("""() => ({
            w: window.innerWidth,
            h: window.innerHeight
        })""")
        w = viewport.get("w") or 800
        h = viewport.get("h") or 600
        # 安全区内随机两点（避开边缘）
        margin = min(80, w // 5, h // 5)
        from_x = random.uniform(margin, w - margin)
        from_y = random.uniform(margin, h - margin)
        to_x = random.uniform(margin, w - margin)
        to_y = random.uniform(margin, h - margin)
        await HumanBehavior.mouse_move(page, from_x, from_y, to_x, to_y, steps=random.randint(15, 35))
    except Exception as e:
        logger.debug("random_mouse_wander 执行异常（已忽略）: %s", e)


async def optional_browse_before_action(
    page: Page,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """步骤前可选「随机浏览」：以一定概率执行轻微滚动或随机鼠标移动，再短暂停留。

    建议在进入发布页后、上传前或关键点击前调用，降低「直接定点操作」的特征。
    config 可含 enable_browse_before_action、browse_probability（0~1）。
    """
    if not _is_human_like_enabled(metadata, config):
        return
    if config is not None and config.get("enable_browse_before_action") is False:
        return
    prob = 0.4
    if config is not None and "browse_probability" in config:
        prob = max(0, min(1, float(config.get("browse_probability", prob))))
    if random.random() > prob:
        return
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
    except ImportError:
        return
    try:
        # 随机选择：仅鼠标移动 / 轻微滚动+停留 / 两者都做
        choice = random.choice(["mouse", "scroll", "both"])
        if choice in ("mouse", "both"):
            await random_mouse_wander(page, metadata, config)
            await page.wait_for_timeout(random.randint(200, 600))
        if choice in ("scroll", "both"):
            await HumanBehavior.scroll(page, direction=random.choice(["down", "up"]), distance=random.uniform(80, 200), smooth=True)
            await page.wait_for_timeout(random.randint(300, 800))
    except Exception as e:
        logger.debug("optional_browse_before_action 执行异常（已忽略）: %s", e)


async def human_click(
    page: Page,
    selector_or_locator: Union[str, Locator],
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    *,
    use_operation_delay: bool = True,
) -> None:
    """拟人点击：在元素有效区域内随机选点，贝塞尔曲线移动后点击；可选操作前延迟。

    若未启用拟人则退化为 page.locator(selector).click()。
    config 可含 enable_human_like、enable_mouse_wander；use_operation_delay 为 True 时会调用 operation_delay（1-5s）。
    """
    if not _is_human_like_enabled(metadata, config):
        locator = page.locator(selector_or_locator) if isinstance(selector_or_locator, str) else selector_or_locator
        await locator.click()
        return
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
        from src.infrastructure.anti_risk.delays import operation_delay
    except ImportError:
        locator = page.locator(selector_or_locator) if isinstance(selector_or_locator, str) else selector_or_locator
        await locator.click()
        return
    if use_operation_delay and (config is None or config.get("operation_delay_before_click", True)):
        await operation_delay(page, metadata, config)
    if config is not None and config.get("enable_mouse_wander", True):
        await random_mouse_wander(page, metadata, config)
        await page.wait_for_timeout(random.randint(150, 500))
    await HumanBehavior.click_in_bounds(page, selector_or_locator, move_from_viewport=True)


async def human_type_text(
    page: Page,
    selector: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
    *,
    use_operation_delay: bool = True,
    clear_first: bool = True,
) -> None:
    """拟人输入：模拟逐字输入节奏（含大小写/数字略慢、可选打错再删），避免瞬间粘贴。

    若未启用拟人则退化为先 clear 再 page.fill(selector, text)。
    config 可含 type_mistake_probability（0~1，默认 0.02）、operation_delay_before_type。
    """
    if not _is_human_like_enabled(metadata, config):
        locator = page.locator(selector)
        if clear_first:
            await locator.clear()
        await locator.fill(text)
        return
    try:
        from src.infrastructure.browser.human_behavior import HumanBehavior
        from src.infrastructure.anti_risk.delays import operation_delay
    except ImportError:
        locator = page.locator(selector)
        if clear_first:
            await locator.clear()
        await locator.fill(text)
        return
    if use_operation_delay and (config is None or config.get("operation_delay_before_type", True)):
        await operation_delay(page, metadata, config)
    mistake_prob = 0.02
    if config is not None and "type_mistake_probability" in config:
        mistake_prob = max(0, min(1, float(config.get("type_mistake_probability", mistake_prob))))
    if clear_first:
        await page.locator(selector).clear()
        await page.wait_for_timeout(random.randint(80, 200))
    await HumanBehavior.type_text(page, selector, text, mistake_probability=mistake_prob)
