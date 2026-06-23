"""
私信互动服务
文件路径：src/services/interaction/message_service.py
"""

import logging
from typing import List, Optional

from src.domain.models.interaction import MessageSession, Message
from src.plugins.core.plugin_manager import PluginManager

logger = logging.getLogger(__name__)

class MessageService:
    """私信互动服务层
    作为 UI 层和插件层之间的桥梁，管理各平台的私信接口调用。
    """

    def __init__(self):
        pass

    async def get_sessions(self, platform_id: str, account_id: str, limit: int = 20) -> List[MessageSession]:
        """拉取指定平台指定账号的最近会话列表"""
        plugin = PluginManager.get_message_plugin(platform_id)
        if not plugin:
            logger.warning(f"平台 {platform_id} 不支持私信功能")
            return []
        try:
            return await plugin.get_sessions(account_id, limit)
        except Exception as e:
            logger.error(f"获取 {platform_id} 会话列表失败: {e}")
            return []

    async def get_messages(self, platform_id: str, account_id: str, session_id: str, limit: int = 50) -> List[Message]:
        """拉取指定会话的历史消息"""
        plugin = PluginManager.get_message_plugin(platform_id)
        if not plugin:
            logger.warning(f"平台 {platform_id} 不支持私信功能")
            return []
        try:
            return await plugin.get_messages(account_id, session_id, limit)
        except Exception as e:
            logger.error(f"获取 {platform_id} 历史消息失败: {e}")
            return []

    async def send_message(self, platform_id: str, account_id: str, session_id: str, content: str) -> bool:
        """发送私信"""
        plugin = PluginManager.get_message_plugin(platform_id)
        if not plugin:
            logger.warning(f"平台 {platform_id} 不支持私信功能")
            return False
        try:
            return await plugin.send_message(account_id, session_id, content)
        except Exception as e:
            logger.error(f"在 {platform_id} 发送私信失败: {e}")
            return False

# 单例实例供外部引入
message_service = MessageService()
