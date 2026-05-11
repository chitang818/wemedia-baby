"""
日期工具函数单元测试
模块：src/utils/date_utils.py
"""
import pytest
from datetime import datetime
from src.utils.date_utils import (
    format_datetime,
    parse_datetime,
    add_days,
    add_hours,
    add_minutes,
    is_date_expired,
    format_schedule_time_st_str,
    merge_latest_publish_display_time,
    get_datetime_diff_seconds,
    DATETIME_FORMAT,
    DATE_FORMAT,
)


class TestFormatDatetime:
    def test_default_format(self):
        dt = datetime(2026, 3, 27, 10, 30, 0)
        assert format_datetime(dt) == "2026-03-27 10:30:00"

    def test_custom_format(self):
        dt = datetime(2026, 3, 27)
        assert format_datetime(dt, DATE_FORMAT) == "2026-03-27"


class TestParseDatetime:
    def test_valid_string(self):
        result = parse_datetime("2026-03-27 10:30:00")
        assert result == datetime(2026, 3, 27, 10, 30, 0)

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            parse_datetime("not-a-date")

    def test_custom_format(self):
        result = parse_datetime("2026-03-27", DATE_FORMAT)
        assert result.year == 2026 and result.month == 3 and result.day == 27


class TestAddDays:
    def test_add_positive_days(self):
        dt = datetime(2026, 3, 27)
        result = add_days(dt, 3)
        assert result.day == 30

    def test_add_negative_days(self):
        dt = datetime(2026, 3, 27)
        result = add_days(dt, -2)
        assert result.day == 25

    def test_add_zero(self):
        dt = datetime(2026, 3, 27)
        assert add_days(dt, 0) == dt


class TestAddHours:
    def test_add_hours(self):
        dt = datetime(2026, 3, 27, 10, 0, 0)
        result = add_hours(dt, 5)
        assert result.hour == 15

    def test_add_negative_hours(self):
        dt = datetime(2026, 3, 27, 10, 0, 0)
        result = add_hours(dt, -3)
        assert result.hour == 7


class TestAddMinutes:
    def test_add_minutes(self):
        dt = datetime(2026, 3, 27, 10, 0, 0)
        result = add_minutes(dt, 90)
        assert result.hour == 11 and result.minute == 30


class TestIsDateExpired:
    def test_past_date_is_expired(self):
        assert is_date_expired("2020-01-01") is True

    def test_future_date_not_expired(self):
        assert is_date_expired("2099-12-31") is False

    def test_invalid_format_treated_as_expired(self):
        assert is_date_expired("not-a-date") is True


class TestFormatScheduleTimeStStr:
    def test_datetime_object(self):
        dt = datetime(2026, 3, 27, 14, 30)
        assert format_schedule_time_st_str(dt) == "2026-03-27 14:30"

    def test_none_returns_none(self):
        assert format_schedule_time_st_str(None) is None

    def test_iso_string(self):
        result = format_schedule_time_st_str("2026-03-27T14:30:00")
        assert result == "2026-03-27 14:30"

    def test_string_with_seconds(self):
        result = format_schedule_time_st_str("2026-03-27 14:30:59")
        assert result == "2026-03-27 14:30"

    def test_string_with_timezone(self):
        result = format_schedule_time_st_str("2026-03-27 14:30:00+08:00")
        assert result == "2026-03-27 14:30"

    def test_already_formatted(self):
        result = format_schedule_time_st_str("2026-03-27 14:30")
        assert result == "2026-03-27 14:30"

    def test_empty_string_returns_none(self):
        assert format_schedule_time_st_str("") is None


class TestMergeLatestPublishDisplayTime:
    def test_both_none(self):
        assert merge_latest_publish_display_time(None, None) is None

    def test_scheduled_only(self):
        dt = datetime(2026, 5, 8, 6, 27)
        assert merge_latest_publish_display_time(dt, None) == "2026-05-08 06:27"

    def test_immediate_only(self):
        dt = datetime(2026, 5, 10, 14, 0)
        assert merge_latest_publish_display_time(None, dt) == "2026-05-10 14:00"

    def test_picks_later_scheduled(self):
        sched = datetime(2026, 6, 1, 12, 0)
        imm = datetime(2026, 5, 10, 14, 0)
        assert merge_latest_publish_display_time(sched, imm) == "2026-06-01 12:00"

    def test_picks_later_immediate(self):
        sched = datetime(2026, 5, 8, 6, 27)
        imm = datetime(2026, 5, 10, 14, 0)
        assert merge_latest_publish_display_time(sched, imm) == "2026-05-10 14:00"


class TestGetDatetimeDiffSeconds:
    def test_positive_diff(self):
        dt1 = datetime(2026, 3, 27, 10, 0, 0)
        dt2 = datetime(2026, 3, 27, 9, 0, 0)
        assert get_datetime_diff_seconds(dt1, dt2) == 3600

    def test_negative_diff(self):
        dt1 = datetime(2026, 3, 27, 9, 0, 0)
        dt2 = datetime(2026, 3, 27, 10, 0, 0)
        assert get_datetime_diff_seconds(dt1, dt2) == -3600

    def test_same_time(self):
        dt = datetime(2026, 3, 27, 10, 0, 0)
        assert get_datetime_diff_seconds(dt, dt) == 0
