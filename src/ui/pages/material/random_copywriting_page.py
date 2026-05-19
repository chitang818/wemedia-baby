"""
随机文案库页面（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/random_copywriting_page.py`
"""

try:
    from src.proprietary.ui.pages.material.random_copywriting_page import RandomCopywritingPage
except Exception as _import_err:
    import logging

    logging.getLogger(__name__).error(
        "随机文案库页面加载失败: %s", _import_err, exc_info=True
    )
    from ..base_page import BasePage

    class RandomCopywritingPage(BasePage):  # type: ignore[no-redef]
        def __init__(self, parent=None):
            super().__init__("随机文案库", parent)
