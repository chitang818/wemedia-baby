"""
事件定义模块（优化版）
文件路径：src/core/common/event/events.py
功能：定义所有事件类型，支持事件溯源
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, Dict


@dataclass
class DomainEvent:
    """领域事件基类
    
    所有领域事件都应继承此类，支持事件溯源。
    
    Attributes:
        timestamp: 事件发生时间
        event_id: 事件唯一ID（可选）
        aggregate_id: 聚合根ID（可选）
        event_type: 事件类型（自动设置）
    """
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: Optional[str] = None
    aggregate_id: Optional[str] = None
    event_type: str = field(init=False)
    
    def __post_init__(self):
        """初始化后设置事件类型"""
        self.event_type = type(self).__name__
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于事件溯源存储
        
        Returns:
            包含所有字段的字典
        """
        result = {
            'event_type': self.event_type,
            'timestamp': self.timestamp.isoformat(),
            'event_id': self.event_id,
            'aggregate_id': self.aggregate_id,
        }
        # 添加所有字段
        for key, value in self.__dict__.items():
            if key not in result:
                if isinstance(value, datetime):
                    result[key] = value.isoformat()
                else:
                    result[key] = value
        return result


# 为了向后兼容，保留Event作为DomainEvent的别名
Event = DomainEvent


@dataclass(kw_only=True)
class AccountAddedEvent(DomainEvent):
    """账号添加事件"""
    user_id: int
    platform_username: str
    platform: str


@dataclass(kw_only=True)
class AccountRemovedEvent(DomainEvent):
    """账号删除事件"""
    user_id: int
    platform_username: str
    platform: str


@dataclass(kw_only=True)
class AccountUpdatedEvent(DomainEvent):
    """账号更新事件（状态、Cookie、昵称等）"""
    user_id: int
    account_id: int
    update_type: str = "state" # state, cookie, nickname, etc.


@dataclass(kw_only=True)
class PublishStartedEvent(DomainEvent):
    """发布开始事件"""
    task_id: Optional[int]
    platform_username: str
    platform: str
    file_path: str


@dataclass(kw_only=True)
class PublishCompletedEvent(DomainEvent):
    """发布完成事件"""
    task_id: Optional[int]
    platform_username: str
    platform: str
    success: bool
    publish_url: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(kw_only=True)
class TaskFailedEvent(DomainEvent):
    """任务失败事件"""
    task_id: int
    error_message: str
    retry_count: int


@dataclass(kw_only=True)
class CookieExpiredEvent(DomainEvent):
    """Cookie过期事件"""
    platform_username: str
    platform: str
    user_id: int


@dataclass(kw_only=True)
class BatchTaskStartedEvent(DomainEvent):
    """批量任务开始事件"""
    task_id: int
    task_name: str
    video_count: int


@dataclass(kw_only=True)
class BatchTaskCompletedEvent(DomainEvent):
    """批量任务完成事件"""
    task_id: int
    task_name: str
    completed_count: int
    failed_count: int


@dataclass(kw_only=True)
class GlobalToastEvent(DomainEvent):
    """全局Toast通知事件"""
    title: str
    content: str
    toast_type: str = "info"  # info, success, warning, error


@dataclass(kw_only=True)
class SessionEvictedEvent(DomainEvent):
    """软件账号会话被顶下线事件（其他设备登录导致当前 token 失效）"""
    reason: str = "您的账号已在其他设备登录，请重新登录。"


@dataclass(kw_only=True)
class PublishQueueExecutingCountChangedEvent(DomainEvent):
    """待发布队列「执行中」条数变化（工作台等订阅以刷新统计）。"""

    executing_count: int = 0


