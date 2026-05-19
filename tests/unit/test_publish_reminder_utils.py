"""
发布提醒工具函数单元测试
模块：src/utils/date_utils.py（compute_publish_reminder_days 等）
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from src.ui.components.recent_activity_widget import _truncate_account_name
from src.utils.date_utils import (
    parse_latest_publish_display_time,
    compute_publish_reminder_days,
    format_publish_reminder_text,
    is_latest_publish_overdue,
)

_SHANGHAI = ZoneInfo("Asia/Shanghai")


class TestParseLatestPublishDisplayTime:
    def test_valid(self):
        dt = parse_latest_publish_display_time("2026-05-20 06:34")
        assert dt == datetime(2026, 5, 20, 6, 34)

    def test_dash_returns_none(self):
        assert parse_latest_publish_display_time("-") is None
        assert parse_latest_publish_display_time("") is None

    def test_invalid_returns_none(self):
        assert parse_latest_publish_display_time("bad") is None


class TestComputePublishReminderDays:
    def test_remaining_five_days(self):
        now = datetime(2026, 5, 15, 12, 0, tzinfo=_SHANGHAI)
        assert compute_publish_reminder_days("2026-05-20 06:34", now=now) == 5

    def test_overdue_three_days(self):
        now = datetime(2026, 5, 15, 12, 0, tzinfo=_SHANGHAI)
        assert compute_publish_reminder_days("2026-05-12 08:00", now=now) == -3

    def test_today(self):
        now = datetime(2026, 5, 15, 12, 0, tzinfo=_SHANGHAI)
        assert compute_publish_reminder_days("2026-05-15 23:59", now=now) == 0

    def test_never_published(self):
        assert compute_publish_reminder_days("-") is None


class TestFormatPublishReminderText:
    def test_remaining(self):
        assert format_publish_reminder_text(5) == "剩余5天"

    def test_overdue(self):
        assert format_publish_reminder_text(-3) == "已逾期3天"

    def test_today(self):
        assert format_publish_reminder_text(0) == "今天"

    def test_never(self):
        assert format_publish_reminder_text(None) == "从未发布"


class TestTruncateAccountName:
    def test_short_unchanged(self):
        assert _truncate_account_name("遥马农业") == "遥马农业"

    def test_long_truncated(self):
        name = "遥马农业 - 增甜转色黑科技"
        out = _truncate_account_name(name)
        assert out.endswith("…")
        assert out[:-1] == name[:9]
        assert len(out) == 10  # 9 字 + 省略号

    def test_exact_nine(self):
        assert _truncate_account_name("一二三四五六七八九") == "一二三四五六七八九"


class TestIsLatestPublishOverdue:
    def test_past_is_overdue(self):
        now = datetime(2026, 5, 15, 12, 0, tzinfo=_SHANGHAI)
        assert is_latest_publish_overdue("2026-05-10 08:00", now=now) is True

    def test_future_not_overdue(self):
        now = datetime(2026, 5, 15, 12, 0, tzinfo=_SHANGHAI)
        assert is_latest_publish_overdue("2026-05-20 06:34", now=now) is False

    def test_dash_not_overdue(self):
        assert is_latest_publish_overdue("-") is False
