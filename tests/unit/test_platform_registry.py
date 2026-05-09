"""
平台注册中心单元测试
模块：src/services/common/platform_registry.py
"""
import pytest
from src.services.common.platform_registry import PlatformRegistry
from src.services.common.platform_adapter import PlatformAdapter


class FakeAdapter(PlatformAdapter):
    """用于测试的最小适配器实现"""

    def __init__(self):
        super().__init__("fake")

    def publish_video(self, browser, cookie_data, publish_config):
        pass

    def publish_image(self, browser, cookie_data, publish_config):
        pass


class AnotherAdapter(PlatformAdapter):
    def __init__(self):
        super().__init__("another")

    def publish_video(self, browser, cookie_data, publish_config):
        pass

    def publish_image(self, browser, cookie_data, publish_config):
        pass


@pytest.fixture(autouse=True)
def clean_registry():
    """每个测试后清空注册，避免交叉污染"""
    yield
    PlatformRegistry._adapters.clear()
    PlatformRegistry._configs.clear()
    PlatformRegistry._display_names.clear()


class TestPlatformRegistry:
    def test_register_and_get_all(self):
        PlatformRegistry.register("test_platform", FakeAdapter, "测试平台")
        platforms = PlatformRegistry.get_all_platforms()
        assert "test_platform" in platforms

    def test_get_adapter_returns_instance(self):
        PlatformRegistry.register("test_platform", FakeAdapter)
        adapter = PlatformRegistry.get_adapter("test_platform")
        assert isinstance(adapter, FakeAdapter)

    def test_get_adapter_unknown_returns_none(self):
        assert PlatformRegistry.get_adapter("nonexistent") is None

    def test_display_name_registered(self):
        PlatformRegistry.register("p1", FakeAdapter, "平台一")
        name = PlatformRegistry.get_platform_display_name("p1")
        assert name == "平台一"

    def test_display_name_fallback_to_id(self):
        PlatformRegistry.register("p2", FakeAdapter)
        name = PlatformRegistry.get_platform_display_name("p2")
        assert name == "p2"

    def test_get_registered_platforms_info(self):
        PlatformRegistry.register("platA", FakeAdapter, "A平台")
        info = PlatformRegistry.get_registered_platforms_info()
        ids = [i["id"] for i in info]
        assert "platA" in ids

    def test_register_multiple_platforms(self):
        PlatformRegistry.register("p1", FakeAdapter, "平台1")
        PlatformRegistry.register("p2", AnotherAdapter, "平台2")
        assert len(PlatformRegistry.get_all_platforms()) == 2
