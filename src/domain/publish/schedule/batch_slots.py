# -*- coding: utf-8 -*-
"""
批量发布时间排期 — 多天展开、平台窗口、去重（规则版 §6～§11）。

纯 datetime 运算，无 Qt；弹窗层负责 QDateTime ↔ datetime 转换。
"""

from __future__ import annotations

import random
import re
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

DAY_END_MIN_EXCLUSIVE = 24 * 60

# 与现有弹窗一致：最早 2.5h、最远 15 天
PLATFORM_MIN_DELAY_SEC = 9000
PLATFORM_MAX_LOOKAHEAD_DAYS = 15


def _parse_hhmm(s: str) -> Optional[Tuple[int, int]]:
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return h, mi
    return None


def _dt_from_date_minutes(d: date, minute_of_day: int) -> datetime:
    minute_of_day = max(0, min(minute_of_day, DAY_END_MIN_EXCLUSIVE - 1))
    h, mi = divmod(minute_of_day, 60)
    return datetime.combine(d, time(h, mi))


def _day_allowed_minute_range(
    target_date: date, min_dt: datetime, max_dt: datetime
) -> Tuple[int, int]:
    """返回 target_date 当日落在 [min_dt, max_dt] 内的分钟区间 [lo, hi_ex)。"""
    if target_date < min_dt.date() or target_date > max_dt.date():
        return (0, 0)
    lo_m = 0
    hi_ex = DAY_END_MIN_EXCLUSIVE
    if target_date == min_dt.date():
        t = min_dt.time()
        lo_m = max(lo_m, t.hour * 60 + t.minute)
    if target_date == max_dt.date():
        t = max_dt.time()
        hi_ex = min(hi_ex, t.hour * 60 + t.minute + 1)
    return (lo_m, hi_ex)


def _feasible_minutes_in_interval(
    target_date: date,
    start_min_inclusive: int,
    end_min_exclusive: int,
    min_dt: datetime,
    max_dt: datetime,
) -> List[int]:
    lo = max(0, start_min_inclusive)
    hi = min(DAY_END_MIN_EXCLUSIVE, end_min_exclusive)
    day_lo, day_hi_ex = _day_allowed_minute_range(target_date, min_dt, max_dt)
    lo2 = max(lo, day_lo)
    hi2 = min(hi, day_hi_ex)
    if lo2 >= hi2:
        return []
    return list(range(lo2, hi2))


def _pick_random_minute_in_feasible(
    target_date: date,
    feasible: List[int],
    seen: Set[str],
    rng: random.Random,
) -> Optional[str]:
    if not feasible:
        return None
    order = feasible[:]
    rng.shuffle(order)
    for minute in order:
        dt = _dt_from_date_minutes(target_date, minute)
        slot = dt.strftime("%Y-%m-%d %H:%M")
        if slot not in seen:
            seen.add(slot)
            return slot
    return None


def compute_batch_schedule_slots(
    daily_time_templates: Sequence[str],
    custom_flags: Sequence[bool],
    days: int,
    start_date: date,
    *,
    random_minutes_mode: bool,
    min_dt: datetime,
    max_dt: datetime,
    rng: Optional[random.Random] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """
    由每日模板与天数生成排期字符串列表。

    random_minutes_mode:
        True — 对「非自定义」行在锚点所在小时内随机分钟；自定义行用固定 HH:mm。
        False — 所有行使用模板时分（整点模式）。

    custom_flags 须与 templates 等长；若短则视为 False 补齐。
    """
    rng = rng or random.Random()
    tpls = list(daily_time_templates)
    n_tpl = len(tpls)
    flags: List[bool] = []
    for i in range(n_tpl):
        flags.append(bool(custom_flags[i]) if i < len(custom_flags) else False)

    if n_tpl == 0 or days < 1:
        return [], {
            "per_day_counts": {},
            "shortfall_total": 0,
            "per_date_shortfall": {},
            "configured_templates_per_day": 0,
        }

    expected_total = n_tpl * days
    result: List[str] = []
    seen: Set[str] = set()

    # 稳定顺序：按模板字符串排序（与原实现一致）
    indexed = sorted(range(n_tpl), key=lambda i: tpls[i])
    for di in range(days):
        target_date = start_date + timedelta(days=di)
        for idx in indexed:
            time_str = tpls[idx]
            is_custom = flags[idx]
            parsed = _parse_hhmm(time_str)
            if parsed is None:
                continue
            h, mi = parsed

            if not random_minutes_mode or is_custom:
                dt = datetime.combine(target_date, time(h, mi))
                if dt < min_dt or dt > max_dt:
                    continue
                slot = dt.strftime("%Y-%m-%d %H:%M")
                if slot in seen:
                    continue
                seen.add(slot)
                result.append(slot)
                continue

            # 随机分钟：锚点所在小时 H 内随机（§6.2）
            hour_anchor = h
            start_m = hour_anchor * 60
            end_m_ex = min((hour_anchor + 1) * 60, DAY_END_MIN_EXCLUSIVE)
            feasible = _feasible_minutes_in_interval(
                target_date, start_m, end_m_ex, min_dt, max_dt
            )
            picked = _pick_random_minute_in_feasible(
                target_date, feasible, seen, rng
            )
            if picked is not None:
                result.append(picked)

    result.sort()
    per_day_counts: Dict[str, int] = dict(Counter(s.split(" ")[0] for s in result))
    shortfall_total = expected_total - len(result)
    per_date_shortfall: Dict[str, int] = {}
    for di in range(days):
        ds = (start_date + timedelta(days=di)).strftime("%Y-%m-%d")
        act = per_day_counts.get(ds, 0)
        if act < n_tpl:
            per_date_shortfall[ds] = n_tpl - act

    return result, {
        "per_day_counts": per_day_counts,
        "shortfall_total": shortfall_total,
        "per_date_shortfall": per_date_shortfall,
        "configured_templates_per_day": n_tpl,
    }


def platform_window_from_now(now: datetime) -> Tuple[datetime, datetime]:
    """与弹窗 `now.addSecs(9000)` / `now.addDays(15)` 一致。"""
    min_dt = now + timedelta(seconds=PLATFORM_MIN_DELAY_SEC)
    max_dt = now + timedelta(days=PLATFORM_MAX_LOOKAHEAD_DAYS)
    return min_dt, max_dt
