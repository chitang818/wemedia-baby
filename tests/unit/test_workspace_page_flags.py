"""工作台页面启动行为标志"""

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.pages.workspace_page import WorkspacePage
from src.ui.pages.workspace.workspace_load_orchestrator import WorkspaceLoadOrchestrator
from src.services.material.media_library_stats_types import MediaLibraryStats
from src.services.workspace.dashboard_snapshot import DashboardSnapshot


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_workspace_page_disables_first_show_freeze_and_fade():
    assert WorkspacePage._freeze_on_first_show is False
    assert WorkspacePage._enable_show_fade is False


def test_workspace_page_does_not_create_charts_in_constructor(qapp, monkeypatch):
    monkeypatch.setattr(WorkspacePage, "_init_services", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_setup_refresh_timer", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_schedule_base_page_timer", lambda *args, **kwargs: None)

    page = WorkspacePage()
    try:
        assert page._charts_created is False
        assert page.platform_chart is None
        assert page.trend_chart is None
        assert page._secondary_widgets_created is False
        assert page._announcement_created is False
        assert page._recent_activity_created is False
        assert not hasattr(page, "recent_activity")
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_noncritical_first_paint_schedules_staggered_tasks(qapp, monkeypatch):
    monkeypatch.setattr(WorkspacePage, "_init_services", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_setup_refresh_timer", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_schedule_base_page_timer", lambda *args, **kwargs: None)

    page = WorkspacePage()
    calls = []
    page._schedule_base_page_timer = lambda key, delay, callback: calls.append(
        (key, delay, callback)
    )
    try:
        page.schedule_noncritical_first_paint()
        assert [call[0] for call in calls] == [
            "workspace_announcement_create",
            "workspace_recent_activity_create",
            "workspace_platform_chart_prewarm",
            "workspace_trend_chart_prewarm",
        ]
        assert [call[1] for call in calls] == [0, 80, 180, 320]
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_recent_activity_consumes_cached_reminders(qapp, monkeypatch):
    monkeypatch.setattr(WorkspacePage, "_init_services", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_setup_refresh_timer", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_schedule_base_page_timer", lambda *args, **kwargs: None)

    page = WorkspacePage()
    reminders = [
        {
            "account_id": 1,
            "account_name": "demo",
            "latest_publish_time": "2026-05-23 10:00",
            "reminder_text": "今天",
        }
    ]
    try:
        page.set_cached_reminders(reminders)
        page.ensure_recent_activity_created()
        assert hasattr(page, "recent_activity")
        assert len(page.recent_activity._reminder_rows) == 1
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_chart_placeholders_are_visual_skeletons(qapp, monkeypatch):
    from src.ui.components.skeleton import SkeletonItem

    monkeypatch.setattr(WorkspacePage, "_init_services", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_setup_refresh_timer", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_schedule_base_page_timer", lambda *args, **kwargs: None)

    page = WorkspacePage()
    try:
        placeholders = [
            page._platform_chart_placeholder,
            page._trend_chart_placeholder,
        ]
        assert all(p.property("workspaceChartPlaceholderKind") for p in placeholders)
        assert sum(len(p.findChildren(SkeletonItem)) for p in placeholders) >= 5
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_startup_refresh_schedules_direct_startup_load(monkeypatch):
    calls = []

    class DummyPage:
        def _schedule_base_page_timer(self, key, delay, callback):
            calls.append((key, delay, callback))

    orchestrator = WorkspaceLoadOrchestrator(DummyPage())
    orchestrator.schedule_startup_refresh()
    orchestrator.schedule_startup_refresh()

    assert len(calls) == 1
    assert calls[0][0] == "workspace_orchestrator_start"
    assert calls[0][2].__name__ == "startup_load"


def test_cached_first_paint_requires_dashboard_and_media(monkeypatch):
    calls = []

    class FakeDashboardService:
        def __init__(self, snapshot):
            self._snapshot = snapshot

        def get_cached_snapshot(self):
            return self._snapshot

        def get_persistent_snapshot(self):
            return None

    class FakeMediaCache:
        def __init__(self, stats):
            self._stats = stats

        def get_memory(self):
            return self._stats

        def get_persistent(self):
            return None

    class FakePage:
        def __init__(self, snapshot):
            self.dashboard_service = FakeDashboardService(snapshot)

        def apply_stats_batch(self, dashboard_snapshot, media_stats, **kwargs):
            calls.append((dashboard_snapshot, media_stats, kwargs))

    snapshot = DashboardSnapshot(account={"total": 1}, publish={"today_count": 2})
    media = MediaLibraryStats()
    monkeypatch.setattr(
        "src.ui.pages.workspace.workspace_load_orchestrator.get_media_library_stats_cache",
        lambda: FakeMediaCache(media),
    )
    orchestrator = WorkspaceLoadOrchestrator(FakePage(snapshot))

    assert orchestrator.apply_cached_first_paint() is True
    assert calls == [(snapshot, media, {"animate_entry": False, "reminders": False})]
    assert orchestrator.get_latest_snapshot() is snapshot

    calls.clear()
    monkeypatch.setattr(
        "src.ui.pages.workspace.workspace_load_orchestrator.get_media_library_stats_cache",
        lambda: FakeMediaCache(None),
    )
    orchestrator = WorkspaceLoadOrchestrator(FakePage(snapshot))

    assert orchestrator.apply_cached_first_paint() is False
    assert calls == []
