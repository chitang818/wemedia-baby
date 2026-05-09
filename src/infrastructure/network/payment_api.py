"""
[已废弃] 支付API
文件路径：src/core/payment_api.py
功能：封装支付接口调用（简化版，实际需要对接第三方支付平台）

⚠️ 本模块为占位实现，仅使用内存字典模拟订单，不会被实际业务调用。
后续接入真实支付平台时应整体替换本文件。
"""
import warnings as _warnings
_warnings.warn(
    "PaymentAPI 是占位实现，不应在生产代码中使用",
    DeprecationWarning,
    stacklevel=2,
)

from typing import Dict, Any, Optional
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


class PaymentAPI:
    """支付API（简化版实现）"""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """初始化支付API
        
        Args:
            api_key: API密钥（可选，实际对接时需要）
            api_secret: API密钥（可选，实际对接时需要）
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.logger = logging.getLogger(__name__)
        # 模拟订单存储（实际应该使用数据库或缓存）
        self._orders: Dict[str, Dict[str, Any]] = {}
    
    def create_order(
        self,
        user_id: int,
        plan_type: str,
        amount: float,
        payment_method: str
    ) -> Dict[str, Any]:
        """创建支付订单
        
        Args:
            user_id: 用户ID
            plan_type: 套餐类型
            amount: 支付金额
            payment_method: 支付方式（wechat/alipay）
        
        Returns:
            订单信息（包含order_id、支付URL或二维码等）
        """
        # 生成订单号
        order_id = f"{payment_method}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # 创建订单记录
        order_info = {
            'order_id': order_id,
            'user_id': user_id,
            'plan_type': plan_type,
            'amount': amount,
            'payment_method': payment_method,
            'status': 'pending',  # pending/paid/failed/cancelled
            'created_at': datetime.now().isoformat(),
            'paid_at': None
        }
        
        self._orders[order_id] = order_info
        
        self.logger.info(
            f"创建支付订单成功: 订单号={order_id}, 用户ID={user_id}, "
            f"套餐={plan_type}, 金额={amount}, 支付方式={payment_method}"
        )
        
        # 返回订单信息
        # 实际对接时，这里应该调用第三方支付API，返回支付URL或二维码
        return {
            'order_id': order_id,
            'payment_url': f"https://payment.example.com/pay/{order_id}",  # 模拟支付URL
            'qr_code': f"data:image/png;base64,{order_id}",  # 模拟二维码（实际应该是base64编码的图片）
            'amount': amount,
            'payment_method': payment_method,
            'expires_in': 1800  # 订单过期时间（秒）
        }
    
    def verify_payment(self, order_id: str) -> Dict[str, Any]:
        """验证支付结果
        
        Args:
            order_id: 订单ID
        
        Returns:
            支付验证结果（包含是否支付成功、支付时间等）
        """
        order = self._orders.get(order_id)
        
        if not order:
            return {
                'success': False,
                'message': '订单不存在'
            }
        
        # 实际对接时，这里应该调用第三方支付API查询订单状态
        # 当前简化版：模拟支付验证逻辑
        if order['status'] == 'paid':
            return {
                'success': True,
                'order_id': order_id,
                'paid_at': order.get('paid_at'),
                'amount': order['amount']
            }
        elif order['status'] == 'pending':
            # 模拟：检查订单是否超时
            created_at = datetime.fromisoformat(order['created_at'])
            if (datetime.now() - created_at).seconds > 1800:  # 30分钟超时
                order['status'] = 'failed'
                return {
                    'success': False,
                    'message': '订单已超时'
                }
            return {
                'success': False,
                'message': '订单未支付',
                'status': 'pending'
            }
        else:
            return {
                'success': False,
                'message': f"订单状态: {order['status']}"
            }
    
    def simulate_payment(self, order_id: str) -> bool:
        """模拟支付成功（仅用于测试）
        
        Args:
            order_id: 订单ID
        
        Returns:
            是否模拟成功
        """
        order = self._orders.get(order_id)
        if not order:
            return False
        
        if order['status'] == 'pending':
            order['status'] = 'paid'
            order['paid_at'] = datetime.now().isoformat()
            self.logger.info(f"模拟支付成功: 订单号={order_id}")
            return True
        
        return False
    
    def cancel_order(self, order_id: str) -> bool:
        """取消订单
        
        Args:
            order_id: 订单ID
        
        Returns:
            是否取消成功
        """
        order = self._orders.get(order_id)
        if not order:
            return False
        
        if order['status'] == 'pending':
            order['status'] = 'cancelled'
            self.logger.info(f"取消订单成功: 订单号={order_id}")
            return True
        
        return False

