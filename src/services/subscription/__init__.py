"""
订阅付费业务逻辑模块（开源包装层）
闭源版实现：`src/proprietary/subscription/`
"""

from .permission_controller_async import PermissionControllerAsync, PermissionController
from .subscription_manager_async import SubscriptionManagerAsync
from .payment_handler_async import PaymentHandlerAsync

SubscriptionManager = SubscriptionManagerAsync
PaymentHandler = PaymentHandlerAsync

__all__ = [
    "PermissionControllerAsync",
    "SubscriptionManagerAsync",
    "PaymentHandlerAsync",
    "PermissionController",
    "SubscriptionManager",
    "PaymentHandler",
]
