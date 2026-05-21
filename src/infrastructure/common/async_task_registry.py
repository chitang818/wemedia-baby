from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import Awaitable
from typing import Any


class AsyncTaskRegistry:
    """Track background asyncio tasks and cancel them predictably on shutdown."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._tasks: dict[str, set[asyncio.Task[Any]]] = defaultdict(set)
        self._task_groups: dict[asyncio.Task[Any], str] = {}
        self._task_log_exceptions: dict[asyncio.Task[Any], bool] = {}

    def create_task(
        self,
        awaitable: Awaitable[Any],
        *,
        name: str | None = None,
        group: str = "default",
        log_exceptions: bool = True,
    ) -> asyncio.Task[Any]:
        task = asyncio.create_task(awaitable, name=name)
        return self.register(task, group=group, log_exceptions=log_exceptions)

    def register(
        self,
        task: asyncio.Task[Any],
        *,
        group: str = "default",
        log_exceptions: bool = True,
    ) -> asyncio.Task[Any]:
        old_group = self._task_groups.get(task)
        if old_group is not None:
            self._tasks[old_group].discard(task)
            if not self._tasks[old_group]:
                self._tasks.pop(old_group, None)
        else:
            task.add_done_callback(self._on_done)

        self._tasks[group].add(task)
        self._task_groups[task] = group
        self._task_log_exceptions[task] = log_exceptions
        return task

    def pending_count(self, group: str | None = None) -> int:
        tasks = self._iter_tasks(group)
        return sum(1 for task in tasks if not task.done())

    async def cancel_group(
        self,
        group: str,
        *,
        timeout: float = 5.0,
    ) -> None:
        await self._cancel_tasks(list(self._tasks.get(group, set())), timeout=timeout)

    async def cancel_all(
        self,
        *,
        timeout: float = 5.0,
        exclude_current: bool = True,
    ) -> None:
        current = asyncio.current_task() if exclude_current else None
        tasks = [task for task in self._iter_tasks() if task is not current]
        await self._cancel_tasks(tasks, timeout=timeout)

    def _iter_tasks(self, group: str | None = None) -> list[asyncio.Task[Any]]:
        if group is not None:
            return list(self._tasks.get(group, set()))

        tasks: list[asyncio.Task[Any]] = []
        for grouped_tasks in self._tasks.values():
            tasks.extend(grouped_tasks)
        return tasks

    async def _cancel_tasks(
        self,
        tasks: list[asyncio.Task[Any]],
        *,
        timeout: float,
    ) -> None:
        pending = [task for task in tasks if not task.done()]
        if not pending:
            return

        for task in pending:
            task.cancel()

        done, still_pending = await asyncio.wait(pending, timeout=timeout)
        for task in done:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                task.result()

        if still_pending:
            names = ", ".join(task.get_name() for task in still_pending)
            self._logger.warning(
                "Timed out while cancelling %d background task(s): %s",
                len(still_pending),
                names,
            )

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        group = self._task_groups.pop(task, None)
        log_exceptions = self._task_log_exceptions.pop(task, True)
        if group is not None:
            self._tasks[group].discard(task)
            if not self._tasks[group]:
                self._tasks.pop(group, None)

        if task.cancelled():
            self._logger.debug("Background task cancelled: %s", task.get_name())
            return

        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return

        if exc is not None and log_exceptions:
            self._logger.error(
                "Background task failed: %s",
                task.get_name(),
                exc_info=(type(exc), exc, exc.__traceback__),
            )


_global_registry = AsyncTaskRegistry()


def get_async_task_registry() -> AsyncTaskRegistry:
    return _global_registry
