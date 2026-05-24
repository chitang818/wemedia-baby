"""Workspace quick action equal-width row layout."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QSizePolicy, QWidget

from src.ui.pages.workspace_page import WorkspacePage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_quick_action_layout_uses_equal_width_row(qapp):
    container = QWidget()
    layout = WorkspacePage._create_quick_action_layout(container)

    assert isinstance(layout, QHBoxLayout)
    assert container.layout() is layout
    assert layout.property("workspaceQuickActionLayoutKind") == "equal"
    assert layout.contentsMargins().left() == 0
    assert layout.spacing() == WorkspacePage._quick_action_spacing


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

        assert isinstance(layout, QHBoxLayout)
        assert layout.property("workspaceQuickActionLayoutKind") == "equal"
        assert layout.count() == 6
        assert all(card.minimumWidth() == WorkspacePage._quick_action_card_min_width for card in cards)
        assert all(
            card.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding for card in cards
        )
        for i, card in enumerate(cards):
            assert layout.itemAt(i).widget() is card
            assert layout.stretch(i) == 1
    finally:
        page.deleteLater()
        qapp.processEvents()
