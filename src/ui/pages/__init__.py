"""
页面模块
提供主窗口的各个页面组件
"""

from .base_page import BasePage
from .workspace_page import WorkspacePage
from .account import AccountPage
from .browser_page import BrowserPage
from .publish_page import PublishPage
from .settings_page import SettingsPage
from .subscription_page import PersonalCenterPage

__all__ = [
    'BasePage',
    'WorkspacePage',
    'AccountPage',
    'BrowserPage',
    'PublishPage',
    'SettingsPage',
    'PersonalCenterPage'
]

