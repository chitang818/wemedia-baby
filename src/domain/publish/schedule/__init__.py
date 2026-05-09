# -*- coding: utf-8 -*-
"""发布时间排期领域规则（与 Qt 弹窗解耦，便于单测与复用）。"""

from src.domain.publish.schedule.batch_slots import (
    PLATFORM_MAX_LOOKAHEAD_DAYS,
    PLATFORM_MIN_DELAY_SEC,
    compute_batch_schedule_slots,
    platform_window_from_now,
)
from src.domain.publish.schedule.templates import (
    END_OF_SCHEDULE_DAY_MINUTE,
    QUICK_SCHEDULE_TIMES_PER_DAY_MAX,
    QUICK_SCHEDULE_TIMES_PER_DAY_MIN,
    generate_daily_templates_random_minute_axis,
    generate_daily_templates_whole_hour_axis,
)

__all__ = [
    "END_OF_SCHEDULE_DAY_MINUTE",
    "PLATFORM_MAX_LOOKAHEAD_DAYS",
    "PLATFORM_MIN_DELAY_SEC",
    "QUICK_SCHEDULE_TIMES_PER_DAY_MAX",
    "QUICK_SCHEDULE_TIMES_PER_DAY_MIN",
    "compute_batch_schedule_slots",
    "generate_daily_templates_random_minute_axis",
    "generate_daily_templates_whole_hour_axis",
    "platform_window_from_now",
]
