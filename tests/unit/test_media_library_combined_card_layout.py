"""MediaLibraryCombinedCard 布局与 reveal 行为"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QSpacerItem

from src.ui.components.media_library_combined_card import MediaLibraryCombinedCard


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _layout_has_standalone_stretch(layout: QHBoxLayout) -> bool:
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is not None and item.spacerItem() is not None:
            sp = item.spacerItem()
            if isinstance(sp, QSpacerItem) and sp.expandingDirections():
                return True
    return False


def test_main_layout_has_no_middle_stretch(qapp):
    card = MediaLibraryCombinedCard()
    try:
        layout = card._main_layout
        assert isinstance(layout, QHBoxLayout)
        assert not _layout_has_standalone_stretch(layout)
        assert layout.itemAt(layout.count() - 1).widget() is card._metrics_host
    finally:
        card.deleteLater()
        qapp.processEvents()


def test_text_host_expands_metrics_host_does_not(qapp):
    card = MediaLibraryCombinedCard()
    try:
        layout = card._main_layout
        text_idx = layout.indexOf(card._text_host)
        metrics_idx = layout.indexOf(card._metrics_host)
        assert text_idx >= 0
        assert metrics_idx >= 0
        assert layout.stretch(text_idx) == 1
        assert layout.stretch(metrics_idx) == 0
    finally:
        card.deleteLater()
        qapp.processEvents()


def test_reveal_sets_desc_and_metric_values(qapp):
    card = MediaLibraryCombinedCard()
    try:
        card.reveal(75, 12, 63, 3, 1, 2)
        assert card._desc_label.text() == "已占用 13 | 未占用 65"
        assert card._video_value.text() == "75"
        assert card._image_value.text() == "3"
        assert "视频素材共 75" in card._video_value.toolTip()
        assert "图片素材共 3" in card._image_value.toolTip()
    finally:
        card.deleteLater()
        qapp.processEvents()


def test_loading_skeleton_attached_to_metrics_host(qapp):
    card = MediaLibraryCombinedCard()
    try:
        card.show_value_loading()
        assert card.is_value_loading
        assert card._skeleton is not None
        assert card._skeleton.parent() is card._metrics_host
        assert card._video_block.isHidden()
        assert card._image_block.isHidden()
    finally:
        card.deleteLater()
        qapp.processEvents()
