"""
工作台仪表盘快照缓存（首屏秒开 + 静默刷新）
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .dashboard_snapshot import DashboardSnapshot

_DEFAULT_TTL_SECONDS = 45.0
_DEFAULT_PERSISTENT_TTL_SECONDS = 24 * 60 * 60.0


class DashboardStatsCache:
    """工作台快照缓存：进程内用于切页秒开，磁盘快照用于冷启动首屏。"""

    def __init__(
        self,
        ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        persistent_ttl_seconds: float = _DEFAULT_PERSISTENT_TTL_SECONDS,
    ) -> None:
        self._ttl = float(ttl_seconds)
        self._persistent_ttl = float(persistent_ttl_seconds)
        self._snapshot: Optional[DashboardSnapshot] = None
        self._user_id: Optional[int] = None
        self._cached_at: float = 0.0

    def get(self, user_id: Optional[int] = None) -> Optional[DashboardSnapshot]:
        return self.get_memory(user_id)

    def get_memory(self, user_id: Optional[int] = None) -> Optional[DashboardSnapshot]:
        if self._snapshot is None:
            return None
        if user_id is not None and self._user_id is not None and user_id != self._user_id:
            return None
        age = time.monotonic() - self._cached_at
        if age > self._ttl:
            return None
        return self._snapshot

    def set(self, snapshot: DashboardSnapshot, user_id: Optional[int] = None) -> None:
        self.set_complete_snapshot(snapshot, user_id=user_id)

    def set_complete_snapshot(
        self,
        snapshot: DashboardSnapshot,
        user_id: Optional[int] = None,
    ) -> None:
        if not isinstance(snapshot, DashboardSnapshot):
            return
        self._snapshot = snapshot
        self._cached_at = time.monotonic()
        if user_id is not None:
            self._user_id = int(user_id)
        self._write_persistent_snapshot(snapshot, user_id=user_id)

    def invalidate(self) -> None:
        self.invalidate_memory_only()

    def invalidate_memory_only(self) -> None:
        self._snapshot = None
        self._cached_at = 0.0

    def invalidate_persistent(self, user_id: Optional[int] = None) -> None:
        path = self._persistent_path(user_id)
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except Exception:
            return

    def get_persistent(
        self,
        user_id: Optional[int] = None,
        *,
        allow_stale: bool = True,
    ) -> Optional[DashboardSnapshot]:
        path = self._persistent_path(user_id)
        if path is None or not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            if user_id is not None and raw.get("user_id") not in (None, int(user_id)):
                return None
            saved_at = float(raw.get("saved_at") or 0.0)
            if not allow_stale and (
                saved_at <= 0 or (time.time() - saved_at) > self._persistent_ttl
            ):
                return None
            snapshot = DashboardSnapshot.from_cache_dict(raw.get("snapshot") or {})
            if snapshot.partial:
                return None
            self._snapshot = snapshot
            self._cached_at = time.monotonic()
            if user_id is not None:
                self._user_id = int(user_id)
            return snapshot
        except Exception:
            return None

    def _persistent_path(self, user_id: Optional[int]) -> Optional[Path]:
        try:
            from src.infrastructure.common.path_manager import PathManager

            cache_dir = PathManager.get_cache_dir() / "workspace"
            suffix = int(user_id) if user_id is not None else "default"
            return cache_dir / f"dashboard_snapshot_{suffix}.json"
        except Exception:
            return None

    def _write_persistent_snapshot(
        self,
        snapshot: DashboardSnapshot,
        *,
        user_id: Optional[int] = None,
    ) -> None:
        if snapshot.partial:
            return
        path = self._persistent_path(user_id)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "user_id": int(user_id) if user_id is not None else None,
                "saved_at": time.time(),
                "snapshot": snapshot.to_cache_dict(),
            }
            path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        except Exception:
            return


_INSTANCE: Optional[DashboardStatsCache] = None


def get_dashboard_stats_cache() -> DashboardStatsCache:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = DashboardStatsCache()
    return _INSTANCE
