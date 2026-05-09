"""
批量发布 — 预览排除集
文件路径：src/ui/pages/publish/batch_preview_exclusion.py

将 batch_task_creation_page 中三套并行排除集抽为独立数据类，
供 batch_preview_builder / batch_publish_builder / 页面共用。

三种排除模式对应预览的四个分支（见 _refresh_preview）：
  1. fingerprint (fp)      — 有账号 + 有视频/时间
  2. media_time             — 仅有视频/时间、无账号（占位行）
  3. account                — 仅有账号、无视频/时间
  4. 空                     — 无数据时不产出行，无排除
"""

from __future__ import annotations

from typing import Any, Dict, Set, Tuple

from src.ui.pages.publish.batch_task_creation_actions import batch_task_fingerprint
from src.ui.pages.publish.batch_task_definitions import BatchTaskFingerprint


class PreviewExclusionSet:
    """封装批量预览的三套排除集与删除行分派逻辑。

    生命周期与批量页面一致：在 ``_reset_all`` 时调用 ``clear()``。
    """

    def __init__(self) -> None:
        self._excluded_keys: Set[BatchTaskFingerprint] = set()
        self._excluded_media_time: Set[Tuple[str, str]] = set()
        self._excluded_accounts: Set[Tuple[str, str]] = set()

    # ---- 查询 ----

    def is_task_excluded(self, task: Dict[str, Any]) -> bool:
        """判断一条 generate_batch_tasks(_isolated) 产出的任务 dict 是否应被排除。

        依次检查三种排除集（与原 _preview_task_is_excluded 逻辑一致）。
        """
        fp = batch_task_fingerprint(task)
        if fp in self._excluded_keys:
            return True
        path = str(task.get("file_path") or "")
        st = str(task.get("scheduled_publish_time") or "")
        if (path, st) in self._excluded_media_time:
            return True
        plat = str(task.get("platform") or "")
        user = str(task.get("platform_username") or "")
        if (plat, user) in self._excluded_accounts:
            return True
        return False

    def is_media_time_excluded(self, path: str, time_str: str) -> bool:
        """占位行（无账号）的排除检查。"""
        return (path, time_str) in self._excluded_media_time

    def is_account_excluded(self, platform: str, username: str) -> bool:
        """仅有账号占位行的排除检查。"""
        return (platform, username) in self._excluded_accounts

    # ---- 记录删除 ----

    def record_deletion(self, row_spec: Dict[str, Any]) -> bool:
        """根据 _preview_delete_row_specs 中的一条 spec 记录排除。

        Args:
            row_spec: ``{"mode": "fp"|"media_time"|"account", ...}``

        Returns:
            是否成功记录（mode 无效时返回 False）。
        """
        mode = row_spec.get("mode")
        if mode == "fp":
            self._excluded_keys.add(row_spec["fp"])
            return True
        if mode == "media_time":
            self._excluded_media_time.add((row_spec["path"], row_spec["time"]))
            return True
        if mode == "account":
            self._excluded_accounts.add((row_spec["platform"], row_spec["username"]))
            return True
        return False

    # ---- 直接操作（兼容页面现有代码逐步迁移） ----

    def add_excluded_key(self, fp: BatchTaskFingerprint) -> None:
        self._excluded_keys.add(fp)

    def add_excluded_media_time(self, path: str, time_str: str) -> None:
        self._excluded_media_time.add((path, time_str))

    def add_excluded_account(self, platform: str, username: str) -> None:
        self._excluded_accounts.add((platform, username))

    # ---- 生命周期 ----

    def clear(self) -> None:
        """重置所有排除集（页面 _reset_all 时调用）。"""
        self._excluded_keys.clear()
        self._excluded_media_time.clear()
        self._excluded_accounts.clear()

    # ---- 调试 ----

    @property
    def total_excluded_count(self) -> int:
        return (
            len(self._excluded_keys)
            + len(self._excluded_media_time)
            + len(self._excluded_accounts)
        )

    def __repr__(self) -> str:
        return (
            f"PreviewExclusionSet("
            f"keys={len(self._excluded_keys)}, "
            f"media_time={len(self._excluded_media_time)}, "
            f"accounts={len(self._excluded_accounts)})"
        )
