"""
平台名称映射（集中管理）
文件路径：src/utils/platform_names.py
功能：提供平台 ID 与中文显示名之间的双向映射，供所有 UI 模块统一引用
"""

PLATFORM_ID_TO_NAME = {
    'douyin': '抖音',
    'kuaishou': '快手',
    'wechat_video': '视频号',
    'xiaohongshu': '小红书',
    'bilibili': '哔哩哔哩',
    'weibo': '微博',
    'toutiao': '头条',
    'baijiahao': '百家号',
    'qiehao': '企鹅号',
    'duoduoshipin': '多多视频',
}

PLATFORM_NAME_TO_ID = {v: k for k, v in PLATFORM_ID_TO_NAME.items()}
# 兼容旧版完整显示名「微信视频号」
PLATFORM_NAME_TO_ID.setdefault("微信视频号", "wechat_video")


def get_platform_display_name(platform_id: str) -> str:
    """根据平台 ID 获取中文显示名，未知 ID 原样返回"""
    return PLATFORM_ID_TO_NAME.get(platform_id, platform_id)


def get_platform_id(display_name: str) -> str:
    """根据中文显示名获取平台 ID，未知名称原样返回"""
    return PLATFORM_NAME_TO_ID.get(display_name, display_name)


def platform_id_is_wechat_video(platform) -> bool:
    """是否为视频号平台 ID（兼容 None、非字符串、大小写差异；dict 时读其 platform 键）。"""
    if platform is None:
        return False
    if isinstance(platform, dict):
        return platform_id_is_wechat_video(platform.get("platform"))
    p = str(platform).strip().lower()
    return p == "wechat_video"
