"""
私信插件接口
文件路径：src/plugins/core/interfaces/message_plugin.py
"""

from abc import ABC, abstractmethod
from typing import List

from src.domain.models.interaction import MessageSession, Message

class MessagePluginInterface(ABC):
    """
    平台私信插件抽象接口
    负责实现拉取会话、拉取历史消息、发送消息等能力
    """
    
    @property
    @abstractmethod
    def platform_id(self) -> str:
        """返回平台唯一标识 (例如 'douyin')"""
        pass
        
    @abstractmethod
    async def get_sessions(self, account_id: str, limit: int = 20) -> List[MessageSession]:
        """获取最近会话列表"""
        pass
        
    @abstractmethod
    async def get_messages(self, account_id: str, session_id: str, limit: int = 50) -> List[Message]:
        """获取指定会话的消息记录"""
        pass
        
    @abstractmethod
    async def send_message(self, account_id: str, session_id: str, content: str) -> bool:
        """发送私信回复"""
        pass
