"""
发布队列 UI 层「正在执行」条数（供工作台等与列表库表 pending 语义对齐）。

说明：待发布页在发布过程中库表可能仍为 pending，仅界面标「发布中」，
故工作台不能仅靠 publish_records.status=running 统计执行中。
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_executing_count: int = 0


def set_publish_queue_executing_count(n: int) -> None:
    """设置当前视为「发布中」的任务条数（通常为 0 或 1）。"""
    global _executing_count
    with _lock:
        _executing_count = max(0, int(n))


def get_publish_queue_executing_count() -> int:
    """返回当前「发布中」条数。"""
    with _lock:
        return _executing_count
