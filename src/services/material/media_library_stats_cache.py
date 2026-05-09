"""
媒体库统计缓存（全局复用）

用途：
- 多个页面/组件需要显示“媒体库总数/已占用/未占用”时，统一读缓存并订阅更新信号；
- 避免各处重复扫描磁盘、重复查库。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.services.material.media_library_stats_types import MediaLibraryStats


class MediaLibraryStatsCache(QObject):
    """全局媒体库统计缓存（单例）。"""

    # payload: MediaLibraryStats
    # 用 object（PyObject）避免 Shiboken 尝试拷贝/转换 dataclass 导致报错
    statsUpdated = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._stats: Optional[MediaLibraryStats] = None

    def set_stats(self, stats: MediaLibraryStats) -> None:
        if not isinstance(stats, MediaLibraryStats):
            return
        self._stats = stats
        self.statsUpdated.emit(stats)

    def get(self) -> Optional[MediaLibraryStats]:
        return self._stats

    def clear(self) -> None:
        self._stats = None


_INSTANCE: Optional[MediaLibraryStatsCache] = None


def get_media_library_stats_cache() -> MediaLibraryStatsCache:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MediaLibraryStatsCache()
    return _INSTANCE

