"""账号管理页：工作台跳转后自动打开添加平台弹窗"""

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.pages.account.view import AccountPage


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_request_open_add_account_sets_pending_flag(qapp):
    page = AccountPage()
    page._content_initialized = True
    try:
        page.request_open_add_account_dialog()
        assert page._pending_open_add_account is True
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_flush_pending_skips_when_not_visible(qapp):
    page = AccountPage()
    page._content_initialized = True
    page._pending_open_add_account = True
    try:
        page._flush_pending_open_add_account()
        assert page._pending_open_add_account is True
    finally:
        page.deleteLater()
        qapp.processEvents()


def test_flush_pending_opens_add_flow_when_visible(qapp, monkeypatch):
    page = AccountPage()
    page._content_initialized = True
    called = []
    monkeypatch.setattr(page, "_ensure_content", lambda: None)
    monkeypatch.setattr(page, "_on_add_account", lambda: called.append(True))
    try:
        page.request_open_add_account_dialog()
        page.show()
        qapp.processEvents()
        page._flush_pending_open_add_account()
        assert called == [True]
        assert page._pending_open_add_account is False
    finally:
        page.hide()
        page.deleteLater()
        qapp.processEvents()
