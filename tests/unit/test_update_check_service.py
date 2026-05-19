"""
更新检查服务单元测试
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services import update_check_service as svc
from src.services.update_check_service import (
    ERROR_CACHE_TTL_SECONDS,
    UpdateCheckResult,
    _build_result_from_json,
    _compare_versions,
    _get_cached_result,
    check_for_updates,
    clear_update_check_cache,
    close_update_check_session,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
async def _reset_update_check_state():
    clear_update_check_cache()
    yield
    clear_update_check_cache()
    await close_update_check_session()


class TestVersionCompare:
    def test_remote_newer(self):
        assert _compare_versions("1.0.0", "1.1.0") > 0

    def test_remote_older(self):
        assert _compare_versions("2.0.0", "1.9.9") < 0

    def test_equal(self):
        assert _compare_versions("1.3.5", "1.3.5") == 0

    def test_unparseable_local_no_false_positive(self):
        assert _compare_versions("bad-ver", "2.0.0") == 0

    def test_unparseable_remote_no_false_positive(self):
        assert _compare_versions("1.0.0", "bad-ver") == 0


class TestBuildResultFromJson:
    def test_no_update(self):
        data = {
            "version": "1.3.5",
            "notes": "ok",
            "download_url": "https://example.com/releases",
        }
        with patch.object(svc, "_get_current_version", return_value="1.3.5"):
            result = _build_result_from_json(data, "1.3.5")
        assert result.has_update is False
        assert result.error is None
        assert result.remote_version == "1.3.5"

    def test_has_update(self):
        data = {"version": "2.0.0", "download_url": "https://example.com/dl"}
        result = _build_result_from_json(data, "1.0.0")
        assert result.has_update is True
        assert result.remote_version == "2.0.0"

    def test_fallback_download_url_when_missing(self):
        data = {"version": "2.0.0"}
        result = _build_result_from_json(data, "1.0.0")
        assert result.has_update is True
        assert result.download_url == svc.DEFAULT_UPDATE_DOWNLOAD_URL

    def test_invalid_version(self):
        result = _build_result_from_json({"version": ""}, "1.0.0")
        assert result.error == "版本信息无效"


class TestCheckForUpdatesCache:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_network(self):
        cached = UpdateCheckResult(
            has_update=False,
            current_version="1.3.5",
            remote_version="1.3.5",
        )
        svc._cache_result = cached
        svc._cache_time = __import__("time").monotonic()

        with patch.object(
            svc,
            "_fetch_with_inflight_dedup",
            new_callable=AsyncMock,
        ) as mock_fetch:
            result = await check_for_updates(force_refresh=False)
            mock_fetch.assert_not_called()

        assert result is cached

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_success_cache(self):
        cached = UpdateCheckResult(
            has_update=False,
            current_version="1.3.5",
            remote_version="1.3.5",
        )
        svc._cache_result = cached
        svc._cache_time = __import__("time").monotonic()

        fresh = UpdateCheckResult(
            has_update=True,
            current_version="1.3.5",
            remote_version="2.0.0",
            download_url="https://example.com",
        )
        with patch.object(
            svc,
            "_fetch_with_inflight_dedup",
            new_callable=AsyncMock,
            return_value=fresh,
        ) as mock_fetch:
            result = await check_for_updates(force_refresh=True)
            mock_fetch.assert_awaited_once()

        assert result.has_update is True

    @pytest.mark.asyncio
    async def test_network_result_is_cached(self):
        ok = UpdateCheckResult(
            has_update=False,
            current_version="1.3.5",
            remote_version="1.3.5",
        )
        with patch.object(
            svc,
            "_fetch_version_json_from_network",
            new_callable=AsyncMock,
            return_value=ok,
        ):
            await check_for_updates(force_refresh=True)

        assert _get_cached_result() is not None

    @pytest.mark.asyncio
    async def test_error_is_short_cached(self):
        err = UpdateCheckResult(
            has_update=False,
            current_version="1.3.5",
            error="网络错误，请稍后重试或检查网络",
        )
        with patch.object(
            svc,
            "_fetch_version_json_from_network",
            new_callable=AsyncMock,
            return_value=err,
        ):
            await check_for_updates(force_refresh=True)

        assert _get_cached_result() is not None
        assert _get_cached_result().error == err.error

    @pytest.mark.asyncio
    async def test_error_cache_expires(self):
        err = UpdateCheckResult(
            has_update=False,
            current_version="1.3.5",
            error="检查更新超时，请稍后重试或检查网络",
        )
        svc._cache_result = err
        svc._cache_time = __import__("time").monotonic() - ERROR_CACHE_TTL_SECONDS - 1

        assert _get_cached_result() is None

    @pytest.mark.asyncio
    async def test_concurrent_calls_single_fetch(self):
        ok = UpdateCheckResult(
            has_update=False,
            current_version="1.3.5",
            remote_version="1.3.5",
        )

        async def slow_fetch():
            await asyncio.sleep(0.05)
            svc._set_cached_result(ok)
            return ok

        with patch.object(svc, "_fetch_version_json_from_network", side_effect=slow_fetch):
            r1, r2 = await asyncio.gather(
                check_for_updates(force_refresh=True),
                check_for_updates(force_refresh=True),
            )

        assert r1.remote_version == "1.3.5"
        assert r2.remote_version == "1.3.5"


class TestFetchNetworkErrors:
    @pytest.mark.asyncio
    async def test_timeout_returns_error_message(self):
        class _TimeoutCtx:
            async def __aenter__(self):
                raise asyncio.TimeoutError()

            async def __aexit__(self, *args):
                return False

        session = MagicMock()
        session.closed = False
        session.get.return_value = _TimeoutCtx()

        with patch.object(svc, "_get_session", new_callable=AsyncMock, return_value=session):
            with patch.object(svc, "_get_current_version", return_value="1.3.5"):
                result = await svc._fetch_version_json_from_network()

        assert result.error == "检查更新超时，请稍后重试或检查网络"

    @pytest.mark.asyncio
    async def test_http_non_200(self):
        class _RespCtx:
            status = 503

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def text(self):
                return ""

        session = MagicMock()
        session.closed = False
        session.get.return_value = _RespCtx()

        with patch.object(svc, "_get_session", new_callable=AsyncMock, return_value=session):
            with patch.object(svc, "_get_current_version", return_value="1.3.5"):
                result = await svc._fetch_version_json_from_network()

        assert result.error == "请求失败: HTTP 503"

    @pytest.mark.asyncio
    async def test_json_parse_error(self):
        class _RespCtx:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def text(self):
                return "not-json"

        session = MagicMock()
        session.closed = False
        session.get.return_value = _RespCtx()

        with patch.object(svc, "_get_session", new_callable=AsyncMock, return_value=session):
            with patch.object(svc, "_get_current_version", return_value="1.3.5"):
                result = await svc._fetch_version_json_from_network()

        assert result.error == "版本信息解析失败"

    @pytest.mark.asyncio
    async def test_generic_exception_uses_friendly_message(self):
        session = MagicMock()
        session.closed = False
        session.get.side_effect = RuntimeError("boom")

        with patch.object(svc, "_get_session", new_callable=AsyncMock, return_value=session):
            with patch.object(svc, "_get_current_version", return_value="1.3.5"):
                result = await svc._fetch_version_json_from_network()

        assert result.error == "检查更新失败，请稍后重试"
