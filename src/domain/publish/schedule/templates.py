# -*- coding: utf-8 -*-
"""
批量发布时间排期 — 日内模板生成（规则版 §5）。

纯函数，无 Qt 依赖；时间与分钟均按「当日内从 0:00 起的分钟数」运算。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

# 历史/文档用：旧版「末日」固定 23:30（仍导出供外部兼容）
END_OF_SCHEDULE_DAY_MINUTE = 23 * 60 + 30  # 1410

# 当日内有效分钟上界（23:59），用于约束结束时刻与输出格式化
_MAX_MINUTE_OF_DAY = 24 * 60 - 1

# 快捷等分：与历史 UI 上限对齐（1～288）
QUICK_SCHEDULE_TIMES_PER_DAY_MIN = 1
QUICK_SCHEDULE_TIMES_PER_DAY_MAX = 288


def _clamp(x: int, lo: int, hi: int) -> int:
    return min(max(x, lo), hi)


def minutes_from_hhmm(hour: int, minute: int) -> int:
    return hour * 60 + minute


def _format_hhmm(total_minutes: int) -> str:
    total_minutes = _clamp(total_minutes, 0, 24 * 60 - 1)
    h, m = divmod(total_minutes, 60)
    return f"{h:02d}:{m:02d}"


def generate_daily_templates_random_minute_axis(
    start_hour: int,
    start_minute: int,
    m: int,
    *,
    end_hour: int = 23,
    end_minute: int = 30,
) -> Tuple[List[str], Optional[str]]:
    """§5.1 随机分钟：在 [T_start, T_end] 分钟轴上等分 m 档（T_end 默认 23:30）。

    末档锚点为 T_end（不再强制截断到 23:30）；仅要求开始不晚于结束、且时刻落在当日内。
    """
    if m < QUICK_SCHEDULE_TIMES_PER_DAY_MIN or m > QUICK_SCHEDULE_TIMES_PER_DAY_MAX:
        return [], "每日档位数超出允许范围"

    s = _clamp(minutes_from_hhmm(start_hour, start_minute), 0, _MAX_MINUTE_OF_DAY)
    e = _clamp(
        minutes_from_hhmm(end_hour, end_minute),
        0,
        _MAX_MINUTE_OF_DAY,
    )
    if s > e:
        return [], "结束时间须不早于开始时间"
    span = e - s

    if m == 1:
        return [_format_hhmm(min(s, e))], None

    minutes_list: List[int] = []
    for i in range(m):
        if i == m - 1:
            mi = e
        else:
            mi = s + int(round(i * span / (m - 1)))
        minutes_list.append(_clamp(mi, s, e))
    return [_format_hhmm(x) for x in minutes_list], None


def generate_daily_templates_whole_hour_axis(
    start_hour: int,
    start_minute: int,
    m: int,
    *,
    end_hour: int = 23,
    end_minute: int = 0,
) -> Tuple[List[str], Optional[str]]:
    """§5.2 整点：在 [Hs, He] 小时轴上等分 m 个 HH:00（He 默认 23，与结束时刻的小时一致）。

    Hs = hour(T_start)（向下：6:02 → 6）。
    """
    _ = end_minute  # 与 UI 对称；整点轴仅使用 end_hour
    if m < QUICK_SCHEDULE_TIMES_PER_DAY_MIN or m > QUICK_SCHEDULE_TIMES_PER_DAY_MAX:
        return [], "每日档位数超出允许范围"

    hs = start_hour
    he = min(23, end_hour)
    if hs > he:
        return [], "结束时间须不早于开始时间（整点轴）"

    distinct_hours = he - hs + 1
    if distinct_hours < m or (hs == he and m > 1):
        return [], "整点档位数不足：请减少每日次数或改用随机分钟"

    span_h = he - hs
    if m == 1:
        return [f"{hs:02d}:00"], None

    hours: List[int] = []
    for i in range(m):
        if i == m - 1:
            hi = he
        else:
            hi = hs + int(round(i * span_h / (m - 1)))
        hours.append(_clamp(hi, hs, he))
    return [f"{h:02d}:00" for h in hours], None
