"""
发布任务领域实体
文件路径：src/core/domain/publish_task.py
功能：定义发布任务领域模型，使用不可变数据结构
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List


@dataclass(frozen=True)
class PublishTask:
    """发布任务领域实体
    
    使用不可变数据结构（frozen=True），确保数据一致性和线程安全。
    
    Attributes:
        task_id: 任务ID（可选，创建时可能为None）
        user_id: 用户ID
        account_name: 账号名称
        platform: 平台名称
        content: 发布内容（文件路径、标题、描述等）
        status: 任务状态（pending/running/success/failed/paused）
        retry_count: 重试次数
        error_message: 错误信息（可选）
        publish_url: 发布后的URL（可选）
        created_at: 创建时间
        updated_at: 更新时间（可选）
        completed_at: 完成时间（可选）
    """
    
    user_id: int
    account_name: str
    platform: str
    content: Dict[str, Any]  # 包含file_path, title, description, tags等
    status: str = "pending"  # pending/running/success/failed/paused
    retry_count: int = 0
    error_message: Optional[str] = None
    publish_url: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    task_id: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于序列化
        
        Returns:
            包含所有字段的字典，datetime对象转换为ISO格式字符串
        """
        result = {
            'task_id': self.task_id,
            'user_id': self.user_id,
            'account_name': self.account_name,
            'platform': self.platform,
            'content': self.content,
            'status': self.status,
            'retry_count': self.retry_count,
            'error_message': self.error_message,
            'publish_url': self.publish_url,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PublishTask':
        """从字典创建PublishTask实体
        
        Args:
            data: 包含PublishTask字段的字典
            
        Returns:
            PublishTask实体实例
            
        Raises:
            ValueError: 如果必需字段缺失或格式错误
        """
        # 处理datetime字段
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()
        
        updated_at = data.get('updated_at')
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        
        completed_at = data.get('completed_at')
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)
        
        return cls(
            task_id=data.get('task_id'),
            user_id=data['user_id'],
            account_name=data['account_name'],
            platform=data['platform'],
            content=data['content'],
            status=data.get('status', 'pending'),
            retry_count=data.get('retry_count', 0),
            error_message=data.get('error_message'),
            publish_url=data.get('publish_url'),
            created_at=created_at,
            updated_at=updated_at,
            completed_at=completed_at,
        )
    
    def with_updates(self, **kwargs) -> 'PublishTask':
        """创建更新后的PublishTask实例（不可变实体的更新方式）
        
        Args:
            **kwargs: 要更新的字段
            
        Returns:
            新的PublishTask实例
        """
        data = self.to_dict()
        data.update(kwargs)
        return self.from_dict(data)
    
    def is_pending(self) -> bool:
        """检查任务是否处于待处理状态
        
        Returns:
            如果状态为pending返回True
        """
        return self.status == "pending"
    
    def is_running(self) -> bool:
        """检查任务是否正在运行
        
        Returns:
            如果状态为running返回True
        """
        return self.status == "running"
    
    def is_completed(self) -> bool:
        """检查任务是否已完成（成功或失败）
        
        Returns:
            如果状态为success或failed返回True
        """
        return self.status in ("success", "failed")
    
    def can_retry(self, max_retries: int = 3) -> bool:
        """检查任务是否可以重试
        
        Args:
            max_retries: 最大重试次数
            
        Returns:
            如果任务失败且未超过最大重试次数返回True
        """
        return self.status == "failed" and self.retry_count < max_retries

