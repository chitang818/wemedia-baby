"""
单条发布任务创建 — 数据层逻辑（写入发布列表）
文件路径：src/ui/pages/publish/single_task_creation_actions.py

功能：从单条任务创建页 UI 抽出的「创建/更新发布记录」逻辑，供 single_task_creation_page 调用。
      此处仅写库生成待发布任务，不执行平台上传。
"""
from typing import Optional, Any, Dict
import logging

logger = logging.getLogger(__name__)


def normalize_publish_record_id(record_id: Any) -> Optional[int]:
    """将发布记录主键规范为 int；无效则 None（避免 str/误判导致走新建分支）。"""
    if record_id is None:
        return None
    try:
        i = int(record_id)
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def _platform_account_id(account: dict) -> Optional[int]:
    """从账号 dict 取平台账号主键；占位或非数字 id 返回 None。"""
    aid = account.get("id")
    if aid is None:
        return None
    if isinstance(aid, int):
        return aid
    if isinstance(aid, str) and aid.isdigit():
        return int(aid)
    return None


def _platform_group_id(account: dict) -> Optional[int]:
    """从账号 dict 中提取整数 group_id。

    账号组展开后的单个账号 dict 里有 group_id 字段（来自 _account_to_dict），
    直接提取并存入发布记录，消除了发布后文件处理多跳查询的依赖。
    """
    gid = account.get("group_id")
    if gid is None:
        return None
    if isinstance(gid, int):
        return gid
    if isinstance(gid, str) and gid.isdigit():
        return int(gid)
    return None


async def add_or_update_publish_record(
    user_id: int,
    editing_record_id: Optional[int],
    account: dict,
    file_path: str,
    file_type: str,
    title: str,
    description: str,
    tags_str: str,
    scheduled_time: Optional[str],
    cover_path: Optional[str],
    poi_info: str,
    micro_app_info: str,
    cart_info: str,
    anchor_info: str,
    privacy_settings: str,
    publish_repo: Any,
    wechat_empty_location_open_picker: Optional[bool] = None,
    editing_record_original_status: Optional[str] = None,
    music_info: Optional[str] = None,
    task_source: Optional[str] = None,
) -> str:
    """创建或更新发布记录。
    
    Args:
        user_id: 用户 ID
        editing_record_id: 若为编辑则传记录 ID，新建为 None
        editing_record_original_status: 保存前记录的状态；若为 failed，更新时改为 pending 并清空错误信息
        account: 账号信息 dict（含 platform_username, platform, id, group_id 等）
        file_path, file_type, title, description, tags_str: 发布内容
        scheduled_time, cover_path: 定时与封面
        poi_info, micro_app_info, cart_info, anchor_info: 扩展信息
        wechat_empty_location_open_picker: 视频号空位置是否在页面点开下拉；None 写 NULL
        privacy_settings: JSON 字符串
        publish_repo: PublishRecordRepositoryAsync 实例
    
    Returns:
        成功消息前缀，如「已添加到发布列表」或「已更新发布任务」
    """
    eid = normalize_publish_record_id(editing_record_id)
    # 仅在账号组任务时写入 group_id（账号组展开后的账号 dict 含此字段）
    group_id = _platform_group_id(account) if task_source == "group" else None
    if eid is not None:
        fields: Dict[str, Any] = {
            "platform_username": account.get("platform_username", ""),
            "platform": account.get("platform", "douyin"),
            "platform_account_id": _platform_account_id(account),
            "group_id": group_id,
            "file_path": file_path,
            "file_type": file_type,
            "title": title,
            "description": description,
            "tags": tags_str,
            "cover_path": cover_path,
            "poi_info": poi_info,
            "wechat_empty_location_open_picker": wechat_empty_location_open_picker,
            "micro_app_info": micro_app_info,
            "cart_info": cart_info,
            "anchor_info": anchor_info,
            "music_info": music_info,
            "privacy_settings": privacy_settings,
            "scheduled_publish_time": scheduled_time,
        }
        if task_source is not None:
            fields["task_source"] = task_source
        # 发布列表：失败任务修改后重新排队；待发布仍为待发布（不写 status）
        if (editing_record_original_status or "").strip().lower() == "failed":
            fields["status"] = "pending"
            fields["error_message"] = None
        await publish_repo.update_content(record_id=eid, **fields)
        return "已更新发布任务"
    await publish_repo.create(
        user_id=user_id,
        platform_username=account.get("platform_username", ""),
        platform=account.get("platform", "douyin"),
        platform_account_id=_platform_account_id(account),
        group_id=group_id,
        file_path=file_path,
        file_type=file_type,
        title=title,
        description=description,
        tags=tags_str,
        cover_path=cover_path,
        poi_info=poi_info,
        wechat_empty_location_open_picker=wechat_empty_location_open_picker,
        micro_app_info=micro_app_info,
        cart_info=cart_info,
        anchor_info=anchor_info,
        music_info=music_info,
        privacy_settings=privacy_settings,
        scheduled_publish_time=scheduled_time,
        task_source=task_source,
    )
    return "已添加到发布列表"
