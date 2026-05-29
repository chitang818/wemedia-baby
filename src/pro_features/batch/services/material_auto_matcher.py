"""
素材自动匹配模块
文件路径：src/pro_features/batch/services/material_auto_matcher.py
功能：根据账号/账号组自动从视频库（或图文库）按文件名排序依次取素材匹配到批量任务中。

设计目标：
- 当前用于批量视频页面的视频库自动匹配；
- 后续可复用于批量图文页面自动匹配图文库素材（通过 media_type 参数区分）。
"""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.ui.pages.publish.batch_task_definitions import BatchMediaPickStrategy
from src.infrastructure.common.path_utils import normalize_media_path

logger = logging.getLogger(__name__)

_FOLDER_MARKER_PREFIX = "__FOLDER__:"


class MaterialAutoMatcher:
    """素材自动匹配器

    职责：根据选定的账号或账号组，从媒体库的对应目录中按文件名排序依次获取素材，
    自动填充到批量任务的视频列表中。

    匹配规则：
    1. 按文件名（自然排序）依次取，不随机；
    2. 每个账号/账号组独立维护已取索引，避免重复分配；
    3. 素材不足时返回不足信息，由上层 UI 弹窗提醒。
    4. 支持传入 exclude_paths 排除已在发布列表中的文件，避免重复分配。

    可复用设计：
    - media_type="video" → 扫描视频/未发布目录
    - media_type="image" → 扫描图文/未发布目录（预留）
    """

    SUPPORTED_VIDEO_EXTENSIONS = {
        ".mp4", ".avi", ".mov", ".flv", ".mkv", ".wmv", ".m4v", ".webm",
    }
    SUPPORTED_IMAGE_EXTENSIONS = {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    }

    def __init__(self, media_type: str = "video"):
        """
        Args:
            media_type: "video" 或 "image"（预留）
        """
        self._media_type = media_type
        # 记录每个账号/账号组已消费的文件索引 {owner_key: next_index}
        self._consumed_index: Dict[str, int] = {}
        # 发布列表中已占用的文件路径（normpath），匹配时跳过
        self._exclude_paths: set = set()

    @property
    def media_type(self) -> str:
        return self._media_type

    def reset(self) -> None:
        """重置所有已消费索引和排除集（页面清空时调用）。"""
        self._consumed_index.clear()
        self._exclude_paths.clear()

    def reset_owner(self, owner_key: str) -> None:
        """重置某个账号/账号组的已消费索引。"""
        self._consumed_index.pop(owner_key, None)

    def set_exclude_paths(self, paths: set) -> None:
        """设置要排除的文件路径集合（normpath 格式）。

        调用方在匹配前从发布列表查询已占用的 file_path 并传入，
        匹配时这些文件会被跳过，避免同一视频重复分配。
        """
        excludes: set[str] = set()
        for raw in paths or set():
            text = str(raw or "").strip()
            if not text:
                continue
            parts = [p.strip() for p in text.split(",") if p.strip()]
            if not parts:
                parts = [text]
            for part in parts:
                if part.startswith(_FOLDER_MARKER_PREFIX):
                    part = part[len(_FOLDER_MARKER_PREFIX):].strip()
                norm = normalize_media_path(part)
                if norm:
                    excludes.add(norm)
            norm_all = normalize_media_path(text)
            if norm_all:
                excludes.add(norm_all)
        self._exclude_paths = excludes

    # ------------------------------------------------------------------
    # 核心接口：为指定账号/账号组取 N 条素材
    # ------------------------------------------------------------------

    def fetch_materials(
        self,
        account: Dict[str, Any],
        count: int,
        groups: Optional[List[Dict[str, Any]]] = None,
        *,
        strategy: BatchMediaPickStrategy = BatchMediaPickStrategy.SEQUENTIAL,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """为单个账号或账号组从视频库取 count 条素材。

        Args:
            account: 已选账号 dict（含 platform / platform_username / _type / group_id / group_name 等）
            count: 需要取多少条素材
            groups: 所有账号组列表（用于查找账号组详情）
            strategy: 从池内取素材的策略（顺序 / 随机 / 循环），
                      参见 batch_task_definitions.BatchMediaPickStrategy。

        Returns:
            (matched_files, shortage_msg)
            - matched_files: 成功匹配的文件列表（每条含 file_path / file_name / file_size）
            - shortage_msg: 素材不足时的提示文案；充足时为 None
        """
        if count <= 0:
            return [], None

        from src.infrastructure.common.material_library_manager import MaterialLibraryManager

        root = MaterialLibraryManager.get_root_dir()
        if root is None:
            return [], "未配置媒体库路径，请先在「设置」中选择媒小宝媒体库存储位置。"

        owner_key = self._owner_key(account)
        scan_dir = self._resolve_scan_dir(root, account, groups)
        if scan_dir is None or not scan_dir.exists():
            owner_label = self.owner_display_name(account)
            return [], f"{owner_label} 的素材目录不存在，请先在媒体库中分配素材。"

        all_files = self._scan_sorted_files(scan_dir)

        if strategy == BatchMediaPickStrategy.RANDOM:
            candidates = [
                f for f in all_files
                if normalize_media_path(f) not in self._exclude_paths
            ]
            random.shuffle(candidates)
            matched = self._pick_from_candidates(candidates, count)
            self._consumed_index[owner_key] = len(all_files)
        elif strategy == BatchMediaPickStrategy.CYCLIC:
            matched, scan_idx = self._pick_cyclic(
                all_files, count, self._consumed_index.get(owner_key, 0),
            )
            self._consumed_index[owner_key] = scan_idx
        else:
            matched, scan_idx = self._pick_sequential(
                all_files, count, self._consumed_index.get(owner_key, 0),
            )
            self._consumed_index[owner_key] = scan_idx

        shortage_msg = None
        if len(matched) < count:
            shortage_msg = self._build_shortage_msg(account, all_files, count)

        return matched, shortage_msg

    def _build_shortage_msg(
        self, account: Dict[str, Any], all_files: List[str], count: int,
    ) -> str:
        """生成素材不足提示文案。"""
        owner_label = self.owner_display_name(account)
        owner_key = self._owner_key(account)
        scan_idx = self._consumed_index.get(owner_key, 0)
        remaining = sum(
            1 for f in all_files[scan_idx:]
            if normalize_media_path(f) not in self._exclude_paths
        )
        total_on_disk = len(all_files)
        n_excluded = sum(
            1 for f in all_files
            if normalize_media_path(f) in self._exclude_paths
        )
        media_label = "视频" if self._media_type == "video" else "图文"
        parts = [f"{owner_label} 的素材不足：需要 {count} 个"]
        if n_excluded > 0:
            parts.append(
                f"目录中共 {total_on_disk} 个{media_label}，"
                f"其中 {n_excluded} 个已在发布列表中，"
                f"剩余可用 {max(0, remaining)} 个"
            )
        else:
            parts.append(f"仅剩余 {max(0, remaining)} 个可用素材")
        parts.append("请补充素材。")
        return "，".join(parts)

    def _pick_from_candidates(
        self, candidates: List[str], count: int,
    ) -> List[Dict[str, Any]]:
        """从预过滤后的候选列表中顺序取 count 条。"""
        matched: List[Dict[str, Any]] = []
        for fp in candidates:
            if len(matched) >= count:
                break
            matched.append(self._build_media_item(fp))
        return matched

    def _pick_sequential(
        self, all_files: List[str], count: int, start_idx: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """顺序取 count 条，返回 (matched, new_scan_idx)。"""
        matched: List[Dict[str, Any]] = []
        scan_idx = start_idx
        while len(matched) < count and scan_idx < len(all_files):
            fp = all_files[scan_idx]
            scan_idx += 1
            if normalize_media_path(fp) in self._exclude_paths:
                continue
            matched.append(self._build_media_item(fp))
        return matched, scan_idx

    def _pick_cyclic(
        self, all_files: List[str], count: int, start_idx: int,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """循环取 count 条：到达末尾后回到开头继续。"""
        n = len(all_files)
        if n == 0:
            return [], start_idx

        available = [
            (i, f) for i, f in enumerate(all_files)
            if normalize_media_path(f) not in self._exclude_paths
        ]
        if not available:
            return [], start_idx

        matched: List[Dict[str, Any]] = []
        idx_in_available = 0
        for i, (orig_i, _) in enumerate(available):
            if orig_i >= start_idx:
                idx_in_available = i
                break

        for _ in range(count):
            _, fp = available[idx_in_available % len(available)]
            matched.append(self._build_media_item(fp))
            idx_in_available += 1

        last_orig_idx = available[(idx_in_available - 1) % len(available)][0]
        return matched, last_orig_idx + 1

    def get_available_count(
        self,
        account: Dict[str, Any],
        groups: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """查询指定账号/账号组剩余可用素材数量（排除已在发布列表中的文件）。"""
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager

        root = MaterialLibraryManager.get_root_dir()
        if root is None:
            return 0

        owner_key = self._owner_key(account)
        scan_dir = self._resolve_scan_dir(root, account, groups)
        if scan_dir is None or not scan_dir.exists():
            return 0

        all_files = self._scan_sorted_files(scan_dir)
        start_idx = self._consumed_index.get(owner_key, 0)
        return sum(
            1 for f in all_files[start_idx:]
            if normalize_media_path(f) not in self._exclude_paths
        )

    def count_unpublished_on_disk(
        self,
        account: Dict[str, Any],
        groups: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """媒体库「未发布」目录中当前素材文件总数（与扫描规则一致，不受已消费索引影响）。"""
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager

        root = MaterialLibraryManager.get_root_dir()
        if root is None:
            return 0

        scan_dir = self._resolve_scan_dir(root, account, groups)
        if scan_dir is None or not scan_dir.exists():
            return 0

        return len(self._scan_sorted_files(scan_dir))

    def count_material_stats(
        self,
        account: Dict[str, Any],
        groups: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[int, int, int]:
        """返回 (目录视频总数, 发布列表已占用, 可匹配数) 三元组，用于素材库数量提醒展示。"""
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager

        root = MaterialLibraryManager.get_root_dir()
        if root is None:
            return 0, 0, 0

        scan_dir = self._resolve_scan_dir(root, account, groups)
        if scan_dir is None or not scan_dir.exists():
            return 0, 0, 0

        all_files = self._scan_sorted_files(scan_dir)
        total = len(all_files)
        excluded = sum(
            1 for f in all_files
            if normalize_media_path(f) in self._exclude_paths
        )
        return total, excluded, total - excluded

    # ------------------------------------------------------------------
    # 批量匹配：为多个账号 × 多个任务槽一次性分配素材
    # ------------------------------------------------------------------

    def batch_match_for_accounts(
        self,
        accounts: List[Dict[str, Any]],
        tasks_per_account: Dict[str, int],
        groups: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
        """批量为多个账号匹配素材。

        Args:
            accounts: 已选账号列表
            tasks_per_account: {owner_key: 需要的素材数量}
            groups: 账号组列表

        Returns:
            (result_map, shortage_messages)
            - result_map: {owner_key: [匹配到的文件列表]}
            - shortage_messages: 所有不足提示的列表
        """
        result_map: Dict[str, List[Dict[str, Any]]] = {}
        shortage_messages: List[str] = []

        for acc in accounts:
            owner_key = self._owner_key(acc)
            needed = tasks_per_account.get(owner_key, 0)
            if needed <= 0:
                result_map[owner_key] = []
                continue
            matched, msg = self.fetch_materials(acc, needed, groups)
            result_map[owner_key] = matched
            if msg:
                shortage_messages.append(msg)

        return result_map, shortage_messages

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _owner_key(account: Dict[str, Any]) -> str:
        """生成账号/账号组的唯一标识键。"""
        if account.get("_type") == "group":
            return f"group:{account.get('group_id', '')}"
        return f"account:{account.get('id', '')}:{account.get('platform', '')}"

    @staticmethod
    def owner_display_name(account: Dict[str, Any]) -> str:
        """生成用于用户提示的账号/账号组显示名称。"""
        if account.get("_type") == "group":
            return f"账号组「{account.get('group_name', '未命名')}」"
        username = account.get("platform_username") or account.get("account_name") or "未命名"
        return f"账号「{username}」"

    def _resolve_scan_dir(
        self,
        root: Path,
        account: Dict[str, Any],
        groups: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Path]:
        """根据账号类型和 media_type 确定要扫描的目录。"""
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager

        if self._media_type == "video":
            if account.get("_type") == "group":
                group_name = (account.get("group_name") or "").strip()
                if not group_name:
                    return None
                return MaterialLibraryManager.group_video_unpublished_dir(root, group_name)
            else:
                return MaterialLibraryManager.resolve_account_video_unpublished_dir(root, account)
        elif self._media_type == "image":
            if account.get("_type") == "group":
                group_name = (account.get("group_name") or "").strip()
                if not group_name:
                    return None
                return MaterialLibraryManager.group_image_unpublished_dir(root, group_name)
            else:
                return MaterialLibraryManager.resolve_account_image_unpublished_dir(root, account)
        return None

    def _scan_sorted_files(self, directory: Path) -> List[str]:
        """扫描目录下符合条件的素材，按名称排序返回绝对路径列表。

        视频模式返回视频文件；图文模式优先返回含图片的子文件夹，每个文件夹
        作为一篇图文任务的素材包，同时也兼容目录根部的散图文件。
        """
        if not directory.exists():
            return []

        extensions = (
            self.SUPPORTED_VIDEO_EXTENSIONS
            if self._media_type == "video"
            else self.SUPPORTED_IMAGE_EXTENSIONS
        )

        files: List[str] = []
        try:
            for entry in os.scandir(str(directory)):
                if self._media_type == "image" and entry.is_dir():
                    image_paths = self._image_paths_in_folder(entry.path)
                    if image_paths:
                        files.append(os.path.abspath(entry.path))
                    continue
                if not entry.is_file():
                    continue
                suffix = os.path.splitext(entry.name)[1].lower()
                if suffix not in extensions:
                    continue
                files.append(os.path.abspath(entry.path))
        except OSError as e:
            logger.warning("扫描素材目录失败 (%s): %s", directory, e)
            return []

        files.sort(key=lambda p: os.path.basename(p).lower())
        return files

    def _image_paths_in_folder(self, folder_path: str) -> List[str]:
        """返回文件夹内按文件名排序的图片路径（一层，与单图文页保持一致）。"""
        paths: List[str] = []
        try:
            for item in os.scandir(str(folder_path)):
                if not item.is_file():
                    continue
                suffix = os.path.splitext(item.name)[1].lower()
                if suffix in self.SUPPORTED_IMAGE_EXTENSIONS:
                    paths.append(os.path.abspath(item.path))
        except OSError:
            return []
        paths.sort(key=lambda p: os.path.basename(p).lower())
        return paths

    def _build_media_item(self, path: str) -> Dict[str, Any]:
        """将扫描结果转成页面可直接加入 video_list 的素材条目。"""
        if self._media_type == "image" and os.path.isdir(path):
            image_paths = self._image_paths_in_folder(path)
            total_size = 0
            for img in image_paths:
                try:
                    total_size += os.path.getsize(img)
                except OSError:
                    pass
            composite = ",".join([f"{_FOLDER_MARKER_PREFIX}{os.path.abspath(path)}", *image_paths])
            return {
                "file_path": composite,
                "file_name": os.path.basename(path),
                "file_size": total_size,
                "source_folder": os.path.abspath(path),
                "image_count": len(image_paths),
            }
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        return {
            "file_path": os.path.abspath(path),
            "file_name": os.path.basename(path),
            "file_size": size,
        }
