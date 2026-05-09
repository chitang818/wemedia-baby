"""
支付处理器（开源包装层）
闭源版实现：`src/proprietary/subscription/payment_handler_async.py`
"""

from __future__ import annotations

from typing import Dict, Any


try:
    from src.proprietary.subscription.payment_handler_async import PaymentHandlerAsync
except Exception:
    class PaymentHandlerAsync:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any):
            pass

        async def create_order(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
            return {"success": False, "error": "开源版不提供支付功能"}
