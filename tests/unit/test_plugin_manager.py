"""
插件管理器单元测试：按需加载与 get_available_platforms 回归
"""
import os
import pytest
from unittest.mock import patch

from src.plugins.core.plugin_manager import PluginManager, PLUGIN_REGISTRY
from src.plugins.core.interfaces.login_plugin import LoginPluginInterface


class TestPluginManagerLazy:
    """按需加载与平台列表（不依赖 PLUGIN_EAGER_INIT）"""

    def test_get_available_platforms_returns_registry_ids(self):
        """get_available_platforms() 不触发 import，返回与 PLUGIN_REGISTRY 一致的平台列表"""
        with patch.dict(os.environ, {"PLUGIN_EAGER_INIT": ""}, clear=False):
            # 可能已被其他测试初始化，仅断言返回值包含所有注册平台
            platforms = PluginManager.get_available_platforms()
        expected = sorted([r[0] for r in PLUGIN_REGISTRY])
        assert platforms == expected, "平台列表应与 PLUGIN_REGISTRY 一致"

    def test_get_login_plugin_douyin_lazy(self):
        """首次 get_login_plugin('douyin') 按需加载并实现 LoginPluginInterface"""
        plugin = PluginManager.get_login_plugin("douyin")
        assert plugin is not None
        assert isinstance(plugin, LoginPluginInterface)
        assert plugin.platform_id == "douyin"

    def test_get_login_plugin_invalid_returns_none(self):
        """不存在的 platform_id 返回 None"""
        plugin = PluginManager.get_login_plugin("invalid_platform_xyz")
        assert plugin is None
