"""
批量图文任务创建页面（占位）
文件路径：src/pro_features/batch/pages/image_batch_task_creation_page.py

实现时复用以下模块（与批量视频页共享）：
  - batch_task_definitions.py       — 类型定义（file_type="image"）
  - batch_preview_builder.py        — build_preview_tasks()
  - batch_publish_builder.py        — build_publish_tasks_for_batch()
  - batch_preview_exclusion.py      — PreviewExclusionSet
  - batch_publish_targets.py        — expand_batch_selected_accounts_for_publish()
  - material_auto_matcher.py        — MaterialAutoMatcher(media_type="image")
  - src.ui.publish.location         — 位置弹窗与标准字段（与批量视频一致）
"""
from src.ui.pages.common.placeholder_page import PlaceholderPage
try:
    from qfluentwidgets import FluentIcon
except ImportError:
    pass


class ImageBatchTaskCreationPage(PlaceholderPage):
    """批量图文任务创建页面（占位）"""

    def __init__(self, parent=None):
        icon = FluentIcon.PHOTO if 'FluentIcon' in globals() else None
        super().__init__(
            "批量图文任务",
            "批量图文任务创建功能即将推出，敬请期待",
            icon,
            parent,
        )
