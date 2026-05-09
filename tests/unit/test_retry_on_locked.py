"""
数据库重试装饰器单元测试
模块：src/infrastructure/storage/retry.py
"""
import pytest
from unittest.mock import AsyncMock, patch
from src.infrastructure.storage.retry import retry_on_locked


class TestRetryOnLocked:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        call_count = 0

        @retry_on_locked(max_retries=3)
        async def ok():
            nonlocal call_count
            call_count += 1
            return "done"

        result = await ok()
        assert result == "done"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_locked_error(self):
        call_count = 0

        @retry_on_locked(max_retries=3, base_delay=0.001)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("database is locked")
            return "ok"

        result = await flaky()
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        @retry_on_locked(max_retries=2, base_delay=0.001)
        async def always_locked():
            raise Exception("database is locked")

        with pytest.raises(Exception, match="locked"):
            await always_locked()

    @pytest.mark.asyncio
    async def test_non_locked_error_not_retried(self):
        call_count = 0

        @retry_on_locked(max_retries=3, base_delay=0.001)
        async def other_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("some other error")

        with pytest.raises(ValueError):
            await other_error()

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_increases_delay(self):
        """验证延迟按指数增长，不超过 max_delay。"""
        delays = []

        original_sleep = __import__("asyncio").sleep

        async def mock_sleep(s):
            delays.append(s)

        @retry_on_locked(max_retries=3, base_delay=0.1, max_delay=0.5)
        async def always_locked():
            raise Exception("database is locked")

        with patch("asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(Exception):
                await always_locked()

        assert len(delays) == 3
        assert delays[0] == 0.1
        assert delays[1] == 0.2
        assert delays[2] <= 0.5
