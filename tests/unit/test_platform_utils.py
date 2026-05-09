"""
平台工具函数单元测试
涵盖模块：
  - src/utils/platform_names.py
  - src/utils/pro_platforms.py
  - src/services/auth/auth_config.py
"""
import os
import pytest
from src.utils.platform_names import (
    get_platform_display_name,
    get_platform_id,
    PLATFORM_ID_TO_NAME,
    PLATFORM_NAME_TO_ID,
)
from src.utils.pro_platforms import is_pro_platform, PRO_PLATFORM_IDS
from src.services.auth.auth_config import get_auth_api_base, is_cloud_auth_enabled


# ─────────────────────────────── platform_names ────────────────────────────── #

class TestPlatformDisplayName:
    def test_known_platform(self):
        assert get_platform_display_name("douyin") == "抖音"

    def test_unknown_platform_returns_id(self):
        assert get_platform_display_name("unknown_platform") == "unknown_platform"

    def test_all_known_ids_have_names(self):
        for pid in PLATFORM_ID_TO_NAME:
            name = get_platform_display_name(pid)
            assert name != pid, f"平台 {pid} 应有中文名"


class TestGetPlatformId:
    def test_known_name(self):
        assert get_platform_id("抖音") == "douyin"

    def test_unknown_name_returns_itself(self):
        assert get_platform_id("未知平台") == "未知平台"

    def test_bidirectional_mapping(self):
        for pid, name in PLATFORM_ID_TO_NAME.items():
            assert get_platform_id(name) == pid


# ─────────────────────────────── pro_platforms ─────────────────────────────── #

class TestProPlatforms:
    def test_wechat_video_is_pro(self):
        assert is_pro_platform("wechat_video") is True

    def test_douyin_not_pro(self):
        assert is_pro_platform("douyin") is False

    def test_kuaishou_not_pro(self):
        assert is_pro_platform("kuaishou") is False

    def test_bilibili_is_pro(self):
        assert is_pro_platform("bilibili") is True

    def test_unknown_is_not_pro(self):
        assert is_pro_platform("unknown_platform") is False

    def test_pro_platform_ids_not_empty(self):
        assert len(PRO_PLATFORM_IDS) > 0


# ─────────────────────────────── auth_config ───────────────────────────────── #

class TestAuthConfig:
    def test_default_base_url_not_empty(self):
        base = get_auth_api_base()
        assert base.startswith("http")

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("AUTH_API_BASE", "https://my-custom-api.com")
        assert get_auth_api_base() == "https://my-custom-api.com"

    def test_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.setenv("AUTH_API_BASE", "https://my-custom-api.com/")
        assert not get_auth_api_base().endswith("/")

    def test_cloud_auth_enabled_by_default(self):
        assert is_cloud_auth_enabled() is True

    def test_cloud_auth_disabled_when_empty(self, monkeypatch):
        monkeypatch.setenv("AUTH_API_BASE", "")
        assert is_cloud_auth_enabled() is False
