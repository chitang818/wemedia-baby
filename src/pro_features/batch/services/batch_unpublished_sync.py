"""
批量发布 - 待发布素材同步核心
文件路径：src/pro_features/batch/services/batch_unpublished_sync.py

与 Qt / UI 完全解耦：输入为数据结构，输出为 SyncOutcome 数据类。
批量视频页与批量图文页均可复用，仅需传入对应的 media_type。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SyncOutcome:
    """素材同步结果。

    Attributes:
        new_items:         新增素材列表，每条含 file_path / file_name / file_size。
        shortage_messages: 素材不足（目录有文件但数量 < 时间槽数）的提示文案列表。
        empty_owner_labels: 目录中完全没有可用素材的账号显示名称列表。
    """

    new_items: List[Dict[str, Any]] = field(default_factory=list)
    shortage_messages: List[str] = field(default_factory=list)
    empty_owner_labels: List[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.shortage_messages or self.empty_owner_labels)

    def build_dialog_message(self, media_type: str = "video") -> str:
        """拼接用于弹窗展示的完整提示文案。"""
        media_label = "视频" if media_type == "video" else "图文"
        parts: List[str] = []
        if self.empty_owner_labels:
            lines = "\n".join(f"· {x}" for x in self.empty_owner_labels)
            parts.append(
                f"以下账号在媒体库「{media_label}/未发布」目录中暂无可用素材，"
                "请先在媒体库分配或移入素材：\n" + lines
            )
        if self.shortage_messages:
            parts.append("\n".join(self.shortage_messages))
        return "\n\n".join(parts)

    def dialog_title(self) -> str:
        """推断弹窗标题（仅有空目录 → 「待发布目录无素材」；有不足信息 → 「素材提示」）。"""
        if self.empty_owner_labels and not self.shortage_messages:
            return "待发布目录无素材"
        return "素材提示"


def sync_unpublished_for_accounts(
    accounts: List[Dict[str, Any]],
    matcher: Any,
    existing_paths: set,
    n_needed: int,
    groups: Optional[List[Dict[str, Any]]] = None,
) -> SyncOutcome:
    """为多个平台账号批量拉取「未发布」目录素材。

    与 UI / asyncio 完全无关。上层页面负责：
    1. 调用本函数取 SyncOutcome；
    2. 遍历 ``outcome.new_items`` 并 await 解析 title / desc，append 到 media_list；
    3. 若 ``outcome.has_issues``，调用页面弹窗展示 ``outcome.build_dialog_message()``。

    Args:
        accounts:       已选平台账号列表（不含账号组占位）。
        matcher:        MaterialAutoMatcher 实例（已按当前 media_type 初始化）。
        existing_paths: 当前已加载素材的 file_path 集合，用于去重。
        n_needed:       每个账号需取的素材数（通常为 max(1, len(time_slots))）。
        groups:         账号组列表，供 matcher 内部路径解析使用。

    Returns:
        SyncOutcome：新增素材条目及提示信息。
    """
    outcome = SyncOutcome()

    for acc in accounts:
        avail = matcher.get_available_count(acc, groups)
        if avail <= 0:
            outcome.empty_owner_labels.append(matcher.owner_display_name(acc))
            continue

        matched, msg = matcher.fetch_materials(acc, n_needed, groups)
        if msg:
            outcome.shortage_messages.append(msg)

        for m in matched:
            fp = m["file_path"]
            if fp not in existing_paths:
                outcome.new_items.append(m)
                existing_paths.add(fp)

    return outcome


def auto_match_for_accounts(
    accounts: List[Dict[str, Any]],
    matcher: Any,
    existing_paths: set,
    n_needed: int,
    groups: Optional[List[Dict[str, Any]]] = None,
) -> SyncOutcome:
    """「自动从媒体库匹配」模式（开关开启时）的素材拉取。

    与 ``sync_unpublished_for_accounts`` 的区别：不区分「无素材」与「素材不足」，
    统一走 fetch_materials 并汇总 shortage_messages（账号目录不存在时由 matcher 返回提示）。

    Args:
        accounts:       已选账号列表（含账号组占位，matcher 内部会按 _type 处理路径）。
        matcher:        MaterialAutoMatcher 实例。
        existing_paths: 当前已加载素材 file_path 集合，去重用。
        n_needed:       每个账号需取的素材数。
        groups:         账号组列表。

    Returns:
        SyncOutcome：新增条目及不足提示（empty_owner_labels 不使用，保持为空）。
    """
    outcome = SyncOutcome()

    for acc in accounts:
        matched, msg = matcher.fetch_materials(acc, n_needed, groups)
        if msg:
            outcome.shortage_messages.append(msg)
        for m in matched:
            fp = m["file_path"]
            if fp not in existing_paths:
                outcome.new_items.append(m)
                existing_paths.add(fp)

    return outcome
