"""
批量图文任务创建页面
文件路径：src/pro_features/batch/pages/image_batch_task_creation_page.py

复用批量视频任务页的布局和流程，仅将素材类型切换为图文。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget

from src.pro_features.batch.pages.batch_task_creation_page import BatchTaskCreationPage


class ImageBatchTaskCreationPage(BatchTaskCreationPage):
    """批量图文任务创建页面。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(
            parent,
            media_type="image",
            page_title="批量图文任务",
        )
