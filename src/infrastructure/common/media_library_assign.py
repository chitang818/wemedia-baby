"""
媒体库视频 / 图文分配算法

将「解析未发布目标目录」「扫描可分配文件」「带重名的移动」等与 UI 解耦，
供视频库、图片库等页面复用。
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Set, Tuple

from src.infrastructure.common.material_library_manager import MaterialLibraryManager

logger = logging.getLogger(__name__)

MediaAssignKind = Literal["video", "image"]
AssignTargetType = Literal["account", "group"]

# 与视频库列表展示一致：公共视频库目录下的文件视为未绑定账号
UNASSIGNED_OWNER_LABEL = "未分配"


@dataclass(frozen=True)
class AssignTarget:
    """分配目标：物理目录与用户提示用文案。"""

    directory: Path
    label: str


@dataclass(frozen=True)
class VideoLibraryScanEntry:
    """视频库扫描结果中的一条记录（不含 ffprobe 元数据）。"""

    path: Path
    owner_label: str
    size_bytes: int
    mtime: float = 0.0


@dataclass(frozen=True)
class ImageLibraryScanEntry:
    """图片库扫描结果中的一条记录（代表一个图片文件夹）。"""

    path: Path
    owner_label: str
    size_bytes: int
    image_count: int = 0
    mtime: float = 0.0


def resolve_assign_target(
    root: Path,
    *,
    media_kind: MediaAssignKind,
    target_type: AssignTargetType,
    target_data: Dict[str, Any],
) -> AssignTarget:
    """根据账号或账号组解析「未发布」素材目录及展示标签。"""
    if target_type == "group":
        group_name = (target_data.get("group_name") or "").strip() or "未命名账号组"
        if media_kind == "video":
            directory = MaterialLibraryManager.group_video_unpublished_dir(root, group_name)
        else:
            directory = MaterialLibraryManager.group_image_unpublished_dir(root, group_name)
        label = f"账号组「{group_name}」"
        return AssignTarget(directory=directory, label=label)

    display_name = (
        (target_data.get("platform_username") or target_data.get("account_name") or "")
        .strip()
        or "未知账号"
    )
    if media_kind == "video":
        directory = MaterialLibraryManager.resolve_account_video_unpublished_dir(root, target_data)
    else:
        directory = MaterialLibraryManager.resolve_account_image_unpublished_dir(root, target_data)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("创建账号素材未发布目录失败: %s (%s)", directory, e)
    label = f"账号「{display_name}」"
    return AssignTarget(directory=directory, label=label)


def move_sources_to_assign_target(
    source_paths: Iterable[Path],
    target_dir: Path,
    *,
    skip_if_already_in_target: bool = True,
) -> int:
    """将源文件移动到目标目录；重名时自动追加 `` (1)`` 等后缀。

    若 ``skip_if_already_in_target`` 为 True，源与目标为同一路径时跳过（避免同目录无意义重命名）。
    返回成功移动的文件数量。
    """
    moved = 0
    touched_bucket_dirs: Set[Path] = set()
    for src in source_paths:
        if not src.exists():
            continue
        dst = target_dir / src.name
        if skip_if_already_in_target:
            try:
                if src.resolve() == dst.resolve():
                    continue
            except OSError:
                pass
        if dst.exists():
            stem = dst.stem
            suffix = dst.suffix
            idx = 1
            while True:
                candidate = target_dir / f"{stem} ({idx}){suffix}"
                if not candidate.exists():
                    dst = candidate
                    break
                idx += 1
        try:
            shutil.move(str(src), str(dst))
            moved += 1
            touched_bucket_dirs.add(src.parent)
            touched_bucket_dirs.add(target_dir)
        except Exception as e:
            logger.warning("移动素材文件失败: %s -> %s (%s)", src, dst, e, exc_info=True)
    if moved > 0:
        try:
            from src.services.material.media_library_stats_service import get_media_library_stats_service
            from src.ui.utils.async_helper import run_async_from_ui

            svc = get_media_library_stats_service()
            svc.invalidate_bucket_paths(touched_bucket_dirs, kinds=("video",))
            run_async_from_ui(lambda: svc.refresh(min_interval_seconds=0))
        except Exception:
            logger.debug("移动视频后刷新媒体库统计失败", exc_info=True)
    return moved


def move_folder_to_assign_target(
    source_folder: Path,
    target_dir: Path,
) -> bool:
    """将整个图片文件夹移动到目标目录下（保持文件夹名称，重名自动追加序号）。

    图文任务中，一个文件夹对应一篇图文的全部素材，需整体移入账号的「图文/未发布」目录，
    而不是将图片散开铺平。

    Args:
        source_folder: 源图片文件夹路径（如 ``图片库/旅行素材``）。
        target_dir:    目标账号「图文/未发布」目录（文件夹将作为其子目录落入）。

    Returns:
        True 表示移动成功，False 表示失败（已记录日志）。
    """
    if not source_folder.exists() or not source_folder.is_dir():
        logger.warning("源图片文件夹不存在或不是目录: %s", source_folder)
        return False

    dst = target_dir / source_folder.name
    if dst.exists():
        stem = source_folder.name
        idx = 1
        while True:
            candidate = target_dir / f"{stem} ({idx})"
            if not candidate.exists():
                dst = candidate
                break
            idx += 1

    try:
        shutil.move(str(source_folder), str(dst))
        try:
            from src.services.material.media_library_stats_service import get_media_library_stats_service
            from src.ui.utils.async_helper import run_async_from_ui

            svc = get_media_library_stats_service()
            svc.invalidate_bucket_paths(
                [source_folder.parent, target_dir],
                kinds=("image",),
            )
            run_async_from_ui(lambda: svc.refresh(min_interval_seconds=0))
        except Exception:
            logger.debug("移动图文文件夹后刷新媒体库统计失败", exc_info=True)
        return True
    except Exception as e:
        logger.warning("移动图片文件夹失败: %s -> %s (%s)", source_folder, dst, e, exc_info=True)
        return False


def distribute_folders_to_targets_grouped(
    folders: List[Path],
    targets: List["AssignTarget"],
    strategy: "Any",
) -> "Dict[AssignTarget, List[Path]]":
    """以文件夹为粒度，将图片文件夹列表按策略分配到各目标账号。

    每个文件夹作为一个整体分配给一个账号（不拆散文件夹内的图片）。
    分配策略（轮流/随机/平均）作用于文件夹粒度。

    Args:
        folders:  待分配的图片文件夹路径列表（来自图片库列表的选中项）。
        targets:  分配目标列表（AssignTarget，含目标目录和展示标签）。
        strategy: 分配策略枚举（AssignStrategy）。

    Returns:
        有序 dict：{AssignTarget: [文件夹路径列表]}。
    """
    from src.infrastructure.common.media_assign_strategy import distribute_items_to_targets

    if not folders or not targets:
        return {}

    pairs = distribute_items_to_targets(folders, targets, strategy)

    result: Dict[Any, List[Path]] = {t: [] for t in targets}
    for folder, target in pairs:
        result[target].append(folder)
    return result


def scan_video_library_entries(
    root: Path,
    extensions: Set[str],
) -> Tuple[List[VideoLibraryScanEntry], Optional[str]]:
    """枚举「视频库」根目录及各账号 / 账号组「视频/未发布」下的视频文件。

    返回 ``(条目列表, 错误提示)``；成功时错误为 None。
    """
    video_dir = root / MaterialLibraryManager.VIDEO_FOLDER_NAME
    account_lib = MaterialLibraryManager.account_library_root(root)
    if not video_dir.exists():
        return [], "未找到「视频库」目录，请在设置中重新选择媒体库路径。"

    entries: List[VideoLibraryScanEntry] = []
    ext_lower = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}

    def append_from_dir(target_dir: Path, owner: str) -> None:
        if not target_dir.exists():
            return
        for item in os.scandir(str(target_dir)):
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
                    owner_label=owner,
                    size_bytes=size_b,
                    mtime=mtime,
                )
            )

    append_from_dir(video_dir, UNASSIGNED_OWNER_LABEL)

    if account_lib.exists():
        for item in os.scandir(str(account_lib)):
            if not item.is_dir():
                continue
            owner = MaterialLibraryManager.owner_label_for_account_library_entry(item.name)
            unpublished_dir = (
                Path(item.path)
                / MaterialLibraryManager.ACCOUNT_MEDIA_VIDEO_NAME
                / MaterialLibraryManager.UNPUBLISHED_NAME
            )
            append_from_dir(unpublished_dir, owner)

    return entries, None


def scan_image_library_entries(
    root: Path,
    extensions: Set[str],
) -> Tuple[List[ImageLibraryScanEntry], Optional[str]]:
    """枚举公共「图片库」根目录及各账号/账号组「图文/未发布」下的图片文件夹。

    与视频库扫描逻辑对齐：分配到账号后的文件夹仍出现在列表中（归属列显示账号名），
    未分配的文件夹归属显示「未分配」。

    返回 ``(条目列表, 错误提示)``；成功时错误为 None。
    """
    image_dir = root / MaterialLibraryManager.IMAGE_FOLDER_NAME
    account_lib = MaterialLibraryManager.account_library_root(root)
    if not image_dir.exists():
        return [], "未找到「图片库」目录，请在设置中重新选择媒体库路径。"

    entries: List[ImageLibraryScanEntry] = []
    ext_lower = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}

    def count_images_in_folder(folder_path: Path) -> Tuple[int, int, float]:
        """统计文件夹内（一层）图片数量、总大小、最新修改时间。"""
        count = 0
        total_size = 0
        latest_mtime = 0.0
        try:
            for item in os.scandir(str(folder_path)):
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

    def append_folders_from_dir(target_dir: Path, owner: str) -> None:
        """将目标目录下的所有子文件夹作为图片任务条目加入结果。"""
        if not target_dir.exists():
            return
        try:
            for item in os.scandir(str(target_dir)):
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
                        owner_label=owner,
                        size_bytes=total_size,
                        image_count=image_count,
                        mtime=mtime,
                    )
                )
        except OSError:
            pass

    # 公共图片库（未分配）
    append_folders_from_dir(image_dir, UNASSIGNED_OWNER_LABEL)

    # 各账号 / 账号组「图文/未发布」下的图片文件夹（已分配）
    if account_lib.exists():
        try:
            for item in os.scandir(str(account_lib)):
                if not item.is_dir():
                    continue
                owner = MaterialLibraryManager.owner_label_for_account_library_entry(item.name)
                unpublished_dir = (
                    Path(item.path)
                    / MaterialLibraryManager.ACCOUNT_MEDIA_IMAGE_NAME
                    / MaterialLibraryManager.UNPUBLISHED_NAME
                )
                append_folders_from_dir(unpublished_dir, owner)
        except OSError:
            pass

    return entries, None
