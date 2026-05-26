"""
Cookie 管理器单元测试
测试范围：CookieManager 构造、save_cookie/load_cookie 明文 JSON 读写
"""
import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.services.account.cookie_manager import (
    CookieManager,
    COOKIE_FILENAME,
    _ENCRYPTED_PREFIX,
    flat_cookies_have_session,
)


@pytest.fixture
def sample_cookies():
    """示例 Cookie 数据"""
    return {
        "sessionid": "test_session_id",
        "sessionid_ss": "test_session_ss",
        "sid_tt": "test_sid_tt",
    }


@pytest.fixture
def tmp_account_dir(tmp_path):
    """创建临时账号目录并 patch PathManager"""
    account_dir = tmp_path / "data" / "douyin" / "profile_abc123"
    account_dir.mkdir(parents=True, exist_ok=True)
    with patch(
        "src.services.account.cookie_manager.PathManager"
    ) as MockPM:
        MockPM.get_platform_account_dir.return_value = account_dir
        yield account_dir, MockPM


class TestCookieManager:
    """Cookie 管理器测试类"""

    def test_constructor_no_args(self):
        """CookieManager 不再需要 user_id"""
        manager = CookieManager()
        assert manager is not None

    def test_save_cookie_creates_json(self, sample_cookies, tmp_account_dir):
        """save_cookie 应创建 cookies.json 文件"""
        account_dir, _ = tmp_account_dir
        manager = CookieManager()
        path = manager.save_cookie(
            platform_username="test_user",
            platform="douyin",
            cookie_data=sample_cookies,
            profile_folder_name="profile_abc123",
        )
        assert path == str(account_dir / COOKIE_FILENAME)
        assert os.path.exists(path)
        with open(path, 'rb') as f:
            saved_raw = f.read()
        assert saved_raw.startswith(_ENCRYPTED_PREFIX)
        assert sample_cookies["sessionid"].encode("utf-8") not in saved_raw
        assert manager.load_cookie(
            platform_username="test_user",
            platform="douyin",
            profile_folder_name="profile_abc123",
        ) == sample_cookies

    def test_save_cookie_rejects_empty_username_or_platform(self, sample_cookies):
        """平台用户名或平台名称为空时应抛出 ValueError"""
        manager = CookieManager()
        with pytest.raises(ValueError, match="不能为空"):
            manager.save_cookie(platform_username="", platform="douyin",
                                cookie_data=sample_cookies, profile_folder_name="p")
        with pytest.raises(ValueError, match="不能为空"):
            manager.save_cookie(platform_username="u", platform="",
                                cookie_data=sample_cookies, profile_folder_name="p")

    def test_save_cookie_rejects_empty_profile(self, sample_cookies):
        """profile_folder_name 为空时应抛出 ValueError"""
        manager = CookieManager()
        with pytest.raises(ValueError, match="profile_folder_name"):
            manager.save_cookie(platform_username="u", platform="douyin",
                                cookie_data=sample_cookies, profile_folder_name="")

    def test_load_cookie_from_json(self, sample_cookies, tmp_account_dir):
        """load_cookie 应兼容旧版明文 cookies.json。"""
        account_dir, _ = tmp_account_dir
        cookies_file = account_dir / COOKIE_FILENAME
        with open(str(cookies_file), 'w', encoding='utf-8') as f:
            json.dump(sample_cookies, f)
        manager = CookieManager()
        result = manager.load_cookie(
            platform_username="test_user", platform="douyin",
            profile_folder_name="profile_abc123",
        )
        assert result == sample_cookies

    def test_load_cookie_ignores_storage_state_only(self, tmp_account_dir):
        """仅有 storage_state.json 而无 cookies.json 时不应视为已加载 Cookie"""
        account_dir, _ = tmp_account_dir
        browser_dir = account_dir / "browser"
        browser_dir.mkdir(parents=True, exist_ok=True)
        storage_data = {"cookies": [{"name": "sid", "value": "abc"}]}
        with open(str(browser_dir / "storage_state.json"), 'w', encoding='utf-8') as f:
            json.dump(storage_data, f)

        manager = CookieManager()
        result = manager.load_cookie(
            platform_username="test_user", platform="douyin",
            profile_folder_name="profile_abc123",
        )
        assert result is None
        assert not os.path.exists(str(account_dir / COOKIE_FILENAME))

    def test_load_cookie_returns_none_for_empty_input(self):
        """平台用户名或平台名称为空时 load_cookie 返回 None"""
        manager = CookieManager()
        assert manager.load_cookie(platform_username="", platform="douyin") is None
        assert manager.load_cookie(platform_username="u", platform="") is None

    def test_load_cookie_returns_none_when_no_files(self, tmp_account_dir):
        """目录存在但无任何 Cookie 文件时返回 None"""
        manager = CookieManager()
        result = manager.load_cookie(
            platform_username="test_user", platform="douyin",
            profile_folder_name="profile_abc123",
        )
        assert result is None

    def test_cookie_exists(self, sample_cookies, tmp_account_dir):
        """cookie_exists 应正确检测 cookies.json"""
        account_dir, _ = tmp_account_dir
        manager = CookieManager()
        assert not manager.cookie_exists("u", "douyin", "profile_abc123")
        with open(str(account_dir / COOKIE_FILENAME), 'w') as f:
            json.dump(sample_cookies, f)
        assert manager.cookie_exists("u", "douyin", "profile_abc123")

    def test_delete_cookie(self, sample_cookies, tmp_account_dir):
        """delete_cookie 应删除 cookies.json"""
        account_dir, _ = tmp_account_dir
        cookies_file = account_dir / COOKIE_FILENAME
        with open(str(cookies_file), 'w') as f:
            json.dump(sample_cookies, f)
        manager = CookieManager()
        assert manager.delete_cookie("u", "douyin", "profile_abc123")
        assert not os.path.exists(str(cookies_file))


class TestMergeStorageState:
    """merge_storage_state_into_flat_cookies 防复活会话测试"""

    def test_flat_cookies_have_session_kuaishou(self):
        assert flat_cookies_have_session(
            {"userId": "1", "kuaishou.web.cp.api_st": "x"}, "kuaishou"
        )
        assert not flat_cookies_have_session({"userId": "1"}, "kuaishou")
        assert not flat_cookies_have_session({}, "kuaishou")

    def test_skips_merge_when_cookies_json_newer(self, tmp_account_dir):
        account_dir, _ = tmp_account_dir
        browser_dir = account_dir / "browser"
        browser_dir.mkdir(parents=True, exist_ok=True)
        cookies_file = account_dir / COOKIE_FILENAME
        state_file = browser_dir / "storage_state.json"
        with open(cookies_file, "w", encoding="utf-8") as f:
            json.dump({"did": "only"}, f)
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cookies": [
                        {"name": "userId", "value": "stale"},
                        {"name": "kuaishou.web.cp.api_st", "value": "stale"},
                    ]
                },
                f,
            )
        import time
        os.utime(cookies_file, (time.time() + 10, time.time() + 10))

        manager = CookieManager()
        merged = manager.merge_storage_state_into_flat_cookies(
            "test_user",
            "kuaishou",
            "profile_abc123",
            {"did": "only"},
        )
        assert merged == {"did": "only"}
        assert "userId" not in merged

    def test_does_not_resurrect_session_without_flat_session(self, tmp_account_dir):
        account_dir, _ = tmp_account_dir
        browser_dir = account_dir / "browser"
        browser_dir.mkdir(parents=True, exist_ok=True)
        state_file = browser_dir / "storage_state.json"
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "cookies": [
                        {"name": "userId", "value": "stale"},
                        {"name": "kuaishou.web.cp.api_st", "value": "stale"},
                        {"name": "did", "value": "device"},
                    ]
                },
                f,
            )
        import time
        past = time.time() - 100
        os.utime(state_file, (past, past))

        manager = CookieManager()
        merged = manager.merge_storage_state_into_flat_cookies(
            "test_user",
            "kuaishou",
            "profile_abc123",
            {},
        )
        assert "userId" not in merged
        assert "kuaishou.web.cp.api_st" not in merged
        assert merged.get("did") == "device"
