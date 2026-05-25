"""
位置推广编辑弹窗（开源包装层）
"""

try:
    from src.proprietary.ui.pages.material.location_promotion_edit_dialog import (
        LocationPromotionEditDialog,
    )
except Exception:
    from src.ui.components.base_dialog import StandardBaseDialog

    class LocationPromotionEditDialog(StandardBaseDialog):
        def __init__(self, parent=None, item_data=None):
            super().__init__(parent, title="位置推广")
