"""
batch_publish_builder 单元测试
模块：src/ui/pages/publish/batch_publish_builder.py
"""
import json
import pytest
from unittest.mock import AsyncMock, patch

from src.ui.pages.publish.batch_publish_builder import (
    build_publish_tasks_for_batch,
    validate_tasks,
    strip_non_wechat_original_declaration,
    PublishBuildResult,
)
from src.ui.pages.publish.batch_preview_exclusion import PreviewExclusionSet


# 辅助 ----------------------------------------------------------------

def _acc(platform: str = "douyin", username: str = "u1", **kw) -> dict:
    d = {"platform": platform, "platform_username": username, "id": 1}
    d.update(kw)
    return d


def _group(name: str = "g1", group_id: int = 100) -> dict:
    return {
        "_type": "group",
        "platform": "account_group",
        "platform_username": name,
        "group_name": name,
        "group_id": group_id,
        "_group_data": {"group_id": group_id, "accounts": [
            {"platform": "douyin", "platform_username": f"{name}_m1", "id": 10},
            {"platform": "douyin", "platform_username": f"{name}_m2", "id": 11},
        ]},
    }


def _vid(path: str = "/v1.mp4", **kw) -> dict:
    d = {"file_path": path}
    d.update(kw)
    return d


COMMON = {
    "user_id": 1, "title": "", "description": "", "tags_str": "",
    "cover_path": None, "poi_info": "", "micro_app_info": "",
    "cart_info": "", "anchor_info": "",
    "privacy_settings": json.dumps({"privacy": "public", "allow_download": True, "is_original": True}),
}

NO_EXCLUSION = PreviewExclusionSet()


# =========================================================================
# validate_tasks
# =========================================================================

class TestValidateTasks:
    def test_all_valid(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.touch()
        tasks = [{"file_path": str(f), "platform": "douyin", "title": ""}]
        assert validate_tasks(tasks) is None

    def test_missing_file(self):
        tasks = [{"file_path": "/nonexistent_999.mp4", "platform": "douyin", "title": ""}]
        err = validate_tasks(tasks)
        assert err is not None
        assert "nonexistent" in err

    def test_wechat_short_title(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.touch()
        tasks = [{"file_path": str(f), "platform": "wechat_video", "title": "abc"}]
        err = validate_tasks(tasks)
        assert err is not None


# =========================================================================
# strip_non_wechat_original_declaration
# =========================================================================

class TestStripOriginalDeclaration:
    def test_non_wechat_gets_stripped(self):
        ps = json.dumps({"is_original": True})
        tasks = [{"platform": "douyin", "privacy_settings": ps}]
        strip_non_wechat_original_declaration(tasks)
        result = json.loads(tasks[0]["privacy_settings"])
        assert result["is_original"] is False

    def test_wechat_keeps_original(self):
        ps = json.dumps({"is_original": True})
        tasks = [{"platform": "wechat_video", "privacy_settings": ps}]
        strip_non_wechat_original_declaration(tasks)
        result = json.loads(tasks[0]["privacy_settings"])
        assert result["is_original"] is True

    def test_no_original_key_untouched(self):
        ps = json.dumps({"privacy": "public"})
        tasks = [{"platform": "douyin", "privacy_settings": ps}]
        strip_non_wechat_original_declaration(tasks)
        result = json.loads(tasks[0]["privacy_settings"])
        assert "is_original" not in result or result.get("is_original") is False


# =========================================================================
# build_publish_tasks_for_batch — 端到端
# =========================================================================

class TestBuildPublishTasksForBatch:
    @pytest.mark.asyncio
    async def test_basic_single_account(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.touch()
        r = await build_publish_tasks_for_batch(
            [_acc()], [_vid(str(f))], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        assert r.validation_error is None
        assert len(r.tasks) == 1
        assert r.tasks[0]["platform"] == "douyin"

    @pytest.mark.asyncio
    async def test_empty_accounts_returns_empty(self):
        r = await build_publish_tasks_for_batch(
            [], [_vid()], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        assert r.tasks == []
        assert r.empty_group_names == []

    @pytest.mark.asyncio
    async def test_group_expansion(self, tmp_path):
        """账号组 + 自动匹配视频（带 _group_id）→ 展开为成员数 × 视频数的任务。"""
        f1 = tmp_path / "v1.mp4"
        f1.touch()
        f2 = tmp_path / "v2.mp4"
        f2.touch()
        r = await build_publish_tasks_for_batch(
            [_group("g1", 100)],
            [_vid(str(f1), _group_id=100), _vid(str(f2), _group_id=100)],
            ["10:00"],
            COMMON, False, NO_EXCLUSION,
        )
        assert r.validation_error is None
        assert len(r.tasks) >= 2
        usernames = {t["platform_username"] for t in r.tasks}
        assert "g1_m1" in usernames
        assert "g1_m2" in usernames

    @pytest.mark.asyncio
    async def test_empty_group_reported(self):
        empty_g = {
            "_type": "group",
            "platform": "account_group",
            "platform_username": "empty_g",
            "group_name": "空组",
            "group_id": 999,
            "_group_data": {"group_id": 999, "accounts": []},
        }
        r = await build_publish_tasks_for_batch(
            [empty_g], [_vid()], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        assert "空组" in r.empty_group_names
        assert r.tasks == []

    @pytest.mark.asyncio
    async def test_exclusion_filters(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.touch()
        es = PreviewExclusionSet()

        r1 = await build_publish_tasks_for_batch(
            [_acc()], [_vid(str(f))], ["10:00"], COMMON, False, es,
        )
        assert len(r1.tasks) == 1
        fp = (
            r1.tasks[0].get("platform", ""),
            r1.tasks[0].get("platform_username", ""),
            r1.tasks[0].get("file_path", ""),
            r1.tasks[0].get("scheduled_publish_time", ""),
        )
        es.add_excluded_key(fp)

        r2 = await build_publish_tasks_for_batch(
            [_acc()], [_vid(str(f))], ["10:00"], COMMON, False, es,
        )
        assert r2.tasks == []

    @pytest.mark.asyncio
    async def test_validation_error_stops_pipeline(self):
        r = await build_publish_tasks_for_batch(
            [_acc()], [_vid("/no_such_file_xyz.mp4")], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        assert r.validation_error is not None
        assert r.tasks == []

    @pytest.mark.asyncio
    async def test_original_stripped_for_non_wechat(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.touch()
        r = await build_publish_tasks_for_batch(
            [_acc("douyin", "u1")], [_vid(str(f))], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        ps = json.loads(r.tasks[0]["privacy_settings"])
        assert ps.get("is_original") is False

    @pytest.mark.asyncio
    async def test_dedup_with_mock_repo(self, tmp_path):
        f = tmp_path / "v.mp4"
        f.touch()
        mock_repo = AsyncMock()

        async def mock_partition(repo, uid, tasks):
            return tasks[:0], ["skip: u1 /v.mp4"]

        with patch(
            "src.ui.pages.publish.publish_duplicate_guard.partition_batch_publish_tasks_by_duplicates",
            side_effect=mock_partition,
        ):
            r = await build_publish_tasks_for_batch(
                [_acc()], [_vid(str(f))], ["10:00"], COMMON, False, NO_EXCLUSION,
                publish_record_repo=mock_repo,
            )
        assert r.tasks == []
        assert len(r.skip_dup_lines) == 1
