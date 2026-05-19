# pyre-ignore-all-errors
"""
批量发布任务创建 — 任务生成与批量写入发布列表
文件路径：src/ui/pages/publish/batch_task_creation_actions.py

说明：生成的是「待发布任务」记录，实际上传在发布列表页执行。
媒体类型无关的通用接口：视频传 file_type="video"，图文传 file_type="image"。
"""
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def batch_task_fingerprint(task: dict) -> Tuple[str, str, str, str]:
    """任务稳定标识键，用于预览排除/批量发布去重。

    仅依赖「账号 + 文件路径 + 发布时间」，与标题等可变展示字段无关，
    使视频页与图文页均可直接引用，无需各自维护副本。
    """
    return (
        str(task.get("platform") or ""),
        str(task.get("platform_username") or ""),
        str(task.get("file_path") or ""),
        str(task.get("scheduled_publish_time") or ""),
    )


def _task_platform_account_id(account: Dict[str, Any]) -> Optional[int]:
    """从账号 dict 中提取整数 platform_account_id。

    账号组应在进入本模块前已由 batch_publish_targets.expand_batch_selected_accounts_for_publish
    （或等价逻辑）展开为真实平台账号并带上 _source_group_id，故此处 _type == "group" 分支理论上不再触发（保留作防御）。
    """
    if account.get("_type") == "group":
        return None
    aid = account.get("id")
    if isinstance(aid, int):
        return aid
    if isinstance(aid, str) and aid.isdigit():
        return int(aid)
    return None


def generate_batch_tasks(
    accounts: List[Dict[str, Any]],
    media_items: List[Dict[str, Any]],
    time_slots: List[Optional[str]],
    common_fields: Dict[str, Any],
    file_type: str = "video",
    *,
    videos: Optional[List[Dict[str, Any]]] = None,
    replicate_media_per_account: bool = False,
    immediate_publish: bool = False,
) -> List[Dict[str, Any]]:
    """根据账号、媒体文件、时间槽组合生成任务列表。

    默认「顺序块分配」（多选独立账号时）：
    - 按 accounts 列表顺序，依次为每个账号从 media_items 头部连续取出最多 len(time_slots) 条；
    - 每条媒体按顺序绑定 time_slots[0]、time_slots[1]、…（不足则循环取模）；
    - 整份 media_items 只遍历一次，不同平台账号不重复占用同一素材。

    当 replicate_media_per_account=True（发布目标曾含账号组、已展开为成员账号时）：
    - 与单条发布页选账号组一致：每个账号都分配全部媒体（每条素材绑定 time_slots[视频下标 % len(time_slots)]）；
    - 任务数为 len(accounts) * len(media_items)。

    Args:
        accounts:    已选真实平台账号列表（账号组须事先展开）。
        media_items: 已导入媒体文件列表，每条含 file_path / file_name。
                     等效于旧参数名 ``videos``，图文也使用同一格式。
        time_slots:  发布时间点列表，格式 "yyyy-MM-dd HH:mm"；元素为 None 时表示该槽位「立即发布」
            （scheduled_publish_time 为 None）。与 immediate_publish=True 二选一：后者等价于单槽 [None]。
        common_fields: 公共字段 dict，含 user_id / title / description / tags_str /
                       cover_path / privacy_settings 等。
        file_type:   媒体类型，"video" 或 "image"，写入 publish_record 的 file_type 字段。
        videos:      旧参数名兼容传入（与 media_items 互斥，优先使用 media_items）。
        replicate_media_per_account: 为 True 时对每个账号复制整套媒体列表。
        immediate_publish: 为 True 时与单条「立即发布」一致：每条任务的 scheduled_publish_time 为 None，
            不按 time_slots 定时；分配规则与仅有一条「虚拟时间槽」时相同。

    Returns:
        待写入的任务字典列表。
    """
    # 旧参数名兼容
    if videos is not None and not media_items:
        media_items = videos

    n_acc = len(accounts)
    n_med = len(media_items)
    n_time = len(time_slots)

    if n_acc == 0 or n_med == 0:
        return []
    if not immediate_publish and n_time == 0:
        return []

    if immediate_publish:
        slot_cycle = [None]
        n_cycle = 1
    else:
        slot_cycle = list(time_slots)
        n_cycle = len(slot_cycle)

    tasks: List[Dict[str, Any]] = []

    if replicate_media_per_account:
        for acc in accounts:
            for vi, med in enumerate(media_items):
                t_slot = slot_cycle[vi % n_cycle]
                tasks.append(_build_task(acc, med, t_slot, common_fields, file_type))
        return tasks

    m_idx = 0
    for acc in accounts:
        for ti in range(n_cycle):
            if m_idx >= n_med:
                break
            med = media_items[m_idx]
            m_idx += 1
            t_slot = slot_cycle[ti % n_cycle]
            tasks.append(_build_task(acc, med, t_slot, common_fields, file_type))

    return tasks


def _build_task(
    account: dict,
    media_item: dict,
    scheduled_time: Optional[str],
    common: dict,
    file_type: str = "video",
) -> dict:
    """组装单条任务字典（视频与图文通用）。"""
    item_title = (media_item.get("title") or "").strip()
    item_desc = (media_item.get("description") or "").strip()
    # 账号带有 _source_group_id 说明是由账号组展开而来，任务源为 group；否则为 account
    task_source = "group" if account.get("_source_group_id") is not None else "account"
    # group_id：账号组任务写入账号的 group_id，供发布后文件整理直接使用（避免多跳查询）
    group_id: Optional[int] = None
    if task_source == "group":
        raw_gid = account.get("group_id") or account.get("_source_group_id")
        if raw_gid is not None:
            try:
                group_id = int(raw_gid)
            except (TypeError, ValueError):
                group_id = None
    return {
        "user_id": common.get("user_id", 1),
        "platform_username": account.get("platform_username", ""),
        "platform": account.get("platform", "douyin"),
        "platform_account_id": _task_platform_account_id(account),
        "group_id": group_id,
        "file_path": media_item.get("file_path", ""),
        "file_type": file_type,
        "title": item_title or common.get("title", ""),
        "description": item_desc or common.get("description", ""),
        "tags": (media_item.get("tags") or "").strip() or common.get("tags_str", ""),
        "cover_path": common.get("cover_path") or None,
        "poi_info": common.get("poi_info", ""),
        "wechat_empty_location_open_picker": common.get(
            "wechat_empty_location_open_picker"
        ),
        "micro_app_info": common.get("micro_app_info", ""),
        "cart_info": common.get("cart_info", ""),
        "anchor_info": common.get("anchor_info", ""),
        "privacy_settings": common.get("privacy_settings", ""),
        "scheduled_publish_time": scheduled_time,
        "task_source": task_source,
    }


def _video_list_has_account_isolation(video_list: List[Dict[str, Any]]) -> bool:
    """判断视频列表中是否存在按账号隔离的标记（_assigned_account_id 或 _group_id）。

    只要有至少一条视频带有隔离标记，就启用隔离分配模式。
    手动导入的视频（无任何标记）在隔离模式下作为「共享视频」处理。
    """
    return any(
        v.get("_assigned_account_id") is not None or v.get("_group_id") is not None
        for v in video_list
    )


def generate_batch_tasks_isolated(
    selected_accounts: List[Dict[str, Any]],
    video_list: List[Dict[str, Any]],
    time_slots: List[Optional[str]],
    common_fields: Dict[str, Any],
    file_type: str = "video",
    *,
    expanded_accounts: Optional[List[Dict[str, Any]]] = None,
    immediate_publish: bool = False,
) -> List[Dict[str, Any]]:
    """隔离分配模式下生成任务列表（账号组和独立账号均支持）。

    统一规则：
    - 带 _group_id 的视频只分配给对应账号组的成员；
    - 带 _assigned_account_id 的视频只分配给对应的独立账号（1对1）；
    - 无任何标记的视频（手动导入）作为「共享视频池」，在无专属视频的账号/组间顺序块分配；
    - 若视频列表中没有任何隔离标记，退化为原来的整体顺序块分配（无账号组时）或
      全量复制分配（有账号组时），保持向后兼容。

    Args:
        selected_accounts:  原始选择列表（含账号组占位 _type=group 和独立账号）。
        video_list:         已导入视频列表，可含 _group_id / _assigned_account_id 字段。
        time_slots:         发布时间槽列表；None 表示该槽为立即发布。
        common_fields:      公共字段 dict。
        file_type:          媒体类型。
        expanded_accounts:  已展开的真实账号列表（每条带 _source_group_id 可选字段）；
                            若为 None，则为预览模式（账号组以占位整体展示，独立账号直接使用）。
        immediate_publish:  为 True 时所有任务 scheduled_publish_time 为 None（立即发布）。
    """
    tasks: List[Dict[str, Any]] = []

    group_placeholders = [a for a in selected_accounts if a.get("_type") == "group"]
    plain_selected = [a for a in selected_accounts if a.get("_type") != "group"]
    has_isolation = _video_list_has_account_isolation(video_list)

    if not group_placeholders and not has_isolation:
        # 纯独立账号且视频无隔离标记：走原有顺序块分配（向后兼容）
        accs = expanded_accounts if expanded_accounts is not None else plain_selected
        return generate_batch_tasks(
            accs, video_list, time_slots, common_fields, file_type,
            immediate_publish=immediate_publish,
        )

    seen_account_ids: set = set()

    # ---- 账号组部分：每组只用带自己 _group_id 的视频 ----
    for grp in group_placeholders:
        gid = grp.get("group_id")
        group_videos = [v for v in video_list if v.get("_group_id") == gid]
        if not group_videos:
            continue
        if expanded_accounts is not None:
            grp_members = [
                a for a in expanded_accounts
                if a.get("_source_group_id") == gid and a.get("id") not in seen_account_ids
            ]
            if not grp_members:
                # 兼容旧展开方式（无 _source_group_id）
                gd = grp.get("_group_data") or {}
                member_ids = {m.get("id") for m in gd.get("accounts") or [] if m.get("id") is not None}
                grp_members = [
                    a for a in expanded_accounts
                    if a.get("id") in member_ids and a.get("id") not in seen_account_ids
                ]
        else:
            grp_members = [grp]

        for a in grp_members:
            aid = a.get("id")
            if aid is not None:
                seen_account_ids.add(aid)

        if not grp_members:
            continue

        grp_tasks = generate_batch_tasks(
            grp_members,
            group_videos,
            time_slots,
            common_fields,
            file_type,
            replicate_media_per_account=(expanded_accounts is not None),
            immediate_publish=immediate_publish,
        )
        tasks.extend(grp_tasks)

    # ---- 独立账号部分 ----
    if plain_selected:
        if has_isolation:
            # 隔离模式：每个账号只用带自己 _assigned_account_id 的视频（1对1）
            for acc in plain_selected:
                acc_id = acc.get("id")
                acc_videos = [
                    v for v in video_list
                    if v.get("_assigned_account_id") == acc_id and not v.get("_group_id")
                ]
                if not acc_videos:
                    continue
                acc_tasks = generate_batch_tasks(
                    [acc],
                    acc_videos,
                    time_slots,
                    common_fields,
                    file_type,
                    replicate_media_per_account=False,
                    immediate_publish=immediate_publish,
                )
                tasks.extend(acc_tasks)

            # 无隔离标记的视频（手动导入）作为共享池，在无专属视频的账号间顺序块分配
            shared_videos = [
                v for v in video_list
                if v.get("_assigned_account_id") is None and not v.get("_group_id")
            ]
            if shared_videos:
                # 只给没有专属视频的账号分配共享视频
                acc_ids_with_own = {
                    v.get("_assigned_account_id")
                    for v in video_list
                    if v.get("_assigned_account_id") is not None and not v.get("_group_id")
                }
                accs_for_shared = [a for a in plain_selected if a.get("id") not in acc_ids_with_own]
                if accs_for_shared:
                    shared_tasks = generate_batch_tasks(
                        accs_for_shared, shared_videos, time_slots, common_fields, file_type,
                        replicate_media_per_account=False,
                        immediate_publish=immediate_publish,
                    )
                    tasks.extend(shared_tasks)
        else:
            # 无隔离标记：纯共享池顺序块分配（无账号组时已在前面返回，此分支为有账号组+独立账号混选情况）
            shared_videos = [v for v in video_list if not v.get("_group_id")]
            if shared_videos:
                accs = (
                    [a for a in expanded_accounts if a.get("id") not in seen_account_ids]
                    if expanded_accounts is not None
                    else plain_selected
                )
                if accs:
                    plain_tasks = generate_batch_tasks(
                        accs, shared_videos, time_slots, common_fields, file_type,
                        replicate_media_per_account=False,
                        immediate_publish=immediate_publish,
                    )
                    tasks.extend(plain_tasks)

    return tasks


async def batch_create_publish_records(
    tasks: List[Dict[str, Any]],
    publish_repo: Any,
) -> int:
    """使用事务批量写入发布记录，提升大量任务的创建效率。

    在事务内使用 bulk_create 批量插入；若 ORM 不支持（或版本过旧），
    则回退到逐条 create（仍在同一事务中，保证原子性）。

    Args:
        tasks:        generate_batch_tasks 返回的任务列表（视频或图文均可）。
        publish_repo: PublishRecordRepositoryAsync 实例。

    Returns:
        成功写入的记录数。
    """
    if not tasks:
        return 0

    from tortoise.transactions import in_transaction
    from src.infrastructure.storage.orm_models.publish_record import PublishRecord

    success_count = 0
    try:
        async with in_transaction():
            objs = [
                PublishRecord(
                    user_id=t["user_id"],
                    platform_username=t["platform_username"],
                    platform=t["platform"],
                    platform_account_id=t.get("platform_account_id"),
                    group_id=t.get("group_id"),
                    file_path=t["file_path"],
                    file_type=t["file_type"],
                    title=t.get("title"),
                    description=t.get("description"),
                    tags=t.get("tags"),
                    cover_path=t.get("cover_path"),
                    poi_info=t.get("poi_info"),
                    wechat_empty_location_open_picker=t.get(
                        "wechat_empty_location_open_picker"
                    ),
                    micro_app_info=t.get("micro_app_info"),
                    cart_info=t.get("cart_info"),
                    anchor_info=t.get("anchor_info"),
                    music_info=t.get("music_info"),
                    privacy_settings=t.get("privacy_settings"),
                    scheduled_publish_time=t.get("scheduled_publish_time"),
                    task_source=t.get("task_source"),
                    status="pending",
                )
                for t in tasks
            ]
            await PublishRecord.bulk_create(objs)
            success_count = len(objs)
    except Exception as bulk_err:
        logger.warning("bulk_create 失败，回退到逐条写入: %s", bulk_err)
        success_count = 0
        for i, task in enumerate(tasks):
            try:
                await publish_repo.create(
                    user_id=task["user_id"],
                    platform_username=task["platform_username"],
                    platform=task["platform"],
                    platform_account_id=task.get("platform_account_id"),
                    file_path=task["file_path"],
                    file_type=task["file_type"],
                    title=task.get("title"),
                    description=task.get("description"),
                    tags=task.get("tags"),
                    cover_path=task.get("cover_path"),
                    poi_info=task.get("poi_info"),
                    wechat_empty_location_open_picker=task.get(
                        "wechat_empty_location_open_picker"
                    ),
                    micro_app_info=task.get("micro_app_info"),
                    cart_info=task.get("cart_info"),
                    anchor_info=task.get("anchor_info"),
                    music_info=task.get("music_info"),
                    privacy_settings=task.get("privacy_settings"),
                    scheduled_publish_time=task.get("scheduled_publish_time"),
                    task_source=task.get("task_source"),
                )
                success_count += 1
            except Exception as e:
                logger.error("批量写入第 %d 条任务失败: %s", i + 1, e, exc_info=True)
    return success_count
