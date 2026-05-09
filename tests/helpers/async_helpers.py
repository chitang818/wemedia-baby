"""
异步测试辅助工具
提供异步上下文管理器、超时控制等工具函数。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Any


async def run_with_timeout(coro, timeout: float = 5.0):
    """以超时方式运行协程，超时抛 asyncio.TimeoutError"""
    return await asyncio.wait_for(coro, timeout=timeout)


@asynccontextmanager
async def assert_completes_within(seconds: float) -> AsyncGenerator[None, None]:
    """上下文管理器：断言代码块在指定秒数内完成"""
    task_holder: list = []

    async def _runner():
        yield

    start = asyncio.get_event_loop().time()
    yield
    elapsed = asyncio.get_event_loop().time() - start
    if elapsed > seconds:
        raise AssertionError(
            f"代码块耗时 {elapsed:.2f}s，超过限制 {seconds}s"
        )


def make_async_mock_callable(return_value: Any = None) -> Callable:
    """创建一个异步 mock callable，直接返回指定值"""
    async def _mock(*args, **kwargs):
        return return_value
    return _mock
