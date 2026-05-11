"""
订阅/权限模块（闭源实现）
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

