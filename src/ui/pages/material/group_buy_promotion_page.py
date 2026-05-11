"""
团购推广页面（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/group_buy_promotion_page.py`
"""

try:
    from src.proprietary.ui.pages.material.group_buy_promotion_page import GroupBuyPromotionPage
except Exception:
    from ..base_page import BasePage
    class GroupBuyPromotionPage(BasePage):
        def __init__(self, parent=None):
            super().__init__("团购推广", parent)
