"""
CheckpointManagerAsync 集成测试
使用临时目录模拟检查点存储，验证原子写入、读取、清除等行为。
"""

from __future__ import annotations

import pytest
from pathlib import Path

from src.pro_features.batch.services.checkpoint_manager_async import CheckpointManagerAsync

pytestmark = pytest.mark.integration


@pytest.fixture
def checkpoint_dir(tmp_path) -> Path:
    d = tmp_path / "checkpoints"
    d.mkdir()
    return d


@pytest.fixture
def manager(checkpoint_dir) -> CheckpointManagerAsync:
    return CheckpointManagerAsync(checkpoint_dir=checkpoint_dir)


class TestSaveCheckpoint:

    async def test_save_creates_file(self, manager, checkpoint_dir):
        result = await manager.save_checkpoint(1, {0, 1, 2}, current_index=3)
        assert result is True
        assert (checkpoint_dir / "task_1.json").exists()

    async def test_save_returns_true_on_success(self, manager):
        result = await manager.save_checkpoint(42, {0}, current_index=1)
        assert result is True

    async def test_no_tmp_file_left_after_save(self, manager, checkpoint_dir):
        await manager.save_checkpoint(1, {0}, current_index=1)
        tmp_files = list(checkpoint_dir.glob("*.tmp"))
        assert tmp_files == []


class TestLoadCheckpoint:

    async def test_load_returns_none_when_not_exists(self, manager):
        result = await manager.load_checkpoint(999)
        assert result is None

    async def test_load_after_save_returns_data(self, manager):
        await manager.save_checkpoint(1, {0, 1, 2}, current_index=3)
        data = await manager.load_checkpoint(1)
        assert data is not None
        assert data["task_id"] == 1
        assert data["current_index"] == 3
        assert isinstance(data["completed_indices"], set)

    async def test_completed_indices_converted_to_set(self, manager):
        await manager.save_checkpoint(1, {5, 10, 15}, current_index=16)
        data = await manager.load_checkpoint(1)
        assert isinstance(data["completed_indices"], set)
        assert {5, 10, 15} == data["completed_indices"]

    async def test_load_corrupt_file_returns_none(self, checkpoint_dir, manager):
        corrupt_path = checkpoint_dir / "task_99.json"
        corrupt_path.write_text("not valid json", encoding="utf-8")
        result = await manager.load_checkpoint(99)
        assert result is None


class TestClearCheckpoint:

    async def test_clear_removes_file(self, manager, checkpoint_dir):
        await manager.save_checkpoint(1, {0}, current_index=1)
        assert (checkpoint_dir / "task_1.json").exists()
        result = await manager.clear_checkpoint(1)
        assert result is True
        assert not (checkpoint_dir / "task_1.json").exists()

    async def test_clear_nonexistent_returns_true(self, manager):
        result = await manager.clear_checkpoint(9999)
        assert result is True


class TestHasCheckpoint:

    async def test_has_checkpoint_false_when_not_exists(self, manager):
        assert await manager.has_checkpoint(999) is False

    async def test_has_checkpoint_true_after_save(self, manager):
        await manager.save_checkpoint(1, {0}, current_index=1)
        assert await manager.has_checkpoint(1) is True

    async def test_has_checkpoint_false_after_clear(self, manager):
        await manager.save_checkpoint(1, {0}, current_index=1)
        await manager.clear_checkpoint(1)
        assert await manager.has_checkpoint(1) is False


class TestGetAllCheckpoints:

    async def test_empty_dir_returns_empty_list(self, manager):
        result = await manager.get_all_checkpoints()
        assert result == []

    async def test_returns_all_saved_checkpoints(self, manager):
        await manager.save_checkpoint(1, {0}, current_index=1)
        await manager.save_checkpoint(2, {0, 1}, current_index=2)
        result = await manager.get_all_checkpoints()
        assert len(result) == 2
        task_ids = {c["task_id"] for c in result}
        assert {1, 2} == task_ids


class TestCleanupOldCheckpoints:

    async def test_cleanup_returns_int(self, manager):
        result = await manager.cleanup_old_checkpoints(max_age_hours=0)
        assert isinstance(result, int)
