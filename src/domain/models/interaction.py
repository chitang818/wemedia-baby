"""
互动与私信领域模型
文件路径：src/domain/models/interaction.py
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

@dataclass
class Message:
    """单条私信内容"""
    message_id: str
    content: str
    sender_id: str
    sender_name: str
    is_self: bool  # 是否是当前账号发出的
    create_time: datetime
    msg_type: str = "text"  # text, image, video 等

@dataclass
class MessageSession:
    """私信会话（对应左侧列表的一个联系人/群组）"""
    session_id: str
    target_id: str
    target_name: str
    target_avatar: str
    last_message: str
    unread_count: int
    update_time: datetime
    messages: List[Message] = field(default_factory=list)
