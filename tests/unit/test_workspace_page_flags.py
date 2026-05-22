"""工作台页面启动行为标志"""

from src.ui.pages.workspace_page import WorkspacePage


def test_workspace_page_disables_first_show_freeze_and_fade():
    assert WorkspacePage._freeze_on_first_show is False
    assert WorkspacePage._enable_show_fade is False
