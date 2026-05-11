"""
发布记录仓储集成测试
模块：src/domain/repositories/publish_record_repository_async.py
"""
import os
from datetime import datetime

import pytest

from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
from src.infrastructure.storage.orm_models.publish_record import PublishRecord
from src.infrastructure.storage.orm_models.user import User


@pytest.fixture
async def repo(test_db):
    user = await User.create(username="pub_user", password_hash="hash", email="pub@t.com")
    return PublishRecordRepositoryAsync(), user.id


class TestPublishRecordRepositoryCRUD:
    @pytest.mark.asyncio
    async def test_create_and_find(self, repo):
        repo_obj, uid = repo
        record_id = await repo_obj.create(
            user_id=uid,
            platform_username="user1",
            platform="douyin",
            file_path="/tmp/video.mp4",
            file_type="video",
            title="测试视频",
        )
        assert isinstance(record_id, int) and record_id > 0

    @pytest.mark.asyncio
    async def test_find_by_id(self, repo):
        repo_obj, uid = repo
        record_id = await repo_obj.create(
            user_id=uid,
            platform_username="user2",
            platform="kuaishou",
            file_path="/tmp/clip.mp4",
            file_type="video",
        )
        found = await repo_obj.find_by_id(record_id)
        assert found is not None
        assert found["platform"] == "kuaishou"

    @pytest.mark.asyncio
    async def test_find_by_id_not_found(self, repo):
        repo_obj, uid = repo
        result = await repo_obj.find_by_id(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_update_status_success(self, repo):
        repo_obj, uid = repo
        record_id = await repo_obj.create(
            user_id=uid,
            platform_username="u1",
            platform="douyin",
            file_path="/tmp/v.mp4",
            file_type="video",
        )
        await repo_obj.update_status(record_id, "success")
        found = await repo_obj.find_by_id(record_id)
        assert found["status"] == "success"
        assert found.get("updated_at"), "update_status 应写入 updated_at 供已发布列表展示发布时间"

    @pytest.mark.asyncio
    async def test_update_status_failed_with_message(self, repo):
        repo_obj, uid = repo
        record_id = await repo_obj.create(
            user_id=uid,
            platform_username="u1",
            platform="douyin",
            file_path="/tmp/v.mp4",
            file_type="video",
        )
        await repo_obj.update_status(record_id, "failed", error_message="网络超时")
        found = await repo_obj.find_by_id(record_id)
        assert found["status"] == "failed"
        assert "网络超时" in (found.get("error_message") or "")

    @pytest.mark.asyncio
    async def test_delete_record(self, repo):
        repo_obj, uid = repo
        record_id = await repo_obj.create(
            user_id=uid,
            platform_username="u1",
            platform="douyin",
            file_path="/tmp/v.mp4",
            file_type="video",
        )
        deleted = await repo_obj.delete_batch([record_id])
        assert deleted is True
        assert await repo_obj.find_by_id(record_id) is None

    @pytest.mark.asyncio
    async def test_find_records_by_user(self, repo):
        repo_obj, uid = repo
        for i in range(3):
            await repo_obj.create(
                user_id=uid,
                platform_username=f"u{i}",
                platform="douyin",
                file_path=f"/tmp/v{i}.mp4",
                file_type="video",
            )
        records = await repo_obj.find_records(user_id=uid, limit=10)
        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_get_active_file_paths_includes_failed(self, repo):
        repo_obj, uid = repo
        acc_id = 101
        pending_id = await repo_obj.create(
            user_id=uid,
            platform_username="u_pending",
            platform="douyin",
            file_path="/tmp/pending.mp4",
            file_type="video",
            platform_account_id=acc_id,
        )
        failed_id = await repo_obj.create(
            user_id=uid,
            platform_username="u_failed",
            platform="douyin",
            file_path="/tmp/failed.mp4",
            file_type="video",
            platform_account_id=acc_id,
        )
        success_id = await repo_obj.create(
            user_id=uid,
            platform_username="u_success",
            platform="douyin",
            file_path="/tmp/success.mp4",
            file_type="video",
            platform_account_id=acc_id,
        )
        await repo_obj.update_status(pending_id, "pending")
        await repo_obj.update_status(failed_id, "failed", error_message="err")
        await repo_obj.update_status(success_id, "success")

        paths = await repo_obj.get_active_file_paths_for_accounts(uid, [acc_id])
        # 仓储内会对路径做 os.path.normpath 规范化（Windows 下为 \\tmp\\xxx.mp4）
        assert os.path.normpath("/tmp/pending.mp4") in paths
        assert os.path.normpath("/tmp/failed.mp4") in paths
        assert os.path.normpath("/tmp/success.mp4") not in paths


class TestLatestPublishDisplayTimeByAccount:
    """账号管理「已发布最晚时间」：定时 MAX(scheduled) 与立即 MAX(updated_at) 合并。"""

    @pytest.mark.asyncio
    async def test_scheduled_success_only(self, repo):
        repo_obj, uid = repo
        acc_id = 9001
        rid = await repo_obj.create(
            user_id=uid,
            platform_username="sched_only",
            platform="douyin",
            file_path="/tmp/a.mp4",
            file_type="video",
            platform_account_id=acc_id,
            scheduled_publish_time=datetime(2026, 6, 10, 8, 30),
        )
        await repo_obj.update_status(rid, "success")
        out = await repo_obj.get_latest_publish_display_time_by_account_ids([acc_id])
        assert out.get(acc_id) == "2026-06-10 08:30"

    @pytest.mark.asyncio
    async def test_immediate_success_uses_updated_at(self, repo):
        repo_obj, uid = repo
        acc_id = 9002
        rid = await repo_obj.create(
            user_id=uid,
            platform_username="imm_only",
            platform="douyin",
            file_path="/tmp/b.mp4",
            file_type="video",
            platform_account_id=acc_id,
        )
        await repo_obj.update_status(rid, "success")
        await PublishRecord.filter(id=rid).update(updated_at=datetime(2026, 8, 15, 9, 0))
        out = await repo_obj.get_latest_publish_display_time_by_account_ids([acc_id])
        assert out.get(acc_id) == "2026-08-15 09:00"

    @pytest.mark.asyncio
    async def test_merge_prefers_later_immediate_completion(self, repo):
        repo_obj, uid = repo
        acc_id = 9003
        r_sched = await repo_obj.create(
            user_id=uid,
            platform_username="mix_s",
            platform="douyin",
            file_path="/tmp/c.mp4",
            file_type="video",
            platform_account_id=acc_id,
            scheduled_publish_time=datetime(2026, 5, 8, 6, 27),
        )
        await repo_obj.update_status(r_sched, "success")
        r_imm = await repo_obj.create(
            user_id=uid,
            platform_username="mix_i",
            platform="douyin",
            file_path="/tmp/d.mp4",
            file_type="video",
            platform_account_id=acc_id,
        )
        await repo_obj.update_status(r_imm, "success")
        await PublishRecord.filter(id=r_imm).update(updated_at=datetime(2026, 7, 1, 12, 0))
        out = await repo_obj.get_latest_publish_display_time_by_account_ids([acc_id])
        assert out.get(acc_id) == "2026-07-01 12:00"

    @pytest.mark.asyncio
    async def test_merge_prefers_scheduled_when_later(self, repo):
        repo_obj, uid = repo
        acc_id = 9004
        r_sched = await repo_obj.create(
            user_id=uid,
            platform_username="late_s",
            platform="douyin",
            file_path="/tmp/e.mp4",
            file_type="video",
            platform_account_id=acc_id,
            scheduled_publish_time=datetime(2026, 9, 1, 10, 0),
        )
        await repo_obj.update_status(r_sched, "success")
        r_imm = await repo_obj.create(
            user_id=uid,
            platform_username="late_i",
            platform="douyin",
            file_path="/tmp/f.mp4",
            file_type="video",
            platform_account_id=acc_id,
        )
        await repo_obj.update_status(r_imm, "success")
        await PublishRecord.filter(id=r_imm).update(updated_at=datetime(2026, 7, 1, 12, 0))
        out = await repo_obj.get_latest_publish_display_time_by_account_ids([acc_id])
        assert out.get(acc_id) == "2026-09-01 10:00"
