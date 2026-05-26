# -*- coding: utf-8 -*-
"""账号库筛选后仅刷新可见账号"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from src.ui.pages.account.components.account_table_model import AccountTableModel
from src.ui.pages.account.components.account_table_view import (
    AccountFilterProxyModel,
    AccountTableViewWidget,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_proxy_is_filter_active(qapp: QApplication) -> None:
    proxy = AccountFilterProxyModel()
    model = AccountTableModel()
    proxy.setSourceModel(model)
    assert proxy.is_filter_active() is False
    proxy.set_filter(keyword="刘")
    assert proxy.is_filter_active() is True
    proxy.set_filter(keyword="", platform="kuaishou")
    assert proxy.is_filter_active() is True


def test_get_visible_records_respects_filter(qapp: QApplication) -> None:
    widget = AccountTableViewWidget()
    widget.load_accounts(
        [
            {"id": 1, "platform": "douyin", "platform_username": "A", "login_status": "online"},
            {"id": 2, "platform": "kuaishou", "platform_username": "刘强东", "login_status": "online"},
            {"id": 3, "platform": "kuaishou", "platform_username": "B", "login_status": "offline"},
        ]
    )
    widget.filter_accounts(keyword="刘", platform="all")
    visible = widget.get_visible_records()
    assert len(visible) == 1
    assert visible[0]["id"] == 2

    widget.filter_accounts(keyword="", platform="kuaishou")
    visible_ks = widget.get_visible_records()
    assert len(visible_ks) == 2
    assert {r["id"] for r in visible_ks} == {2, 3}


def test_on_refresh_legacy_uses_visible_when_filtered(qapp: QApplication) -> None:
    from src.ui.pages.account.view import AccountPage

    page = MagicMock(spec=AccountPage)
    page.account_manager = MagicMock()
    page._refresh_silent_mode = False
    page._show_warning = MagicMock()

    table = AccountTableViewWidget()
    table.load_accounts(
        [
            {"id": 1, "platform": "douyin", "platform_username": "A"},
            {"id": 2, "platform": "kuaishou", "platform_username": "刘强东"},
        ]
    )
    table.filter_accounts(keyword="刘", platform="all")
    page.account_table_widget = table

    validator = MagicMock()
    page.validator_service = validator

    from src.ui.pages.account.view import AccountPage as RealPage

    RealPage._on_refresh_legacy(page, silent=False)

    validator.verify_accounts.assert_called_once()
    args, kwargs = validator.verify_accounts.call_args
    assert len(args[0]) == 1
    assert args[0][0]["id"] == 2
    validator.start_verify_all.assert_not_called()
