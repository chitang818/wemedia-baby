"""
批量发布 — 预览任务构建器
文件路径：src/ui/pages/publish/batch_preview_builder.py

将 batch_task_creation_page._refresh_preview 中的核心数据生成逻辑
抽为纯函数，页面仅负责表格渲染与 UI 状态更新。

标准三步流程对应四状态：
  1. full     — 账号 + 时间 + 视频均已配置 → generate_batch_tasks_isolated
  2. no_video — 有账号 + 有时间，尚无视频 → 按时间数生成占位行
  3. no_time  — 有账号，尚未配置时间 → 每个已选账号一行占位（时间/文件为待配置）
  4. empty    — 未选账号 → 空表，文案提示
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from src.ui.pages.publish.batch_preview_exclusion import PreviewExclusionSet
from src.ui.pages.publish.batch_task_creation_actions import (
    batch_task_fingerprint,
    generate_batch_tasks_isolated,
)


class PreviewBuildResult:
    """``build_preview_tasks`` 的返回值，供页面消费。

    Attributes:
        branch: 当前所处的预览状态（"full" / "no_video" / "no_time" / "empty"）。
        tasks: branch=="full" 时经排除过滤后的任务 dict 列表；其它状态为空列表。
        no_video_placeholder_rows: branch=="no_video" 时的占位任务 dict 列表（含时间、账号信息，视频"待配置"）。
        no_time_placeholder_rows: branch=="no_time" 时的占位任务 dict（每账号一行，时间待配置）。
        status_text: 统计面板状态文案。
        n_preview: 最终可见预览行数。
        n_acc: 已选账号数。
        n_vid: 已选视频数。
        n_time: 已选时间数。
        time_pill_text: 时间胶囊文案（"立即发布" 或 None）。
        row_specs: 每可见行对应的删除 spec（供 _preview_delete_row_specs）。
        video_path_hints: 每可见行对应的 normalized 视频路径（或 None）。
    """

    __slots__ = (
        "branch", "tasks", "no_video_placeholder_rows", "no_time_placeholder_rows",
        "status_text", "n_preview", "n_acc", "n_vid", "n_time",
        "time_pill_text", "row_specs", "video_path_hints",
    )

    def __init__(self) -> None:
        self.branch: str = "empty"
        self.tasks: List[Dict[str, Any]] = []
        self.no_video_placeholder_rows: List[Dict[str, Any]] = []
        self.no_time_placeholder_rows: List[Dict[str, Any]] = []
        self.status_text: str = ""
        self.n_preview: int = 0
        self.n_acc: int = 0
        self.n_vid: int = 0
        self.n_time: int = 0
        self.time_pill_text: Optional[str] = None
        self.row_specs: List[Dict[str, Any]] = []
        self.video_path_hints: List[Optional[str]] = []


def _norm_video_path(task_or_item: Dict[str, Any]) -> Optional[str]:
    """从任务/视频 dict 中提取 normalized 视频路径，无效时返回 None。"""
    raw = (task_or_item.get("file_path") or "").strip()
    if not raw or "待配置" in raw:
        return None
    np = os.path.normpath(raw)
    return np or raw


def _no_video_mock_media_items(
    selected_accounts: List[Dict[str, Any]],
    n_time: int,
) -> List[Dict[str, Any]]:
    """无视频时供 generate_batch_tasks_isolated 使用的占位媒体列表。

    账号组：每条占位须带对应 ``_group_id``，否则隔离逻辑筛不到视频、只会退化为补 1 行。
    独立账号：顺序块分配需要 ``n_time * 账号数`` 条占位，才能得到「每账号 × 每时间槽」行数。
    """
    if n_time <= 0:
        return [{"file_path": "待配置"}]
    groups = [a for a in selected_accounts if a.get("_type") == "group"]
    plains = [a for a in selected_accounts if a.get("_type") != "group"]
    out: List[Dict[str, Any]] = []
    for g in groups:
        gid = g.get("group_id")
        for _ in range(n_time):
            row: Dict[str, Any] = {"file_path": "待配置"}
            if gid is not None:
                row["_group_id"] = gid
            out.append(row)
    for _ in range(n_time * len(plains)):
        out.append({"file_path": "待配置"})
    return out


def build_preview_tasks(
    selected_accounts: List[Dict[str, Any]],
    video_list: List[Dict[str, Any]],
    time_slots: List[Optional[str]],
    common_fields: Dict[str, Any],
    immediate_publish: bool,
    exclusion: PreviewExclusionSet,
    *,
    file_type: str = "video",
    media_label: str = "视频",
) -> PreviewBuildResult:
    """根据当前选择状态生成预览数据（纯函数，不涉及 UI）。

    标准三步流程：①选账号 → ②配置时间 → ③添加视频。
    各步骤完成情况决定 branch 状态，页面据此渲染表格与状态文案。

    Args:
        selected_accounts: 已选账号（含账号组占位）。
        video_list: 已选视频列表（append 顺序 = 分配顺序）。
        time_slots: 已选发布时间。
        common_fields: ``_collect_common_fields()`` 的输出。
        immediate_publish: 是否立即发布。
        exclusion: 预览排除集实例。

    Returns:
        PreviewBuildResult — 页面用于渲染表格与统计面板。
    """
    result = PreviewBuildResult()
    n_acc = len(selected_accounts)
    n_vid = len(video_list)
    n_time = len(time_slots)
    imm = immediate_publish

    result.n_acc = n_acc
    result.n_vid = n_vid
    result.n_time = n_time
    has_imm_slot = any(s is None for s in time_slots) if time_slots else False
    has_sched_slot = any(
        isinstance(s, str) and str(s).strip() for s in time_slots
    ) if time_slots else False
    if imm:
        result.time_pill_text = "立即发布"
    elif has_imm_slot and has_sched_slot:
        result.time_pill_text = "定时+立即"
    elif has_imm_slot:
        result.time_pill_text = "立即发布"
    else:
        result.time_pill_text = None

    common_ps = common_fields.get("privacy_settings") or "{}"

    # ---- 状态 4: empty — 未选账号 ----
    if n_acc == 0:
        result.branch = "empty"
        result.status_text = "请先①选择账号"
        logger.info(
            "[batch_preview] branch=empty n_preview=0 n_acc=0 n_time=0 n_vid=0"
        )
        return result

    # ---- 状态 3: no_time — 有账号，未配置时间（立即发布未勾选且无时间槽）----
    if not imm and n_time == 0:
        result.branch = "no_time"
        result.status_text = "请②配置发布时间"
        # 表格仍展示已选账号占位行，避免选完账号后预览区空白
        rows: List[Dict[str, Any]] = []
        for acc in selected_accounts:
            plat_u = str(acc.get("platform") or "")
            user_u = str(acc.get("platform_username") or "")
            if exclusion.is_account_excluded(plat_u, user_u):
                continue
            syn: Dict[str, Any] = {
                "platform": plat_u,
                "platform_username": user_u,
                "file_path": "待配置",
                "scheduled_publish_time": "待配置",
                "title": common_fields.get("title", "") or "",
                "description": common_fields.get("description", "") or "",
                "privacy_settings": common_ps,
                "cart_info": common_fields.get("cart_info", "") or "",
                "anchor_info": common_fields.get("anchor_info", "") or "",
                "poi_info": common_fields.get("poi_info", ""),
                "wechat_empty_location_open_picker": common_fields.get(
                    "wechat_empty_location_open_picker"
                ),
                "platform_account_id": acc.get("id"),
                # 供页面「作品申明」占位列判断账号组
                "_type": acc.get("_type"),
                "_group_data": acc.get("_group_data") if acc.get("_type") == "group" else None,
            }
            if not exclusion.is_task_excluded(syn):
                rows.append(syn)
        result.no_time_placeholder_rows = rows
        result.n_preview = len(rows)
        for t in rows:
            result.row_specs.append({"mode": "fp", "fp": batch_task_fingerprint(t)})
            result.video_path_hints.append(None)
        logger.info(
            "[batch_preview] branch=no_time n_preview=%d n_acc=%d n_time=0 n_vid=%d "
            "(已选账号占位行，待配置时间)",
            result.n_preview, n_acc, n_vid,
        )
        return result

    # ---- 状态 2: no_video — 有账号+时间，未添加视频 ----
    if n_vid == 0:
        result.branch = "no_video"
        result.status_text = f"请③添加{media_label}"

        mock_videos = _no_video_mock_media_items(selected_accounts, n_time)
        mock_time = (
            time_slots
            if n_time > 0
            else ([] if imm else ["待配置"])
        )

        raw = generate_batch_tasks_isolated(
            selected_accounts, mock_videos, mock_time, common_fields, file_type,
            expanded_accounts=None,
            immediate_publish=imm,
        )

        # 确保每个账号至少出现一行
        represented = {
            (t.get("platform", ""), t.get("platform_username", ""))
            for t in raw
        }
        for acc in selected_accounts:
            acc_key = (acc.get("platform", ""), acc.get("platform_username", ""))
            if acc_key not in represented:
                _fallback_sched: Optional[str]
                if mock_time:
                    _fallback_sched = mock_time[0]
                elif imm:
                    _fallback_sched = None
                else:
                    _fallback_sched = "待配置"
                raw.append({
                    "platform": acc.get("platform", ""),
                    "platform_username": acc.get("platform_username", ""),
                    "file_path": "待配置",
                    "scheduled_publish_time": _fallback_sched,
                    "title": common_fields.get("title", "") or "",
                    "description": common_fields.get("description", "") or "",
                    "privacy_settings": common_ps,
                    "cart_info": common_fields.get("cart_info", "") or "",
                    "anchor_info": common_fields.get("anchor_info", "") or "",
                    "poi_info": common_fields.get("poi_info", ""),
                    "wechat_empty_location_open_picker": common_fields.get(
                        "wechat_empty_location_open_picker"
                    ),
                    "platform_account_id": acc.get("id"),
                })
                represented.add(acc_key)

        placeholder_rows = [t for t in raw if not exclusion.is_task_excluded(t)]
        result.no_video_placeholder_rows = placeholder_rows
        result.n_preview = len(placeholder_rows)

        for t in placeholder_rows:
            result.row_specs.append(
                {"mode": "fp", "fp": batch_task_fingerprint(t)}
            )
            result.video_path_hints.append(None)

        logger.info(
            "[batch_preview] branch=no_video n_preview=%d n_acc=%d n_time=%d n_vid=0",
            result.n_preview, n_acc, n_time,
        )
        return result

    # ---- 状态 1: full — 账号 + 时间 + 视频均已配置 ----
    result.branch = "full"

    raw = generate_batch_tasks_isolated(
        selected_accounts, video_list, time_slots, common_fields, file_type,
        expanded_accounts=None,
        immediate_publish=imm,
    )

    # 确保每个账号至少出现一行（视频不足时补占位）
    represented = {
        (t.get("platform", ""), t.get("platform_username", ""))
        for t in raw
    }
    mock_time = (
        time_slots
        if n_time > 0
        else ([] if imm else ["待配置"])
    )
    for acc in selected_accounts:
        acc_key = (acc.get("platform", ""), acc.get("platform_username", ""))
        if acc_key not in represented:
            _fb_sched: Optional[str]
            if mock_time:
                _fb_sched = mock_time[0]
            elif imm:
                _fb_sched = None
            else:
                _fb_sched = "待配置"
            raw.append({
                "platform": acc.get("platform", ""),
                "platform_username": acc.get("platform_username", ""),
                "file_path": "待配置",
                "scheduled_publish_time": _fb_sched,
                "title": common_fields.get("title", "") or "",
                "description": common_fields.get("description", "") or "",
                "privacy_settings": common_ps,
                "cart_info": common_fields.get("cart_info", "") or "",
                "anchor_info": common_fields.get("anchor_info", "") or "",
                "poi_info": common_fields.get("poi_info", ""),
                "wechat_empty_location_open_picker": common_fields.get(
                    "wechat_empty_location_open_picker"
                ),
                "platform_account_id": acc.get("id"),
            })
            represented.add(acc_key)

    tasks = [t for t in raw if not exclusion.is_task_excluded(t)]
    result.tasks = tasks
    result.n_preview = len(tasks)

    for t in tasks:
        result.row_specs.append(
            {"mode": "fp", "fp": batch_task_fingerprint(t)}
        )
        result.video_path_hints.append(_norm_video_path(t))

    logger.info(
        "[batch_preview] branch=full n_preview=%d n_acc=%d n_time=%d n_vid=%d",
        result.n_preview, n_acc, n_time, n_vid,
    )
    return result
