"""
批量发布 — 发布任务构建器
文件路径：src/ui/pages/publish/batch_publish_builder.py

将 batch_task_creation_page._on_batch_publish 中「展开 → 生成 → 排除 → 校验 →
去重 → 原创声明剥离」流水线提取为可测试的异步函数。
页面只负责 UI 交互（InfoBar / 按钮灰化 / 导航 / 写库）。

批量视频页与批量图文页均可复用此模块。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.domain.publish.work_declaration import strip_non_wechat_original_declaration
from src.ui.pages.publish.batch_preview_exclusion import PreviewExclusionSet
from src.ui.pages.publish.batch_publish_targets import (
    BatchSelectedAccountsExpandResult,
    expand_batch_selected_accounts_for_publish,
)
from src.ui.pages.publish.batch_task_creation_actions import (
    generate_batch_tasks_isolated,
)
from src.ui.pages.publish.publish_validators import (
    publish_file_missing_error,
    wechat_video_short_title_validation_error,
)

logger = logging.getLogger(__name__)


class PublishBuildResult:
    """``build_publish_tasks_for_batch`` 的返回值。

    Attributes:
        tasks: 经过全部流水线后可写库的任务列表（可能为空）。
        skip_dup_lines: 去重跳过的描述文本列表（用于 UI 提示）。
        empty_group_names: 展开时发现的空账号组名称列表。
        validation_error: 校验失败时的错误信息；为 None 表示校验通过。
    """

    __slots__ = ("tasks", "skip_dup_lines", "empty_group_names", "validation_error")

    def __init__(self) -> None:
        self.tasks: List[Dict[str, Any]] = []
        self.skip_dup_lines: List[str] = []
        self.empty_group_names: List[str] = []
        self.validation_error: Optional[str] = None


def validate_tasks(tasks: List[Dict[str, Any]]) -> Optional[str]:
    """逐任务校验文件是否存在、视频号标题长度。

    Returns:
        首个校验错误描述；全部通过返回 None。
    """
    for t in tasks:
        file_err = publish_file_missing_error(t.get("file_path"))
        if file_err:
            return f"{t.get('file_path', '?')}: {file_err}"
        err = wechat_video_short_title_validation_error(
            t.get("platform", ""), t.get("title"),
        )
        if err:
            return err
    return None


async def build_publish_tasks_for_batch(
    selected_accounts: List[Dict[str, Any]],
    video_list: List[Dict[str, Any]],
    time_slots: List[Optional[str]],
    common_fields: Dict[str, Any],
    immediate_publish: bool,
    exclusion: PreviewExclusionSet,
    *,
    user_id: int = 1,
    group_service: Optional[Any] = None,
    publish_record_repo: Optional[Any] = None,
    file_type: str = "video",
) -> PublishBuildResult:
    """执行批量发布任务的完整构建流水线。

    流水线步骤：
      1. 账号组展开
      2. 任务生成（generate_batch_tasks_isolated）
      3. 排除过滤（与预览一致）
      4. 逐任务校验（文件存在 + 标题长度）
      5. 去重守卫（可选，需传入 publish_record_repo）
      6. 作品申明字段按平台裁剪（仅保留各任务对应平台的申明键）

    Args:
        selected_accounts: 批量页已选账号列表（含账号组占位）。
        video_list: 视频列表（append 顺序 = 分配顺序）。
        time_slots: 发布时间槽列表；元素为 None 时表示该槽「立即发布」。
        common_fields: ``_collect_common_fields()`` 的输出。
        immediate_publish: 是否立即发布。
        exclusion: 预览排除集。
        user_id: 当前用户 ID。
        group_service: 账号组服务（用于展开组成员）。
        publish_record_repo: PublishRecordRepositoryAsync 实例。
            为 None 时跳过去重步骤。

    Returns:
        PublishBuildResult
    """
    result = PublishBuildResult()

    # Step 1: 展开账号组
    expand_res: BatchSelectedAccountsExpandResult = (
        await expand_batch_selected_accounts_for_publish(
            selected_accounts, group_service=group_service,
        )
    )
    result.empty_group_names = expand_res.empty_group_names
    expanded = expand_res.expanded_accounts

    if not expanded:
        return result

    # Step 2: 生成任务
    raw = generate_batch_tasks_isolated(
        selected_accounts,
        video_list,
        time_slots,
        common_fields,
        file_type,
        expanded_accounts=expanded,
        immediate_publish=immediate_publish,
    )

    # Step 3: 排除过滤
    tasks = [t for t in raw if not exclusion.is_task_excluded(t)]
    if not tasks:
        return result

    # Step 4: 校验
    err = validate_tasks(tasks)
    if err:
        result.validation_error = err
        return result

    # Step 5: 去重
    if publish_record_repo is not None:
        from src.ui.pages.publish.publish_duplicate_guard import (
            partition_batch_publish_tasks_by_duplicates,
        )
        tasks, skip_lines = await partition_batch_publish_tasks_by_duplicates(
            publish_record_repo, user_id, tasks,
        )
        result.skip_dup_lines = skip_lines
        if not tasks:
            result.tasks = []
            return result

    # Step 6: privacy_settings 申明字段按平台裁剪
    strip_non_wechat_original_declaration(tasks)

    result.tasks = tasks
    return result
