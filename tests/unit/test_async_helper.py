import asyncio

import pytest

from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.ui.utils.async_helper import run_async_from_ui, run_async_task


@pytest.mark.asyncio
async def test_run_async_from_ui_registers_task():
    async def work():
        await asyncio.sleep(0)
        return "ok"

    registry = get_async_task_registry()
    task = run_async_from_ui(work)

    assert task is not None
    assert task.get_name() == "ui.work"
    assert registry.pending_count("ui") >= 1
    assert await task == "ok"
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_run_async_task_registers_task():
    async def work(value):
        await asyncio.sleep(0)
        return value

    task = run_async_task(work, 42)

    assert task.get_name() == "ui.work"
    assert await task == 42
    await asyncio.sleep(0)
