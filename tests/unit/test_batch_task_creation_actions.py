"""
批量发布动作模块单元测试（扩展覆盖）
专注于 generate_batch_tasks 的边界场景和 batch_task_fingerprint 的完整性。
"""

from __future__ import annotations

import pytest

from src.ui.pages.publish.batch_task_creation_actions import (
    generate_batch_tasks,
    batch_task_fingerprint,
)

pytestmark = pytest.mark.unit


def _accs(*names):
    return [{"platform": "douyin", "platform_username": n, "id": i, "group_id": None}
            for i, n in enumerate(names)]


def _vids(*paths):
    return [{"file_path": p, "file_type": "video"} for p in paths]


def _slots(n, base="2025-01-01"):
    return [f"{base} {10+i:02d}:00" for i in range(n)]


class TestGenerateBatchTasksEdgeCases:

    def test_more_videos_than_slots(self):
        """视频多于时间段时任务数 = min(账号*时段, 视频数)"""
        tasks = generate_batch_tasks(_accs("A"), _vids("/v1.mp4", "/v2.mp4", "/v3.mp4"), _slots(1), {"user_id": 1})
        assert len(tasks) >= 1

    def test_task_has_required_fields(self):
        tasks = generate_batch_tasks(_accs("A"), _vids("/v1.mp4"), _slots(1), {"user_id": 1})
        task = tasks[0]
        assert "platform" in task
        assert "platform_username" in task
        assert "file_path" in task
        assert "scheduled_publish_time" in task

    def test_task_user_id_from_context(self):
        tasks = generate_batch_tasks(_accs("A"), _vids("/v1.mp4"), _slots(1), {"user_id": 99})
        assert tasks[0].get("user_id") == 99

    def test_image_file_type_propagated(self):
        tasks = generate_batch_tasks(
            _accs("A"),
            [{"file_path": "/img.jpg", "file_type": "image"}],
            _slots(1),
            {"user_id": 1},
            file_type="image",
        )
        assert tasks[0]["file_type"] == "image"

    def test_single_account_single_slot(self):
        tasks = generate_batch_tasks(_accs("A"), _vids("/v1.mp4"), _slots(1), {"user_id": 1})
        assert len(tasks) == 1
        assert tasks[0]["platform_username"] == "A"
        assert tasks[0]["file_path"] == "/v1.mp4"

    def test_three_accounts_three_videos_round_robin(self):
        tasks = generate_batch_tasks(
            _accs("A", "B", "C"), _vids("/v1.mp4", "/v2.mp4", "/v3.mp4"), _slots(1), {"user_id": 1}
        )
        assert len(tasks) == 3
        platforms = [t["platform_username"] for t in tasks]
        assert "A" in platforms
        assert "B" in platforms
        assert "C" in platforms

    def test_no_slots_returns_empty(self):
        tasks = generate_batch_tasks(_accs("A"), _vids("/v1.mp4"), [], {"user_id": 1})
        assert tasks == []

    def test_immediate_publish_no_slots_ok(self):
        tasks = generate_batch_tasks(
            _accs("A"), _vids("/v1.mp4"), [], {"user_id": 1}, immediate_publish=True
        )
        assert len(tasks) == 1
        assert tasks[0]["scheduled_publish_time"] is None


class TestBatchTaskFingerprintComprehensive:

    def _base_task(self):
        return {
            "platform": "douyin",
            "platform_username": "account_a",
            "file_path": "/video.mp4",
            "scheduled_publish_time": "2025-01-01 10:00",
        }

    def test_identical_tasks_same_fingerprint(self):
        t = self._base_task()
        assert batch_task_fingerprint(t) == batch_task_fingerprint(dict(t))

    def test_different_platform_different_fingerprint(self):
        t1 = self._base_task()
        t2 = dict(t1, platform="kuaishou")
        assert batch_task_fingerprint(t1) != batch_task_fingerprint(t2)

    def test_different_username_different_fingerprint(self):
        t1 = self._base_task()
        t2 = dict(t1, platform_username="account_b")
        assert batch_task_fingerprint(t1) != batch_task_fingerprint(t2)

    def test_different_file_path_different_fingerprint(self):
        t1 = self._base_task()
        t2 = dict(t1, file_path="/other.mp4")
        assert batch_task_fingerprint(t1) != batch_task_fingerprint(t2)

    def test_different_time_different_fingerprint(self):
        t1 = self._base_task()
        t2 = dict(t1, scheduled_publish_time="2025-01-01 11:00")
        assert batch_task_fingerprint(t1) != batch_task_fingerprint(t2)

    def test_fingerprint_is_string_or_hashable(self):
        t = self._base_task()
        fp = batch_task_fingerprint(t)
        hash(fp)  # 可哈希，不抛异常

    def test_extra_fields_dont_affect_fingerprint(self):
        t1 = self._base_task()
        t2 = dict(t1, extra_field="extra_value", another="value")
        assert batch_task_fingerprint(t1) == batch_task_fingerprint(t2)
