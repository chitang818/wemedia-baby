"""
batch_preview_builder 单元测试
模块：src/ui/pages/publish/batch_preview_builder.py

标准三步：①选账号 → ②配置时间 → ③添加视频。
"""
import pytest

from src.ui.pages.publish.batch_preview_builder import (
    build_preview_tasks,
    PreviewBuildResult,
)
from src.ui.pages.publish.batch_preview_exclusion import PreviewExclusionSet


# 测试辅助 ----------------------------------------------------------------

def _acc(platform: str = "douyin", username: str = "u1", **kw) -> dict:
    d = {"platform": platform, "platform_username": username}
    d.update(kw)
    return d


def _group(name: str = "g1", group_id: int = 100, **kw) -> dict:
    d = {
        "_type": "group",
        "platform": "account_group",
        "platform_username": name,
        "group_name": name,
        "group_id": group_id,
    }
    d.update(kw)
    return d


def _vid(path: str = "/v1.mp4", **kw) -> dict:
    d = {"file_path": path}
    d.update(kw)
    return d


COMMON = {
    "user_id": 1, "title": "", "description": "", "tags_str": "",
    "cover_path": None, "poi_info": "", "micro_app_info": "",
    "cart_info": "", "anchor_info": "", "privacy_settings": "{}",
}

NO_EXCLUSION = PreviewExclusionSet()


# =========================================================================
# empty
# =========================================================================

class TestEmptyBranch:
    def test_nothing_selected(self):
        r = build_preview_tasks([], [], [], COMMON, False, NO_EXCLUSION)
        assert r.branch == "empty"
        assert r.n_preview == 0
        assert r.tasks == []
        assert r.row_specs == []


# =========================================================================
# no_time：有账号，未配置时间（非立即发布）
# =========================================================================

class TestNoTimeBranch:
    def test_single_account_placeholder_rows(self):
        r = build_preview_tasks([_acc()], [], [], COMMON, False, NO_EXCLUSION)
        assert r.branch == "no_time"
        assert r.n_preview == 1
        assert r.n_acc == 1
        assert len(r.no_time_placeholder_rows) == 1
        assert r.no_time_placeholder_rows[0]["platform"] == "douyin"
        assert r.no_time_placeholder_rows[0]["scheduled_publish_time"] == "待配置"
        assert len(r.row_specs) == 1
        assert r.row_specs[0]["mode"] == "fp"
        assert r.status_text == "请②配置发布时间"

    def test_account_excluded(self):
        es = PreviewExclusionSet()
        es.add_excluded_account("douyin", "u1")
        r = build_preview_tasks([_acc()], [], [], COMMON, False, es)
        assert r.branch == "no_time"
        assert r.n_preview == 0
        assert r.no_time_placeholder_rows == []

    def test_group_placeholder(self):
        r = build_preview_tasks([_group()], [], [], COMMON, False, NO_EXCLUSION)
        assert r.branch == "no_time"
        assert r.n_preview == 1
        assert r.no_time_placeholder_rows[0].get("_type") == "group"


# =========================================================================
# 无账号时：不再用 media_time 占位分支，统一视为 empty
# （产品规范要求先选账号）
# =========================================================================

class TestNoAccountNoPreviewRows:
    def test_videos_only_is_empty(self):
        vids = [_vid("/a.mp4"), _vid("/b.mp4")]
        r = build_preview_tasks([], vids, [], COMMON, False, NO_EXCLUSION)
        assert r.branch == "empty"

    def test_times_only_is_empty(self):
        r = build_preview_tasks([], [], ["10:00", "11:00"], COMMON, False, NO_EXCLUSION)
        assert r.branch == "empty"


# =========================================================================
# no_video / full
# =========================================================================

class TestFullBranch:
    def test_one_account_one_video_one_time(self):
        r = build_preview_tasks(
            [_acc()], [_vid("/v.mp4")], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        assert r.branch == "full"
        assert r.n_preview == 1
        assert r.tasks[0]["platform"] == "douyin"
        assert r.tasks[0]["file_path"] == "/v.mp4"

    def test_missing_account_gets_placeholder(self):
        accs = [_acc("douyin", "u1"), _acc("kuaishou", "u2")]
        vids = [_vid("/v.mp4")]
        r = build_preview_tasks(accs, vids, ["10:00"], COMMON, False, NO_EXCLUSION)
        assert r.branch == "full"
        assert r.n_preview == 2
        usernames = {t["platform_username"] for t in r.tasks}
        assert "u1" in usernames
        assert "u2" in usernames

    def test_no_videos_with_time_is_no_video(self):
        r = build_preview_tasks(
            [_acc()], [], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        assert r.branch == "no_video"
        assert r.status_text == "请③添加视频"

    def test_no_video_account_group_three_times_three_rows(self):
        """账号组 + 多个时间槽、无视频：预览行数 = 时间槽数（文档 3.1）。"""
        times = ["2026-04-01 08:00", "2026-04-02 09:00", "2026-04-03 10:00"]
        r = build_preview_tasks([_group("账号组1", 100)], [], times, COMMON, False, NO_EXCLUSION)
        assert r.branch == "no_video"
        assert r.n_preview == 3
        assert len(r.no_video_placeholder_rows) == 3
        sched = {row.get("scheduled_publish_time") for row in r.no_video_placeholder_rows}
        assert sched == set(times)

    def test_no_video_two_plain_accounts_two_times_four_rows(self):
        accs = [_acc("douyin", "u1"), _acc("douyin", "u2")]
        times = ["10:00", "11:00"]
        r = build_preview_tasks(accs, [], times, COMMON, False, NO_EXCLUSION)
        assert r.branch == "no_video"
        assert r.n_preview == 4

    def test_account_time_but_video_added_before_time_not_reachable_in_ui(self):
        """纯函数层面：若已有视频但未配时间，仍命中 no_time，视频被忽略至下一步。"""
        r = build_preview_tasks(
            [_acc()], [_vid()], [], COMMON, False, NO_EXCLUSION,
        )
        assert r.branch == "no_time"

    def test_exclusion_filters_tasks(self):
        es = PreviewExclusionSet()
        r1 = build_preview_tasks(
            [_acc()], [_vid("/v.mp4")], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        assert r1.n_preview == 1
        fp = r1.row_specs[0]["fp"]
        es.add_excluded_key(fp)
        r2 = build_preview_tasks(
            [_acc()], [_vid("/v.mp4")], ["10:00"], COMMON, False, es,
        )
        assert r2.n_preview == 0

    def test_row_specs_are_fp_mode(self):
        r = build_preview_tasks(
            [_acc()], [_vid()], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        assert all(s["mode"] == "fp" for s in r.row_specs)

    def test_multiple_accounts_multiple_videos(self):
        accs = [_acc("douyin", f"u{i}") for i in range(3)]
        vids = [_vid(f"/v{i}.mp4") for i in range(6)]
        times = ["10:00", "11:00"]
        r = build_preview_tasks(accs, vids, times, COMMON, False, NO_EXCLUSION)
        assert r.branch == "full"
        assert r.n_preview >= 3

    def test_group_placeholder_single_row(self):
        r = build_preview_tasks(
            [_group("g1", 100)], [_vid()], ["10:00"], COMMON, False, NO_EXCLUSION,
        )
        assert r.branch == "full"
        assert r.n_preview >= 1
        group_tasks = [t for t in r.tasks if t.get("platform") == "account_group"]
        assert len(group_tasks) >= 1
