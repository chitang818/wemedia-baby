"""
账号领域实体
文件路径：src/core/domain/account.py
功能：定义账号领域模型，使用不可变数据结构
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class Account:
    """账号领域实体
    
    使用不可变数据结构（frozen=True），确保数据一致性和线程安全。
    
    Attributes:
        user_id: 用户ID
        account_id: 账号ID（可选，创建时可能为None）
        platform: 平台名称（如：douyin、kuaishou）
        account_name: 账号名称
        platform_username: 平台用户名
        encrypted_cookies: 加密的Cookie数据（bytes）
        status: 账号状态（active/inactive/expired）
        login_status: 登录状态（online/offline）
        last_login_at: 最后登录时间（可选）
        is_active: 是否激活
        created_at: 创建时间
        updated_at: 更新时间（可选）
        group_id: 账号组ID（可选，None表示未分组）
    """
    
    user_id: int
    platform: str
    account_name: str
    platform_username: Optional[str] = None
    encrypted_cookies: Optional[bytes] = None
    status: str = "active"  # active/inactive/expired
    login_status: str = "offline"  # online/offline
    last_login_at: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    account_id: Optional[int] = None
    group_id: Optional[int] = None  # 账号组ID，None表示未分组
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于序列化
        
        Returns:
            包含所有字段的字典，datetime对象转换为ISO格式字符串
        """
        result = {
            'user_id': self.user_id,
            'platform': self.platform,
            'account_name': self.account_name,
            'platform_username': self.platform_username,
            'encrypted_cookies': self.encrypted_cookies.hex() if self.encrypted_cookies else None,
            'status': self.status,
            'login_status': self.login_status,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'account_id': self.account_id,
            'group_id': self.group_id,
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Account':
        """从字典创建Account实体
        
        Args:
            data: 包含Account字段的字典
            
        Returns:
            Account实体实例
            
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
        
        last_login_at = data.get('last_login_at')
        if isinstance(last_login_at, str):
            last_login_at = datetime.fromisoformat(last_login_at)
        
        # 处理encrypted_cookies
        encrypted_cookies = data.get('encrypted_cookies')
        if isinstance(encrypted_cookies, str):
            encrypted_cookies = bytes.fromhex(encrypted_cookies)
        
        return cls(
            user_id=data['user_id'],
            platform=data['platform'],
            account_name=data['account_name'],
            platform_username=data.get('platform_username'),
            encrypted_cookies=encrypted_cookies,
            status=data.get('status', 'active'),
            login_status=data.get('login_status', 'offline'),
            last_login_at=last_login_at,
            is_active=data.get('is_active', True),
            created_at=created_at,
            updated_at=updated_at,
            account_id=data.get('account_id'),
            group_id=data.get('group_id'),
        )
    
    def with_updates(self, **kwargs) -> 'Account':
        """创建更新后的Account实例（不可变实体的更新方式）
        
        Args:
            **kwargs: 要更新的字段
            
        Returns:
            新的Account实例
        """
        data = self.to_dict()
        data.update(kwargs)
        return self.from_dict(data)

