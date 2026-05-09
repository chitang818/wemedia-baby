"""
发布时间规范化函数单元测试
_normalize_time_str 依赖 Qt QTime，在有 Qt 的环境中运行。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

# 检查 Qt 是否可用（打包/CI 环境下可能没有显示器但有 Qt 库）
try:
    from PySide6.QtCore import QCoreApplication, QTime
    import sys
    if not QCoreApplication.instance():
        _app = QCoreApplication(sys.argv[:1])
    _QT_AVAILABLE = True
except Exception:
    _QT_AVAILABLE = False

skip_no_qt = pytest.mark.skipif(not _QT_AVAILABLE, reason="Qt 不可用，跳过时间规范化测试")


@skip_no_qt
class TestNormalizeTimeStr:

    def _normalize(self, s):
        from src.pro_features.batch.dialogs.publish_time_dialog import _normalize_time_str
        return _normalize_time_str(s)

    def test_standard_hhmm(self):
        assert self._normalize("09:30") == "09:30"

    def test_single_digit_hour(self):
        assert self._normalize("9:5") == "09:05"

    def test_midnight(self):
        assert self._normalize("00:00") == "00:00"

    def test_end_of_day(self):
        assert self._normalize("23:59") == "23:59"

    def test_empty_string_returns_none(self):
        assert self._normalize("") is None

    def test_none_returns_none(self):
        assert self._normalize(None) is None  # type: ignore

    def test_invalid_format_returns_none(self):
        assert self._normalize("25:00") is None

    def test_invalid_minutes_returns_none(self):
        assert self._normalize("10:60") is None

    def test_random_text_returns_none(self):
        assert self._normalize("not_a_time") is None

    def test_strips_whitespace(self):
        result = self._normalize("  10:00  ")
        assert result == "10:00"


@skip_no_qt
class TestNormalizeRandomModePoolInput:
    def _norm(self, s):
        from src.pro_features.batch.dialogs.publish_time_dialog import (
            _normalize_random_mode_pool_input,
        )
        return _normalize_random_mode_pool_input(s)

    def test_hh_random(self):
        assert self._norm("08:随机") == "08:00"
        assert self._norm("9:随机") == "09:00"

    def test_hour_only(self):
        assert self._norm("14") == "14:00"

    def test_falls_back_to_hhmm(self):
        assert self._norm("10:30") == "10:30"


@skip_no_qt
class TestParseTimesPerDayFromQuickUi:
    def _parse(self, s):
        from src.pro_features.batch.dialogs.publish_time_dialog import (
            _parse_times_per_day_from_quick_ui,
        )
        return _parse_times_per_day_from_quick_ui(s)

    def test_preset_style(self):
        assert self._parse("一天3次") == 3
        assert self._parse("一天20次") == 20

    def test_plain_number(self):
        assert self._parse("6") == 6
        assert self._parse("  7 次/天 ") == 7

    def test_out_of_range(self):
        assert self._parse("0") is None
        assert self._parse("9999") is None
        assert self._parse("7") == 7
        assert self._parse("100") is None


@skip_no_qt
class TestDailyTemplatesRandomMinuteAxis:
    """分钟轴等分（规则版 §5.1），末日 23:30。"""

    def _templates(self, n: int, hour: int, minute: int = 0):
        from src.domain.publish.schedule.templates import (
            generate_daily_templates_random_minute_axis,
        )

        tpl, err = generate_daily_templates_random_minute_axis(hour, minute, n)
        assert err is None, err
        return tpl

    def test_n2_start_6(self):
        assert self._templates(2, 6, 0) == ["06:00", "23:30"]

    def test_n4_start_6_until_2330(self):
        assert self._templates(4, 6, 0) == [
            "06:00",
            "11:50",
            "17:40",
            "23:30",
        ]

    def test_n3_start_midnight(self):
        assert self._templates(3, 0, 0) == ["00:00", "11:45", "23:30"]

    def test_n3_start_12(self):
        assert self._templates(3, 12, 0) == ["12:00", "17:45", "23:30"]

    def test_n1_only_start_anchor(self):
        assert self._templates(1, 6, 0) == ["06:00"]

    def test_invalid_n_returns_empty(self):
        from src.domain.publish.schedule.templates import (
            QUICK_SCHEDULE_TIMES_PER_DAY_MAX,
            generate_daily_templates_random_minute_axis,
        )

        assert generate_daily_templates_random_minute_axis(0, 0, 0)[0] == []
        assert generate_daily_templates_random_minute_axis(
            0, 0, QUICK_SCHEDULE_TIMES_PER_DAY_MAX + 1
        )[0] == []

    def test_n6_start_0(self):
        assert self._templates(6, 0, 0) == [
            "00:00",
            "04:42",
            "09:24",
            "14:06",
            "18:48",
            "23:30",
        ]

    def test_n5_start_6(self):
        assert self._templates(5, 6, 0) == [
            "06:00",
            "10:22",
            "14:45",
            "19:08",
            "23:30",
        ]

    def test_start_after_2331_returns_empty(self):
        from src.domain.publish.schedule.templates import (
            generate_daily_templates_random_minute_axis,
        )

        assert generate_daily_templates_random_minute_axis(23, 31, 3)[0] == []

    def test_n20_start_6_spans_to_2330(self):
        t = self._templates(20, 6, 0)
        assert len(t) == 20
        assert t[0] == "06:00"
        assert t[-1] == "23:30"


@skip_no_qt
class TestComputeBatchScheduleSlotsCore:
    """compute_batch_schedule_slots_core：委托 domain，随机分钟按小时桶与篇数统计。"""

    def test_random_mode_hour_matches_template_hour(self):
        """随机分钟：结果的小时与模板锚点的小时一致（与「HH:随机」一致）。"""
        import random
        from collections import Counter

        from PySide6.QtCore import QDate, QDateTime, QTime

        from src.pro_features.batch.dialogs.publish_time_dialog import (
            compute_batch_schedule_slots_core,
        )

        tpl = ["06:00", "11:50", "17:40", "23:30"]
        base = QDate(2026, 4, 10)
        min_dt = QDateTime(base, QTime(0, 0))
        max_dt = QDateTime(base.addDays(30), QTime(23, 59))
        slots, meta = compute_batch_schedule_slots_core(
            tpl, 1, base, True, min_dt, max_dt, rng=random.Random(123)
        )
        assert len(slots) == 4
        assert meta["shortfall_total"] == 0
        exp_h = Counter(QTime.fromString(s, "HH:mm").hour() for s in tpl)
        act_h = Counter(int(x.split()[1].split(":")[0]) for x in slots)
        assert act_h == exp_h

    def test_random_mode_two_days_matches_template_times_days(self):
        import random

        from PySide6.QtCore import QDate, QDateTime, QTime

        from src.domain.publish.schedule.templates import (
            generate_daily_templates_random_minute_axis,
        )
        from src.pro_features.batch.dialogs.publish_time_dialog import (
            compute_batch_schedule_slots_core,
        )

        tpl, err = generate_daily_templates_random_minute_axis(6, 0, 55)
        assert err is None
        assert len(tpl) == 55
        base = QDate(2026, 6, 1)
        min_dt = QDateTime(base, QTime(0, 0))
        max_dt = QDateTime(base.addDays(30), QTime(23, 59))
        rng = random.Random(42)
        slots, meta = compute_batch_schedule_slots_core(
            tpl, 2, base, True, min_dt, max_dt, rng=rng
        )
        assert len(slots) == 110
        assert meta["shortfall_total"] == 0
        assert meta["configured_templates_per_day"] == 55

    def test_random_mode_hour_multiset_matches_templates(self):
        """全日模板各小时出现次数与结果一致（小时桶语义）。"""
        import random
        from collections import Counter

        from PySide6.QtCore import QDate, QDateTime, QTime

        from src.domain.publish.schedule.templates import (
            generate_daily_templates_random_minute_axis,
        )
        from src.pro_features.batch.dialogs.publish_time_dialog import (
            compute_batch_schedule_slots_core,
        )

        tpl, err = generate_daily_templates_random_minute_axis(6, 0, 55)
        assert err is None
        base = QDate(2026, 6, 1)
        min_dt = QDateTime(base, QTime(0, 0))
        max_dt = QDateTime(base.addDays(30), QTime(23, 59))
        rng = random.Random(7)
        slots, meta = compute_batch_schedule_slots_core(
            tpl, 1, base, True, min_dt, max_dt, rng=rng
        )
        assert len(slots) == 55
        assert meta["shortfall_total"] == 0
        exp_h = Counter(QTime.fromString(s, "HH:mm").hour() for s in tpl)
        act_h = Counter(int(x.split()[1].split(":")[0]) for x in slots)
        assert act_h == exp_h

    def test_shortfall_when_min_dt_after_first_intervals(self):
        """首日部分小时整段早于 min_dt 时产生缺口与 per_date_shortfall。"""
        import random

        from PySide6.QtCore import QDate, QDateTime, QTime

        from src.domain.publish.schedule.templates import (
            generate_daily_templates_random_minute_axis,
        )
        from src.pro_features.batch.dialogs.publish_time_dialog import (
            compute_batch_schedule_slots_core,
        )

        tpl, err = generate_daily_templates_random_minute_axis(6, 0, 10)
        assert err is None
        base = QDate(2026, 6, 1)
        # 首日 12:00 之后才允许 → 上午档无法排入
        min_dt = QDateTime(base, QTime(12, 0))
        max_dt = QDateTime(base.addDays(30), QTime(23, 59))
        rng = random.Random(1)
        slots, meta = compute_batch_schedule_slots_core(
            tpl, 1, base, True, min_dt, max_dt, rng=rng
        )
        assert meta["shortfall_total"] > 0
        assert "2026-06-01" in meta["per_date_shortfall"]
        assert len(slots) == 10 - meta["shortfall_total"]

    def test_on_hour_mode_unchanged_semantics(self):
        import random

        from PySide6.QtCore import QDate, QDateTime, QTime

        from src.domain.publish.schedule.templates import (
            generate_daily_templates_whole_hour_axis,
        )
        from src.pro_features.batch.dialogs.publish_time_dialog import (
            compute_batch_schedule_slots_core,
        )

        tpl, err = generate_daily_templates_whole_hour_axis(8, 0, 5)
        assert err is None
        base = QDate(2026, 6, 10)
        min_dt = QDateTime(base, QTime(0, 0))
        max_dt = QDateTime(base.addDays(30), QTime(23, 59))
        slots, meta = compute_batch_schedule_slots_core(
            tpl, 1, base, False, min_dt, max_dt, rng=random.Random(0)
        )
        assert len(slots) == 5
        assert meta["shortfall_total"] == 0
        times = [s.split()[1] for s in slots]
        assert sorted(times) == sorted(tpl)
