"""
平台插件设置工具函数单元测试
模块：src/utils/plugin_settings.py
"""
import pytest
from unittest.mock import MagicMock
from src.utils.plugin_settings import (
    get_default_enabled_platform_ids,
    filter_enabled_platform_ids,
    get_enabled_platform_ids,
    is_platform_enabled,
)


class TestDefaultEnabledPlatforms:
    def test_default_not_empty(self):
        defaults = get_default_enabled_platform_ids()
        assert len(defaults) > 0

    def test_douyin_in_defaults(self):
        assert "douyin" in get_default_enabled_platform_ids()

    def test_kuaishou_in_defaults(self):
        assert "kuaishou" in get_default_enabled_platform_ids()


class TestFilterEnabledPlatformIds:
    def test_returns_intersection(self):
        all_ids = ["douyin", "kuaishou", "wechat_video", "bilibili"]
        enabled = ["douyin", "bilibili"]
        result = filter_enabled_platform_ids(all_ids, enabled)
        assert sorted(result) == ["bilibili", "douyin"]

    def test_empty_all_ids(self):
        assert filter_enabled_platform_ids([], ["douyin"]) == []

    def test_empty_enabled_ids(self):
        assert filter_enabled_platform_ids(["douyin"], []) == []

    def test_preserves_order_from_all_ids(self):
        all_ids = ["a", "b", "c"]
        result = filter_enabled_platform_ids(all_ids, ["c", "a"])
        assert result == ["a", "c"]


class TestGetEnabledPlatformIds:
    def _mock_config(self, value):
        cfg = MagicMock()
        cfg.get_app_config.return_value = {"enabled_platform_plugins": value}
        return cfg

    def test_returns_configured_ids(self):
        cfg = self._mock_config(["douyin", "kuaishou"])
        result = get_enabled_platform_ids(cfg)
        assert result == ["douyin", "kuaishou"]

    def test_falls_back_to_defaults_when_none(self):
        cfg = self._mock_config(None)
        result = get_enabled_platform_ids(cfg)
        assert result == get_default_enabled_platform_ids()

    def test_falls_back_when_empty_list(self):
        cfg = self._mock_config([])
        result = get_enabled_platform_ids(cfg)
        assert result == get_default_enabled_platform_ids()


class TestIsPlatformEnabled:
    def _mock_config(self, enabled_ids):
        cfg = MagicMock()
        cfg.get_app_config.return_value = {"enabled_platform_plugins": enabled_ids}
        return cfg

    def test_enabled_platform(self):
        cfg = self._mock_config(["douyin", "kuaishou"])
        assert is_platform_enabled("douyin", config_center=cfg) is True

    def test_disabled_platform(self):
        cfg = self._mock_config(["douyin"])
        assert is_platform_enabled("bilibili", config_center=cfg) is False
