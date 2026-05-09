"""发布时间排期领域规则（domain/publish/schedule），无 Qt 依赖。"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta

import pytest

from src.domain.publish.schedule.batch_slots import compute_batch_schedule_slots
from src.domain.publish.schedule.templates import (
    generate_daily_templates_random_minute_axis,
    generate_daily_templates_whole_hour_axis,
)

pytestmark = pytest.mark.unit


class TestRandomMinuteAxis:
    def test_last_anchor_2330(self):
        tpl, err = generate_daily_templates_random_minute_axis(6, 0, 2)
        assert err is None
        assert tpl == ["06:00", "23:30"]

    def test_n4_start_6(self):
        tpl, err = generate_daily_templates_random_minute_axis(6, 0, 4)
        assert err is None
        assert tpl[0] == "06:00"
        assert tpl[-1] == "23:30"
        assert len(tpl) == 4

    def test_start_602_first_anchor_600(self):
        tpl, err = generate_daily_templates_random_minute_axis(6, 2, 2)
        assert err is None
        assert tpl[0] == "06:02"
        assert tpl[-1] == "23:30"

    def test_start_after_2331_empty(self):
        tpl, err = generate_daily_templates_random_minute_axis(23, 31, 2)
        assert tpl == []
        assert err is not None

    def test_m1(self):
        tpl, err = generate_daily_templates_random_minute_axis(8, 0, 1)
        assert err is None
        assert tpl == ["08:00"]

    def test_last_anchor_follows_end_not_2330(self):
        """末档对齐结束时间，不再强制 23:30。"""
        tpl, err = generate_daily_templates_random_minute_axis(
            6, 0, 2, end_hour=22, end_minute=0
        )
        assert err is None
        assert tpl == ["06:00", "22:00"]

    def test_last_anchor_can_be_2359(self):
        tpl, err = generate_daily_templates_random_minute_axis(
            23, 0, 2, end_hour=23, end_minute=59
        )
        assert err is None
        assert tpl[0] == "23:00"
        assert tpl[-1] == "23:59"


class TestWholeHourAxis:
    def test_602_down_to_600(self):
        tpl, err = generate_daily_templates_whole_hour_axis(6, 2, 2)
        assert err is None
        assert tpl[0] == "06:00"

    def test_grid_insufficient(self):
        tpl, err = generate_daily_templates_whole_hour_axis(23, 0, 3)
        assert tpl == []
        assert err is not None

    def test_hs23_m1(self):
        tpl, err = generate_daily_templates_whole_hour_axis(23, 45, 1)
        assert err is None
        assert tpl == ["23:00"]


class TestComputeBatchSlotsCustom:
    def test_custom_row_no_reroll_random_in_hour(self):
        """§6.2：自定义行固定 HH:mm，不在小时内二次随机。"""
        base = date(2026, 6, 1)
        min_dt = datetime.combine(base, time(0, 0))
        max_dt = datetime.combine(base, time(23, 59))
        tpl = ["08:11"]
        flags = [True]
        slots, meta = compute_batch_schedule_slots(
            tpl,
            flags,
            1,
            base,
            random_minutes_mode=True,
            min_dt=min_dt,
            max_dt=max_dt,
            rng=random.Random(0),
        )
        assert len(slots) == 1
        assert slots[0].endswith("08:11")
        assert meta["shortfall_total"] == 0

    def test_quick_row_random_uses_hour_bucket(self):
        base = date(2026, 6, 1)
        min_dt = datetime.combine(base, time(0, 0))
        max_dt = datetime.combine(base, time(23, 59))
        tpl = ["11:40"]
        flags = [False]
        rng = random.Random(123)
        slots, _ = compute_batch_schedule_slots(
            tpl,
            flags,
            1,
            base,
            random_minutes_mode=True,
            min_dt=min_dt,
            max_dt=max_dt,
            rng=rng,
        )
        h = int(slots[0].split()[1].split(":")[0])
        assert h == 11
