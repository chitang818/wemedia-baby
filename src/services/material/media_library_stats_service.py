"""
媒体库素材统计服务（统一入口）

统计口径（与你确认的一致）：
- “已使用”按待发布任务引用判定：pending/failed/running（见 media_usage_service）。
- 统计范围：全局汇总 + 按 owner_label（账号/账号组/未分配）分组汇总。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple, List, Callable, TypeVar

from src.infrastructure.common.path_manager import PathManager
from src.infrastructure.common.material_library_manager import MaterialLibraryManager
from src.infrastructure.common.media_library_assign import (
    ImageLibraryScanEntry,
    UNASSIGNED_OWNER_LABEL,
    VideoLibraryScanEntry,
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

logger = logging.getLogger(__name__)


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


def _dedupe_paths(paths: List[Path]) -> List[Path]:
    """同一视频/文件夹多条路径时去重（尽量 resolve，失败则退回 str）。"""
    seen: set[str] = set()
    out: List[Path] = []
    for p in paths or []:
        if not p:
            continue
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _paths_by_owner(entries: list) -> Dict[str, List[Path]]:
    out: Dict[str, List[Path]] = defaultdict(list)
    for entry in entries or []:
        owner = str(getattr(entry, "owner_label", "") or "").strip()
        path = getattr(entry, "path", None)
        if owner and path:
            out[owner].append(path)
    return dict(out)


def _candidate_account_owner_labels(entries_by_owner: Dict[str, List[Path]]) -> List[str]:
    return [
        owner
        for owner in entries_by_owner
        if owner
        and owner != UNASSIGNED_OWNER_LABEL
        and not owner.startswith("账号组-")
    ]


def _build_account_and_group_path_maps(
    *,
    root: Path,
    accounts: List[dict],
    groups: List[dict],
    video_entries: list,
    image_entries: list,
    video_exts: set[str],
) -> tuple[
    Dict[int, List[Path]],
    Dict[int, List[Path]],
    Dict[int, List[Path]],
    Dict[int, List[Path]],
]:
    """Build account/group media path maps using synchronous filesystem APIs.

    This function is intentionally free of async database access so callers can
    run it in a worker thread and keep the qasync event loop responsive.
    """
    video_paths_by_owner = _paths_by_owner(video_entries)
    image_paths_by_owner = _paths_by_owner(image_entries)
    video_account_owners = _candidate_account_owner_labels(video_paths_by_owner)
    image_account_owners = _candidate_account_owner_labels(image_paths_by_owner)

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

        v_paths: List[Path] = []
        for ol in video_account_owners:
            try:
                if MaterialLibraryManager.account_library_owner_folder_matches_account(ol, acc):
                    v_paths.extend(video_paths_by_owner.get(ol) or [])
            except Exception:
                continue
        video_by_account[aid_int] = _dedupe_paths(v_paths)

        i_paths: List[Path] = []
        for ol in image_account_owners:
            try:
                if MaterialLibraryManager.account_library_owner_folder_matches_account(ol, acc):
                    i_paths.extend(image_paths_by_owner.get(ol) or [])
            except Exception:
                continue
        image_by_account[aid_int] = _dedupe_paths(i_paths)

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
            group_folder = MaterialLibraryManager.account_group_material_folder_name(gname)
            group_owner = MaterialLibraryManager.owner_label_for_group_material_folder(group_folder)
        except Exception:
            group_owner = ""
        video_by_group[gid_int] = _dedupe_paths(video_paths_by_owner.get(group_owner) or [])
        image_by_group[gid_int] = _dedupe_paths(image_paths_by_owner.get(group_owner) or [])

    return video_by_account, image_by_account, video_by_group, image_by_group


_SCAN_CACHE_VERSION = 1
_SCAN_CACHE_MAX_AGE_SECONDS = 600.0
_SCAN_CACHE_FINGERPRINT_DEPTH = 5
_SCAN_CACHE_BUCKET_DEPTH = 3

TScanEntry = TypeVar("TScanEntry", VideoLibraryScanEntry, ImageLibraryScanEntry)


@dataclass(frozen=True)
class _ScanBucket:
    key: str
    path: Path
    owner_label: str
    required: bool = False


def _scan_cache_file_path() -> Path:
    return PathManager.get_cache_dir() / "material_library_scan_index.json"


def _scan_cache_db_path() -> Path:
    return PathManager.get_cache_dir() / "material_library_scan_index.sqlite3"


def _scan_cache_entry_to_dict(entry) -> dict:
    return {
        "path": str(entry.path),
        "owner_label": str(entry.owner_label or ""),
        "size_bytes": int(getattr(entry, "size_bytes", 0) or 0),
        "image_count": int(getattr(entry, "image_count", 0) or 0),
        "mtime": float(getattr(entry, "mtime", 0.0) or 0.0),
    }


def _path_key(path: Path) -> str:
    try:
        return os.path.normcase(os.path.abspath(str(path)))
    except Exception:
        return str(path)


def _dir_stat_fingerprint(path: Path) -> dict:
    try:
        st = path.stat()
        mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000)))
    except OSError:
        return {"path": str(path), "exists": False, "mtime_ns": 0, "child_count": 0}

    child_count = 0
    file_count = 0
    file_size = 0
    file_mtime_ns = 0
    try:
        with os.scandir(str(path)) as it:
            for entry in it:
                child_count += 1
                try:
                    if entry.is_file():
                        file_count += 1
                        est = entry.stat()
                        file_size += int(getattr(est, "st_size", 0) or 0)
                        file_mtime_ns += int(
                            getattr(est, "st_mtime_ns", int(est.st_mtime * 1_000_000_000))
                        )
                except OSError:
                    pass
    except OSError:
        child_count = 0
    return {
        "path": str(path),
        "exists": True,
        "mtime_ns": mtime_ns,
        "child_count": child_count,
        "file_count": file_count,
        "file_size": file_size,
        "file_mtime_ns": file_mtime_ns,
    }


def _walk_material_dirs_for_fingerprint(root: Path) -> List[Path]:
    """Collect material-library directories for cheap cache invalidation.

    Directory mtimes and immediate child counts catch common add/remove/move
    operations without opening every media file. Depth is bounded to keep this
    much cheaper than the full media scan.
    """
    seeds = [
        root / MaterialLibraryManager.VIDEO_FOLDER_NAME,
        root / MaterialLibraryManager.IMAGE_FOLDER_NAME,
        MaterialLibraryManager.account_library_root(root),
    ]
    out: List[Path] = []
    seen: set[str] = set()

    def add_dir(d: Path, depth: int) -> None:
        if depth > _SCAN_CACHE_FINGERPRINT_DEPTH:
            return
        try:
            key = str(d.resolve())
        except OSError:
            key = str(d)
        if key in seen:
            return
        seen.add(key)
        out.append(d)
        if not d.exists() or not d.is_dir():
            return
        try:
            with os.scandir(str(d)) as it:
                children = [Path(e.path) for e in it if e.is_dir()]
        except OSError:
            return
        for child in children:
            add_dir(child, depth + 1)

    for seed in seeds:
        add_dir(seed, 0)
    return out


def _build_scan_cache_fingerprint(root: Path) -> List[dict]:
    return [
        _dir_stat_fingerprint(path)
        for path in _walk_material_dirs_for_fingerprint(root)
    ]


def _walk_dirs_for_bucket_fingerprint(root: Path, max_depth: int) -> List[Path]:
    out: List[Path] = []
    seen: set[str] = set()

    def add_dir(d: Path, depth: int) -> None:
        if depth > max_depth:
            return
        key = _path_key(d)
        if key in seen:
            return
        seen.add(key)
        out.append(d)
        if not d.exists() or not d.is_dir():
            return
        try:
            with os.scandir(str(d)) as it:
                children = [Path(e.path) for e in it if e.is_dir()]
        except OSError:
            return
        for child in children:
            add_dir(child, depth + 1)

    add_dir(root, 0)
    return out


def _build_bucket_fingerprint(path: Path) -> List[dict]:
    return [
        _dir_stat_fingerprint(d)
        for d in _walk_dirs_for_bucket_fingerprint(path, _SCAN_CACHE_BUCKET_DEPTH)
    ]


def _video_entry_from_cache(data: dict) -> Optional[VideoLibraryScanEntry]:
    try:
        return VideoLibraryScanEntry(
            path=Path(str(data.get("path") or "")),
            owner_label=str(data.get("owner_label") or UNASSIGNED_OWNER_LABEL),
            size_bytes=int(data.get("size_bytes") or 0),
            mtime=float(data.get("mtime") or 0.0),
        )
    except Exception:
        return None


def _image_entry_from_cache(data: dict) -> Optional[ImageLibraryScanEntry]:
    try:
        return ImageLibraryScanEntry(
            path=Path(str(data.get("path") or "")),
            owner_label=str(data.get("owner_label") or UNASSIGNED_OWNER_LABEL),
            size_bytes=int(data.get("size_bytes") or 0),
            image_count=int(data.get("image_count") or 0),
            mtime=float(data.get("mtime") or 0.0),
        )
    except Exception:
        return None


def _init_scan_cache_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_cache_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_cache_buckets (
            kind TEXT NOT NULL,
            bucket_key TEXT NOT NULL,
            path TEXT NOT NULL,
            owner_label TEXT NOT NULL,
            fingerprint_json TEXT NOT NULL,
            PRIMARY KEY (kind, bucket_key)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_cache_entries (
            kind TEXT NOT NULL,
            bucket_key TEXT NOT NULL,
            path TEXT NOT NULL,
            owner_label TEXT NOT NULL,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            image_count INTEGER NOT NULL DEFAULT 0,
            mtime REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (kind, path)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_scan_cache_entries_bucket "
        "ON scan_cache_entries(kind, bucket_key)"
    )


def _load_scan_cache_raw_sqlite_sync(
    *,
    root: Path,
    video_exts: set[str],
    image_exts: set[str],
    max_age_seconds: float = _SCAN_CACHE_MAX_AGE_SECONDS,
) -> Optional[dict]:
    db_file = _scan_cache_db_path()
    if not db_file.exists():
        return None
    try:
        with sqlite3.connect(str(db_file)) as conn:
            conn.row_factory = sqlite3.Row
            _init_scan_cache_db(conn)
            meta = {
                str(row["key"]): str(row["value"])
                for row in conn.execute("SELECT key, value FROM scan_cache_meta")
            }
            if int(meta.get("version") or 0) != _SCAN_CACHE_VERSION:
                return None
            if meta.get("root", "") != str(root):
                return None
            if json.loads(meta.get("video_exts", "[]")) != sorted(video_exts):
                return None
            if json.loads(meta.get("image_exts", "[]")) != sorted(image_exts):
                return None
            created_at = float(meta.get("created_at") or 0.0)
            if created_at <= 0 or (time.time() - created_at) > float(max_age_seconds):
                return None

            raw = {
                "version": _SCAN_CACHE_VERSION,
                "created_at": created_at,
                "root": str(root),
                "video_exts": sorted(video_exts),
                "image_exts": sorted(image_exts),
                "fingerprint": json.loads(meta.get("fingerprint", "[]")),
                "video_buckets": {},
                "image_buckets": {},
                "video_entries": [],
                "image_entries": [],
            }

            buckets_by_kind: Dict[str, dict] = {"video": {}, "image": {}}
            for row in conn.execute(
                "SELECT kind, bucket_key, path, owner_label, fingerprint_json "
                "FROM scan_cache_buckets"
            ):
                kind = str(row["kind"])
                if kind not in buckets_by_kind:
                    continue
                buckets_by_kind[kind][str(row["bucket_key"])] = {
                    "path": str(row["path"]),
                    "owner_label": str(row["owner_label"]),
                    "fingerprint": json.loads(str(row["fingerprint_json"] or "[]")),
                    "entries": [],
                }

            for row in conn.execute(
                "SELECT kind, bucket_key, path, owner_label, size_bytes, image_count, mtime "
                "FROM scan_cache_entries"
            ):
                kind = str(row["kind"])
                item = {
                    "path": str(row["path"]),
                    "owner_label": str(row["owner_label"]),
                    "size_bytes": int(row["size_bytes"] or 0),
                    "image_count": int(row["image_count"] or 0),
                    "mtime": float(row["mtime"] or 0.0),
                }
                if kind == "video":
                    raw["video_entries"].append(item)
                    bucket = buckets_by_kind["video"].get(str(row["bucket_key"]))
                elif kind == "image":
                    raw["image_entries"].append(item)
                    bucket = buckets_by_kind["image"].get(str(row["bucket_key"]))
                else:
                    bucket = None
                if bucket is not None:
                    bucket["entries"].append(item)

            raw["video_buckets"] = buckets_by_kind["video"]
            raw["image_buckets"] = buckets_by_kind["image"]
            return raw
    except Exception:
        return None


def _load_scan_cache_raw_sync(
    *,
    root: Path,
    video_exts: set[str],
    image_exts: set[str],
    max_age_seconds: float = _SCAN_CACHE_MAX_AGE_SECONDS,
) -> Optional[dict]:
    sqlite_raw = _load_scan_cache_raw_sqlite_sync(
        root=root,
        video_exts=video_exts,
        image_exts=image_exts,
        max_age_seconds=max_age_seconds,
    )
    if sqlite_raw is not None:
        logger.debug("媒体库扫描缓存命中: source=sqlite")
        return sqlite_raw

    cache_file = _scan_cache_file_path()
    try:
        raw = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    try:
        if int(raw.get("version") or 0) != _SCAN_CACHE_VERSION:
            return None
        if str(raw.get("root") or "") != str(root):
            return None
        if list(raw.get("video_exts") or []) != sorted(video_exts):
            return None
        if list(raw.get("image_exts") or []) != sorted(image_exts):
            return None
        created_at = float(raw.get("created_at") or 0.0)
        if created_at <= 0 or (time.time() - created_at) > float(max_age_seconds):
            return None
    except Exception:
        return None
    logger.debug("媒体库扫描缓存命中: source=json")
    return raw


def _scan_cache_entries_from_raw(
    raw: dict,
) -> tuple[List[VideoLibraryScanEntry], List[ImageLibraryScanEntry]]:
    video_entries: List[VideoLibraryScanEntry] = []
    for item in raw.get("video_entries") or []:
        entry = _video_entry_from_cache(item if isinstance(item, dict) else {})
        if entry is not None and str(entry.path):
            video_entries.append(entry)

    image_entries: List[ImageLibraryScanEntry] = []
    for item in raw.get("image_entries") or []:
        entry = _image_entry_from_cache(item if isinstance(item, dict) else {})
        if entry is not None and str(entry.path):
            image_entries.append(entry)

    return video_entries, image_entries


def _load_scan_cache_sync(
    *,
    root: Path,
    video_exts: set[str],
    image_exts: set[str],
    max_age_seconds: float = _SCAN_CACHE_MAX_AGE_SECONDS,
) -> Optional[tuple[List[VideoLibraryScanEntry], List[ImageLibraryScanEntry]]]:
    raw = _load_scan_cache_raw_sync(
        root=root,
        video_exts=video_exts,
        image_exts=image_exts,
        max_age_seconds=max_age_seconds,
    )
    if raw is None:
        return None

    try:
        cached_fp = raw.get("fingerprint")
        if cached_fp != _build_scan_cache_fingerprint(root):
            return None
    except Exception:
        return None

    return _scan_cache_entries_from_raw(raw)


def _build_video_scan_buckets(root: Path) -> List[_ScanBucket]:
    buckets = [
        _ScanBucket(
            key=_path_key(root / MaterialLibraryManager.VIDEO_FOLDER_NAME),
            path=root / MaterialLibraryManager.VIDEO_FOLDER_NAME,
            owner_label=UNASSIGNED_OWNER_LABEL,
            required=True,
        )
    ]
    account_lib = MaterialLibraryManager.account_library_root(root)
    if account_lib.exists():
        try:
            with os.scandir(str(account_lib)) as it:
                for item in it:
                    if not item.is_dir():
                        continue
                    owner = MaterialLibraryManager.owner_label_for_account_library_entry(item.name)
                    path = (
                        Path(item.path)
                        / MaterialLibraryManager.ACCOUNT_MEDIA_VIDEO_NAME
                        / MaterialLibraryManager.UNPUBLISHED_NAME
                    )
                    buckets.append(_ScanBucket(key=_path_key(path), path=path, owner_label=owner))
        except OSError:
            pass
    return buckets


def _build_image_scan_buckets(root: Path) -> List[_ScanBucket]:
    buckets = [
        _ScanBucket(
            key=_path_key(root / MaterialLibraryManager.IMAGE_FOLDER_NAME),
            path=root / MaterialLibraryManager.IMAGE_FOLDER_NAME,
            owner_label=UNASSIGNED_OWNER_LABEL,
            required=True,
        )
    ]
    account_lib = MaterialLibraryManager.account_library_root(root)
    if account_lib.exists():
        try:
            with os.scandir(str(account_lib)) as it:
                for item in it:
                    if not item.is_dir():
                        continue
                    owner = MaterialLibraryManager.owner_label_for_account_library_entry(item.name)
                    path = (
                        Path(item.path)
                        / MaterialLibraryManager.ACCOUNT_MEDIA_IMAGE_NAME
                        / MaterialLibraryManager.UNPUBLISHED_NAME
                    )
                    buckets.append(_ScanBucket(key=_path_key(path), path=path, owner_label=owner))
        except OSError:
            pass
    return buckets


def _scan_video_bucket_entries(
    bucket: _ScanBucket,
    extensions: set[str],
) -> tuple[List[VideoLibraryScanEntry], Optional[str]]:
    if not bucket.path.exists():
        if bucket.required:
            return [], "未找到视频库目录，请在设置中重新选择媒体库路径。"
        return [], None

    entries: List[VideoLibraryScanEntry] = []
    ext_lower = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
    try:
        with os.scandir(str(bucket.path)) as it:
            for item in it:
                if not item.is_file():
                    continue
                suffix = os.path.splitext(item.name)[1].lower()
                if suffix not in ext_lower:
                    continue
                try:
                    st = item.stat()
                    size_b = st.st_size
                    mtime = st.st_mtime
                except OSError:
                    size_b = 0
                    mtime = 0.0
                entries.append(
                    VideoLibraryScanEntry(
                        path=Path(item.path),
                        owner_label=bucket.owner_label,
                        size_bytes=size_b,
                        mtime=mtime,
                    )
                )
    except OSError:
        return entries, None
    return entries, None


def _scan_image_bucket_entries(
    bucket: _ScanBucket,
    extensions: set[str],
) -> tuple[List[ImageLibraryScanEntry], Optional[str]]:
    if not bucket.path.exists():
        if bucket.required:
            return [], "未找到图片库目录，请在设置中重新选择媒体库路径。"
        return [], None

    entries: List[ImageLibraryScanEntry] = []
    ext_lower = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}

    def count_images_in_folder(folder_path: Path) -> Tuple[int, int, float]:
        count = 0
        total_size = 0
        latest_mtime = 0.0
        try:
            with os.scandir(str(folder_path)) as it:
                for item in it:
                    if not item.is_file():
                        continue
                    suffix = os.path.splitext(item.name)[1].lower()
                    if suffix not in ext_lower:
                        continue
                    count += 1
                    try:
                        st = item.stat()
                        total_size += st.st_size
                        if st.st_mtime > latest_mtime:
                            latest_mtime = st.st_mtime
                    except OSError:
                        pass
        except OSError:
            pass
        return count, total_size, latest_mtime

    try:
        with os.scandir(str(bucket.path)) as it:
            for item in it:
                if not item.is_dir():
                    continue
                folder_path = Path(item.path)
                image_count, total_size, mtime = count_images_in_folder(folder_path)
                try:
                    if mtime == 0.0:
                        mtime = item.stat().st_mtime
                except OSError:
                    pass
                entries.append(
                    ImageLibraryScanEntry(
                        path=folder_path,
                        owner_label=bucket.owner_label,
                        size_bytes=total_size,
                        image_count=image_count,
                        mtime=mtime,
                    )
                )
    except OSError:
        return entries, None
    return entries, None


def _build_bucket_cache_payload(
    buckets: List[_ScanBucket],
    entries: List[TScanEntry],
    bucket_key_for_entry: Callable[[TScanEntry], str],
) -> dict:
    by_bucket: Dict[str, List[TScanEntry]] = defaultdict(list)
    for entry in entries or []:
        by_bucket[bucket_key_for_entry(entry)].append(entry)

    payload = {}
    for bucket in buckets:
        payload[bucket.key] = {
            "path": str(bucket.path),
            "owner_label": bucket.owner_label,
            "fingerprint": _build_bucket_fingerprint(bucket.path),
            "entries": [
                _scan_cache_entry_to_dict(entry)
                for entry in by_bucket.get(bucket.key, [])
            ],
        }
    return payload


def _load_bucket_entries(
    raw_bucket: dict,
    entry_from_cache: Callable[[dict], Optional[TScanEntry]],
) -> Optional[List[TScanEntry]]:
    if not isinstance(raw_bucket, dict):
        return None
    entries: List[TScanEntry] = []
    for item in raw_bucket.get("entries") or []:
        entry = entry_from_cache(item if isinstance(item, dict) else {})
        if entry is not None and str(entry.path):
            entries.append(entry)
    return entries


def _scan_with_bucket_cache(
    *,
    buckets: List[_ScanBucket],
    cached_buckets: dict,
    extensions: set[str],
    scan_bucket: Callable[[_ScanBucket, set[str]], tuple[List[TScanEntry], Optional[str]]],
    entry_from_cache: Callable[[dict], Optional[TScanEntry]],
    stats: Optional[dict] = None,
) -> tuple[List[TScanEntry], Optional[str]]:
    entries: List[TScanEntry] = []
    errors: List[str] = []

    for bucket in buckets:
        cached = cached_buckets.get(bucket.key) if isinstance(cached_buckets, dict) else None
        try:
            if (
                isinstance(cached, dict)
                and cached.get("fingerprint") == _build_bucket_fingerprint(bucket.path)
            ):
                cached_entries = _load_bucket_entries(cached, entry_from_cache)
                if cached_entries is not None:
                    entries.extend(cached_entries)
                    if stats is not None:
                        stats["reused"] = int(stats.get("reused") or 0) + 1
                    continue
        except Exception:
            pass

        scanned_entries, err = scan_bucket(bucket, extensions)
        if stats is not None:
            stats["rescanned"] = int(stats.get("rescanned") or 0) + 1
        entries.extend(scanned_entries or [])
        if err:
            errors.append(err)

    return entries, "；".join(errors) if errors else None


def _load_scan_cache_incremental_sync(
    *,
    root: Path,
    video_exts: set[str],
    image_exts: set[str],
    max_age_seconds: float = _SCAN_CACHE_MAX_AGE_SECONDS,
) -> Optional[tuple[List[VideoLibraryScanEntry], List[ImageLibraryScanEntry], str]]:
    raw = _load_scan_cache_raw_sync(
        root=root,
        video_exts=video_exts,
        image_exts=image_exts,
        max_age_seconds=max_age_seconds,
    )
    if raw is None:
        return None

    video_cached_buckets = raw.get("video_buckets")
    image_cached_buckets = raw.get("image_buckets")
    if not isinstance(video_cached_buckets, dict) or not isinstance(image_cached_buckets, dict):
        return None

    stats = {"reused": 0, "rescanned": 0}
    video_entries, v_err = _scan_with_bucket_cache(
        buckets=_build_video_scan_buckets(root),
        cached_buckets=video_cached_buckets,
        extensions=video_exts,
        scan_bucket=_scan_video_bucket_entries,
        entry_from_cache=_video_entry_from_cache,
        stats=stats,
    )
    image_entries, i_err = _scan_with_bucket_cache(
        buckets=_build_image_scan_buckets(root),
        cached_buckets=image_cached_buckets,
        extensions=image_exts,
        scan_bucket=_scan_image_bucket_entries,
        entry_from_cache=_image_entry_from_cache,
        stats=stats,
    )
    logger.debug(
        "媒体库扫描缓存增量命中: reused_buckets=%s rescanned_buckets=%s",
        stats["reused"],
        stats["rescanned"],
    )
    err = "；".join([e for e in [v_err, i_err] if e])
    return video_entries, image_entries, err


def _scan_cache_bucket_entry_rows(kind: str, bucket_key: str, bucket: dict) -> List[tuple]:
    rows: List[tuple] = []
    for entry in bucket.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        rows.append(
            (
                kind,
                str(bucket_key),
                str(entry.get("path") or ""),
                str(entry.get("owner_label") or ""),
                int(entry.get("size_bytes") or 0),
                int(entry.get("image_count") or 0),
                float(entry.get("mtime") or 0.0),
            )
        )
    return sorted(rows, key=lambda row: row[2])


def _load_sqlite_bucket_signatures(conn: sqlite3.Connection) -> Dict[tuple[str, str], tuple]:
    signatures: Dict[tuple[str, str], tuple] = {}
    for row in conn.execute(
        "SELECT kind, bucket_key, path, owner_label, fingerprint_json "
        "FROM scan_cache_buckets"
    ):
        signatures[(str(row[0]), str(row[1]))] = (
            str(row[2]),
            str(row[3]),
            str(row[4] or "[]"),
            [],
        )

    entry_rows: Dict[tuple[str, str], List[tuple]] = defaultdict(list)
    for row in conn.execute(
        "SELECT kind, bucket_key, path, owner_label, size_bytes, image_count, mtime "
        "FROM scan_cache_entries"
    ):
        key = (str(row[0]), str(row[1]))
        entry_rows[key].append(
            (
                str(row[0]),
                str(row[1]),
                str(row[2]),
                str(row[3]),
                int(row[4] or 0),
                int(row[5] or 0),
                float(row[6] or 0.0),
            )
        )

    for key, meta in list(signatures.items()):
        signatures[key] = (
            meta[0],
            meta[1],
            meta[2],
            sorted(entry_rows.get(key, []), key=lambda row: row[2]),
        )
    return signatures


def _save_scan_cache_sqlite_sync(payload: dict) -> None:
    db_file = _scan_cache_db_path()
    db_file.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    with sqlite3.connect(str(db_file)) as conn:
        _init_scan_cache_db(conn)
        conn.commit()
        existing = _load_sqlite_bucket_signatures(conn)
        seen_bucket_keys: set[tuple[str, str]] = set()
        changed_buckets = 0
        deleted_buckets = 0

        conn.execute("BEGIN")
        meta_items = {
            "version": str(payload.get("version") or _SCAN_CACHE_VERSION),
            "created_at": str(payload.get("created_at") or time.time()),
            "root": str(payload.get("root") or ""),
            "video_exts": json.dumps(payload.get("video_exts") or [], ensure_ascii=False),
            "image_exts": json.dumps(payload.get("image_exts") or [], ensure_ascii=False),
            "fingerprint": json.dumps(payload.get("fingerprint") or [], ensure_ascii=False),
        }
        conn.executemany(
            "INSERT OR REPLACE INTO scan_cache_meta(key, value) VALUES (?, ?)",
            list(meta_items.items()),
        )
        conn.execute(
            "DELETE FROM scan_cache_meta WHERE key NOT IN "
            "('version', 'created_at', 'root', 'video_exts', 'image_exts', 'fingerprint')"
        )
        for kind, buckets_key in (("video", "video_buckets"), ("image", "image_buckets")):
            buckets = payload.get(buckets_key) or {}
            for bucket_key, bucket in buckets.items():
                if not isinstance(bucket, dict):
                    continue
                key = (kind, str(bucket_key))
                seen_bucket_keys.add(key)
                fingerprint_json = json.dumps(bucket.get("fingerprint") or [], ensure_ascii=False)
                entry_rows = _scan_cache_bucket_entry_rows(kind, str(bucket_key), bucket)
                signature = (
                    str(bucket.get("path") or ""),
                    str(bucket.get("owner_label") or ""),
                    fingerprint_json,
                    entry_rows,
                )
                if existing.get(key) == signature:
                    continue

                changed_buckets += 1
                conn.execute(
                    "DELETE FROM scan_cache_entries WHERE kind = ? AND bucket_key = ?",
                    key,
                )
                conn.execute(
                    """
                    INSERT OR REPLACE INTO scan_cache_buckets
                    (kind, bucket_key, path, owner_label, fingerprint_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        kind,
                        str(bucket_key),
                        str(bucket.get("path") or ""),
                        str(bucket.get("owner_label") or ""),
                        fingerprint_json,
                    ),
                )
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO scan_cache_entries
                    (kind, bucket_key, path, owner_label, size_bytes, image_count, mtime)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    entry_rows,
                )

        stale_keys = set(existing) - seen_bucket_keys
        for kind, bucket_key in stale_keys:
            deleted_buckets += 1
            conn.execute(
                "DELETE FROM scan_cache_entries WHERE kind = ? AND bucket_key = ?",
                (kind, bucket_key),
            )
            conn.execute(
                "DELETE FROM scan_cache_buckets WHERE kind = ? AND bucket_key = ?",
                (kind, bucket_key),
            )
        conn.commit()
    logger.debug(
        "媒体库扫描缓存保存: changed_buckets=%s deleted_buckets=%s elapsed_ms=%.1f",
        changed_buckets,
        deleted_buckets,
        (time.perf_counter() - start) * 1000,
    )


def _delete_scan_cache_json_sync() -> None:
    try:
        _scan_cache_file_path().unlink(missing_ok=True)
    except Exception:
        pass


def _delete_scan_cache_buckets_sync(bucket_keys: Iterable[tuple[str, str]]) -> int:
    keys = {(str(kind), str(bucket_key)) for kind, bucket_key in (bucket_keys or []) if bucket_key}
    if not keys:
        return 0

    db_file = _scan_cache_db_path()
    if not db_file.exists():
        _delete_scan_cache_json_sync()
        return 0

    deleted = 0
    try:
        with sqlite3.connect(str(db_file)) as conn:
            _init_scan_cache_db(conn)
            conn.commit()
            conn.execute("BEGIN")
            for kind, bucket_key in keys:
                cur = conn.execute(
                    "DELETE FROM scan_cache_entries WHERE kind = ? AND bucket_key = ?",
                    (kind, bucket_key),
                )
                conn.execute(
                    "DELETE FROM scan_cache_buckets WHERE kind = ? AND bucket_key = ?",
                    (kind, bucket_key),
                )
                deleted += int(cur.rowcount or 0)
            conn.commit()
    except Exception:
        logger.debug("媒体库扫描缓存定向失效失败，回退整库清理", exc_info=True)
        _delete_scan_cache_sync()
        return 0

    _delete_scan_cache_json_sync()
    logger.debug(
        "媒体库扫描缓存定向失效: buckets=%s deleted_entries=%s",
        len(keys),
        deleted,
    )
    return deleted


def _save_scan_cache_sync(
    *,
    root: Path,
    video_exts: set[str],
    image_exts: set[str],
    video_entries: List[VideoLibraryScanEntry],
    image_entries: List[ImageLibraryScanEntry],
) -> None:
    cache_file = _scan_cache_file_path()
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _SCAN_CACHE_VERSION,
            "created_at": time.time(),
            "root": str(root),
            "video_exts": sorted(video_exts),
            "image_exts": sorted(image_exts),
            "fingerprint": _build_scan_cache_fingerprint(root),
            "video_buckets": _build_bucket_cache_payload(
                _build_video_scan_buckets(root),
                video_entries or [],
                lambda entry: _path_key(entry.path.parent),
            ),
            "image_buckets": _build_bucket_cache_payload(
                _build_image_scan_buckets(root),
                image_entries or [],
                lambda entry: _path_key(entry.path.parent),
            ),
            "video_entries": [_scan_cache_entry_to_dict(e) for e in video_entries or []],
            "image_entries": [_scan_cache_entry_to_dict(e) for e in image_entries or []],
        }
        _save_scan_cache_sqlite_sync(payload)
        tmp_file = cache_file.with_name(f"{cache_file.name}.tmp")
        tmp_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp_file.replace(cache_file)
    except Exception:
        return


def _delete_scan_cache_sync() -> None:
    _delete_scan_cache_json_sync()
    try:
        _scan_cache_db_path().unlink(missing_ok=True)
    except Exception:
        pass


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

    def invalidate(self, *, clear_cache: bool = False) -> None:
        """标记需重算统计；可选清空缓存，避免短暂返回旧对象。"""
        self._last_done_ts = 0.0
        if clear_cache:
            get_media_library_stats_cache().clear()
            try:
                _delete_scan_cache_sync()
            except Exception:
                pass

    def invalidate_bucket_paths(
        self,
        bucket_paths: Iterable[Path],
        *,
        kinds: Iterable[str] = ("video", "image"),
        clear_memory: bool = True,
    ) -> None:
        """Invalidate selected scan buckets without dropping the whole persistent index."""
        self._last_done_ts = 0.0
        if clear_memory:
            get_media_library_stats_cache().clear()

        paths = [Path(p) for p in (bucket_paths or []) if p]
        kind_values = [str(k) for k in (kinds or []) if k]
        keys = [(kind, _path_key(path)) for kind in kind_values for path in paths]
        if keys:
            _delete_scan_cache_buckets_sync(keys)

    async def compute_stats(
        self,
        *,
        statuses: Tuple[str, ...] = ("pending", "failed", "running"),
    ) -> MediaLibraryStats:
        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            return MediaLibraryStats(error="未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。")

        video_exts = self._default_video_exts()
        image_exts = self._default_image_exts()
        usage_task = asyncio.create_task(get_pending_media_usage(statuses=statuses))

        scan_cache = await asyncio.to_thread(
            _load_scan_cache_sync,
            root=root,
            video_exts=video_exts,
            image_exts=image_exts,
        )
        if scan_cache is not None:
            video_entries, image_entries = scan_cache
            err = ""
        else:
            incremental_cache = await asyncio.to_thread(
                _load_scan_cache_incremental_sync,
                root=root,
                video_exts=video_exts,
                image_exts=image_exts,
            )
            if incremental_cache is not None:
                video_entries, image_entries, err = incremental_cache
            else:
                logger.debug("媒体库扫描缓存未命中，执行全量扫描")
                video_scan_task = asyncio.to_thread(scan_video_library_entries, root, video_exts)
                image_scan_task = asyncio.to_thread(scan_image_library_entries, root, image_exts)

                (video_entries, v_err), (image_entries, i_err) = await asyncio.gather(
                    video_scan_task,
                    image_scan_task,
                )
                if v_err or i_err:
                    # 不中断：仍尽量返回可用统计（哪个为空就算 0），并把错误文案带回 UI
                    err = "；".join([e for e in [v_err, i_err] if e])
                else:
                    err = ""
            await asyncio.to_thread(
                _save_scan_cache_sync,
                root=root,
                video_exts=video_exts,
                image_exts=image_exts,
                video_entries=video_entries or [],
                image_entries=image_entries or [],
            )

        usage = await usage_task

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

        # ---- 按账号组维度统计（用于批量页选择账号组时展示）----
        try:
            from src.domain.repositories.account_group_repository_async import (
                AccountGroupRepositoryAsync,
            )

            group_repo = AccountGroupRepositoryAsync()
            groups = await group_repo.find_all(user_id=None)
        except Exception:
            groups = []

        (
            video_by_account,
            image_by_account,
            video_by_group,
            image_by_group,
        ) = await asyncio.to_thread(
            _build_account_and_group_path_maps,
            root=root,
            accounts=accounts or [],
            groups=groups or [],
            video_entries=video_entries or [],
            image_entries=image_entries or [],
            video_exts=video_exts,
        )

        video_by_account_counts = build_account_video_stats(
            account_id_to_video_paths=video_by_account,
            usage=usage,
        )
        image_by_account_counts = build_account_image_stats(
            account_id_to_image_folder_paths=image_by_account,
            usage=usage,
        )

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

