"""
功能开关单元测试
测试 FeatureFlags 的各分支逻辑及装饰器行为。
注意：FeatureFlags._pro_licensed 是类变量，每个测试后需重置。
"""

import pytest

from config.feature_flags import (
    FeatureFlags,
    FeatureNotAvailableError,
    require_feature,
    require_pro,
    require_platform,
    is_feature_enabled,
    is_platform_available,
    is_pro,
    get_available_platforms,
    USE_PLUGIN_SYSTEM,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_pro_flag():
    """每个测试后重置 Pro 状态，避免测试间污染"""
    FeatureFlags._pro_licensed = False
    FeatureFlags._license_key = ""
    yield
    FeatureFlags._pro_licensed = False
    FeatureFlags._license_key = ""


class TestCommunityFeatures:

    def test_community_feature_always_enabled(self):
        assert FeatureFlags.is_feature_enabled("douyin_login") is True
        assert FeatureFlags.is_feature_enabled("basic_ui") is True
        assert FeatureFlags.is_feature_enabled("browser_manager") is True

    def test_all_community_features_enabled(self):
        for feat in FeatureFlags.COMMUNITY_FEATURES:
            assert FeatureFlags.is_feature_enabled(feat) is True

    def test_unknown_feature_returns_false(self):
        assert FeatureFlags.is_feature_enabled("nonexistent_feature_xyz") is False


class TestProFeatures:

    def test_pro_feature_disabled_without_license(self):
        assert FeatureFlags.is_feature_enabled("batch_publish") is False
        assert FeatureFlags.is_feature_enabled("scheduled_publish") is False

    def test_pro_feature_enabled_after_activate(self):
        FeatureFlags.activate_pro("valid_key_123")
        assert FeatureFlags.is_feature_enabled("batch_publish") is True

    def test_all_pro_features_enabled_after_activate(self):
        FeatureFlags.activate_pro("key")
        for feat in FeatureFlags.PRO_FEATURES:
            assert FeatureFlags.is_feature_enabled(feat) is True

    def test_activate_pro_with_empty_key_fails(self):
        result = FeatureFlags.activate_pro("")
        assert result is False
        assert FeatureFlags.is_pro_licensed() is False

    def test_activate_pro_returns_true_with_valid_key(self):
        result = FeatureFlags.activate_pro("any_non_empty_key")
        assert result is True


class TestPlatformAvailability:

    def test_douyin_always_available(self):
        assert FeatureFlags.is_platform_available("douyin") is True

    def test_pro_platform_unavailable_without_license(self):
        assert FeatureFlags.is_platform_available("kuaishou") is False
        assert FeatureFlags.is_platform_available("xiaohongshu") is False
        assert FeatureFlags.is_platform_available("wechat_video") is False

    def test_pro_platform_available_after_activate(self):
        FeatureFlags.activate_pro("key")
        assert FeatureFlags.is_platform_available("kuaishou") is True
        assert FeatureFlags.is_platform_available("xiaohongshu") is True

    def test_unknown_platform_returns_false(self):
        assert FeatureFlags.is_platform_available("unknown_platform") is False

    def test_get_available_platforms_community(self):
        platforms = FeatureFlags.get_available_platforms()
        assert "douyin" in platforms
        assert "kuaishou" not in platforms

    def test_get_available_platforms_pro(self):
        FeatureFlags.activate_pro("key")
        platforms = FeatureFlags.get_available_platforms()
        assert "douyin" in platforms
        assert "kuaishou" in platforms


class TestDecorators:

    def test_require_feature_allows_community_feature(self):
        @require_feature("douyin_login")
        def func():
            return "ok"
        assert func() == "ok"

    def test_require_feature_raises_without_pro(self):
        @require_feature("batch_publish")
        def func():
            return "ok"
        with pytest.raises(FeatureNotAvailableError) as exc_info:
            func()
        assert exc_info.value.feature == "batch_publish"

    def test_require_feature_allows_pro_feature_when_licensed(self):
        FeatureFlags.activate_pro("key")

        @require_feature("batch_publish")
        def func():
            return "pro_ok"
        assert func() == "pro_ok"

    def test_require_pro_raises_without_license(self):
        @require_pro
        def func():
            return "pro_only"
        with pytest.raises(FeatureNotAvailableError):
            func()

    def test_require_pro_passes_with_license(self):
        FeatureFlags.activate_pro("key")

        @require_pro
        def func():
            return "pro_ok"
        assert func() == "pro_ok"

    def test_require_platform_allows_open_source(self):
        @require_platform("douyin")
        def func():
            return "ok"
        assert func() == "ok"

    def test_require_platform_raises_for_pro_without_license(self):
        @require_platform("kuaishou")
        def func():
            return "ok"
        with pytest.raises(FeatureNotAvailableError):
            func()


class TestConvenienceFunctions:

    def test_is_feature_enabled(self):
        assert is_feature_enabled("basic_ui") is True
        assert is_feature_enabled("batch_publish") is False

    def test_is_platform_available(self):
        assert is_platform_available("douyin") is True

    def test_is_pro(self):
        assert is_pro() is False
        FeatureFlags.activate_pro("key")
        assert is_pro() is True

    def test_get_available_platforms(self):
        platforms = get_available_platforms()
        assert isinstance(platforms, set)
        assert "douyin" in platforms

    def test_use_plugin_system_flag(self):
        assert USE_PLUGIN_SYSTEM is True

    def test_edition_name(self):
        assert FeatureFlags.get_edition_name() == "Community Edition"
        FeatureFlags.activate_pro("key")
        assert FeatureFlags.get_edition_name() == "Pro Edition"
