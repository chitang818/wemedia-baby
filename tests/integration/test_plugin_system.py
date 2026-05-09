"""
插件系统集成测试
验证插件注册表、懒加载机制及接口契约。
"""

import os
import pytest

from src.plugins.core.plugin_manager import PluginManager
from src.plugins.core.interfaces.login_plugin import LoginPluginInterface
from config.feature_flags import USE_PLUGIN_SYSTEM

pytestmark = pytest.mark.integration


def test_feature_flag_enabled():
    """USE_PLUGIN_SYSTEM 开关默认应为开启"""
    assert USE_PLUGIN_SYSTEM is True, "Plugin system should be enabled by default"


def test_douyin_plugin_loader():
    """抖音登录插件可正常加载，且符合接口契约"""
    plugin = PluginManager.get_login_plugin("douyin")
    assert plugin is not None, "抖音插件应成功加载"
    assert isinstance(plugin, LoginPluginInterface), "插件必须实现 LoginPluginInterface"
    assert plugin.platform_id == "douyin"
    assert plugin.platform_name == "抖音"
    assert plugin.login_url  # 不为空


def test_kuaishou_plugin_loader():
    """快手登录插件可正常加载"""
    plugin = PluginManager.get_login_plugin("kuaishou")
    assert plugin is not None, "快手插件应成功加载"
    assert isinstance(plugin, LoginPluginInterface)
    assert plugin.platform_id == "kuaishou"


def test_xiaohongshu_plugin_loader():
    """小红书插件加载（Pro）：若 Pro 目录存在则断言，否则跳过"""
    plugin = PluginManager.get_login_plugin("xiaohongshu")
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.exists(os.path.join(project_root, "plugins_pro", "plugins", "xiaohongshu")):
        assert plugin is not None, "小红书 Pro 插件应成功加载"
    else:
        pytest.skip("Pro 插件目录不存在，跳过小红书插件测试")


def test_wechat_video_plugin_loader():
    """视频号插件加载（Pro）：若 Pro 目录存在则断言，否则跳过"""
    plugin = PluginManager.get_login_plugin("wechat_video")
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if os.path.exists(os.path.join(project_root, "plugins_pro", "plugins", "wechat_video")):
        assert plugin is not None, "视频号 Pro 插件应成功加载"
    else:
        pytest.skip("Pro 插件目录不存在，跳过视频号插件测试")


def test_invalid_plugin_returns_none():
    """不存在的平台 ID 应返回 None"""
    plugin = PluginManager.get_login_plugin("invalid_platform_xyz")
    assert plugin is None, "无效平台 ID 应返回 None"
