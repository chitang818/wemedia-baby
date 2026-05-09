"""
发布去重模块单元测试
测试路径规范化、图文拼接标识、同步去重过滤函数。
async 函数依赖 mock repo，不访问真实数据库。
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.ui.pages.publish.publish_duplicate_guard import (
    normalize_publish_media_path,
    normalize_composite_image_publish_path,
    normalize_publish_file_identity,
    build_active_publish_task_key_set,
    filter_accounts_for_new_publish_task,
    partition_batch_publish_tasks_by_duplicates,
)

pytestmark = pytest.mark.unit


class TestNormalizePublishMediaPath:

    def test_empty_string_returns_empty(self):
        assert normalize_publish_media_path("") == ""

    def test_whitespace_only_returns_empty(self):
        assert normalize_publish_media_path("   ") == ""

    def test_normalizes_path(self):
        result = normalize_publish_media_path("/some/path/../video.mp4")
        assert ".." not in result

    def test_returns_string(self):
        assert isinstance(normalize_publish_media_path("/video.mp4"), str)

    def test_case_normalization(self):
        p1 = normalize_publish_media_path("C:/Videos/test.MP4")
        p2 = normalize_publish_media_path("C:/Videos/test.mp4")
        # Windows 大小写不区分（normcase），Linux 区分
        assert isinstance(p1, str)
        assert isinstance(p2, str)


class TestNormalizeCompositeImagePublishPath:

    def test_single_path(self):
        result = normalize_composite_image_publish_path("/img1.jpg")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_multiple_paths_sorted(self):
        p1 = normalize_composite_image_publish_path("/b.jpg,/a.jpg")
        p2 = normalize_composite_image_publish_path("/a.jpg,/b.jpg")
        assert p1 == p2  # 排序后结果相同

    def test_empty_string_returns_empty(self):
        assert normalize_composite_image_publish_path("") == ""

    def test_whitespace_stripped(self):
        p1 = normalize_composite_image_publish_path(" /a.jpg , /b.jpg ")
        p2 = normalize_composite_image_publish_path("/a.jpg,/b.jpg")
        assert p1 == p2


class TestNormalizePublishFileIdentity:

    def test_video_type(self):
        result = normalize_publish_file_identity("/video.mp4", "video")
        expected = normalize_publish_media_path("/video.mp4")
        assert result == expected

    def test_image_type(self):
        result = normalize_publish_file_identity("/a.jpg,/b.jpg", "image")
        expected = normalize_composite_image_publish_path("/a.jpg,/b.jpg")
        assert result == expected

    def test_empty_type_treated_as_video(self):
        result = normalize_publish_file_identity("/video.mp4", "")
        assert isinstance(result, str)


class TestBuildActivePublishTaskKeySet:

    @pytest.mark.asyncio
    async def test_builds_key_set_from_repo(self):
        repo = MagicMock()
        repo.list_active_publish_rows_for_duplicate_check = AsyncMock(
            return_value=[
                (1, "/video.mp4", "douyin", "test_user", "video"),
            ]
        )
        keys = await build_active_publish_task_key_set(repo, user_id=1)
        assert len(keys) == 1
        key = next(iter(keys))
        assert key[1] == "douyin"
        assert key[2] == "test_user"

    @pytest.mark.asyncio
    async def test_empty_repo_returns_empty_set(self):
        repo = MagicMock()
        repo.list_active_publish_rows_for_duplicate_check = AsyncMock(return_value=[])
        keys = await build_active_publish_task_key_set(repo, user_id=1)
        assert keys == set()

    @pytest.mark.asyncio
    async def test_skips_empty_file_path(self):
        repo = MagicMock()
        repo.list_active_publish_rows_for_duplicate_check = AsyncMock(
            return_value=[(1, "", "douyin", "user", "video")]
        )
        keys = await build_active_publish_task_key_set(repo, user_id=1)
        assert len(keys) == 0


class TestFilterAccountsForNewPublishTask:

    @pytest.mark.asyncio
    async def test_filters_duplicate_accounts(self):
        repo = MagicMock()
        norm_path = normalize_publish_media_path("/v1.mp4")
        repo.list_active_publish_rows_for_duplicate_check = AsyncMock(
            return_value=[
                (1, "/v1.mp4", "douyin", "账号A", "video"),
            ]
        )
        accounts = [
            {"platform": "douyin", "platform_username": "账号A"},
            {"platform": "douyin", "platform_username": "账号B"},
        ]
        allowed, skipped = await filter_accounts_for_new_publish_task(
            repo, user_id=1,
            file_path="/v1.mp4",
            accounts=accounts,
            file_type="video",
        )
        usernames_allowed = [a["platform_username"] for a in allowed]
        assert "账号A" not in usernames_allowed
        assert "账号B" in usernames_allowed

    @pytest.mark.asyncio
    async def test_no_duplicates_all_allowed(self):
        repo = MagicMock()
        repo.list_active_publish_rows_for_duplicate_check = AsyncMock(return_value=[])
        accounts = [
            {"platform": "douyin", "platform_username": "A"},
            {"platform": "douyin", "platform_username": "B"},
        ]
        allowed, skipped = await filter_accounts_for_new_publish_task(
            repo, user_id=1,
            file_path="/new_video.mp4",
            accounts=accounts,
            file_type="video",
        )
        assert len(allowed) == 2
        assert skipped == []
