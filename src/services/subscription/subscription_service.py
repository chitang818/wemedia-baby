"""
订阅服务
文件路径：src/core/application/services/subscription_service.py
功能：订阅付费业务逻辑协调
"""

from typing import Optional, Dict, Any
import logging
from datetime import datetime, timedelta

from src.infrastructure.common.di.service_locator import ServiceLocator
from src.domain import Subscription
from src.domain.repositories.subscription_repository_async import SubscriptionRepositoryAsync

logger = logging.getLogger(__name__)


class SubscriptionService:
    """订阅服务 - 订阅付费业务逻辑协调"""
    
    def __init__(
        self,
        subscription_repo: Optional[SubscriptionRepositoryAsync] = None
    ):
        """初始化订阅服务
        
        Args:
            subscription_repo: 订阅 Repository（可选，默认从 ServiceLocator 获取）
        """
        self.service_locator = ServiceLocator()
        self.subscription_repo = subscription_repo or self.service_locator.get(SubscriptionRepositoryAsync)
        self.logger = logging.getLogger(__name__)
    
    async def create_subscription(
        self,
        user_id: int,
        plan_type: str,
        price: float,
        duration_days: int = 30,
        order_id: Optional[str] = None
    ) -> Subscription:
        """创建订阅（异步）
        
        Args:
            user_id: 用户ID
            plan_type: 套餐类型（trial/basic/premium）
            price: 价格
            duration_days: 订阅时长（天）
            order_id: 订单ID（可选）
        
        Returns:
            Subscription实体
        """
        start_date = datetime.now()
        end_date = start_date + timedelta(days=duration_days)
        
        subscription_id = await self.subscription_repo.create(
            user_id=user_id,
            plan_type=plan_type,
            price=price,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            order_id=order_id
        )
        
        subscription = Subscription(
            subscription_id=subscription_id,
            user_id=user_id,
            plan_type=plan_type,
            price=price,
            start_date=start_date,
            end_date=end_date,
            status="active",
            order_id=order_id
        )
        
        self.logger.info(f"创建订阅成功: 用户ID={user_id}, 套餐={plan_type}")
        return subscription
    
    async def get_user_subscription(self, user_id: int) -> Optional[Subscription]:
        """获取用户订阅（异步）
        
        Args:
            user_id: 用户ID
        
        Returns:
            Subscription实体，如果不存在返回None
        """
        subscription_data = await self.subscription_repo.get_active_subscription(user_id)
        if not subscription_data:
            return None
        
        return Subscription.from_dict({
            'subscription_id': subscription_data['id'],
            'user_id': subscription_data['user_id'],
            'plan_type': subscription_data['plan_type'],
            'price': subscription_data['price'],
            'start_date': subscription_data['start_date'],
            'end_date': subscription_data['end_date'],
            'auto_renew': subscription_data.get('auto_renew', False),
            'status': subscription_data.get('status', 'active'),
            'payment_method': subscription_data.get('payment_method'),
            'order_id': subscription_data.get('order_id'),
            'created_at': subscription_data.get('created_at'),
            'updated_at': subscription_data.get('updated_at'),
        })
    
    async def check_subscription_active(self, user_id: int) -> bool:
        """检查用户订阅是否激活（异步）
        
        Args:
            user_id: 用户ID
        
        Returns:
            如果订阅激活返回True，否则返回False
        """
        subscription = await self.get_user_subscription(user_id)
        if not subscription:
            return False
        
        return subscription.is_active()

