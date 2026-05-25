"""启动调度与预加载偏好单元测试"""

import pytest

from src.infrastructure.common.startup_scheduler import StartupScheduler


class _FakeWindow:
    def __init__(self) -> None:
        self.visible = True
        self.cancelled_prefixes: list[str | None] = []
        self.preload_scheduled = 0

    def isVisible(self) -> bool:
        return self.visible

    def _cancel_scheduled_timers(self, prefix: str | None = None) -> None:
        self.cancelled_prefixes.append(prefix)

    def _schedule_startup_preloads(self) -> None:
        self.preload_scheduled += 1


def test_pause_preloads_cancels_preload_timers():
    window = _FakeWindow()
    scheduler = StartupScheduler(window)
    scheduler.pause_preloads("navigate:account_page")
    assert scheduler.preload_paused
    assert window.cancelled_prefixes == ["preload:"]
    assert not scheduler.should_run_preload()


def test_resume_preloads_when_visible():
    window = _FakeWindow()
    scheduler = StartupScheduler(window)
    scheduler.pause_preloads()
    scheduler.resume_preloads_if_idle()
    assert not scheduler.preload_paused
    assert window.preload_scheduled == 1


def test_should_not_run_preload_when_hidden():
    window = _FakeWindow()
    window.visible = False
    scheduler = StartupScheduler(window)
    assert not scheduler.should_run_preload()
