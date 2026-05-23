"""Workspace quick action flow layout behavior."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QGridLayout, QWidget

from src.ui.pages.workspace_page import WorkspacePage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _expected_layout_kind() -> str:
    for module_name, class_name, kind in (
        ("qfluentwidgets", "AdaptiveFlowLayout", "adaptive"),
        ("qfluentwidgets.components.layout.flow_layout", "AdaptiveFlowLayout", "adaptive"),
        ("qfluentwidgets", "FlowLayout", "flow"),
        ("qfluentwidgets.components.layout.flow_layout", "FlowLayout", "flow"),
    ):
        try:
            module = __import__(module_name, fromlist=[class_name])
            getattr(module, class_name)
            return kind
        except (ImportError, AttributeError):
            continue
    return "grid"


def test_quick_action_layout_prefers_adaptive_flow_when_available(qapp):
    container = QWidget()
    layout = WorkspacePage._create_quick_action_layout(container)

    assert container.layout() is layout
    assert layout.property("workspaceQuickActionLayoutKind") == _expected_layout_kind()
    assert layout.contentsMargins().left() == 0
    assert layout.contentsMargins().top() == 0
    if hasattr(layout, "horizontalSpacing"):
        assert layout.horizontalSpacing() == 12
    if hasattr(layout, "verticalSpacing"):
        assert layout.verticalSpacing() == 12
    if layout.property("workspaceQuickActionLayoutKind") == "adaptive":
        assert hasattr(layout, "setWidgetMinimumWidth")
        assert hasattr(layout, "setWidgetMaximumWidth")


def test_workspace_page_quick_actions_use_flow_layout(qapp, monkeypatch):
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

        assert layout.property("workspaceQuickActionLayoutKind") == _expected_layout_kind()
        assert layout.count() == 6
        assert all(card.minimumWidth() == WorkspacePage._quick_action_card_min_width for card in cards)
        assert all(card.maximumWidth() == WorkspacePage._quick_action_card_max_width for card in cards)
        if isinstance(layout, QGridLayout):
            assert layout.itemAtPosition(0, 0).widget() is page.action_add_account
            assert layout.itemAtPosition(1, 2).widget() is page.action_batch_image
    finally:
        page.deleteLater()
        qapp.processEvents()
