"""
AsyncHttpClient 集成测试
使用 aioresponses mock HTTP 响应，测试请求发送、重试和会话管理。
需要安装 aioresponses：pip install aioresponses
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

try:
    from aioresponses import aioresponses as mock_aiohttp
    AIORESPONSES_AVAILABLE = True
except ImportError:
    AIORESPONSES_AVAILABLE = False

skip_no_aioresponses = pytest.mark.skipif(
    not AIORESPONSES_AVAILABLE,
    reason="aioresponses 未安装，跳过 HTTP 客户端集成测试",
)

from src.infrastructure.network.http_client import AsyncHttpClient


class TestAsyncHttpClientInit:

    def test_default_timeout(self):
        client = AsyncHttpClient()
        assert client.timeout is not None

    def test_custom_timeout(self):
        client = AsyncHttpClient(timeout=60)
        assert client.timeout.total == 60

    def test_max_retries(self):
        client = AsyncHttpClient(max_retries=5)
        assert client.max_retries == 5

    def test_base_url(self):
        client = AsyncHttpClient(base_url="https://example.com")
        assert client.base_url == "https://example.com"

    def test_session_initially_none(self):
        client = AsyncHttpClient()
        assert client._session is None


class TestAsyncHttpClientSession:

    async def test_get_session_creates_session(self):
        client = AsyncHttpClient()
        try:
            session = await client._get_session()
            assert session is not None
            assert not session.closed
        finally:
            await client.close()

    async def test_get_session_returns_same_instance(self):
        client = AsyncHttpClient()
        try:
            s1 = await client._get_session()
            s2 = await client._get_session()
            assert s1 is s2
        finally:
            await client.close()

    async def test_close_closes_session(self):
        client = AsyncHttpClient()
        await client._get_session()
        await client.close()
        assert client._session is None or client._session.closed


@skip_no_aioresponses
class TestAsyncHttpClientGet:

    async def test_get_success(self):
        client = AsyncHttpClient()
        try:
            with mock_aiohttp() as m:
                m.get("https://example.com/api/test", payload={"status": "ok"})
                result = await client.get("https://example.com/api/test")
                assert result is not None
        finally:
            await client.close()

    async def test_get_with_params(self):
        client = AsyncHttpClient()
        try:
            with mock_aiohttp() as m:
                m.get("https://example.com/api?key=value", payload={"data": "test"})
                result = await client.get(
                    "https://example.com/api",
                    params={"key": "value"}
                )
                assert result is not None
        finally:
            await client.close()
