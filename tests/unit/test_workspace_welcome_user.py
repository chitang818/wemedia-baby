"""工作台欢迎语用户名展示与登录态刷新"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from src.infrastructure.common.event.events import CurrentUserChangedEvent
from src.ui.pages.workspace_page import WorkspacePage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_page(monkeypatch, *, init_services: bool = False) -> WorkspacePage:
    monkeypatch.setattr(WorkspacePage, "_init_services", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_setup_refresh_timer", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_schedule_base_page_timer", lambda *args, **kwargs: None)
    if not init_services:
        page = WorkspacePage()
        return page
    return WorkspacePage()


def test_resolve_welcome_username_from_logged_in_user(qapp, monkeypatch):
    page = _make_page(monkeypatch)
    mock_svc = MagicMock()
    mock_svc.get_user.return_value = {"username": "张三"}
    page._current_user_svc = mock_svc
    monkeypatch.setattr(
        "src.services.auth.auth_remember.get_remembered_credentials",
        lambda: (False, None, None),
    )
    try:
        assert page._resolve_welcome_username() == "张三"
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_resolve_welcome_username_from_remember_me_when_not_logged_in(qapp, monkeypatch):
    page = _make_page(monkeypatch)
    mock_svc = MagicMock()
    mock_svc.get_user.return_value = None
    page._current_user_svc = mock_svc
    monkeypatch.setattr(
        "src.services.auth.auth_remember.get_remembered_credentials",
        lambda: (True, "李四", "secret"),
    )
    try:
        assert page._resolve_welcome_username() == "李四"
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_resolve_welcome_username_empty_when_no_user_and_no_remember(qapp, monkeypatch):
    page = _make_page(monkeypatch)
    mock_svc = MagicMock()
    mock_svc.get_user.return_value = None
    page._current_user_svc = mock_svc
    monkeypatch.setattr(
        "src.services.auth.auth_remember.get_remembered_credentials",
        lambda: (False, None, None),
    )
    try:
        assert page._resolve_welcome_username() is None
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_update_welcome_text_shows_username_from_remember_me(qapp, monkeypatch):
    page = _make_page(monkeypatch)
    mock_svc = MagicMock()
    mock_svc.get_user.return_value = None
    page._current_user_svc = mock_svc
    monkeypatch.setattr(
        "src.services.auth.auth_remember.get_remembered_credentials",
        lambda: (True, "王五", "secret"),
    )
    try:
        page._update_welcome_text("2026年05月24日")
        text = page.welcome_line.text()
        assert "王五，欢迎回来" in text
        assert "2026年05月24日" in text
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_update_welcome_text_generic_when_credentials_cleared(qapp, monkeypatch):
    page = _make_page(monkeypatch)
    mock_svc = MagicMock()
    mock_svc.get_user.return_value = None
    page._current_user_svc = mock_svc
    monkeypatch.setattr(
        "src.services.auth.auth_remember.get_remembered_credentials",
        lambda: (False, None, None),
    )
    try:
        page._update_welcome_text("2026年05月24日")
        text = page.welcome_line.text()
        assert text.startswith("欢迎回来 ·")
        assert "王五" not in text
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_refresh_welcome_requested_updates_welcome_line(qapp, monkeypatch):
    page = _make_page(monkeypatch)
    mock_svc = MagicMock()
    mock_svc.get_user.return_value = {"username": "赵六"}
    page._current_user_svc = mock_svc
    monkeypatch.setattr(
        "src.services.auth.auth_remember.get_remembered_credentials",
        lambda: (False, None, None),
    )
    try:
        page._update_welcome_text("2026年05月24日")
        assert "赵六" in page.welcome_line.text()

        mock_svc.get_user.return_value = None
        monkeypatch.setattr(
            "src.services.auth.auth_remember.get_remembered_credentials",
            lambda: (False, None, None),
        )
        page.refreshWelcomeRequested.emit()
        qapp.processEvents()
        assert page.welcome_line.text().startswith("欢迎回来 ·")
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_current_user_changed_event_subscription_refreshes_welcome(qapp, monkeypatch):
    captured_handler = {}

    class FakeEventBus:
        def subscribe(self, event_type, handler):
            if event_type == "CurrentUserChangedEvent":
                captured_handler["handler"] = handler

    monkeypatch.setattr(WorkspacePage, "_setup_refresh_timer", lambda self: None)
    monkeypatch.setattr(WorkspacePage, "_schedule_base_page_timer", lambda *args, **kwargs: None)

    from src.infrastructure.common.di import service_locator as sl_mod

    fake_locator = MagicMock()
    fake_locator.get.return_value = FakeEventBus()
    monkeypatch.setattr(sl_mod, "ServiceLocator", lambda: fake_locator)

    page = WorkspacePage()
    mock_svc = MagicMock()
    mock_svc.get_user.return_value = None
    page._current_user_svc = mock_svc
    monkeypatch.setattr(
        "src.services.auth.auth_remember.get_remembered_credentials",
        lambda: (False, None, None),
    )
    try:
        assert "handler" in captured_handler
        page._update_welcome_text("2026年05月24日")
        assert page.welcome_line.text().startswith("欢迎回来 ·")

        mock_svc.get_user.return_value = {"username": "event_user"}
        captured_handler["handler"](
            CurrentUserChangedEvent(username="event_user", logged_in=True, source="auto_login")
        )
        qapp.processEvents()
        assert "event_user，欢迎回来" in page.welcome_line.text()
    finally:
        page.deleteLater()
        qapp.processEvents()
