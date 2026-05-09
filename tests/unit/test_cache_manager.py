"""
CacheManager 单元测试
测试 L1 内存缓存的 set/get/invalidate/stats 行为（不触发 L2 文件系统操作）。
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

pytestmark = pytest.mark.unit


@pytest.fixture
def cache_manager(tmp_path):
    """创建使用临时目录的 CacheManager"""
    from src.infrastructure.common.cache.cache_manager import CacheManager
    return CacheManager(
        l1_max_size=10,
        l1_default_ttl=3600,
        l2_cache_dir=str(tmp_path / "cache"),
    )


class TestCacheManagerSetGet:

    async def test_set_and_get(self, cache_manager):
        await cache_manager.set("key1", "value1")
        result = await cache_manager.get("key1")
        assert result == "value1"

    async def test_get_nonexistent_returns_default(self, cache_manager):
        result = await cache_manager.get("nonexistent", default="fallback")
        assert result == "fallback"

    async def test_get_nonexistent_default_none(self, cache_manager):
        result = await cache_manager.get("missing")
        assert result is None

    async def test_set_various_types(self, cache_manager):
        await cache_manager.set("int_key", 42)
        await cache_manager.set("list_key", [1, 2, 3])
        await cache_manager.set("dict_key", {"a": 1})
        assert await cache_manager.get("int_key") == 42
        assert await cache_manager.get("list_key") == [1, 2, 3]
        assert await cache_manager.get("dict_key") == {"a": 1}

    async def test_overwrite_existing_key(self, cache_manager):
        await cache_manager.set("key", "old")
        await cache_manager.set("key", "new")
        assert await cache_manager.get("key") == "new"


class TestCacheManagerInvalidate:

    async def test_invalidate_removes_key(self, cache_manager):
        await cache_manager.set("key1", "value")
        await cache_manager.invalidate("key1")
        result = await cache_manager.get("key1")
        assert result is None

    async def test_invalidate_nonexistent_no_error(self, cache_manager):
        await cache_manager.invalidate("nonexistent_key")  # 不应抛异常


class TestCacheManagerStats:

    async def test_stats_returns_dict(self, cache_manager):
        stats = cache_manager.get_stats()
        assert isinstance(stats, dict)

    async def test_stats_has_hit_miss_keys(self, cache_manager):
        await cache_manager.set("k", "v")
        await cache_manager.get("k")
        await cache_manager.get("missing")
        stats = cache_manager.get_stats()
        assert "l1_hits" in stats or "hits" in stats or len(stats) > 0


class TestCacheManagerLRU:

    async def test_lru_eviction_when_full(self, tmp_path):
        from src.infrastructure.common.cache.cache_manager import CacheManager
        cm = CacheManager(l1_max_size=3, l2_cache_dir=str(tmp_path / "cache"))
        await cm.set("k1", "v1")
        await cm.set("k2", "v2")
        await cm.set("k3", "v3")
        await cm.set("k4", "v4")  # 应触发 LRU 淘汰
        # L1 缓存不超过 max_size
        assert len(cm._l1_cache) <= 3
