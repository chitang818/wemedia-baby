"""
工作台仪表盘快照缓存（首屏秒开 + 静默刷新）
"""

from __future__ import annotations

import time
from typing import Optional

from .dashboard_snapshot import DashboardSnapshot

_DEFAULT_TTL_SECONDS = 45.0


class DashboardStatsCache:
    """进程内工作台快照缓存。"""

    def __init__(self, ttl_seconds: float = _DEFAULT_TTL_SECONDS) -> None:
        self._ttl = float(ttl_seconds)
        self._snapshot: Optional[DashboardSnapshot] = None
        self._user_id: Optional[int] = None
        self._cached_at: float = 0.0

    def get(self, user_id: Optional[int] = None) -> Optional[DashboardSnapshot]:
        if self._snapshot is None:
            return None
        if user_id is not None and self._user_id is not None and user_id != self._user_id:
            return None
        age = time.monotonic() - self._cached_at
        if age > self._ttl:
            return None
        return self._snapshot

    def set(self, snapshot: DashboardSnapshot, user_id: Optional[int] = None) -> None:
        if not isinstance(snapshot, DashboardSnapshot):
            return
        self._snapshot = snapshot
        self._cached_at = time.monotonic()
        if user_id is not None:
            self._user_id = int(user_id)

    def invalidate(self) -> None:
        self._snapshot = None
        self._cached_at = 0.0


_INSTANCE: Optional[DashboardStatsCache] = None


def get_dashboard_stats_cache() -> DashboardStatsCache:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = DashboardStatsCache()
    return _INSTANCE
