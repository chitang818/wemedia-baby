"""
视频库页面（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/video_library_page.py`
"""

try:
    from src.proprietary.ui.pages.material.video_library_page import VideoLibraryPage
except Exception:
    from ..base_page import BasePage
    class VideoLibraryPage(BasePage):
        def __init__(self, parent=None):
            super().__init__("视频库", parent)
