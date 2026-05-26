"""单条发布页发布设置平台能力表单元测试。"""

from __future__ import annotations

import pytest

from src.domain.publish.single_publish_options_capabilities import (
    ALL_TAG_TYPES,
    capabilities_for_platform,
)

pytestmark = pytest.mark.unit


class TestCapabilitiesForPlatform:

    def test_douyin_video(self):
        cap = capabilities_for_platform("douyin", is_image_mode=False)
        assert cap.show_add_tags is True
        assert cap.tag_types == ALL_TAG_TYPES
        assert "位置" not in cap.tag_types
        assert cap.show_location is True
        assert cap.show_location_mode is True
        assert cap.show_promotion is True
        assert cap.show_music is False
        assert cap.show_privacy is True
        assert cap.show_work_declaration is True

    def test_douyin_image_has_music(self):
        cap = capabilities_for_platform("douyin", is_image_mode=True)
        assert cap.show_music is True

    def test_kuaishou_only_work_declaration(self):
        cap = capabilities_for_platform("kuaishou", is_image_mode=False)
        assert cap.show_add_tags is False
        assert cap.show_location is False
        assert cap.show_promotion is False
        assert cap.show_privacy is False
        assert cap.show_work_declaration is True

    def test_xiaohongshu_location_and_privacy(self):
        cap = capabilities_for_platform("xiaohongshu", is_image_mode=False)
        assert cap.show_add_tags is False
        assert cap.show_location is True
        assert cap.show_location_mode is False
        assert cap.show_wechat_empty_location is False
        assert cap.show_promotion is False
        assert cap.show_privacy is True
        assert cap.show_work_declaration is True

    def test_wechat_video_location_only(self):
        cap = capabilities_for_platform("wechat_video", is_image_mode=False)
        assert cap.show_add_tags is False
        assert cap.show_location is True
        assert cap.show_wechat_empty_location is True
        assert cap.show_privacy is False
        assert cap.show_work_declaration is True

    def test_unknown_platform_empty(self):
        cap = capabilities_for_platform("bilibili", is_image_mode=False)
        assert cap.show_add_tags is False
        assert cap.show_location is False
        assert cap.show_work_declaration is False

    def test_platform_id_normalized(self):
        cap = capabilities_for_platform("  DOUYIN  ", is_image_mode=False)
        assert cap.show_promotion is True
