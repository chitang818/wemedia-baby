"""工作台双列概览区布局（还原/最大化/性能）"""

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.pages.workspace_page import WorkspacePage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_workspace_page(monkeypatch) -> WorkspacePage:
    monkeypatch.setattr(WorkspacePage, "_init_services", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_setup_refresh_timer", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_schedule_base_page_timer", lambda *args, **kwargs: None)
    return WorkspacePage()


def test_overview_total_scroll_height_uses_layout_formula(qapp, monkeypatch):
    page = _make_workspace_page(monkeypatch)
    try:
        page.resize(1100, 760)
        page.show()
        qapp.processEvents()
        host_h = 300
        above = page._scroll_sections_height_before_overview()
        spacing = page._overview_layout_spacing()
        assert page._overview_total_scroll_height(host_h) == above + spacing + host_h
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_clamp_overview_pair_to_viewport_does_not_apply_heights(qapp, monkeypatch):
    page = _make_workspace_page(monkeypatch)
    apply_calls = []

    def track_apply(host_height, **kwargs):
        apply_calls.append(host_height)

    try:
        page.resize(1100, 760)
        page.show()
        qapp.processEvents()
        monkeypatch.setattr(page, "_apply_overview_pair_heights", track_apply)
        monkeypatch.setattr(page, "_overview_pair_height_budget", lambda **kwargs: 400)
        result = page._clamp_overview_pair_to_viewport(500, stacked=False)
        assert result == 400
        assert apply_calls == []
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_schedule_deferred_overview_sync_uses_debounce_and_post_animation(qapp, monkeypatch):
    page = _make_workspace_page(monkeypatch)
    calls = []

    def capture_timer(key, delay, callback):
        calls.append((key, delay, callback))

    monkeypatch.setattr(page, "_schedule_base_page_timer", capture_timer)
    try:
        page._schedule_deferred_overview_sync(post_animation=False)
        assert len(calls) == 1
        assert calls[0][0] == "workspace_overview_layout_debounced"
        assert calls[0][1] == WorkspacePage._OVERVIEW_SYNC_DEBOUNCE_MS

        calls.clear()
        page._schedule_deferred_overview_sync(post_animation=True)
        assert len(calls) == 2
        assert calls[0][0] == "workspace_overview_layout_debounced"
        assert calls[1][0] == "workspace_overview_layout_post_animation"
        assert calls[1][1] == WorkspacePage._OVERVIEW_SYNC_POST_ANIMATION_MS
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_maximized_state_change_reapplies_host_height(qapp, monkeypatch):
    page = _make_workspace_page(monkeypatch)
    try:
        page.resize(1100, 760)
        page.show()
        qapp.processEvents()

        states = [False]

        monkeypatch.setattr(page, "_is_overview_maximized", lambda: states[-1])
        monkeypatch.setattr(page, "_overview_pair_height_budget", lambda **kwargs: 480)

        page._sync_overview_pair_layout()
        default_height = page._overview_pair_host_height
        assert default_height is not None

        page._overview_pair_host.setFixedHeight(999)
        states.append(True)
        page._sync_overview_pair_layout()
        assert page._overview_pair_host.height() == page._overview_pair_host_height

        page._overview_pair_host.setFixedHeight(999)
        states.append(False)
        page._sync_overview_pair_layout()
        assert page._overview_pair_host.height() == page._overview_pair_host_height
        assert page._overview_pair_host.height() == default_height
    finally:
        page.deleteLater()
        qapp.processEvents()
