"""发布统计卡加载态与 reveal 行为"""

import pytest
from PySide6.QtWidgets import QApplication

from PySide6.QtWidgets import QFrame

from src.ui.components.recent_activity_widget import (
    RecentActivityWidget,
    ReminderLoadState,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _sample_row(account_id: int = 1) -> dict:
    return {
        "account_id": account_id,
        "account_name": "演示账号",
        "latest_publish_time": "2026-05-23 10:00",
        "reminder_text": "今天",
    }


def test_recent_activity_starts_in_loading_not_empty(qapp):
    widget = RecentActivityWidget()
    try:
        assert widget.is_loading
        assert widget._load_state == ReminderLoadState.LOADING
        assert len(widget._skeleton_rows) > 0
        assert widget._header_slot.isHidden()
        assert len(widget._reminder_rows) == 0
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_reveal_reminders_replaces_skeleton_with_rows(qapp):
    widget = RecentActivityWidget()
    try:
        widget.reveal_reminders([_sample_row()], animate=False)
        qapp.processEvents()
        assert not widget.is_loading
        assert widget._load_state == ReminderLoadState.READY
        assert len(widget._skeleton_rows) == 0
        assert len(widget._reminder_rows) == 1
        assert widget._header_row is not None
        assert not widget._header_slot.isHidden()
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_reveal_reminders_offline_row_has_red_status_dot(qapp):
    widget = RecentActivityWidget()
    try:
        widget.reveal_reminders(
            [
                {
                    "account_id": 2,
                    "account_name": "离线视频号",
                    "latest_publish_time": "-",
                    "reminder_text": "从未发布",
                    "is_online": False,
                }
            ],
            animate=False,
        )
        qapp.processEvents()
        row = widget._reminder_rows[0]
        dots = row.findChildren(QFrame)
        assert any(d.width() == 8 and d.height() == 8 for d in dots)
        assert row._is_online is False
    finally:
        widget.deleteLater()
        qapp.processEvents()


def test_reveal_empty_after_loading_shows_empty_message(qapp):
    widget = RecentActivityWidget()
    try:
        widget.reveal_reminders([], animate=False)
        qapp.processEvents()
        assert not widget.is_loading
        assert len(widget._reminder_rows) == 0
        assert widget._header_slot.isHidden()
    finally:
        widget.deleteLater()
        qapp.processEvents()
