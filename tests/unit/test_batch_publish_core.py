"""
批量发布核心模块单元测试

覆盖：
1. generate_batch_tasks 顺序块分配 + file_type 透传
2. batch_task_fingerprint 四字段唯一性
3. sync_unpublished_for_accounts / auto_match_for_accounts 核心逻辑
4. copywriting_helpers 三个纯函数
"""

import pytest
from unittest.mock import MagicMock


# ──────────────────────────────────────────────
# 辅助工厂函数
# ──────────────────────────────────────────────

def _make_accounts(*names):
    return [{"platform": "douyin", "platform_username": n, "id": i}
            for i, n in enumerate(names)]


def _make_videos(n):
    return [{"file_path": f"/v{i}.mp4"} for i in range(n)]


def _make_slots(n):
    return [f"2025-01-01 {10+i:02d}:00" for i in range(n)]


# ──────────────────────────────────────────────
# generate_batch_tasks
# ──────────────────────────────────────────────

class TestGenerateBatchTasks:

    def test_sequential_allocation_single_slot(self):
        from src.ui.pages.publish.batch_task_creation_actions import generate_batch_tasks
        accs = _make_accounts("A", "B", "C")
        vids = _make_videos(3)
        tasks = generate_batch_tasks(accs, vids, _make_slots(1), {"user_id": 1})
        assert len(tasks) == 3
        assert [t["file_path"] for t in tasks] == ["/v0.mp4", "/v1.mp4", "/v2.mp4"]

    def test_multi_slot_per_account(self):
        from src.ui.pages.publish.batch_task_creation_actions import generate_batch_tasks
        accs = _make_accounts("A", "B")
        vids = _make_videos(4)
        tasks = generate_batch_tasks(accs, vids, _make_slots(2), {"user_id": 1})
        assert len(tasks) == 4
        a_paths = [t["file_path"] for t in tasks if t["platform_username"] == "A"]
        b_paths = [t["file_path"] for t in tasks if t["platform_username"] == "B"]
        assert a_paths == ["/v0.mp4", "/v1.mp4"]
        assert b_paths == ["/v2.mp4", "/v3.mp4"]

    def test_file_type_video(self):
        from src.ui.pages.publish.batch_task_creation_actions import generate_batch_tasks
        tasks = generate_batch_tasks(
            _make_accounts("X"), _make_videos(1), _make_slots(1),
            {"user_id": 1}, file_type="video",
        )
        assert tasks[0]["file_type"] == "video"

    def test_file_type_image(self):
        from src.ui.pages.publish.batch_task_creation_actions import generate_batch_tasks
        tasks = generate_batch_tasks(
            _make_accounts("X"), _make_videos(1), _make_slots(1),
            {"user_id": 1}, file_type="image",
        )
        assert tasks[0]["file_type"] == "image"

    def test_empty_returns_empty(self):
        from src.ui.pages.publish.batch_task_creation_actions import generate_batch_tasks
        assert generate_batch_tasks([], [], [], {}) == []

    def test_legacy_videos_kwarg(self):
        """旧调用方式：传 videos= 关键字参数仍可正常工作"""
        from src.ui.pages.publish.batch_task_creation_actions import generate_batch_tasks
        tasks = generate_batch_tasks(
            _make_accounts("X"), [],
            _make_slots(1), {"user_id": 1},
            videos=_make_videos(1),
        )
        assert len(tasks) == 1

    def test_replicate_per_account_matches_single_video_group_semantics(self):
        """选账号组时：每个账号都分配全部素材（与单条发布页一致）。"""
        from src.ui.pages.publish.batch_task_creation_actions import generate_batch_tasks
        accs = _make_accounts("A", "B")
        vids = _make_videos(3)
        slots = _make_slots(2)
        tasks = generate_batch_tasks(
            accs, vids, slots, {"user_id": 1}, replicate_media_per_account=True
        )
        assert len(tasks) == 6
        a_paths = [t["file_path"] for t in tasks if t["platform_username"] == "A"]
        b_paths = [t["file_path"] for t in tasks if t["platform_username"] == "B"]
        assert a_paths == ["/v0.mp4", "/v1.mp4", "/v2.mp4"]
        assert b_paths == ["/v0.mp4", "/v1.mp4", "/v2.mp4"]
        assert [t["scheduled_publish_time"] for t in tasks[:3]] == [
            "2025-01-01 10:00",
            "2025-01-01 11:00",
            "2025-01-01 10:00",
        ]

    def test_immediate_publish_all_none(self):
        from src.ui.pages.publish.batch_task_creation_actions import generate_batch_tasks
        accs = _make_accounts("A", "B")
        vids = _make_videos(2)
        tasks = generate_batch_tasks(
            accs, vids, [], {"user_id": 1}, immediate_publish=True
        )
        assert len(tasks) == 2
        assert all(t["scheduled_publish_time"] is None for t in tasks)


# ──────────────────────────────────────────────
# batch_task_fingerprint
# ──────────────────────────────────────────────

class TestBatchTaskFingerprint:

    def test_same_task_same_fingerprint(self):
        from src.ui.pages.publish.batch_task_creation_actions import batch_task_fingerprint
        t = {
            "platform": "douyin",
            "platform_username": "A",
            "file_path": "/v1.mp4",
            "scheduled_publish_time": "2025-01-01 10:00",
        }
        assert batch_task_fingerprint(t) == batch_task_fingerprint(dict(t))

    def test_diff_file_diff_fingerprint(self):
        from src.ui.pages.publish.batch_task_creation_actions import batch_task_fingerprint
        t1 = {
            "platform": "douyin",
            "platform_username": "A",
            "file_path": "/v1.mp4",
            "scheduled_publish_time": "2025-01-01 10:00",
        }
        t2 = dict(t1, file_path="/v2.mp4")
        assert batch_task_fingerprint(t1) != batch_task_fingerprint(t2)


# ──────────────────────────────────────────────
# copywriting_helpers（扩展测试，去重与 test_copywriting_helpers.py 不重叠）
# ──────────────────────────────────────────────

class TestCopywritingHelpersInBatchContext:

    def test_parse_topic_list_basic(self):
        from src.pro_features.batch.copywriting_helpers import parse_topic_list
        assert parse_topic_list("今天很开心 #好心情 #每日打卡") == ["好心情", "每日打卡"]

    def test_parse_topic_list_empty(self):
        from src.pro_features.batch.copywriting_helpers import parse_topic_list
        assert parse_topic_list("") == []

    def test_extract_work_id_with_dash(self):
        from src.pro_features.batch.copywriting_helpers import extract_work_id_from_filename
        assert extract_work_id_from_filename("A0001-快乐每一天.mp4") == "A0001"

    def test_extract_work_id_no_dash(self):
        from src.pro_features.batch.copywriting_helpers import extract_work_id_from_filename
        assert extract_work_id_from_filename("A0002.mp4") == "A0002"

    def test_extract_work_id_full_path(self):
        from src.pro_features.batch.copywriting_helpers import extract_work_id_from_filename
        assert extract_work_id_from_filename("/some/path/B0003-title.jpg") == "B0003"

    def test_merge_apply_all_uses_same_text(self):
        from src.pro_features.batch.copywriting_helpers import merge_title_desc_from_copywriting_item
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=True,
            same_title="统一标题",
            same_desc="统一简介",
            use_lib_title=True,
            use_lib_desc=True,
            item={"short_title": "库标题", "description": "库简介"},
        )
        assert t == "统一标题"
        assert d == "统一简介"

    def test_merge_apply_all_falls_back_to_library(self):
        from src.pro_features.batch.copywriting_helpers import merge_title_desc_from_copywriting_item
        t, d = merge_title_desc_from_copywriting_item(
            apply_all=True,
            same_title="",
            same_desc="",
            use_lib_title=True,
            use_lib_desc=True,
            item={"short_title": "库标题", "description": "库简介"},
        )
        assert t == "库标题"
        assert d == "库简介"


# ──────────────────────────────────────────────
# batch_unpublished_sync
# ──────────────────────────────────────────────

def _make_matcher(avail_map, materials_map):
    """构造 mock matcher，按 owner_key 决定可用数量和返回素材"""
    matcher = MagicMock()
    matcher.get_available_count.side_effect = lambda acc, _groups: avail_map.get(acc["id"], 0)
    matcher.fetch_materials.side_effect = lambda acc, n, _groups: (
        materials_map.get(acc["id"], [])[:n], None
    )
    matcher.owner_display_name.side_effect = lambda acc: acc.get("platform_username", "?")
    return matcher


class TestSyncUnpublishedForAccounts:

    def test_normal_allocation(self):
        from src.pro_features.batch.services.batch_unpublished_sync import sync_unpublished_for_accounts
        accs = [{"id": 1, "platform_username": "A"}, {"id": 2, "platform_username": "B"}]
        matcher = _make_matcher(
            {1: 2, 2: 1},
            {
                1: [{"file_path": "/a1.mp4", "file_name": "a1.mp4"},
                    {"file_path": "/a2.mp4", "file_name": "a2.mp4"}],
                2: [{"file_path": "/b1.mp4", "file_name": "b1.mp4"}],
            },
        )
        outcome = sync_unpublished_for_accounts(accs, matcher, set(), n_needed=2)
        assert len(outcome.new_items) == 3
        assert outcome.empty_owner_labels == []

    def test_empty_directory_recorded(self):
        from src.pro_features.batch.services.batch_unpublished_sync import sync_unpublished_for_accounts
        accs = [{"id": 1, "platform_username": "无素材账号"}]
        matcher = _make_matcher({1: 0}, {})
        outcome = sync_unpublished_for_accounts(accs, matcher, set(), n_needed=1)
        assert outcome.new_items == []
        assert "无素材账号" in outcome.empty_owner_labels

    def test_dedup_existing_paths(self):
        from src.pro_features.batch.services.batch_unpublished_sync import sync_unpublished_for_accounts
        accs = [{"id": 1, "platform_username": "A"}]
        matcher = _make_matcher(
            {1: 1},
            {1: [{"file_path": "/v1.mp4", "file_name": "v1.mp4"}]},
        )
        outcome = sync_unpublished_for_accounts(accs, matcher, {"/v1.mp4"}, n_needed=1)
        assert outcome.new_items == []


class TestMaterialAutoMatcherExcludePaths:
    """exclude_paths 排除已在发布列表中的视频"""

    def _make_real_matcher(self, tmp_path, filenames):
        """创建真实 matcher + 临时目录内的文件，并 patch 掉路径解析。"""
        from src.pro_features.batch.services.material_auto_matcher import MaterialAutoMatcher
        matcher = MaterialAutoMatcher(media_type="video")
        for name in filenames:
            (tmp_path / name).write_bytes(b"\x00" * 1024)
        matcher._resolve_scan_dir = lambda root, acc, groups=None: tmp_path
        return matcher

    @pytest.fixture(autouse=True)
    def _patch_root_dir(self, tmp_path):
        with MagicMock() as _:
            pass
        from unittest.mock import patch
        with patch(
            "src.infrastructure.common.material_library_manager.MaterialLibraryManager.get_root_dir",
            return_value=tmp_path,
        ):
            yield

    def test_exclude_paths_skip_matched_files(self, tmp_path):
        import os
        matcher = self._make_real_matcher(tmp_path, ["01.mp4", "02.mp4", "03.mp4"])
        matcher.set_exclude_paths({os.path.normpath(str(tmp_path / "01.mp4"))})

        matched, msg = matcher.fetch_materials(
            {"id": 1, "platform": "douyin", "platform_username": "A"},
            count=2,
        )
        names = [m["file_name"] for m in matched]
        assert "01.mp4" not in names
        assert len(matched) == 2
        assert names == ["02.mp4", "03.mp4"]

    def test_exclude_paths_affects_available_count(self, tmp_path):
        import os
        matcher = self._make_real_matcher(tmp_path, ["01.mp4", "02.mp4", "03.mp4"])
        matcher.set_exclude_paths({os.path.normpath(str(tmp_path / "02.mp4"))})

        count = matcher.get_available_count(
            {"id": 1, "platform": "douyin", "platform_username": "A"},
        )
        assert count == 2

    def test_no_exclude_paths_returns_all(self, tmp_path):
        matcher = self._make_real_matcher(tmp_path, ["01.mp4", "02.mp4"])

        matched, msg = matcher.fetch_materials(
            {"id": 1, "platform": "douyin", "platform_username": "A"},
            count=5,
        )
        assert len(matched) == 2
        assert msg is not None

    def test_all_excluded_returns_empty(self, tmp_path):
        import os
        matcher = self._make_real_matcher(tmp_path, ["01.mp4", "02.mp4"])
        matcher.set_exclude_paths({
            os.path.normpath(str(tmp_path / "01.mp4")),
            os.path.normpath(str(tmp_path / "02.mp4")),
        })

        matched, msg = matcher.fetch_materials(
            {"id": 1, "platform": "douyin", "platform_username": "A"},
            count=1,
        )
        assert matched == []
        assert msg is not None

    def test_reset_clears_exclude_paths(self):
        from src.pro_features.batch.services.material_auto_matcher import MaterialAutoMatcher
        import os
        matcher = MaterialAutoMatcher(media_type="video")
        matcher.set_exclude_paths({os.path.normpath("/some/file.mp4")})
        matcher.reset()
        assert matcher._exclude_paths == set()

    def test_shortage_msg_reflects_remaining_after_exclude(self, tmp_path):
        """排除后剩余数不足时，shortage 提示中包含已在发布列表和剩余可用数。"""
        import os
        matcher = self._make_real_matcher(tmp_path, ["01.mp4", "02.mp4", "03.mp4"])
        matcher.set_exclude_paths({os.path.normpath(str(tmp_path / "01.mp4"))})

        matched, msg = matcher.fetch_materials(
            {"id": 1, "platform": "douyin", "platform_username": "A"},
            count=5,
        )
        assert len(matched) == 2
        assert msg is not None
        assert "已在发布列表" in msg
        assert "剩余可用 0 个" in msg
        assert "共 3 个视频" in msg


class TestAutoMatchForAccounts:

    def test_shortage_message_collected(self):
        from src.pro_features.batch.services.batch_unpublished_sync import auto_match_for_accounts
        matcher = MagicMock()
        matcher.fetch_materials.return_value = ([], "素材不足：需要 2 个，仅剩余 0 个")
        accs = [{"id": 1, "platform_username": "A"}]
        outcome = auto_match_for_accounts(accs, matcher, set(), n_needed=2)
        assert len(outcome.shortage_messages) > 0
        assert outcome.has_issues
