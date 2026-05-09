"""
人类行为模拟工具
文件路径:src/infrastructure/browser/human_behavior.py
功能:模拟真实人类的鼠标、键盘、滚动等行为,提升自动化的真实性
"""

import random
import asyncio
import logging
from typing import Optional, Union
from playwright.async_api import Page, Locator

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
        """模拟人类鼠标移动轨迹(贝塞尔曲线)
        
        Args:
            page: Playwright Page对象
            from_x: 起始X坐标
            from_y: 起始Y坐标
            to_x: 目标X坐标
            to_y: 目标Y坐标
            steps: 移动步数,None则随机
        """
        if steps is None:
            steps = random.randint(20, 40)
        
        # 生成贝塞尔曲线控制点
        control_x1 = from_x + (to_x - from_x) * 0.25 + random.uniform(-50, 50)
        control_y1 = from_y + (to_y - from_y) * 0.25 + random.uniform(-50, 50)
        control_x2 = from_x + (to_x - from_x) * 0.75 + random.uniform(-50, 50)
        control_y2 = from_y + (to_y - from_y) * 0.75 + random.uniform(-50, 50)
        
        logger.debug(f"鼠标移动: ({from_x},{from_y}) -> ({to_x},{to_y}), {steps}步")
        
        for i in range(steps):
            t = i / steps
            # 三次贝塞尔曲线公式
            x = (1-t)**3 * from_x + 3*(1-t)**2*t * control_x1 + \
                3*(1-t)*t**2 * control_x2 + t**3 * to_x
            y = (1-t)**3 * from_y + 3*(1-t)**2*t * control_y1 + \
                3*(1-t)*t**2 * control_y2 + t**3 * to_y
            
            # 添加微小抖动
            x += random.uniform(-1, 1)
            y += random.uniform(-1, 1)
            
            await page.mouse.move(x, y)
            await asyncio.sleep(random.uniform(0.005, 0.02))
    
    @staticmethod
    async def type_text(
        page: Page,
        selector: str,
        text: str,
        mistake_probability: float = 0.05
    ) -> None:
        """模拟人类打字节奏
        
        Args:
            page: Playwright Page对象
            selector: 输入框选择器
            text: 要输入的文本
            mistake_probability: 打错字的概率(0-1)
        """
        await page.click(selector)
        logger.debug(f"开始输入文本: {text[:20]}...")
        
        for i, char in enumerate(text):
            # 基础延迟: 50-150ms
            delay = random.uniform(0.05, 0.15)
            
            # 某些字符打字更慢(如大写、数字、符号)
            if char.isupper() or char.isdigit() or not char.isalnum():
                delay *= 1.5
            
            # 偶尔打错字然后删除
            if random.random() < mistake_probability and i > 0:
                wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                await page.keyboard.type(wrong_char)
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await page.keyboard.press('Backspace')
                await asyncio.sleep(random.uniform(0.05, 0.1))
            
            await page.keyboard.type(char)
            await asyncio.sleep(delay)
        
        logger.debug("文本输入完成")
    
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
            # 获取页面高度
            page_height = await page.evaluate('document.body.scrollHeight')
            viewport_height = await page.evaluate('window.innerHeight')
            # 滚动50-80%的可见区域
            distance = viewport_height * random.uniform(0.5, 0.8)
        
        # 分段滚动
        if smooth:
            steps = random.randint(5, 10)
            step_distance = distance / steps
            
            logger.debug(f"平滑滚动{direction}: {distance}px, {steps}步")
            
            for _ in range(steps):
                # 滚动一段
                delta_y = step_distance if direction == 'down' else -step_distance
                await page.mouse.wheel(0, delta_y)
                
                # 随机停留(模拟阅读)
                await asyncio.sleep(random.uniform(0.3, 1.5))
        else:
            # 一次性滚动
            delta_y = distance if direction == 'down' else -distance
            await page.mouse.wheel(0, delta_y)
            logger.debug(f"快速滚动{direction}: {distance}px")
    
    @staticmethod
    async def random_delay(min_ms: int = 100, max_ms: int = 500) -> None:
        """随机延迟
        
        Args:
            min_ms: 最小延迟(毫秒)
            max_ms: 最大延迟(毫秒)
        """
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        await asyncio.sleep(delay)
    
    @staticmethod
    async def click_in_bounds(
        page: Page,
        selector_or_locator: Union[str, Locator],
        inner_margin: Optional[int] = None,
        move_from_viewport: bool = True,
    ) -> None:
        """在元素有效区域内随机选点，先贝塞尔曲线移动再点击，避免固定点中心。

        Args:
            page: Playwright Page
            selector_or_locator: 选择器字符串或 Locator
            inner_margin: 相对元素边界内缩像素，避免点到边缘；None 则取 min(8, 宽高约10%)
            move_from_viewport: True 时从视口内随机起点移动过去，False 时从元素中心附近移动
        """
        locator = page.locator(selector_or_locator) if isinstance(selector_or_locator, str) else selector_or_locator
        box = await locator.bounding_box()
        if not box:
            await locator.click()
            return
        x, y, w, h = box["x"], box["y"], box["width"], box["height"]
        margin = inner_margin if inner_margin is not None else min(8, int(min(w, h) * 0.1))
        margin = max(0, min(margin, w / 2 - 1, h / 2 - 1))
        cx = x + margin
        cy = y + margin
        cw = max(1, w - 2 * margin)
        ch = max(1, h - 2 * margin)
        to_x = cx + random.uniform(0, cw)
        to_y = cy + random.uniform(0, ch)
        if move_from_viewport:
            vp = await page.evaluate("() => ({ w: window.innerWidth, h: window.innerHeight })")
            vw = vp.get("w") or 800
            vh = vp.get("h") or 600
            from_x = random.uniform(0, max(1, vw))
            from_y = random.uniform(0, max(1, vh))
        else:
            from_x = x + w * (0.3 + random.random() * 0.4)
            from_y = y + h * (0.3 + random.random() * 0.4)
        await HumanBehavior.mouse_move(page, from_x, from_y, to_x, to_y, steps=random.randint(18, 35))
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.03, 0.12))
        await page.mouse.up()
        logger.debug("click_in_bounds: 在元素内随机点点击完成")

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
            delay_before = random.randint(100, 500)
        await asyncio.sleep(delay_before / 1000)
        
        # 点击
        await page.click(selector)
        logger.debug(f"点击元素: {selector}")
        
        # 点击后延迟
        if delay_after is None:
            delay_after = random.randint(200, 800)
        await asyncio.sleep(delay_after / 1000)
    
    @staticmethod
    async def read_page(page: Page, duration: Optional[float] = None) -> None:
        """模拟阅读页面
        
        Args:
            page: Playwright Page对象
            duration: 阅读时长(秒),None则随机
        """
        if duration is None:
            duration = random.uniform(2, 8)
        
        logger.debug(f"模拟阅读页面: {duration:.1f}秒")
        
        # 在阅读期间随机滚动
        elapsed = 0
        while elapsed < duration:
            # 随机决定是否滚动
            if random.random() < 0.3:
                await HumanBehavior.scroll(page, direction='down', smooth=True)
                elapsed += random.uniform(2, 4)
            else:
                # 停留不动
                await asyncio.sleep(random.uniform(1, 2))
                elapsed += random.uniform(1, 2)
    
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
            duration = random.uniform(0.5, 2)
        
        await page.hover(selector)
        logger.debug(f"悬停在元素: {selector}, {duration:.1f}秒")
        await asyncio.sleep(duration)
