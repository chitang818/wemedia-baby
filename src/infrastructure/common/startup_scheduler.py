"""
启动任务调度：统一延迟常量，并在用户导航时推迟低优先级预加载。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 优先级（数值越小越先执行）
PRIORITY_CHECKS = 10
PRIORITY_ACCOUNT_PREWARM = 20
PRIORITY_UPDATE_CHECK = 30
PRIORITY_PRELOAD = 40


class StartupScheduler:
    """主窗口 show 后编排启动任务；导航时暂停预加载队列。"""

    def __init__(self, window: Any) -> None:
        self._window = window
        self._preload_paused = False
        self._preload_pause_reason: Optional[str] = None

    @property
    def preload_paused(self) -> bool:
        return self._preload_paused

    def pause_preloads(self, reason: str = "navigation") -> None:
        if self._preload_paused:
            return
        self._preload_paused = True
        self._preload_pause_reason = reason
        cancel = getattr(self._window, "_cancel_scheduled_timers", None)
        if callable(cancel):
            cancel("preload:")
        logger.debug("启动预加载已暂停: %s", reason)

    def resume_preloads_if_idle(self) -> None:
        """用户回到工作台且仍无目标页实例时，可重新调度预加载。"""
        if not self._preload_paused:
            return
        self._preload_paused = False
        self._preload_pause_reason = None
        schedule = getattr(self._window, "_schedule_startup_preloads", None)
        if callable(schedule) and self._window.isVisible():
            schedule()

    def should_run_preload(self) -> bool:
        return not self._preload_paused and bool(
            getattr(self._window, "isVisible", lambda: False)()
        )

    def schedule(
        self,
        key: str,
        delay_ms: int,
        callback: Callable[[], None],
        *,
        priority: int = PRIORITY_PRELOAD,
    ) -> Any:
        schedule_fn = getattr(self._window, "_schedule_single_shot", None)
        if not callable(schedule_fn):
            return None
        return schedule_fn(key, delay_ms, callback)
