"""
发布列表去重（独立模块，供单页/批量等多处调用）。

规则：待发布/进行中状态下，同一「素材标识 + 平台 + 平台用户名」不可重复创建。
- 视频：素材标识为单个文件的规范化完整路径。
- 图文：file_path 为英文逗号分隔的多图路径，各路径规范化后排序再拼接为稳定标识（顺序无关）。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Literal, Set, Tuple

from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
from src.utils.platform_names import get_platform_display_name

MediaFileType = Literal["video", "image"]

# 图文多图拼接符（路径内不会出现）
_COMPOSITE_SEP = "\x1e"


def normalize_publish_media_path(path: str) -> str:
    """单文件路径规范化（完整路径、大小写归一）。"""
    if not path or not str(path).strip():
        return ""
    p = str(path).strip()
    try:
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))
    except OSError:
        return os.path.normcase(os.path.normpath(p))


def normalize_composite_image_publish_path(composite: str) -> str:
    """图文任务 file_path：逗号分隔多图 → 各段规范化后排序拼接，便于同套图判重。"""
    parts = [p.strip() for p in str(composite).split(",") if p.strip()]
    norms = sorted(
        normalize_publish_media_path(p) for p in parts if normalize_publish_media_path(p)
    )
    return _COMPOSITE_SEP.join(norms)


def normalize_publish_file_identity(file_path: str, file_type: str) -> str:
    """按发布记录 file_type 得到与库记录可比的素材标识字符串。"""
    ft = (file_type or "").strip().lower()
    if ft == "image":
        return normalize_composite_image_publish_path(file_path)
    return normalize_publish_media_path(file_path)


def _account_key_parts(account: Dict[str, Any]) -> Tuple[str, str]:
    plat = (account.get("platform") or "").strip()
    user = (account.get("platform_username") or "").strip()
    return plat, user


def _format_skip_line(platform: str, platform_username: str, file_path: str) -> str:
    dn = get_platform_display_name(platform) or platform or "未知平台"
    return f"• {platform_username}｜{dn}\n  {file_path}"


async def build_active_publish_task_key_set(
    repo: PublishRecordRepositoryAsync,
    user_id: int,
    *,
    file_types: Tuple[str, ...] = ("video", "image"),
    exclude_record_id: int | None = None,
) -> Set[Tuple[str, str, str]]:
    """库中待发布/进行中任务的 (素材标识, 平台, 平台用户名) 集合。"""
    rows = await repo.list_active_publish_rows_for_duplicate_check(
        user_id,
        file_types=file_types,
        exclude_record_id=exclude_record_id,
    )
    keys: Set[Tuple[str, str, str]] = set()
    for _rid, fp, plat, user, ft in rows:
        ident = normalize_publish_file_identity(fp, ft)
        if not ident:
            continue
        keys.add((ident, (plat or "").strip(), (user or "").strip()))
    return keys


async def filter_accounts_for_new_publish_task(
    repo: PublishRecordRepositoryAsync,
    user_id: int,
    file_path: str,
    accounts: List[Dict[str, Any]],
    *,
    file_type: MediaFileType,
    exclude_record_id: int | None = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """单页添加：过滤已在发布列表中存在相同待发布/进行中任务的账号。

    Args:
        file_type: ``video`` 或 ``image``，须与即将写入的发布记录一致。

    Returns:
        (可添加的账号列表, 跳过原因文案行列表)
    """
    if not accounts:
        return [], []
    ft = (file_type or "").strip().lower()
    if ft not in ("video", "image"):
        return list(accounts), []

    ident = normalize_publish_file_identity(file_path, ft)
    if not ident:
        return list(accounts), []

    existing = await build_active_publish_task_key_set(
        repo,
        user_id,
        file_types=(ft,),
        exclude_record_id=exclude_record_id,
    )
    ok: List[Dict[str, Any]] = []
    lines: List[str] = []
    display_path = file_path.strip()
    for acc in accounts:
        plat, user = _account_key_parts(acc)
        key = (ident, plat, user)
        if key in existing:
            lines.append(_format_skip_line(plat, user, display_path))
            continue
        ok.append(acc)
        existing.add(key)
    return ok, lines


async def filter_accounts_for_new_video_task(
    repo: PublishRecordRepositoryAsync,
    user_id: int,
    file_path: str,
    accounts: List[Dict[str, Any]],
    *,
    exclude_record_id: int | None = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """兼容旧调用名：等价于 ``file_type=\"video\"``。"""
    return await filter_accounts_for_new_publish_task(
        repo,
        user_id,
        file_path,
        accounts,
        file_type="video",
        exclude_record_id=exclude_record_id,
    )


async def partition_batch_publish_tasks_by_duplicates(
    repo: PublishRecordRepositoryAsync,
    user_id: int,
    tasks: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """批量写入前：相对库中待发布/进行中记录 + 本批已接纳任务去重；允许部分成功。

    仅处理 ``file_type`` 为 ``video`` / ``image`` 的任务，其它类型原样保留。
    """
    if not tasks:
        return [], []

    existing = await build_active_publish_task_key_set(
        repo, user_id, file_types=("video", "image")
    )
    accepted: List[Dict[str, Any]] = []
    lines: List[str] = []

    for task in tasks:
        ft = (task.get("file_type") or "").strip().lower()
        if ft not in ("video", "image"):
            accepted.append(task)
            continue
        raw_path = str(task.get("file_path") or "").strip()
        ident = normalize_publish_file_identity(raw_path, ft)
        plat = (task.get("platform") or "").strip()
        user = (task.get("platform_username") or "").strip()
        if not ident or not plat or not user:
            accepted.append(task)
            continue
        key = (ident, plat, user)
        if key in existing:
            lines.append(_format_skip_line(plat, user, raw_path))
            continue
        accepted.append(task)
        existing.add(key)
    return accepted, lines


# 旧名保留，避免外部引用断裂
partition_batch_video_tasks_by_duplicates = partition_batch_publish_tasks_by_duplicates
