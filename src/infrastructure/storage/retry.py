"""
数据库操作重试装饰器
功能：为数据库操作提供 SQLite 锁冲突自动重试能力（指数退避策略）
"""

import asyncio
import functools
import logging
from typing import TypeVar, Callable, Any

logger = logging.getLogger(__name__)

# 默认重试配置（配合 busy_timeout=10s 使用）
DEFAULT_MAX_RETRIES = 5  # 最大重试次数
DEFAULT_BASE_DELAY = 0.15  # 初始延迟（秒）
DEFAULT_MAX_DELAY = 3.0  # 最大延迟（秒）

T = TypeVar("T")


def retry_on_locked(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> Callable:
    """SQLite 锁冲突自动重试装饰器（指数退避策略）

    当 SQLite 数据库发生 'database is locked' 错误时，自动进行重试。
    每次重试的等待时间按指数递增（base_delay * 2^attempt），但不超过 max_delay。

    适用场景：
        - Repository 层的写入操作
        - 事务操作
        - 任何可能因并发写入而触发锁冲突的异步数据库方法

    Args:
        max_retries: 最大重试次数（默认 3 次）
        base_delay: 初始重试延迟，单位为秒（默认 0.1 秒）
        max_delay: 最大重试延迟，单位为秒（默认 2.0 秒）

    Returns:
        装饰器函数

    用法示例::

        class AccountRepository:
            @retry_on_locked(max_retries=5)
            async def update_status(self, account_id: int, status: str):
                account = await PlatformAccount.get(id=account_id)
                account.login_status = status
                await account.save()
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            delay = base_delay
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e).lower()

                    # 判断是否为 SQLite 锁冲突错误
                    if "locked" in error_msg or "database is locked" in error_msg:
                        last_error = e
                        if attempt < max_retries:
                            actual_delay = min(delay, max_delay)
                            logger.debug(
                                f"数据库锁冲突，正在重试 "
                                f"({attempt + 1}/{max_retries})，"
                                f"延迟 {actual_delay:.2f} 秒"
                            )
                            await asyncio.sleep(actual_delay)
                            delay *= 2  # 指数退避
                            continue
                        else:
                            logger.error(
                                f"数据库操作失败（已重试 {max_retries} 次）: "
                                f"{func.__name__} - {e}"
                            )
                            raise
                    else:
                        # 非锁冲突错误，直接抛出
                        raise

            # 理论上不会走到这里，但作为安全兜底
            if last_error:
                raise last_error

        return wrapper

    return decorator
