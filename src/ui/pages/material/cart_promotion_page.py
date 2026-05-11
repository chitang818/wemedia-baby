"""
购物车推广页面（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/cart_promotion_page.py`
"""

try:
    from src.proprietary.ui.pages.material.cart_promotion_page import CartPromotionPage
except Exception:
    from ..base_page import BasePage
    class CartPromotionPage(BasePage):
        def __init__(self, parent=None):
            super().__init__("购物车推广", parent)
