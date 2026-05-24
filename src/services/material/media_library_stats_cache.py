"""
媒体库统计缓存（全局复用）

用途：
- 多个页面/组件需要显示“媒体库总数/已占用/未占用”时，统一读缓存并订阅更新信号；
- 避免各处重复扫描磁盘、重复查库。
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.services.material.media_library_stats_types import MediaCounts, MediaKindStats, MediaLibraryStats

_PERSISTENT_TTL_SECONDS = 24 * 60 * 60.0


class MediaLibraryStatsCache(QObject):
    """全局媒体库统计缓存（单例）。"""

    # payload: MediaLibraryStats
    # 用 object（PyObject）避免 Shiboken 尝试拷贝/转换 dataclass 导致报错
    statsUpdated = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._stats: Optional[MediaLibraryStats] = None

    def set_stats(self, stats: MediaLibraryStats) -> None:
        self.set_complete_snapshot(stats)

    def set_complete_snapshot(self, stats: MediaLibraryStats) -> None:
        if not isinstance(stats, MediaLibraryStats):
            return
        self._stats = stats
        self._write_persistent(stats)
        self.statsUpdated.emit(stats)

    def get(self) -> Optional[MediaLibraryStats]:
        return self.get_memory()

    def get_memory(self) -> Optional[MediaLibraryStats]:
        return self._stats

    def get_persistent(self, *, allow_stale: bool = True) -> Optional[MediaLibraryStats]:
        path = self._persistent_path()
        if path is None or not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            saved_at = float(raw.get("saved_at") or 0.0)
            if not allow_stale and (
                saved_at <= 0 or (time.time() - saved_at) > _PERSISTENT_TTL_SECONDS
            ):
                return None
            stats = _stats_from_dict(raw.get("stats") or {})
            self._stats = stats
            return stats
        except Exception:
            return None

    def clear(self) -> None:
        self.invalidate_memory_only()

    def invalidate_memory_only(self) -> None:
        self._stats = None

    def invalidate_persistent(self) -> None:
        path = self._persistent_path()
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except Exception:
            return

    def _persistent_path(self) -> Optional[Path]:
        try:
            from src.infrastructure.common.path_manager import PathManager

            return PathManager.get_cache_dir() / "workspace" / "media_library_stats.json"
        except Exception:
            return None

    def _write_persistent(self, stats: MediaLibraryStats) -> None:
        path = self._persistent_path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "saved_at": time.time(),
                "stats": asdict(stats),
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except Exception:
            return


def _counts_from_dict(data) -> MediaCounts:
    if not isinstance(data, dict):
        return MediaCounts()
    return MediaCounts(
        total=int(data.get("total") or 0),
        used=int(data.get("used") or 0),
        unused=int(data.get("unused") or 0),
    )


def _counts_map_from_dict(data, *, int_keys: bool = False):
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, value in data.items():
        try:
            out[int(key) if int_keys else str(key)] = _counts_from_dict(value)
        except Exception:
            continue
    return out


def _kind_from_dict(data) -> MediaKindStats:
    if not isinstance(data, dict):
        return MediaKindStats()
    return MediaKindStats(
        counts=_counts_from_dict(data.get("counts")),
        by_owner=_counts_map_from_dict(data.get("by_owner")),
        by_account_id=_counts_map_from_dict(data.get("by_account_id"), int_keys=True),
        by_group_id=_counts_map_from_dict(data.get("by_group_id"), int_keys=True),
    )


def _stats_from_dict(data) -> MediaLibraryStats:
    if not isinstance(data, dict):
        return MediaLibraryStats()
    return MediaLibraryStats(
        video=_kind_from_dict(data.get("video")),
        image=_kind_from_dict(data.get("image")),
        all_media=_counts_from_dict(data.get("all_media")),
        error=str(data.get("error") or ""),
    )


_INSTANCE: Optional[MediaLibraryStatsCache] = None


def get_media_library_stats_cache() -> MediaLibraryStatsCache:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MediaLibraryStatsCache()
    return _INSTANCE

