"""
标准文案库页面（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/copywriting_library_page.py`
"""

try:
    from src.proprietary.ui.pages.material.copywriting_library_page import CopywritingLibraryPage
except Exception as _import_err:
    import logging

    logging.getLogger(__name__).error(
        "标准文案库页面加载失败: %s", _import_err, exc_info=True
    )
    from ..base_page import BasePage

    class CopywritingLibraryPage(BasePage):  # type: ignore[no-redef]
        def __init__(self, parent=None):
            super().__init__("标准文案库", parent)
