"""
图片库页面（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/image_library_page.py`
"""

try:
    from src.proprietary.ui.pages.material.image_library_page import ImageLibraryPage
except Exception:
    from ..base_page import BasePage
    class ImageLibraryPage(BasePage):
        def __init__(self, parent=None):
            super().__init__("图片库", parent)
