"""
待发布任务与媒体库路径策略
文件路径：src/infrastructure/common/publish_material_path_policy.py

规则：
- 任务主文件位于「媒小宝媒体库/视频库」或「媒小宝媒体库/图片库」下时，发布后文件处理须为「移动」；
- 主文件位于已配置的「媒小宝媒体库」根目录树下（含账号库等）时，不允许选择「不处理」。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.infrastructure.common.material_library_manager import MaterialLibraryManager

# 与 list_settings_dialog 常量一致（避免循环 import 时仅用于类型/比较）
ACTION_NONE = "none"
ACTION_MOVE = "move"
ACTION_DELETE = "delete"


def iter_record_media_paths(record: Dict[str, Any]) -> Iterable[str]:
    """任务 file_path 中每条实际路径（逗号分隔多图）。"""
    fp = record.get("file_path") or ""
    for part in str(fp).split(","):
        s = part.strip()
        if s:
            yield s


def _resolve_path(p: str) -> Optional[Path]:
    try:
        return Path(p).expanduser().resolve()
    except Exception:
        return None


def path_under_mx_media_root(path_str: str) -> bool:
    """路径是否位于当前配置的「…/媒小宝媒体库」目录之下。"""
    root = MaterialLibraryManager.get_root_dir()
    if root is None:
        return False
    p = _resolve_path(path_str)
    if p is None:
        return False
    try:
        p.relative_to(root.resolve())
        return True
    except ValueError:
        return False
    except Exception:
        return False


def path_in_public_video_or_image_pool(path_str: str) -> bool:
    """是否在「媒小宝媒体库」下且第一级子目录为「视频库」或「图片库」（公共池）。"""
    root = MaterialLibraryManager.get_root_dir()
    if root is None:
        return False
    p = _resolve_path(path_str)
    if p is None:
        return False
    try:
        rel = p.relative_to(root.resolve())
    except ValueError:
        return False
    except Exception:
        return False
    parts = rel.parts
    if not parts:
        return False
    top = parts[0]
    return top == MaterialLibraryManager.VIDEO_FOLDER_NAME or top == MaterialLibraryManager.IMAGE_FOLDER_NAME


def publish_record_matches_any_path(
    record: Dict[str, Any], predicate
) -> bool:
    for s in iter_record_media_paths(record):
        try:
            if predicate(s):
                return True
        except Exception:
            continue
    return False


def publish_record_in_public_pool(record: Dict[str, Any]) -> bool:
    return publish_record_matches_any_path(record, path_in_public_video_or_image_pool)


def publish_record_under_material_library_tree(record: Dict[str, Any]) -> bool:
    """位于已配置媒体库根（媒小宝媒体库）之下，视为素材库相关任务。"""
    return publish_record_matches_any_path(record, path_under_mx_media_root)


def pending_records_any_public_pool(records: List[Dict[str, Any]]) -> bool:
    return any(publish_record_in_public_pool(r) for r in records)


def pending_records_any_material_library_tree(records: List[Dict[str, Any]]) -> bool:
    return any(publish_record_under_material_library_tree(r) for r in records)


def resolve_effective_post_publish_action_for_queue(
    pending_records: List[Dict[str, Any]], persisted_action: str
) -> str:
    """发布队列实际采用的处理方式（在持久化配置之上套用媒体库规则）。"""
    if not pending_records:
        return persisted_action
    if pending_records_any_public_pool(pending_records):
        return ACTION_MOVE
    if persisted_action == ACTION_NONE and pending_records_any_material_library_tree(pending_records):
        return ACTION_MOVE
    return persisted_action


def desired_persisted_post_publish_action(records: List[Dict[str, Any]], current: str) -> Optional[str]:
    """若配置应被规则改写则返回新值，否则返回 None。"""
    if not records:
        return None
    if pending_records_any_public_pool(records):
        if current != ACTION_MOVE:
            return ACTION_MOVE
        return None
    if pending_records_any_material_library_tree(records) and current == ACTION_NONE:
        return ACTION_MOVE
    return None


def message_for_auto_post_publish_change(
    records: List[Dict[str, Any]], previous_action: str
) -> Optional[str]:
    """自动改写发布后文件处理时，供界面展示的说明文案；无需提示时返回 None。"""
    if not records:
        return None
    if pending_records_any_public_pool(records) and previous_action != ACTION_MOVE:
        return (
            "待发布列表中有来自「视频库」或「图片库」的任务，"
            "已将「发布后文件处理」自动设为「移动至媒体库已发布目录」。"
        )
    if (
        previous_action == ACTION_NONE
        and pending_records_any_material_library_tree(records)
        and not pending_records_any_public_pool(records)
    ):
        return (
            "待发布列表中有位于媒体库内的素材，"
            "已将「发布后文件处理」从「不处理」自动改为「移动至媒体库已发布目录」。"
        )
    return None


def sanitize_post_publish_action_for_save(
    chosen_action: str, pending_policy_records: List[Dict[str, Any]]
) -> str:
    """发布设置「确认」写入前校正选项，防止禁用项仍被写入。"""
    if not pending_policy_records:
        return chosen_action
    if pending_records_any_public_pool(pending_policy_records):
        return ACTION_MOVE
    if chosen_action == ACTION_NONE and pending_records_any_material_library_tree(
        pending_policy_records
    ):
        return ACTION_MOVE
    return chosen_action

