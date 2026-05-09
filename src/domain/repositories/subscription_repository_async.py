"""
订阅 Repository（异步版本）- 基于 Tortoise ORM
功能：封装订阅相关的数据访问操作
"""

from typing import Optional, Dict, Any
import logging

from .base_repository_async import BaseRepositoryAsync
from src.infrastructure.storage.orm_models.subscription import Subscription as SubscriptionModel
from src.infrastructure.storage.retry import retry_on_locked

logger = logging.getLogger(__name__)


class SubscriptionRepositoryAsync(BaseRepositoryAsync):
    """订阅 Repository（异步版本）- 基于 Tortoise ORM

    封装 subscriptions 表的所有数据访问操作。
    """

    model_class = SubscriptionModel

    @retry_on_locked()
    async def create(
        self,
        user_id: int,
        plan_type: str,
        price: float,
        start_date: str,
        end_date: str,
        order_id: Optional[str] = None,
    ) -> int:
        """创建订阅

        Args:
            user_id: 用户ID
            plan_type: 套餐类型
            price: 价格
            start_date: 开始日期（ISO格式字符串）
            end_date: 结束日期（ISO格式字符串）
            order_id: 订单ID（可选）

        Returns:
            新创建的订阅ID
        """
        try:
            sub = await SubscriptionModel.create(
                user_id=user_id,
                plan_type=plan_type,
                price=price,
                start_date=start_date,
                end_date=end_date,
                order_id=order_id,
                status="active",
            )
            self.logger.info(f"创建订阅成功: 用户ID={user_id}, 套餐={plan_type}, ID={sub.id}")
            return sub.id
        except Exception as e:
            self.handle_error(e, "create")
            raise

    async def get_active_subscription(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户的活跃订阅

        Args:
            user_id: 用户ID

        Returns:
            订阅信息字典，如果不存在返回 None
        """
        try:
            sub = await (
                SubscriptionModel.filter(user_id=user_id, status="active")
                .order_by("-created_at")
                .first()
            )
            return self._to_dict(sub) if sub else None
        except Exception as e:
            self.handle_error(e, "get_active_subscription")
            return None

    @staticmethod
    def _to_dict(sub: SubscriptionModel) -> Dict[str, Any]:
        """将 ORM 模型实例转换为字典（兼容旧格式）"""
        return {
            "id": sub.id,
            "user_id": sub.user_id,
            "plan_type": sub.plan_type,
            "price": sub.price,
            "start_date": sub.start_date.isoformat() if sub.start_date else None,
            "end_date": sub.end_date.isoformat() if sub.end_date else None,
            "auto_renew": sub.auto_renew,
            "status": sub.status,
            "payment_method": sub.payment_method,
            "order_id": sub.order_id,
            "created_at": sub.created_at.isoformat() if sub.created_at else None,
        }
