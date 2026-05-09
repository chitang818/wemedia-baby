"""
通用装饰器单元测试
模块：src/infrastructure/common/decorators.py
"""
import pytest
import asyncio
from src.infrastructure.common.decorators import safe_execute


class TestSafeExecute:
    """safe_execute 装饰器：捕获异常并返回默认值"""

    def test_sync_success(self):
        @safe_execute(error_return=-1)
        def ok():
            return 42

        assert ok() == 42

    def test_sync_exception_returns_default(self):
        @safe_execute(error_return=-1, log_error=False)
        def fail():
            raise ValueError("oops")

        assert fail() == -1

    def test_sync_default_return_is_none(self):
        @safe_execute(log_error=False)
        def fail():
            raise RuntimeError("boom")

        assert fail() is None

    @pytest.mark.asyncio
    async def test_async_success(self):
        @safe_execute(error_return="fallback")
        async def ok():
            return "result"

        assert await ok() == "result"

    @pytest.mark.asyncio
    async def test_async_exception_returns_default(self):
        @safe_execute(error_return="fallback", log_error=False)
        async def fail():
            raise ValueError("async oops")

        assert await fail() == "fallback"

    def test_preserves_function_name(self):
        @safe_execute()
        def my_function():
            pass

        assert my_function.__name__ == "my_function"
