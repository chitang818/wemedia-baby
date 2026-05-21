import asyncio
import logging

import pytest

from src.infrastructure.common.async_task_registry import AsyncTaskRegistry


@pytest.mark.asyncio
async def test_completed_task_is_unregistered():
    registry = AsyncTaskRegistry()

    async def work():
        return "ok"

    task = registry.create_task(work(), name="unit.done", group="unit")
    assert registry.pending_count("unit") == 1

    await task
    await asyncio.sleep(0)

    assert registry.pending_count("unit") == 0


@pytest.mark.asyncio
async def test_cancel_all_cancels_registered_tasks():
    registry = AsyncTaskRegistry()
    cancelled = asyncio.Event()

    async def work():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    task = registry.create_task(work(), name="unit.cancel", group="unit")
    await asyncio.sleep(0)

    await registry.cancel_all(timeout=1.0)

    assert task.cancelled()
    assert cancelled.is_set()
    assert registry.pending_count("unit") == 0


@pytest.mark.asyncio
async def test_failed_task_is_logged(caplog):
    registry = AsyncTaskRegistry(logging.getLogger("test.async_task_registry"))

    async def work():
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR, logger="test.async_task_registry"):
        task = registry.create_task(work(), name="unit.fail", group="unit")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert task.done()

    assert any(
        record.message == "Background task failed: unit.fail"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_supervised_failure_can_skip_error_log(caplog):
    registry = AsyncTaskRegistry(logging.getLogger("test.async_task_registry"))

    async def work():
        raise RuntimeError("handled elsewhere")

    with caplog.at_level(logging.ERROR, logger="test.async_task_registry"):
        task = registry.create_task(
            work(),
            name="unit.supervised",
            group="unit",
            log_exceptions=False,
        )
        await asyncio.sleep(0)
        assert task.done()

    assert not any(
        record.message == "Background task failed: unit.supervised"
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_registering_same_task_moves_group_without_duplicate_tracking():
    registry = AsyncTaskRegistry()

    async def work():
        await asyncio.sleep(0)

    task = asyncio.create_task(work(), name="unit.move")
    registry.register(task, group="first")
    registry.register(task, group="second")

    assert registry.pending_count("first") == 0
    assert registry.pending_count("second") == 1

    await task
    await asyncio.sleep(0)

    assert registry.pending_count("second") == 0
