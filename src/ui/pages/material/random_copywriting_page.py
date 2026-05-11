"""
随机文案库页面（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/random_copywriting_page.py`
"""

try:
    from src.proprietary.ui.pages.material.random_copywriting_page import RandomCopywritingPage
except Exception:
    from ..base_page import BasePage
    class RandomCopywritingPage(BasePage):
        def __init__(self, parent=None):
            super().__init__("随机文案库", parent)
