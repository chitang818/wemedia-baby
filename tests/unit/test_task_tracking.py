import asyncio

import pytest

from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.ui.utils.task_tracking import TrackedTaskMixin


class _Owner(TrackedTaskMixin):
    def __init__(self):
        self._init_task_tracking()


@pytest.mark.asyncio
async def test_tracked_task_registers_and_removes_local_reference():
    await get_async_task_registry().cancel_group("ui", timeout=1.0)
    owner = _Owner()

    async def work():
        await asyncio.sleep(0)
        return "ok"

    task = owner._track_task(asyncio.create_task(work(), name="unit.ui.done"))

    assert task in owner._pending_tasks
    assert get_async_task_registry().pending_count("ui") == 1

    assert await task == "ok"
    await asyncio.sleep(0)

    assert owner._pending_tasks == []
    assert get_async_task_registry().pending_count("ui") == 0


@pytest.mark.asyncio
async def test_cancel_tracked_tasks_cancels_pending_work():
    await get_async_task_registry().cancel_group("ui", timeout=1.0)
    owner = _Owner()
    cancelled = asyncio.Event()

    async def work():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = owner._track_task(asyncio.create_task(work(), name="unit.ui.cancel"))
    await asyncio.sleep(0)

    owner._cancel_tracked_tasks()
    await asyncio.sleep(0)

    assert task.cancelled()
    assert cancelled.is_set()
    assert owner._pending_tasks == []
    assert get_async_task_registry().pending_count("ui") == 0


@pytest.mark.asyncio
async def test_create_tracked_task_names_and_registers_task():
    await get_async_task_registry().cancel_group("ui", timeout=1.0)
    owner = _Owner()

    async def work():
        await asyncio.sleep(0)
        return "created"

    task = owner._create_tracked_task(
        work(),
        name="unit.ui.created",
    )

    assert task.get_name() == "unit.ui.created"
    assert task in owner._pending_tasks
    assert get_async_task_registry().pending_count("ui") == 1

    assert await task == "created"
    await asyncio.sleep(0)

    assert owner._pending_tasks == []
    assert get_async_task_registry().pending_count("ui") == 0
