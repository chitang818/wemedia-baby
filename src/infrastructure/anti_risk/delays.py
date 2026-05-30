"""
发布层防风控：延迟与节流
文件路径：src/infrastructure/anti_risk/delays.py
供各平台发布步骤调用，与 speed_rate、平台配置配合，降低固定节奏带来的风控风险。
"""

import random
import asyncio
import logging
from typing import Dict, Any, Optional

from playwright.async_api import Page

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


def _speed_rate(metadata: Optional[Dict[str, Any]]) -> float:
    return max(0.1, float(metadata.get("speed_rate", 1.0) if metadata else 1.0))


def _jitter_ratio(config: Optional[Dict[str, Any]]) -> float:
    """随机抖动范围，如 0.2 表示 ±20%。"""
    if not config or "delay_jitter_ratio" not in config:
        return 0.2
    return max(0, min(0.5, float(config.get("delay_jitter_ratio", 0.2))))


async def random_delay(
    page: Page,
    base_ms: int,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """带 speed_rate 与随机抖动的延迟，避免固定节奏。

    Args:
        page: Playwright Page，用于 wait_for_timeout
        base_ms: 基准毫秒数
        metadata: 发布元数据，含 speed_rate
        config: 可选平台风控配置，含 delay_jitter_ratio
    """
    rate = _speed_rate(metadata)
    jitter = _jitter_ratio(config)
    # 最终 = base * rate * (1 ± jitter)
    mult = 1.0 + random.uniform(-jitter, jitter)
    ms = max(0, int(base_ms * rate * mult))
    if ms > 0:
        await page.wait_for_timeout(ms)


async def step_interval(
    page: Page,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """步骤间最小间隔（基准 + 随机），步骤结束后调用。

    config 可含 step_interval_base_seconds / step_interval_jitter_seconds。
    """
    base_s = 0.5
    jitter_s = 2.5
    if config:
        base_s = max(0, float(config.get("step_interval_base_seconds", base_s)))
        jitter_s = max(0, float(config.get("step_interval_jitter_seconds", jitter_s)))
    rate = _speed_rate(metadata)
    total_s = (base_s + random.uniform(0, jitter_s)) * rate
    ms = int(total_s * 1000)
    if ms > 0:
        await page.wait_for_timeout(ms)


async def operation_delay(
    page: Page,
    metadata: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """单次操作前/后的随机延迟（如点击、输入、滚动前），默认 0.5-3 秒，避免固定间隔。

    config 可含 operation_delay_min_seconds、operation_delay_max_seconds（默认 0.5、3.0）。
    会受 speed_rate 与 delay_jitter_ratio 影响。
    """
    min_s = 0.5
    max_s = 3.0
    if config:
        min_s = max(0, float(config.get("operation_delay_min_seconds", min_s)))
        max_s = max(min_s, float(config.get("operation_delay_max_seconds", max_s)))
    rate = _speed_rate(metadata)
    jitter = _jitter_ratio(config)
    base_s = random.uniform(min_s, max_s)
    mult = 1.0 + random.uniform(-jitter, jitter)
    total_s = base_s * rate * mult
    ms = max(0, int(total_s * 1000))
    if ms > 0:
        await page.wait_for_timeout(ms)


async def cooldown_before_retry(
    seconds: float,
    reason: str = "操作频繁",
) -> None:
    """检测到「操作频繁」等后的冷却等待，重试提交前调用。

    Args:
        seconds: 冷却秒数（建议由平台配置传入，如 180）
        reason: 日志原因描述
    """
    sec = max(0, float(seconds))
    if sec <= 0:
        return
    logger.info("防风控冷却: %s，等待 %.0f 秒后重试", reason, sec)
    try:
        USER_LOG.info(f"防风控冷却: {reason}，{sec:.0f} 秒后重试")
    except Exception:
        pass
    await asyncio.sleep(sec)


async def cognitive_pause(
    page: Page,
    metadata: Optional[Dict[str, Any]] = None,
    probability: float = 0.15,
) -> None:
    """高层认知暂停机制（模拟用户由于某些原因分心、发呆或离开一小会）。
    
    Args:
        page: Playwright Page 对象
        metadata: 任务元数据
        probability: 触发的长暂停概率，默认 15%
    """
    if random.random() >= probability:
        return
        
    # 分布：70% 概率在 20-50 秒，30% 概率在 50-120 秒
    if random.random() < 0.7:
        pause_s = random.uniform(20, 50)
    else:
        pause_s = random.uniform(50, 120)
        
    logger.info("触发认知暂停 (CognitivePause)，等待 %.0f 秒以模拟用户分心行为", pause_s)
    try:
        USER_LOG.info(f"▶ 触发认知暂停（模拟用户分心），将等待 {pause_s:.0f} 秒")
    except Exception:
        pass
        
    elapsed = 0.0
    while elapsed < pause_s:
        # 在长暂停中维持极少的互动，防止判定挂机
        if random.random() < 0.2:
            try:
                from src.infrastructure.browser.human_behavior import HumanBehavior
                await HumanBehavior.scroll(page, direction='down', smooth=True)
                await asyncio.sleep(random.uniform(1.0, 3.0))
                await HumanBehavior.scroll(page, direction='up', smooth=True)
            except Exception:
                pass
                
        chunk = random.uniform(2.0, 5.0)
        await asyncio.sleep(chunk)
        elapsed += chunk
