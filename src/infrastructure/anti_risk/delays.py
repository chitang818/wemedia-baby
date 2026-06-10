"""
发布层防风控：延迟与节流
文件路径：src/infrastructure/anti_risk/delays.py
供各平台发布步骤调用，与 speed_rate、平台配置配合，降低固定节奏带来的风控风险。
"""

import logging
from typing import Dict, Any, Optional

from src.infrastructure.browser.automation_api import Page

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


def _speed_rate(metadata: Optional[Dict[str, Any]]) -> float:
    return max(0.1, float(metadata.get("speed_rate", 1.0) if metadata else 1.0))


def _jitter_ratio(config: Optional[Dict[str, Any]]) -> float:
    """Legacy compatibility: runtime jitter is disabled."""
    return 0.0


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
    ms = max(0, int(base_ms * rate))
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
    if config:
        base_s = max(0, float(config.get("step_interval_base_seconds", base_s)))
    rate = _speed_rate(metadata)
    total_s = base_s * rate
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
    if config:
        min_s = max(0, float(config.get("operation_delay_min_seconds", min_s)))
    rate = _speed_rate(metadata)
    total_s = min_s * rate
    ms = max(0, int(total_s * 1000))
    if ms > 0:
        await page.wait_for_timeout(ms)


async def cooldown_before_retry(
    seconds: float,
    reason: str = "操作频繁",
) -> None:
    """Compatibility no-op: risk/frequency prompts now stop the account immediately."""
    sec = max(0.0, seconds)
    if sec <= 0:
        return
    logger.info("检测到%s，已取消冷却重试并交由发布队列停止该账号", reason)
    try:
        USER_LOG.warning(f"检测到{reason}，已停止重试，请人工检查账号状态")
    except Exception:
        pass


async def cognitive_pause(
    page: Page,
    metadata: Optional[Dict[str, Any]] = None,
    probability: float = 0.15,
) -> None:
    """Compatibility no-op: synthetic cognitive pauses are disabled."""
    return None
