"""
账号组领域实体
文件路径：src/domain/models/account_group.py
功能：定义账号组领域模型，使用不可变数据结构
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List


@dataclass(frozen=True)
class AccountGroup:
    """账号组领域实体
    
    账号组是将不同平台的多个账号组合在一起的逻辑单元。
    每个账号组可包含多个账号，但同一平台最多只能有一个账号。
    
    Attributes:
        group_id: 账号组ID
        user_id: 用户ID
        group_name: 账号组名称
        description: 描述（可选）
        created_at: 创建时间
        updated_at: 更新时间（可选）
    """
    
    user_id: int
    group_name: str
    group_id: Optional[int] = None
    description: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于序列化
        
        Returns:
            包含所有字段的字典
        """
        return {
            'group_id': self.group_id,
            'id': self.group_id,  # 兼容数据库字段名
            'user_id': self.user_id,
            'group_name': self.group_name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AccountGroup':
        """从字典创建AccountGroup实体
        
        Args:
            data: 包含AccountGroup字段的字典
            
        Returns:
            AccountGroup实体实例
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
        
        return cls(
            group_id=data.get('group_id') or data.get('id'),
            user_id=data['user_id'],
            group_name=data['group_name'],
            description=data.get('description'),
            created_at=created_at,
            updated_at=updated_at,
        )
    
    def with_updates(self, **kwargs) -> 'AccountGroup':
        """创建更新后的AccountGroup实例（不可变实体的更新方式）
        
        Args:
            **kwargs: 要更新的字段
            
        Returns:
            新的AccountGroup实例
        """
        data = self.to_dict()
        data.update(kwargs)
        return self.from_dict(data)
