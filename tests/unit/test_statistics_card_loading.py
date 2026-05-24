"""StatisticsCard loading / reveal 行为"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.ui.components.statistics_card import StatCardLoadState, StatisticsCard
from src.ui.workspace_chart_animation_prefs import STATS_SKELETON_MIN_MS


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_show_value_loading_sets_loading_state(qapp):
    card = StatisticsCard("测试", "0", "描述")
    card.show_value_loading()
    assert card.is_value_loading
    assert card._load_state == StatCardLoadState.LOADING


def test_default_card_keeps_original_minimum_height(qapp):
    card = StatisticsCard("测试", "0", "描述")
    assert card.minimumHeight() == 90


def test_compact_card_uses_smaller_metrics(qapp):
    normal = StatisticsCard("测试", "0", "描述")
    compact = StatisticsCard("测试", "0", "描述", compact=True)

    assert compact.minimumHeight() == 78
    assert compact.minimumHeight() < normal.minimumHeight()
    assert compact._value_font_px_default < normal._value_font_px_default
    assert compact._value_font_px_percent < normal._value_font_px_percent


def test_compact_loading_skeleton_does_not_exceed_value_size(qapp):
    card = StatisticsCard("测试", "0", "描述", compact=True)
    card.show_value_loading()

    assert card.is_value_loading
    assert card._value_skeleton is not None
    assert card._value_skeleton.height() == 24


def test_reveal_without_loading_no_animation(qapp):
    card = StatisticsCard("测试", "0", "旧描述")
    card.reveal("42", "新描述", animate=False)
    assert card.value_label.text() == "42"
    assert card.desc_label.text() == "新描述"
    assert card._load_state == StatCardLoadState.READY


def test_reveal_after_loading_with_min_delay(qapp):
    card = StatisticsCard("测试", "—", "总 — | 已占用 — | 未占用 —")
    card.show_value_loading()
    with patch.object(card, "_fade_in_value_label"):
        card.reveal("18", "总 18 | 已占用 2 | 未占用 16", animate=True)
    QTest.qWait(STATS_SKELETON_MIN_MS + 80)
    assert card.value_label.text() == "18"
    assert card._load_state == StatCardLoadState.READY


def test_cancel_pending_reveal_stops_timer(qapp):
    card = StatisticsCard("测试", "0", "描述")
    card.show_value_loading()
    card.reveal("1", "d", animate=True)
    card.cancel_pending_reveal()
    assert card._reveal_timer is None


def test_value_label_stays_visible_after_resize(qapp):
    card = StatisticsCard("账号总数", "18", "12 在线 | 6 离线")
    card.resize(420, 90)
    card.resize(760, 90)
    qapp.processEvents()

    assert not card.value_label.isHidden()
    assert card.value_label.minimumWidth() > 0
    assert card.value_label.text() == "18"


def test_compact_value_label_stays_visible_after_loading_and_resize(qapp):
    card = StatisticsCard("账号总数", "18", "12 在线 | 6 离线", compact=True)
    card.show_value_loading()
    card.reveal("86%", "7日发布成功率", animate=False)
    card.resize(420, 78)
    qapp.processEvents()

    assert not card.value_label.isHidden()
    assert card.value_label.minimumWidth() > 0
    assert card.value_label.text() == "86%"
    assert card._load_state == StatCardLoadState.READY
