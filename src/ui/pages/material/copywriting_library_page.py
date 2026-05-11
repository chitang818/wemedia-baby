"""
标准文案库页面（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/copywriting_library_page.py`
"""

try:
    from src.proprietary.ui.pages.material.copywriting_library_page import CopywritingLibraryPage
except Exception:
    from ..base_page import BasePage
    class CopywritingLibraryPage(BasePage):
        def __init__(self, parent=None):
            super().__init__("标准文案库", parent)
