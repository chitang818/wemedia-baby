"""
PreviewExclusionSet 单元测试
模块：src/ui/pages/publish/batch_preview_exclusion.py
"""
from src.ui.pages.publish.batch_preview_exclusion import PreviewExclusionSet


TASK_A = {
    "platform": "douyin",
    "platform_username": "user_a",
    "file_path": "/v1.mp4",
    "scheduled_publish_time": "2026-03-29 10:00",
}

TASK_B = {
    "platform": "kuaishou",
    "platform_username": "user_b",
    "file_path": "/v2.mp4",
    "scheduled_publish_time": "2026-03-29 11:00",
}


class TestFingerprintExclusion:
    def test_excluded_after_record_fp(self):
        es = PreviewExclusionSet()
        spec = {"mode": "fp", "fp": ("douyin", "user_a", "/v1.mp4", "2026-03-29 10:00")}
        assert es.record_deletion(spec)
        assert es.is_task_excluded(TASK_A)
        assert not es.is_task_excluded(TASK_B)

    def test_add_excluded_key_directly(self):
        es = PreviewExclusionSet()
        es.add_excluded_key(("douyin", "user_a", "/v1.mp4", "2026-03-29 10:00"))
        assert es.is_task_excluded(TASK_A)


class TestMediaTimeExclusion:
    def test_excluded_after_record_media_time(self):
        es = PreviewExclusionSet()
        spec = {"mode": "media_time", "path": "/v1.mp4", "time": "2026-03-29 10:00"}
        assert es.record_deletion(spec)
        assert es.is_media_time_excluded("/v1.mp4", "2026-03-29 10:00")
        assert not es.is_media_time_excluded("/v1.mp4", "2026-03-29 11:00")

    def test_media_time_also_excludes_task(self):
        """media_time 排除同样被 is_task_excluded 捕获。"""
        es = PreviewExclusionSet()
        es.add_excluded_media_time("/v1.mp4", "2026-03-29 10:00")
        assert es.is_task_excluded(TASK_A)


class TestAccountExclusion:
    def test_excluded_after_record_account(self):
        es = PreviewExclusionSet()
        spec = {"mode": "account", "platform": "douyin", "username": "user_a"}
        assert es.record_deletion(spec)
        assert es.is_account_excluded("douyin", "user_a")
        assert not es.is_account_excluded("kuaishou", "user_b")

    def test_account_also_excludes_task(self):
        """account 排除同样被 is_task_excluded 捕获。"""
        es = PreviewExclusionSet()
        es.add_excluded_account("douyin", "user_a")
        assert es.is_task_excluded(TASK_A)
        assert not es.is_task_excluded(TASK_B)


class TestCrossModeSafety:
    def test_different_modes_do_not_interfere(self):
        """fp 排除不影响 media_time 查询，反之亦然。"""
        es = PreviewExclusionSet()
        es.add_excluded_key(("douyin", "user_a", "/v1.mp4", "2026-03-29 10:00"))
        assert not es.is_media_time_excluded("/v1.mp4", "2026-03-29 10:00")
        assert not es.is_account_excluded("douyin", "user_a")

    def test_unknown_mode_returns_false(self):
        es = PreviewExclusionSet()
        assert not es.record_deletion({"mode": "unknown"})


class TestClearAndLifecycle:
    def test_clear_resets_all(self):
        es = PreviewExclusionSet()
        es.add_excluded_key(("douyin", "user_a", "/v1.mp4", "10:00"))
        es.add_excluded_media_time("/v2.mp4", "11:00")
        es.add_excluded_account("kuaishou", "user_b")
        assert es.total_excluded_count == 3
        es.clear()
        assert es.total_excluded_count == 0
        assert not es.is_task_excluded(TASK_A)

    def test_repr(self):
        es = PreviewExclusionSet()
        es.add_excluded_key(("a", "b", "c", "d"))
        assert "keys=1" in repr(es)
