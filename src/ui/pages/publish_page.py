"""
发布管理主页面 (作为导航栏父级页面)
文件路径：src/ui/pages/publish_page.py
功能：作为发布管理的入口页面，默认显示发布记录列表
注意：为了满足"点击发布管理默认显示发布列表"的需求，此类直接继承自PublishRecordsPage
"""

from src.ui.pages.publish.publish_records_page import PublishRecordsPage

class PublishPage(PublishRecordsPage):
    """
    发布管理主页面
    作为父级菜单的页面展示，逻辑与发布记录页面一致
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # 可以根据需要覆盖标题或其他属性
        self.setObjectName("publish_page_parent")
