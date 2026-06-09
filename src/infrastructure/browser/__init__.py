"""
浏览器模块
提供基于 Patchright 的浏览器自动化能力
"""

from .automation_api import ENGINE_NAME
from .browser_manager import UndetectedBrowserManager
from .browser_factory import BrowserFactory
from .profile_manager import ProfileManager
from .process_supervisor import ProcessSupervisor
from .detached_chrome_launcher import DetachedChromeLauncher, DetachedChromeLaunchResult

__all__ = [
    "ENGINE_NAME",
    "UndetectedBrowserManager",
    "BrowserFactory",
    "ProfileManager",
    "ProcessSupervisor",
    "DetachedChromeLauncher",
    "DetachedChromeLaunchResult",
]
