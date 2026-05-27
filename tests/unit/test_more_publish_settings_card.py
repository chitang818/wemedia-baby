"""更多发布设置卡片：图文音乐行显隐。"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.pages.publish.single_more_publish_settings.more_publish_settings_card import (
    MorePublishSettingsCard,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestMorePublishSettingsCardMusic:
    def test_image_mode_has_music_row(self, qapp):
        card = MorePublishSettingsCard(is_image_mode=True)
        assert getattr(card, "_row_music", None) is not None
        card.refresh("none", platforms_in_selection=set())
        assert not card._row_music.isHidden()

    def test_video_mode_has_no_music_row(self, qapp):
        card = MorePublishSettingsCard(is_image_mode=False)
        assert getattr(card, "_row_music", None) is None

    def test_image_mode_music_row_visible_for_douyin(self, qapp):
        card = MorePublishSettingsCard(is_image_mode=True)
        card.refresh("douyin", platforms_in_selection={"douyin"})
        assert not card._row_music.isHidden()

    def test_image_mode_music_row_visible_for_mixed_group(self, qapp):
        card = MorePublishSettingsCard(is_image_mode=True)
        card.refresh("mixed", platforms_in_selection={"douyin", "kuaishou"})
        assert not card._row_music.isHidden()

    def test_music_type_specific_shows_name_edit(self, qapp):
        card = MorePublishSettingsCard(is_image_mode=True)
        card._music_type_combo.setCurrentIndex(2)
        assert not card._music_name_edit.isHidden()
