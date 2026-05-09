"""
批量发布 - 发布对象展开模块
文件路径：src/ui/pages/publish/batch_publish_targets.py
功能：将账号选择结果（账号或账号组）展开为扁平的真实平台账号列表。

单条发布与批量发布均需要此逻辑，统一在此模块实现，避免重复。

批量视频页、批量图文页在点击「添加到发布列表」时，需将界面上的
``selected_accounts``（含 ``_type=='group'`` 占位）展开为写库用的真实账号列表，
请使用 `expand_batch_selected_accounts_for_publish`；其与
`generate_batch_tasks_isolated(..., expanded_accounts=...)` 配套使用。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, NamedTuple, Optional

logger = logging.getLogger(__name__)


class BatchSelectedAccountsExpandResult(NamedTuple):
    """`expand_batch_selected_accounts_for_publish` 的返回值。"""

    expanded_accounts: List[Dict[str, Any]]
    """扁平真实账号列表；从组展开的成员带 `_source_group_id`。"""
    empty_group_names: List[str]
    """成员为空的账号组显示名（用于 UI 提示），顺序与遍历顺序一致。"""


async def resolve_batch_publish_targets_to_accounts(
    result: Dict[str, Any],
    *,
    group_service: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """将账号选择结果展开为扁平的真实平台账号列表。

    Args:
        result: AccountSelectionDialog.get_selected_result() 的返回值，格式：
                {'type': 'account', 'data': account | [account, ...]}
                {'type': 'group',   'data': group   | [group, ...]}
        group_service: AccountGroupService 实例（可选）。当账号组 accounts 字段为空时，
                       通过 get_group_by_id 重新查询，防止弹窗未带完整成员数据。

    Returns:
        去重后的真实平台账号列表，每条保持弹窗/数据库原有字段结构不变。
        空列表表示没有有效账号（空组、空选等）。
    """
    if not result:
        return []

    result_type = result.get("type", "")
    data = result.get("data")

    if result_type == "account":
        if data is None:
            return []
        accounts = data if isinstance(data, list) else [data]
        # 浅拷贝避免后续修改影响弹窗内部数据
        return [dict(a) for a in accounts if a]

    if result_type == "group":
        groups = data if isinstance(data, list) else ([data] if data else [])
        return await _expand_groups(groups, group_service=group_service)

    logger.warning("resolve_batch_publish_targets_to_accounts: 未知 result type=%r", result_type)
    return []


async def _expand_groups(
    groups: List[Dict[str, Any]],
    *,
    group_service: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """将多个账号组展开并去重，返回扁平真实账号列表。"""
    seen_ids: set = set()
    flat: List[Dict[str, Any]] = []

    for group in groups:
        if not group:
            continue

        accounts = list(group.get("accounts") or [])

        # 防御：弹窗传入的 group 可能未附带 accounts，尝试通过服务回填
        if not accounts and group_service is not None:
            gid = group.get("id") or group.get("group_id")
            if gid is not None:
                try:
                    full_group = await group_service.get_group_by_id(gid)
                    if full_group:
                        accounts = list(full_group.get("accounts") or [])
                except Exception as exc:
                    logger.warning(
                        "回填账号组成员失败 (group_id=%s): %s", gid, exc, exc_info=True
                    )

        for acc in accounts:
            if not acc:
                continue
            aid = acc.get("id")
            if aid is not None and aid in seen_ids:
                continue
            if aid is not None:
                seen_ids.add(aid)
            flat.append(dict(acc))

    return flat


async def expand_batch_selected_accounts_for_publish(
    selected_accounts: List[Dict[str, Any]],
    *,
    group_service: Optional[Any] = None,
) -> BatchSelectedAccountsExpandResult:
    """将批量任务页已选的账号/账号组占位展开为生成发布任务用的真实账号列表。

    - **独立账号**：原样加入结果列表（与调用方传入同一 dict 引用，便于保持既有行为）。
    - **账号组**（``acc.get("_type") == "group"``）：调用 `resolve_batch_publish_targets_to_accounts`
      解析成员；每个成员做浅拷贝并写入 ``_source_group_id = acc.get("group_id")``，
      供 `generate_batch_tasks_isolated` 与素材隔离逻辑识别来源组。
    - **空组**：不加入任何成员，将 ``acc.get("group_name") or ""`` 记入 ``empty_group_names``。

    Args:
        selected_accounts: 批量页 `selected_accounts`（组占位含 `_group_data` / `group_id` / `group_name`）。
        group_service: 与 `resolve_batch_publish_targets_to_accounts` 相同，用于回填组成员。

    Returns:
        BatchSelectedAccountsExpandResult
    """
    expanded: List[Dict[str, Any]] = []
    empty_group_names: List[str] = []

    for acc in selected_accounts:
        if not acc:
            continue
        if acc.get("_type") == "group":
            group_result = {"type": "group", "data": acc.get("_group_data") or acc}
            members = await resolve_batch_publish_targets_to_accounts(
                group_result, group_service=group_service
            )
            if not members:
                empty_group_names.append(str(acc.get("group_name") or ""))
            else:
                gid = acc.get("group_id")
                for m in members:
                    m_copy = dict(m)
                    m_copy["_source_group_id"] = gid
                    expanded.append(m_copy)
        else:
            expanded.append(acc)

    return BatchSelectedAccountsExpandResult(expanded, empty_group_names)
