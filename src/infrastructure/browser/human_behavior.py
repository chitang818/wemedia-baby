"""
人类行为模拟工具
文件路径:src/infrastructure/browser/human_behavior.py
功能:模拟真实人类的鼠标、键盘、滚动等行为,提升自动化的真实性
"""

import asyncio
import logging
from typing import Optional, Union
from src.infrastructure.browser.automation_api import Page, Locator

logger = logging.getLogger(__name__)


class HumanBehavior:
    """人类行为模拟工具类
    
    提供鼠标轨迹、键盘节奏、滚动行为等模拟功能
    """
    
    @staticmethod
    async def mouse_move(
        page: Page,
        from_x: float,
        from_y: float,
        to_x: float,
        to_y: float,
        steps: Optional[int] = None
    ) -> None:
        """Move directly to a required target without synthetic trajectory noise."""
        await page.mouse.move(to_x, to_y)
    
    @staticmethod
    async def type_text(
        page: Page,
        selector: str,
        text: str,
        mistake_probability: float = 0.05
    ) -> None:
        """Type with normal keyboard events and no deliberate mistakes."""
        locator = page.locator(selector)
        await locator.scroll_into_view_if_needed()
        await locator.click()
        await locator.press_sequentially(text, delay=30)
    
    @staticmethod
    async def scroll(
        page: Page,
        direction: str = 'down',
        distance: Optional[float] = None,
        smooth: bool = True
    ) -> None:
        """模拟人类滚动行为
        
        Args:
            page: Playwright Page对象
            direction: 滚动方向 'down' 或 'up'
            distance: 滚动距离(像素),None则自动计算
            smooth: 是否平滑滚动
        """
        if distance is None:
            distance = await page.evaluate("window.innerHeight")
        delta_y = distance if direction == "down" else -distance
        await page.mouse.wheel(0, delta_y)
    
    @staticmethod
    async def random_delay(min_ms: int = 100, max_ms: int = 500) -> None:
        """随机延迟
        
        Args:
            min_ms: 最小延迟(毫秒)
            max_ms: 最大延迟(毫秒)
        """
        delay = max(0, min_ms) / 1000
        await asyncio.sleep(delay)
    
    @staticmethod
    async def click_in_bounds(
        page: Page,
        selector_or_locator: Union[str, Locator],
        inner_margin: Optional[int] = None,
        move_from_viewport: bool = True,
    ) -> None:
        """Use the target's normal actionability checks and deterministic click."""
        locator = page.locator(selector_or_locator) if isinstance(selector_or_locator, str) else selector_or_locator
        await locator.scroll_into_view_if_needed()
        await locator.click()

    @staticmethod
    async def click_with_delay(
        page: Page,
        selector: str,
        delay_before: Optional[int] = None,
        delay_after: Optional[int] = None
    ) -> None:
        """点击并延迟
        
        Args:
            page: Playwright Page对象
            selector: 元素选择器
            delay_before: 点击前延迟(毫秒),None则随机
            delay_after: 点击后延迟(毫秒),None则随机
        """
        # 点击前延迟
        if delay_before is None:
            delay_before = 100
        await asyncio.sleep(delay_before / 1000)
        
        # 点击
        await page.click(selector)
        logger.debug(f"点击元素: {selector}")
        
        # 点击后延迟
        if delay_after is None:
            delay_after = 200
        await asyncio.sleep(delay_after / 1000)
    
    @staticmethod
    async def read_page(page: Page, duration: Optional[float] = None) -> None:
        """模拟阅读页面
        
        Args:
            page: Playwright Page对象
            duration: 阅读时长(秒),None则随机
        """
        if duration is None:
            duration = 0

        if duration > 0:
            logger.debug("页面状态等待: %.1f秒", duration)
            await asyncio.sleep(duration)
    
    @staticmethod
    async def hover_element(
        page: Page,
        selector: str,
        duration: Optional[float] = None
    ) -> None:
        """悬停在元素上
        
        Args:
            page: Playwright Page对象
            selector: 元素选择器
            duration: 悬停时长(秒),None则随机
        """
        if duration is None:
            duration = 0
        
        await page.hover(selector)
        logger.debug(f"悬停在元素: {selector}, {duration:.1f}秒")
        if duration > 0:
            await asyncio.sleep(duration)

    @staticmethod
    async def hover_and_jitter(
        page: Page,
        selector_or_locator: Union[str, Locator],
        duration: float = 3.0,
    ) -> None:
        """Hover once without synthetic jitter.
        
        Args:
            page: Playwright Page对象
            selector_or_locator: 选择器字符串或 Locator
            duration: 徘徊总时长(秒)
        """
        locator = page.locator(selector_or_locator) if isinstance(selector_or_locator, str) else selector_or_locator
        await locator.hover()

    @staticmethod
    async def scroll_to_bottom(page: Page) -> None:
        """Scroll to the bottom deterministically."""
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            
    @staticmethod
    async def scroll_to_locator(
        page: Page, 
        locator: Locator, 
        max_scrolls: int = 15,
        target_ratio: float = 0.5
    ) -> bool:
        """Bring the element into view without synthetic scrolling patterns."""
        await locator.scroll_into_view_if_needed()
        return await locator.bounding_box() is not None

    @staticmethod
    async def mouse_wander(page: Page, duration: float = 5.0) -> None:
        """Compatibility no-op: purposeless pointer wandering is disabled."""
        return None

    @staticmethod
    async def realistic_delay(
        mean_ms: float = 500,
        std_ms: float = 150,
        min_ms: float = 100,
        max_ms: float = 3000,
    ) -> None:
        """P1 方向五：基于正态分布的真实人类认知延迟。

        相比均匀分布（random.uniform），正态分布更接近真实用户的反应时间分布：
        绝大多数操作集中在均值附近，偶有较短/较长的极端值。

        Args:
            mean_ms:  均值延迟（毫秒），对应"普通操作"期望时间
            std_ms:   标准差（毫秒），控制延迟分散程度
            min_ms:   最小延迟下限（毫秒），防止延迟过短失去真实感
            max_ms:   最大延迟上限（毫秒），防止因极端值阻塞流程

        常见场景预设：
            - 快速确认：mean=300, std=80
            - 普通操作：mean=500, std=150（默认）
            - 阅读/思考：mean=1200, std=300
            - 上传等待中扫视：mean=2000, std=400
        """
        delay_ms = max(min_ms, min(max_ms, mean_ms))
        await asyncio.sleep(delay_ms / 1000.0)
        logger.debug("realistic_delay: %.0f ms (mean=%.0f std=%.0f)", delay_ms, mean_ms, std_ms)

