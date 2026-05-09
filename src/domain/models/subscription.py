"""
订阅领域实体
文件路径：src/core/domain/subscription.py
功能：定义订阅领域模型，使用不可变数据结构
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class Subscription:
    """订阅领域实体
    
    使用不可变数据结构（frozen=True），确保数据一致性和线程安全。
    
    Attributes:
        subscription_id: 订阅ID（可选，创建时可能为None）
        user_id: 用户ID
        plan_type: 套餐类型（trial/basic/premium）
        price: 价格
        start_date: 开始日期
        end_date: 结束日期
        auto_renew: 是否自动续费
        status: 订阅状态（active/expired/cancelled）
        payment_method: 支付方式（可选）
        order_id: 订单ID（可选）
        created_at: 创建时间
        updated_at: 更新时间（可选）
    """
    
    user_id: int
    plan_type: str  # trial/basic/premium
    price: float
    start_date: datetime
    end_date: datetime
    auto_renew: bool = False
    status: str = "active"  # active/expired/cancelled
    payment_method: Optional[str] = None
    order_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    subscription_id: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于序列化
        
        Returns:
            包含所有字段的字典，datetime对象转换为ISO格式字符串
        """
        result = {
            'subscription_id': self.subscription_id,
            'user_id': self.user_id,
            'plan_type': self.plan_type,
            'price': self.price,
            'start_date': self.start_date.isoformat(),
            'end_date': self.end_date.isoformat(),
            'auto_renew': self.auto_renew,
            'status': self.status,
            'payment_method': self.payment_method,
            'order_id': self.order_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Subscription':
        """从字典创建Subscription实体
        
        Args:
            data: 包含Subscription字段的字典
            
        Returns:
            Subscription实体实例
            
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
        
        start_date = data.get('start_date')
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date)
        else:
            raise ValueError("start_date is required")
        
        end_date = data.get('end_date')
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date)
        else:
            raise ValueError("end_date is required")
        
        return cls(
            subscription_id=data.get('subscription_id'),
            user_id=data['user_id'],
            plan_type=data['plan_type'],
            price=data['price'],
            start_date=start_date,
            end_date=end_date,
            auto_renew=data.get('auto_renew', False),
            status=data.get('status', 'active'),
            payment_method=data.get('payment_method'),
            order_id=data.get('order_id'),
            created_at=created_at,
            updated_at=updated_at,
        )
    
    def with_updates(self, **kwargs) -> 'Subscription':
        """创建更新后的Subscription实例（不可变实体的更新方式）
        
        Args:
            **kwargs: 要更新的字段
            
        Returns:
            新的Subscription实例
        """
        data = self.to_dict()
        data.update(kwargs)
        return self.from_dict(data)
    
    def is_active(self) -> bool:
        """检查订阅是否激活
        
        Returns:
            如果状态为active且未过期返回True
        """
        now = datetime.now()
        return self.status == "active" and self.start_date <= now <= self.end_date
    
    def is_expired(self) -> bool:
        """检查订阅是否过期
        
        Returns:
            如果已过期返回True
        """
        now = datetime.now()
        return now > self.end_date or self.status == "expired"
    
    def days_remaining(self) -> int:
        """获取剩余天数
        
        Returns:
            剩余天数，如果已过期返回0
        """
        if self.is_expired():
            return 0
        delta = self.end_date - datetime.now()
        return max(0, delta.days)

