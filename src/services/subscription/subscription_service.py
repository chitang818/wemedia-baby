"""
订阅服务（开源包装层）

闭源版真实实现：`src/proprietary/subscription/subscription_service.py`
开源版：若缺失闭源目录，则提供最小空壳实现，保证程序不崩溃。
"""

from __future__ import annotations

from typing import Optional, Any


try:
    from src.proprietary.subscription.subscription_service import SubscriptionService
except Exception:
    class SubscriptionService:  # type: ignore[no-redef]
        """订阅服务开源空壳 —— 所有方法安全返回空值，不影响主程序启动和开源功能运行。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def create_subscription(
            self,
            user_id: int,
            plan_type: str,
            price: float,
            duration_days: int = 30,
            order_id: Optional[str] = None,
        ) -> None:
            """开源版不提供订阅创建功能。"""
            return None

        async def get_user_subscription(self, user_id: int) -> None:
            """开源版不提供订阅查询功能。"""
            return None

        async def check_subscription_active(self, user_id: int) -> bool:
            """开源版不限制订阅状态，默认返回 False。"""
            return False
