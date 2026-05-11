"""
订阅管理器（闭源实现）
原路径：src/services/subscription/subscription_manager_async.py
"""

from typing import List, Optional, Dict, Any
from src.infrastructure.common.event.event_bus import EventBus
from src.infrastructure.common.di.service_locator import ServiceLocator
from src.services.subscription.subscription_service import SubscriptionService
import logging

logger = logging.getLogger(__name__)


class SubscriptionManagerAsync:
    def __init__(self, user_id: int, event_bus: Optional[EventBus] = None):
        self.user_id = user_id
        self.service_locator = ServiceLocator()
        # EventBus 未注入且容器未注册时，不得阻塞个人中心（否则刷新按钮无效）
        if event_bus is not None:
            self.event_bus = event_bus
        else:
            try:
                self.event_bus = self.service_locator.get(EventBus)
            except Exception:
                self.event_bus = None
        self.subscription_service = SubscriptionService()
        self.logger = logging.getLogger(__name__)

    def get_subscription_plans(self) -> List[Dict[str, Any]]:
        return [
            {
                "plan_type": "free",
                "name": "免费版",
                "price": 0,
                "duration_days": 0,
                "price_hint": "开源版 · 永久可用",
                "features": [
                    "抖音、快手等社区平台发布",
                    "按额度使用（账号数/发布次数等）",
                    "执行已有批量发布任务",
                ],
            },
            {
                "plan_type": "pro",
                "name": "Pro 会员",
                "price": 0,
                "duration_days": 0,
                "price_hint": "关注公众号 · 发送用户名 · 免费开通",
                "features": [
                    "全部平台账号与发布能力",
                    "更高额度或不限（以云端同步为准）",
                    "批量创建任务、媒体库、带货与数据中心等",
                ],
                "badge": "关注公众号免费获取",
                "recommended": True,
            },
        ]

    async def get_user_subscription(self) -> Optional[Dict[str, Any]]:
        subscription = await self.subscription_service.get_user_subscription(self.user_id)
        if subscription:
            return subscription.to_dict()
        return None

    async def check_subscription_active(self) -> bool:
        return await self.subscription_service.check_subscription_active(self.user_id)

