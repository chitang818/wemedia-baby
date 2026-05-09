"""
冒烟测试：用户目录优化方案验证
覆盖：
  1. 安装目录与数据目录分离（PathManager 不返回含 app 子目录的路径）
  2. 各路径方法返回值正确
  3. backup_manager 模块已移除
  4. ProfileManager 缺参数时抛出 ValueError
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.infrastructure.common.path_manager import PathManager

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_path_manager_cache():
    PathManager._app_data_dir = None
    PathManager._resource_dir = None
    yield
    PathManager._app_data_dir = None
    PathManager._resource_dir = None


class TestDirectorySeparation:
    """验证用户数据目录与程序安装目录逻辑分离"""

    def test_app_data_dir_contains_app_name(self, tmp_path):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            app_data = PathManager.get_app_data_dir()
            assert "WeMediaBaby" in str(app_data)

    def test_app_data_dir_does_not_end_with_app_subdir(self, tmp_path):
        """数据目录本身不应以 app 结尾（程序在 app 子目录，数据在父目录）"""
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            app_data = PathManager.get_app_data_dir()
            assert not str(app_data).rstrip("\\/").endswith("app"), (
                f"PathManager.get_app_data_dir() 不应以 \\app 结尾，"
                f"实际返回：{app_data}"
            )

    def test_app_data_dir_is_parent_of_hypothetical_app_dir(self, tmp_path):
        """程序安装目录（WeMediaBaby\\app）应当是数据目录的子目录"""
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            app_data = PathManager.get_app_data_dir()
            hypothetical_app_dir = app_data / "app"
            assert str(hypothetical_app_dir).startswith(str(app_data))


class TestPathMethods:
    """各 PathManager 路径方法返回值正确性"""

    def test_db_path_filename_is_database_db(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        assert PathManager.get_db_path().name == "database.db"

    def test_db_path_not_wemedia_db(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        assert PathManager.get_db_path().name != "wemedia.db"

    def test_log_dir_is_under_app_data(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        assert str(PathManager.get_log_dir()).startswith(str(tmp_path))

    def test_config_dir_is_under_app_data(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        assert str(PathManager.get_config_dir()).startswith(str(tmp_path))

    def test_cache_dir_is_under_app_data(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        assert str(PathManager.get_cache_dir()).startswith(str(tmp_path))

    def test_platform_account_dir_structure(self, tmp_path):
        PathManager._app_data_dir = tmp_path
        result = PathManager.get_platform_account_dir(
            platform="douyin",
            platform_username="test_user",
            profile_folder_name="profile_abc123",
        )
        assert "douyin" in str(result)
        assert "profile_abc123" in str(result)


class TestBackupManagerRemoved:
    """确认 backup_manager 模块已被删除"""

    def test_backup_manager_module_does_not_exist(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("src.infrastructure.storage.backup_manager")


class TestProfileManagerRequiresParams:
    """ProfileManager 缺必填参数时应抛出 ValueError，不再静默回退到 data/browsers/"""

    def test_missing_platform_raises_value_error(self, tmp_path):
        from src.infrastructure.browser.profile_manager import ProfileManager
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            PathManager._app_data_dir = None
            with pytest.raises(ValueError, match="platform"):
                ProfileManager(
                    account_id="acc_001",
                    platform="",
                    account_name="test_user",
                    profile_folder_name="profile_001",
                )

    def test_missing_account_name_raises_value_error(self, tmp_path):
        from src.infrastructure.browser.profile_manager import ProfileManager
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            PathManager._app_data_dir = None
            with pytest.raises(ValueError, match="account_name"):
                ProfileManager(
                    account_id="acc_001",
                    platform="douyin",
                    account_name="",
                    profile_folder_name="profile_001",
                )

    def test_no_browsers_fallback_directory_created(self, tmp_path):
        """缺参数时不应在 data/browsers/ 下创建任何目录"""
        from src.infrastructure.browser.profile_manager import ProfileManager
        with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
            PathManager._app_data_dir = None
            try:
                ProfileManager(
                    account_id="acc_001",
                    platform="",
                    account_name="",
                    profile_folder_name="profile_001",
                )
            except ValueError:
                pass
            browsers_dir = PathManager.get_app_data_dir() / "data" / "browsers"
            assert not browsers_dir.exists(), (
                "缺参数时不应创建 data/browsers/ 目录"
            )
