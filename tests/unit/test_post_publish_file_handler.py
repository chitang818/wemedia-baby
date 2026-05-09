"""
发布后文件操作处理器单元测试
模块：src/infrastructure/common/post_publish_file_handler.py

测试纯逻辑部分：on_task_success / on_task_failed 状态变更，
以及 build_file_groups 的空输入处理（文件 I/O 和 DB 查询均 mock）。
"""
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.infrastructure.common.post_publish_file_handler import (
    PostPublishFileHandler,
    FileGroupInfo,
    _STATUSES_BLOCKING_SHARED_FILE_MOVE,
)


def _mock_orm_queryset(values_rows):
    """模拟 Tortoise：filter().exclude().values() 链。"""
    qs = MagicMock()
    qs.exclude = MagicMock(return_value=qs)
    qs.values = AsyncMock(return_value=values_rows)
    return qs


def _make_group(task_ids, file_paths=None):
    """辅助：构建 FileGroupInfo"""
    ids = set(task_ids)
    return FileGroupInfo(
        file_paths=file_paths or ["/tmp/video.mp4"],
        task_ids=ids,
        pending_task_ids=set(ids),
        has_failed=False,
    )


class TestOnTaskFailed:
    def test_marks_group_failed(self):
        info = _make_group({1, 2})
        file_groups = {"key1": info}
        PostPublishFileHandler.on_task_failed(1, file_groups)
        assert info.has_failed is True

    def test_removes_from_pending(self):
        info = _make_group({1, 2})
        file_groups = {"key1": info}
        PostPublishFileHandler.on_task_failed(1, file_groups)
        assert 1 not in info.pending_task_ids

    def test_task_not_in_any_group_no_error(self):
        info = _make_group({2, 3})
        file_groups = {"key1": info}
        PostPublishFileHandler.on_task_failed(99, file_groups)
        assert info.has_failed is False


class TestOnTaskSuccess:
    @pytest.mark.asyncio
    async def test_last_task_success_triggers_action(self, tmp_path):
        """所有任务成功后，应执行文件操作（此处 delete）"""
        src = tmp_path / "video.mp4"
        src.write_bytes(b"\x00")

        info = _make_group({1}, file_paths=[str(src)])
        file_groups = {"key1": info}
        user_log = logging.getLogger("test")

        await PostPublishFileHandler.on_task_success(
            1, {"id": 1}, file_groups, "delete", user_log
        )
        # 文件被删除后不再存在
        assert not src.exists()

    @pytest.mark.asyncio
    async def test_pending_tasks_remain_no_action(self, tmp_path):
        """还有未完成任务时，不执行文件操作"""
        src = tmp_path / "video.mp4"
        src.write_bytes(b"\x00")

        info = _make_group({1, 2}, file_paths=[str(src)])
        file_groups = {"key1": info}
        user_log = logging.getLogger("test")

        await PostPublishFileHandler.on_task_success(
            1, {"id": 1}, file_groups, "delete", user_log
        )
        # 任务 2 仍 pending，文件不应被删除
        assert src.exists()

    @pytest.mark.asyncio
    async def test_failed_group_skips_action(self, tmp_path):
        """已有失败标记的分组，即使最后一个任务成功也不操作文件"""
        src = tmp_path / "video.mp4"
        src.write_bytes(b"\x00")

        info = _make_group({1}, file_paths=[str(src)])
        info.has_failed = True
        file_groups = {"key1": info}
        user_log = logging.getLogger("test")

        await PostPublishFileHandler.on_task_success(
            1, {"id": 1}, file_groups, "delete", user_log
        )
        assert src.exists()


class TestBuildFileGroups:
    @pytest.mark.asyncio
    async def test_empty_pending_tasks_returns_empty(self):
        mock_repo = AsyncMock()
        mock_group_repo = AsyncMock()
        result = await PostPublishFileHandler.build_file_groups(
            [], mock_repo, mock_group_repo
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_single_task_creates_one_group(self):
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = {"group_id": None}
        mock_group_repo = AsyncMock()

        tasks = [
            {
                "id": 1,
                "platform_account_id": 10,
                "file_path": "/tmp/clip.mp4",
                "platform": "douyin",
                "platform_username": "user1",
            }
        ]
        result = await PostPublishFileHandler.build_file_groups(
            tasks, mock_repo, mock_group_repo
        )
        assert len(result) == 1
        info = next(iter(result.values()))
        assert 1 in info.task_ids


class TestCheckOtherTasksUsingFile:
    """账号组共享文件：查库仅应统计 pending/running/failed，不得把 success 当阻塞。"""

    @pytest.mark.asyncio
    async def test_no_blocking_rows_allows_move(self):
        """模拟 ORM 仅返回阻塞状态行；空结果表示可移动（同组其余任务已成功，不会出现在查询中）。"""
        fp = "/data/unpublished/clip.mp4"
        mock_repo = MagicMock()
        with patch(
            "src.infrastructure.storage.orm_models.publish_record.PublishRecord"
        ) as MockPR:
            MockPR.filter.return_value = _mock_orm_queryset([])
            out = await PostPublishFileHandler._check_other_tasks_using_file(
                fp, exclude_task_id=229, publish_repo=mock_repo
            )
        assert out is False
        MockPR.filter.assert_called_once()
        _kw = MockPR.filter.call_args.kwargs
        assert set(_kw["status__in"]) == _STATUSES_BLOCKING_SHARED_FILE_MOVE

    @pytest.mark.asyncio
    async def test_pending_same_path_blocks(self):
        fp = "/data/unpublished/clip.mp4"
        mock_repo = MagicMock()
        with patch(
            "src.infrastructure.storage.orm_models.publish_record.PublishRecord"
        ) as MockPR:
            MockPR.filter.return_value = _mock_orm_queryset(
                [{"id": 228, "file_path": fp}]
            )
            out = await PostPublishFileHandler._check_other_tasks_using_file(
                fp, exclude_task_id=227, publish_repo=mock_repo
            )
        assert out is True
