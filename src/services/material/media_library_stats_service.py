"""
媒体库素材统计服务（统一入口）

统计口径（与你确认的一致）：
- “已使用”按待发布任务引用判定：pending/failed/running（见 media_usage_service）。
- 统计范围：全局汇总 + 按 owner_label（账号/账号组/未分配）分组汇总。
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple, List

from src.infrastructure.common.material_library_manager import MaterialLibraryManager
from src.infrastructure.common.media_library_assign import (
    scan_image_library_entries,
    scan_video_library_entries,
)
from src.services.material.media_library_stats_cache import get_media_library_stats_cache
from src.services.material.media_library_stats_types import (
    MediaCounts,
    MediaKindStats,
    MediaLibraryStats,
)
from src.services.material.media_usage_service import (
    PendingMediaUsage,
    get_pending_media_usage,
    is_image_folder_used,
    is_video_used,
)


def _safe_owner(owner_label: str) -> str:
    s = str(owner_label or "").strip()
    return s or "未分配"


def _counts(total: int, used: int) -> MediaCounts:
    t = max(0, int(total or 0))
    u = max(0, int(used or 0))
    if u > t:
        u = t
    return MediaCounts(total=t, used=u, unused=t - u)


def _aggregate_kind(
    *,
    owners: Iterable[str],
    used_flags: Iterable[bool],
) -> Tuple[MediaCounts, Dict[str, MediaCounts]]:
    total = 0
    used = 0
    per_owner_total: Dict[str, int] = {}
    per_owner_used: Dict[str, int] = {}

    for owner, is_used in zip(owners, used_flags):
        o = _safe_owner(owner)
        total += 1
        per_owner_total[o] = per_owner_total.get(o, 0) + 1
        if is_used:
            used += 1
            per_owner_used[o] = per_owner_used.get(o, 0) + 1

    by_owner: Dict[str, MediaCounts] = {}
    for o, t in per_owner_total.items():
        u = per_owner_used.get(o, 0)
        by_owner[o] = _counts(t, u)

    return _counts(total, used), by_owner


def build_media_library_stats(
    *,
    video_owner_labels: Iterable[str],
    video_paths: Iterable[Path],
    image_owner_labels: Iterable[str],
    image_folder_paths: Iterable[Path],
    usage: PendingMediaUsage,
) -> MediaLibraryStats:
    """纯聚合函数：方便单元测试（不触碰磁盘、不查数据库）。"""

    v_owners = list(video_owner_labels or [])
    v_paths = list(video_paths or [])
    i_owners = list(image_owner_labels or [])
    i_paths = list(image_folder_paths or [])

    # 防御：长度不一致时按最短长度对齐
    v_n = min(len(v_owners), len(v_paths))
    i_n = min(len(i_owners), len(i_paths))
    v_owners = v_owners[:v_n]
    v_paths = v_paths[:v_n]
    i_owners = i_owners[:i_n]
    i_paths = i_paths[:i_n]

    v_used_flags = [bool(is_video_used(usage, p)) for p in v_paths]
    i_used_flags = [bool(is_image_folder_used(usage, p)) for p in i_paths]

    v_counts, v_by_owner = _aggregate_kind(owners=v_owners, used_flags=v_used_flags)
    i_counts, i_by_owner = _aggregate_kind(owners=i_owners, used_flags=i_used_flags)

    all_counts = _counts(v_counts.total + i_counts.total, v_counts.used + i_counts.used)

    return MediaLibraryStats(
        video=MediaKindStats(counts=v_counts, by_owner=v_by_owner),
        image=MediaKindStats(counts=i_counts, by_owner=i_by_owner),
        all_media=all_counts,
        error="",
    )


def build_account_video_stats(
    *,
    account_id_to_video_paths: Dict[int, List[Path]],
    usage: PendingMediaUsage,
) -> Dict[int, MediaCounts]:
    """纯函数：按账号汇总视频库总/已占用/未占用（方便测试）。"""
    out: Dict[int, MediaCounts] = {}
    for aid, paths in (account_id_to_video_paths or {}).items():
        try:
            aid_int = int(aid)
        except Exception:
            continue
        total = 0
        used = 0
        for p in paths or []:
            if not p:
                continue
            total += 1
            if is_video_used(usage, p):
                used += 1
        out[aid_int] = _counts(total, used)
    return out


def build_account_image_stats(
    *,
    account_id_to_image_folder_paths: Dict[int, List[Path]],
    usage: PendingMediaUsage,
) -> Dict[int, MediaCounts]:
    """纯函数：按账号汇总图文库总/已占用/未占用（以文件夹为单位，方便测试）。"""
    out: Dict[int, MediaCounts] = {}
    for aid, paths in (account_id_to_image_folder_paths or {}).items():
        try:
            aid_int = int(aid)
        except Exception:
            continue
        total = 0
        used = 0
        for p in paths or []:
            if not p:
                continue
            total += 1
            if is_image_folder_used(usage, p):
                used += 1
        out[aid_int] = _counts(total, used)
    return out


class MediaLibraryStatsService:
    """统一统计服务：计算并写入全局缓存（带并发保护与简单防抖）。"""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_done_ts = 0.0

    @staticmethod
    def _default_video_exts() -> set[str]:
        exts = set(getattr(MaterialLibraryManager, "VIDEO_PICKER_EXTENSIONS", set()) or set())
        if exts:
            return {e.lower() for e in exts}
        return {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".m4v", ".webm"}

    @staticmethod
    def _default_image_exts() -> set[str]:
        return {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

    def get_cached(self) -> Optional[MediaLibraryStats]:
        return get_media_library_stats_cache().get()

    def invalidate(self) -> None:
        # 只做轻量标记：下次 refresh 会重新计算
        self._last_done_ts = 0.0

    async def compute_stats(
        self,
        *,
        statuses: Tuple[str, ...] = ("pending", "failed", "running"),
    ) -> MediaLibraryStats:
        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            return MediaLibraryStats(error="未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。")

        video_entries, v_err = scan_video_library_entries(root, self._default_video_exts())
        image_entries, i_err = scan_image_library_entries(root, self._default_image_exts())
        if v_err or i_err:
            # 不中断：仍尽量返回可用统计（哪个为空就算 0），并把错误文案带回 UI
            err = "；".join([e for e in [v_err, i_err] if e])
        else:
            err = ""

        usage = await get_pending_media_usage(statuses=statuses)

        stats = build_media_library_stats(
            video_owner_labels=[e.owner_label for e in (video_entries or [])],
            video_paths=[e.path for e in (video_entries or [])],
            image_owner_labels=[e.owner_label for e in (image_entries or [])],
            image_folder_paths=[e.path for e in (image_entries or [])],
            usage=usage,
        )

        # ---- 按账号维度统计（视频库/图文库：总/已占用/未占用）----
        try:
            from src.domain.repositories.account_repository_async import AccountRepositoryAsync

            repo = AccountRepositoryAsync()
            accounts = await repo.find_all(user_id=None, platform=None)
        except Exception:
            accounts = []

        video_exts = self._default_video_exts()

        def _scan_video_files_in_dir(d: Optional[Path]) -> List[Path]:
            if d is None or (not d.exists()):
                return []
            out_paths: List[Path] = []
            try:
                for e in os.scandir(str(d)):
                    if not e.is_file():
                        continue
                    suf = os.path.splitext(e.name)[1].lower()
                    if suf in video_exts:
                        out_paths.append(Path(e.path))
            except OSError:
                return []
            return out_paths

        def _scan_image_folders_in_dir(d: Optional[Path]) -> List[Path]:
            if d is None or (not d.exists()):
                return []
            out_paths: List[Path] = []
            try:
                for e in os.scandir(str(d)):
                    if e.is_dir():
                        out_paths.append(Path(e.path))
            except OSError:
                return []
            return out_paths

        video_by_account: Dict[int, List[Path]] = {}
        image_by_account: Dict[int, List[Path]] = {}

        for acc in accounts or []:
            if not isinstance(acc, dict):
                continue
            try:
                aid_int = int(acc.get("id")) if acc.get("id") is not None else None
            except Exception:
                aid_int = None
            if aid_int is None:
                continue

            try:
                v_dir = MaterialLibraryManager.resolve_account_video_unpublished_dir(root, acc)
            except Exception:
                v_dir = None
            try:
                i_dir = MaterialLibraryManager.account_image_unpublished_dir(root, acc)
            except Exception:
                i_dir = None

            video_by_account[aid_int] = _scan_video_files_in_dir(v_dir if isinstance(v_dir, Path) else None)
            image_by_account[aid_int] = _scan_image_folders_in_dir(i_dir if isinstance(i_dir, Path) else None)

        video_by_account_counts = build_account_video_stats(
            account_id_to_video_paths=video_by_account,
            usage=usage,
        )
        image_by_account_counts = build_account_image_stats(
            account_id_to_image_folder_paths=image_by_account,
            usage=usage,
        )

        # ---- 按账号组维度统计（用于批量页选择账号组时展示）----
        try:
            from src.domain.repositories.account_group_repository_async import (
                AccountGroupRepositoryAsync,
            )

            group_repo = AccountGroupRepositoryAsync()
            groups = await group_repo.find_all(user_id=None)
        except Exception:
            groups = []

        video_by_group: Dict[int, List[Path]] = {}
        image_by_group: Dict[int, List[Path]] = {}
        for g in groups or []:
            if not isinstance(g, dict):
                continue
            gid = g.get("id")
            gname = (g.get("group_name") or "").strip()
            try:
                gid_int = int(gid) if gid is not None else None
            except Exception:
                gid_int = None
            if gid_int is None or not gname:
                continue
            try:
                gv_dir = MaterialLibraryManager.group_video_unpublished_dir(root, gname)
            except Exception:
                gv_dir = None
            try:
                gi_dir = MaterialLibraryManager.group_image_unpublished_dir(root, gname)
            except Exception:
                gi_dir = None
            video_by_group[gid_int] = _scan_video_files_in_dir(gv_dir if isinstance(gv_dir, Path) else None)
            image_by_group[gid_int] = _scan_image_folders_in_dir(gi_dir if isinstance(gi_dir, Path) else None)

        video_by_group_counts = build_account_video_stats(
            account_id_to_video_paths=video_by_group,
            usage=usage,
        )
        image_by_group_counts = build_account_image_stats(
            account_id_to_image_folder_paths=image_by_group,
            usage=usage,
        )

        stats = replace(
            stats,
            video=replace(
                stats.video,
                by_account_id=video_by_account_counts,
                by_group_id=video_by_group_counts,
            ),
            image=replace(
                stats.image,
                by_account_id=image_by_account_counts,
                by_group_id=image_by_group_counts,
            ),
        )
        if err:
            stats = replace(stats, error=err)
        return stats

    async def refresh(
        self,
        *,
        min_interval_seconds: float = 3.0,
        statuses: Tuple[str, ...] = ("pending", "failed", "running"),
    ) -> MediaLibraryStats:
        """计算并写入缓存。短时间内重复触发会合并（简单防抖）。"""
        async with self._lock:
            now = time.time()
            cached = get_media_library_stats_cache().get()
            if cached is not None and (now - self._last_done_ts) < float(min_interval_seconds):
                return cached

            stats = await self.compute_stats(statuses=statuses)
            get_media_library_stats_cache().set_stats(stats)
            self._last_done_ts = time.time()
            return stats


_INSTANCE: Optional[MediaLibraryStatsService] = None


def get_media_library_stats_service() -> MediaLibraryStatsService:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = MediaLibraryStatsService()
    return _INSTANCE

