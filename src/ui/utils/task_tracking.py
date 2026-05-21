from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from src.infrastructure.common.async_task_registry import get_async_task_registry


class TrackedTaskMixin:
    """Small helper for QWidget pages that own cancellable background tasks."""

    def _init_task_tracking(self) -> None:
        self._pending_tasks: list[asyncio.Task] = []

    def _track_task(self, task: asyncio.Task) -> asyncio.Task:
        if not hasattr(self, "_pending_tasks"):
            self._init_task_tracking()
        self._pending_tasks.append(task)
        get_async_task_registry().register(task, group="ui")
        task.add_done_callback(self._on_task_done)
        return task

    def _create_tracked_task(
        self,
        awaitable: Awaitable,
        *,
        name: str,
        group: str = "ui",
        log_exceptions: bool = True,
    ) -> asyncio.Task:
        if not hasattr(self, "_pending_tasks"):
            self._init_task_tracking()
        task = get_async_task_registry().create_task(
            awaitable,
            name=name,
            group=group,
            log_exceptions=log_exceptions,
        )
        self._pending_tasks.append(task)
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task) -> None:
        pending = getattr(self, "_pending_tasks", [])
        if task in pending:
            pending.remove(task)

    def _cancel_tracked_tasks(self) -> None:
        for task in list(getattr(self, "_pending_tasks", [])):
            if not task.done():
                task.cancel()
        getattr(self, "_pending_tasks", []).clear()

    def closeEvent(self, event) -> None:
        self._cancel_tracked_tasks()
        super().closeEvent(event)

    def shutdown(self) -> None:
        self._cancel_tracked_tasks()
