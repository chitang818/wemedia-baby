"""
位置推广页面（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/location_promotion_page.py`
"""

try:
    from src.proprietary.ui.pages.material.location_promotion_page import (
        LocationPromotionPage,
    )
except Exception:
    from ..base_page import BasePage

    class LocationPromotionPage(BasePage):
        def __init__(self, parent=None):
            super().__init__("位置推广", parent)
