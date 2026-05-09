# 写入发布任务或执行发布前的校验（任务创建页与发布列表/管道共用）
import os
from typing import Optional, List

_WECHAT_VIDEO_PLATFORM = "wechat_video"
_WECHAT_SHORT_TITLE_MIN_LEN = 6


def wechat_video_short_title_validation_error(
    platform: str, title: Optional[str]
) -> Optional[str]:
    """视频号：若已填写作品标题（任务创建页用作短标题），则长度须 ≥ 6。

    未填写标题时不校验（插件侧会跳过短标题步骤）。
    """
    if (platform or "").strip() != _WECHAT_VIDEO_PLATFORM:
        return None
    short_title = (title or "").strip()
    if not short_title:
        return None
    if len(short_title) < _WECHAT_SHORT_TITLE_MIN_LEN:
        return "短标题文字不足6个字"
    return None


_FOLDER_MARKER_PREFIX = "__FOLDER__:"


def publish_file_missing_error(file_path: Optional[str]) -> Optional[str]:
    """校验发布任务的媒体文件（视频/图片）是否存在。

    file_path 可能是逗号分隔的多文件路径（图文发布），首条可能含 __FOLDER__: 标记。
    返回错误描述字符串，全部存在时返回 None。
    """
    if not file_path or not file_path.strip():
        return "未指定发布文件路径"
    paths = [
        p.strip() for p in file_path.split(",")
        if p.strip() and not p.strip().startswith(_FOLDER_MARKER_PREFIX)
    ]
    if not paths:
        return "未指定发布文件路径"
    missing: List[str] = [p for p in paths if not os.path.isfile(p)]
    if not missing:
        return None
    if len(paths) == 1:
        return f"文件不存在: {os.path.basename(missing[0])}"
    names = ", ".join(os.path.basename(m) for m in missing[:3])
    suffix = f" 等共 {len(missing)} 个" if len(missing) > 3 else ""
    return f"部分文件不存在: {names}{suffix}"
