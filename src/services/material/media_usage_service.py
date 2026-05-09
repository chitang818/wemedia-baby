"""
媒体库素材占用检测（用于媒体库表格“使用统计”列）。

规则：
- 只要素材被「待发布」列表中的任务引用（pending/failed/running），就认为“已占用”；
- 视频：按视频文件的绝对路径匹配；
- 图文：优先匹配任务 file_path 中的 "__FOLDER__:<folder>" 标记；没有标记时，若该任务图片都在同一父目录，
        则用该父目录作为“图文文件夹”占用路径。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Set, Tuple


_FOLDER_MARKER_PREFIX = "__FOLDER__:"

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".m4v", ".webm"}


def _norm_path(p: str) -> str:
    p = (p or "").strip()
    if not p:
        return ""
    try:
        p = os.path.abspath(p)
    except Exception:
        pass
    return os.path.normcase(os.path.normpath(p))


def _split_parts(file_path: str) -> list[str]:
    return [p.strip() for p in str(file_path or "").split(",") if p.strip()]


def _extract_folder_marker(file_path: str) -> Optional[str]:
    for part in _split_parts(file_path):
        if part.startswith(_FOLDER_MARKER_PREFIX):
            return part[len(_FOLDER_MARKER_PREFIX) :].strip() or None
    return None


def _extract_real_paths(file_path: str) -> list[str]:
    return [
        p
        for p in _split_parts(file_path)
        if not p.startswith(_FOLDER_MARKER_PREFIX)
    ]


def _looks_like_image(p: str) -> bool:
    try:
        return Path(p).suffix.lower() in _IMAGE_EXTS
    except Exception:
        return False


def _looks_like_video(p: str) -> bool:
    try:
        return Path(p).suffix.lower() in _VIDEO_EXTS
    except Exception:
        return False


@dataclass(frozen=True)
class PendingMediaUsage:
    """待发布（含失败/发布中）任务中素材引用集合。"""

    used_video_files: Set[str]
    used_image_folders: Set[str]


async def get_pending_media_usage(
    *,
    statuses: Tuple[str, ...] = ("pending", "failed", "running"),
) -> PendingMediaUsage:
    """读取发布记录表，返回待发布任务占用的素材路径集合。"""
    from src.infrastructure.storage.orm_models.publish_record import PublishRecord

    rows = await (
        PublishRecord.filter(status__in=list(statuses))
        .values("file_path", "file_type")
    )

    used_videos: Set[str] = set()
    used_image_folders: Set[str] = set()

    for r in rows or []:
        fp = str(r.get("file_path") or "")
        ftype = str(r.get("file_type") or "").strip().lower()

        # ---- 图文：优先 folder marker ----
        folder = _extract_folder_marker(fp)
        if folder:
            used_image_folders.add(_norm_path(folder))

        real_paths = _extract_real_paths(fp)
        if not real_paths:
            continue

        # ---- 视频 ----
        if ftype == "video" or any(_looks_like_video(p) for p in real_paths):
            for p in real_paths:
                if _looks_like_video(p) or ftype == "video":
                    np = _norm_path(p)
                    if np:
                        used_videos.add(np)
            continue

        # ---- 图文（无 marker 时兜底）----
        if ftype == "image" or any(_looks_like_image(p) for p in real_paths):
            # 兜底：如果所有图片都来自同一父目录，用该目录视为“图片文件夹”
            parents: Set[str] = set()
            for p in real_paths:
                if not _looks_like_image(p):
                    continue
                try:
                    parent = str(Path(p).parent)
                except Exception:
                    parent = ""
                n_parent = _norm_path(parent)
                if n_parent:
                    parents.add(n_parent)
            if len(parents) == 1:
                used_image_folders |= parents

    return PendingMediaUsage(
        used_video_files=used_videos,
        used_image_folders=used_image_folders,
    )


def is_video_used(usage: PendingMediaUsage, video_path: os.PathLike | str) -> bool:
    return _norm_path(os.fspath(video_path)) in (usage.used_video_files or set())


def is_image_folder_used(usage: PendingMediaUsage, folder_path: os.PathLike | str) -> bool:
    return _norm_path(os.fspath(folder_path)) in (usage.used_image_folders or set())

