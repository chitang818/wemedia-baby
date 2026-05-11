"""
订阅管理器（开源包装层）
闭源版实现：`src/proprietary/subscription/subscription_manager_async.py`
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List


try:
    from src.proprietary.subscription.subscription_manager_async import SubscriptionManagerAsync
except Exception:
    class SubscriptionManagerAsync:  # type: ignore[no-redef]
        def __init__(self, user_id: int, *args: Any, **kwargs: Any):
            self.user_id = user_id

        def get_subscription_plans(self) -> List[Dict[str, Any]]:
            """与个人中心静态套餐展示一致（无可用的闭源实现时使用）。"""
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
            return None

        async def check_subscription_active(self) -> bool:
            return False

