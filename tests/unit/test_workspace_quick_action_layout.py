"""Workspace quick action equal-width row layout."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QGridLayout, QSizePolicy, QWidget

from src.ui.pages.workspace_page import WorkspacePage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_quick_action_layout_uses_responsive_grid(qapp):
    container = QWidget()
    layout = WorkspacePage._create_quick_action_layout(container)

    assert isinstance(layout, QGridLayout)
    assert container.layout() is layout
    assert layout.property("workspaceQuickActionLayoutKind") == "responsive-grid"
    assert layout.contentsMargins().left() == 0
    assert layout.horizontalSpacing() == WorkspacePage._quick_action_spacing
    assert layout.verticalSpacing() == WorkspacePage._quick_action_spacing


def test_workspace_page_quick_actions_stretch_equally(qapp, monkeypatch):
    monkeypatch.setattr(WorkspacePage, "_init_services", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_setup_refresh_timer", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_schedule_base_page_timer", lambda *args, **kwargs: None)

    page = WorkspacePage()
    try:
        layout = page._quick_action_layout
        cards = (
            page.action_add_account,
            page.action_single_video,
            page.action_batch_video,
            page.action_publish_list,
            page.action_single_image,
            page.action_batch_image,
        )

        assert isinstance(layout, QGridLayout)
        assert layout.property("workspaceQuickActionLayoutKind") == "responsive-grid"
        assert layout.count() == 6
        assert all(card.minimumWidth() == WorkspacePage._quick_action_card_min_width for card in cards)
        assert all(
            card.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding for card in cards
        )
        page._relayout_quick_actions(900)
        assert page._quick_action_grid_columns == 6
        for i, card in enumerate(cards):
            assert layout.itemAtPosition(0, i).widget() is card

        page._relayout_quick_actions(360)
        assert page._quick_action_grid_columns == 2
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_workspace_stats_columns_follow_width_breakpoints(qapp):
    assert WorkspacePage._stats_columns_for_width(500) == 2
    assert WorkspacePage._stats_columns_for_width(620) == 4
    assert WorkspacePage._stats_columns_for_width(900) == 4


def test_quick_action_columns_single_row_when_wide_enough(qapp, monkeypatch):
    monkeypatch.setattr(WorkspacePage, "_init_services", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_setup_refresh_timer", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_schedule_base_page_timer", lambda *args, **kwargs: None)

    page = WorkspacePage()
    try:
        min_w = WorkspacePage._quick_action_single_row_min_width
        assert page._quick_action_columns_for_width(min_w) == 6
        assert page._quick_action_columns_for_width(900) == 6
        assert page._quick_action_columns_for_width(min_w - 1) == 3
        assert page._quick_action_columns_for_width(360) == 2
    finally:
        page.deleteLater()
        qapp.processEvents()
