"""
订阅管理器（开源包装层）
闭源版实现：`src/proprietary/subscription/subscription_manager_async.py`
"""

from __future__ import annotations

from typing import Optional, Dict, Any


try:
    from src.proprietary.subscription.subscription_manager_async import SubscriptionManagerAsync
except Exception:
    class SubscriptionManagerAsync:  # type: ignore[no-redef]
        def __init__(self, user_id: int, *args: Any, **kwargs: Any):
            self.user_id = user_id

        async def get_user_subscription(self) -> Optional[Dict[str, Any]]:
            return None

        async def check_subscription_active(self) -> bool:
            return False

