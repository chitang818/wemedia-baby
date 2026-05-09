"""
浏览器模块
提供 Undetected Playwright 浏览器自动化能力
"""

from .browser_manager import UndetectedBrowserManager
from .browser_factory import BrowserFactory
from .profile_manager import ProfileManager
from .process_supervisor import ProcessSupervisor

# 保留旧类以兼容现有代码
from .undetected_playwright_browser import UndetectedPlaywrightBrowser

__all__ = [
    "UndetectedBrowserManager",
    "BrowserFactory",
    "ProfileManager",
    "ProcessSupervisor",
    "UndetectedPlaywrightBrowser",  # 兼容
]
