"""
发布管线过滤器单元测试
覆盖：PermissionCheckFilterAsync 的缓存逻辑、限流、降级放行
"""
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.publish.pipeline.filters.permission_check_filter_async import (
    _get_cached_publish_check,
    _set_publish_check_cache,
    _PUBLISH_CHECK_CACHE,
    _CACHE_MAX_SIZE,
    _maybe_cleanup_cache,
    _evict_oldest_if_full,
    PermissionCheckFilterAsync,
)


@pytest.fixture(autouse=True)
def clear_cache():
    """每个测试前清空缓存。"""
    _PUBLISH_CHECK_CACHE.clear()
    yield
    _PUBLISH_CHECK_CACHE.clear()


class TestPublishCheckCache:
    """publish_check 缓存逻辑测试"""

    def test_cache_miss_returns_none(self):
        assert _get_cached_publish_check("tok", "douyin", False) is None

    def test_cache_hit_returns_true(self):
        _set_publish_check_cache("tok", "douyin", False, True)
        assert _get_cached_publish_check("tok", "douyin", False) is True

    def test_denied_result_not_cached(self):
        _set_publish_check_cache("tok", "douyin", False, False)
        assert _get_cached_publish_check("tok", "douyin", False) is None

    def test_expired_entry_evicted(self):
        key = ("tok", "douyin", False)
        _PUBLISH_CHECK_CACHE[key] = (True, time.monotonic() - 10)
        assert _get_cached_publish_check("tok", "douyin", False) is None
        assert key not in _PUBLISH_CHECK_CACHE

    def test_max_size_eviction(self):
        for i in range(_CACHE_MAX_SIZE + 10):
            _set_publish_check_cache(f"tok{i}", "p", False, True)
        assert len(_PUBLISH_CHECK_CACHE) <= _CACHE_MAX_SIZE


class TestPermissionCheckFilterAsync:
    """PermissionCheckFilterAsync 过滤器测试"""

    @pytest.mark.asyncio
    async def test_subscription_disabled_passes(self):
        """订阅功能未启用时应放行。"""
        f = PermissionCheckFilterAsync(permission_controller=None)
        ctx = MagicMock()
        with patch("src.services.publish.pipeline.filters.permission_check_filter_async.FeatureFlags") as MockFF:
            MockFF.is_feature_enabled.return_value = False
            # 需要 mock 掉 import
            with patch.dict("sys.modules", {"config.feature_flags": MagicMock(FeatureFlags=MockFF)}):
                result = await f.process(ctx)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_permission_controller_passes(self):
        """无权限控制器时应放行（开源版场景）。"""
        f = PermissionCheckFilterAsync(permission_controller=None)
        ctx = MagicMock()
        # FeatureFlags 启用但控制器为 None
        mock_ff = MagicMock()
        mock_ff.is_feature_enabled.return_value = True
        with patch.dict("sys.modules", {"config.feature_flags": MagicMock(FeatureFlags=mock_ff)}):
            result = await f.process(ctx)
        assert result is True
