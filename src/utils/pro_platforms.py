"""
Pro 平台 ID 列表
文件路径：src/utils/pro_platforms.py
功能：定义需要 Pro 会员才能发布的平台 ID，供权限校验使用。
"""

# 需要 Pro 会员才能发布的平台（src/plugins/pro/ 下的插件）
PRO_PLATFORM_IDS = frozenset({
    "wechat_video",
    "xiaohongshu",
    "bilibili",
    "weibo",
    "toutiao",
    "baijiahao",
    "duoduoshipin",
    "qiehao",
})


def is_pro_platform(platform_id: str) -> bool:
    """判断平台是否为 Pro 平台（需要 Pro 会员才能发布）"""
    return platform_id in PRO_PLATFORM_IDS
