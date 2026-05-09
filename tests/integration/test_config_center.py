"""
ConfigCenter 集成测试
使用临时目录验证配置读取、版本管理逻辑。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infrastructure.common.config.config_center import ConfigVersionManager, ConfigCenter

pytestmark = pytest.mark.integration


class TestConfigVersionManager:

    def test_save_and_get_version(self):
        manager = ConfigVersionManager(max_versions=5)
        config_data = {"key": "value", "nested": {"a": 1}}
        version = manager.save_version("test_config", config_data)
        assert version >= 1
        retrieved = manager.get_version("test_config", version)
        assert retrieved == config_data

    def test_get_latest_version(self):
        manager = ConfigVersionManager()
        manager.save_version("cfg", {"v": 1})
        manager.save_version("cfg", {"v": 2})
        latest = manager.get_latest_version("cfg")
        assert latest == {"v": 2}

    def test_get_latest_version_none_when_empty(self):
        manager = ConfigVersionManager()
        result = manager.get_latest_version("nonexistent")
        assert result is None

    def test_max_versions_limit(self):
        manager = ConfigVersionManager(max_versions=3)
        for i in range(5):
            manager.save_version("cfg", {"v": i})
        # 旧版本应被裁剪，只保留最新 3 个（versions 属性为公开属性）
        history = manager.versions.get("cfg", [])
        assert len(history) <= 3

    def test_different_data_produces_new_version(self):
        manager = ConfigVersionManager()
        v1 = manager.save_version("cfg", {"k": "v1"})
        v2 = manager.save_version("cfg", {"k": "v2"})
        assert v2 > v1

    def test_save_version_returns_version_number(self):
        manager = ConfigVersionManager()
        v = manager.save_version("cfg", {"key": "value"})
        assert isinstance(v, int)
        assert v >= 1


class TestConfigCenterLocalLoad:

    @pytest.fixture
    def config_dir(self, tmp_path) -> Path:
        d = tmp_path / "config"
        d.mkdir()
        return d

    async def test_get_returns_default_before_load(self, config_dir):
        cc = ConfigCenter(config_dir=str(config_dir))
        try:
            result = cc.get("nonexistent.key", default="default_val")
            assert result == "default_val"
        finally:
            cc.close()

    async def test_get_app_config_returns_dict(self, config_dir):
        app_config = {"version": "1.0", "debug": False}
        (config_dir / "app_config.json").write_text(
            json.dumps(app_config), encoding="utf-8"
        )
        cc = ConfigCenter(config_dir=str(config_dir))
        try:
            await cc.initialize()
            cfg = cc.get_app_config()
            assert isinstance(cfg, dict)
        finally:
            cc.close()

    async def test_get_returns_none_for_unknown_key(self, config_dir):
        cc = ConfigCenter(config_dir=str(config_dir))
        try:
            await cc.initialize()
            cfg = cc.get("nonexistent.platform.key")
            assert cfg is None
        finally:
            cc.close()

    async def test_get_platform_config_is_dict_or_none(self, config_dir):
        """get_platform_config 在有本地 platforms/ 目录时返回 dict，否则返回 None"""
        cc = ConfigCenter(config_dir=str(config_dir))
        try:
            await cc.initialize()
            cfg = cc.get_platform_config("douyin")
            assert cfg is None or isinstance(cfg, dict)
        finally:
            cc.close()
