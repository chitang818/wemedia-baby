"""
PathManager 单元测试
使用 monkeypatch 隔离真实系统路径，测试各目录获取方法的逻辑分支。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.common.path_manager import PathManager

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_path_manager_cache():
    """每个测试后重置 PathManager 的内部缓存，避免测试间污染"""
    PathManager._app_data_dir = None
    PathManager._resource_dir = None
    yield
    PathManager._app_data_dir = None
    PathManager._resource_dir = None


class TestGetResourceDir:

    def test_dev_environment_returns_path(self):
        with patch.object(sys, "frozen", False, create=True):
            resource_dir = PathManager.get_resource_dir()
            assert isinstance(resource_dir, Path)
            assert resource_dir.exists()

    def test_caches_result(self):
        r1 = PathManager.get_resource_dir()
        r2 = PathManager.get_resource_dir()
        assert r1 == r2

    def test_frozen_pyinstaller_uses_meipass(self, tmp_path):
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "_MEIPASS", str(tmp_path), create=True):
                PathManager._resource_dir = None
                result = PathManager.get_resource_dir()
                assert result == tmp_path

    def test_get_resource_path(self, tmp_path):
        PathManager._resource_dir = tmp_path
        (tmp_path / "resources").mkdir()
        (tmp_path / "resources" / "test.txt").write_text("x")
        p = PathManager.get_resource_path("resources/test.txt")
        assert p == tmp_path / "resources" / "test.txt"


class TestGetAppDataDir:

    def test_returns_path_object(self, tmp_path):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            PathManager._app_data_dir = None
            result = PathManager.get_app_data_dir()
            assert isinstance(result, Path)

    def test_creates_directory(self, tmp_path):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            PathManager._app_data_dir = None
            result = PathManager.get_app_data_dir()
            assert result.exists()

    def test_path_contains_app_name(self, tmp_path):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            PathManager._app_data_dir = None
            result = PathManager.get_app_data_dir()
            assert "WeMediaBaby" in str(result)

    def test_caches_after_first_call(self, tmp_path):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            PathManager._app_data_dir = None
            r1 = PathManager.get_app_data_dir()
            r2 = PathManager.get_app_data_dir()
            assert r1 == r2


class TestGetDbPath:

    def test_db_path_is_under_app_data(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        db_path = PathManager.get_db_path()
        assert str(tmp_path) in str(db_path)
        assert db_path.name == "database.db"


class TestGetDebugScreenshotsDir:

    def test_under_app_data_and_creates_dir(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        p = PathManager.get_debug_screenshots_dir("douyin")
        assert "debug" in str(p)
        assert "screenshots" in str(p)
        assert p.name == "douyin"
        assert p.is_dir()

    def test_raises_empty_platform(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        with pytest.raises(ValueError):
            PathManager.get_debug_screenshots_dir("")


class TestGetPlatformAccountDir:

    def test_returns_correct_structure(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        result = PathManager.get_platform_account_dir(
            platform="douyin",
            platform_username="test",
            profile_folder_name="profile_001",
        )
        assert "douyin" in str(result)
        assert "profile_001" in str(result)

    def test_raises_without_profile_folder_name(self):
        with pytest.raises(ValueError, match="profile_folder_name"):
            PathManager.get_platform_account_dir(
                platform="douyin",
                platform_username="test",
                profile_folder_name="",
            )

    def test_raises_with_none_profile_folder_name(self):
        with pytest.raises(ValueError):
            PathManager.get_platform_account_dir(
                platform="douyin",
                platform_username="test",
                profile_folder_name=None,
            )


class TestGetAccountRoot:

    def test_resolves_from_profile_folder_name(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        account = {
            "platform": "douyin",
            "platform_username": "test",
            "profile_folder_name": "profile_abc",
        }
        result = PathManager.get_account_root(account)
        assert "profile_abc" in str(result)

    def test_resolves_from_cookie_path(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        account = {
            "platform": "douyin",
            "platform_username": "test",
            "profile_folder_name": "",
            "cookie_path": str(tmp_path / "data" / "douyin" / "profile_xyz" / "cookies.json"),
        }
        result = PathManager.get_account_root(account)
        assert "profile_xyz" in str(result)

    def test_raises_when_no_profile_info(self):
        account = {
            "platform": "douyin",
            "platform_username": "test",
            "profile_folder_name": "",
            "cookie_path": "",
        }
        with pytest.raises(ValueError):
            PathManager.get_account_root(account)
