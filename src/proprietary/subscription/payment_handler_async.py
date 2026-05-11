"""
支付处理器（闭源实现）
原路径：src/services/subscription/payment_handler_async.py
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging
import secrets

from src.infrastructure.common.event.event_bus import EventBus
from src.infrastructure.common.di.service_locator import ServiceLocator

logger = logging.getLogger(__name__)


class PaymentHandlerAsync:
    def __init__(self, user_id: int, event_bus: Optional[EventBus] = None):
        self.user_id = user_id
        self.service_locator = ServiceLocator()
        self.event_bus = event_bus or self.service_locator.get(EventBus)
        self.logger = logging.getLogger(__name__)

    async def create_order(self, plan_type: str, price: float, payment_method: str = "alipay") -> Dict[str, Any]:
        order_id = self._generate_order_id()
        payment_url = self._generate_payment_url(order_id=order_id, amount=price, payment_method=payment_method)
        return {
            "success": True,
            "order_id": order_id,
            "payment_url": payment_url,
            "amount": price,
            "payment_method": payment_method,
            "expires_at": (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _generate_order_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = secrets.token_hex(4).upper()
        return f"ORD{timestamp}{random_suffix}"

    def _generate_payment_url(self, order_id: str, amount: float, payment_method: str) -> str:
        if payment_method == "alipay":
            return f"https://openapi.alipay.com/gateway.do?order_id={order_id}"
        if payment_method == "wechat":
            return f"weixin://wxpay/bizpayurl?order_id={order_id}"
        return f"https://payment.example.com/pay?order_id={order_id}"

