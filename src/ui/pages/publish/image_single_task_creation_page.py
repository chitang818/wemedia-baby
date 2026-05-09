"""
单条图文发布任务创建页面
文件路径：src/ui/pages/publish/image_single_task_creation_page.py

与单视频任务页同布局与写库流程，media_mode=image；仅创建任务，执行发布在发布列表页。
"""

from typing import Optional

from PySide6.QtWidgets import QWidget

from .single_task_creation_page import SingleTaskCreationPage


class ImageSingleTaskCreationPage(SingleTaskCreationPage):
    """单条图文任务创建（复用 SingleTaskCreationPage）"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent, page_title="单个图文任务", media_mode="image")
