"""工作台 DashboardService 单元测试"""

from __future__ import annotations

import time
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.workspace.dashboard_service import (
    DashboardService,
    build_account_statistics,
)
from src.utils.date_utils import (
    compute_publish_reminder_days,
    format_publish_reminder_text,
    is_latest_publish_overdue,
)
from src.services.workspace.dashboard_snapshot import DashboardSnapshot
from src.services.workspace.dashboard_stats_cache import DashboardStatsCache


def test_build_account_statistics_online_offline():
    accounts = [
        {"platform": "douyin", "login_status": "online"},
        {"platform": "douyin", "login_status": "offline"},
        {"platform": "kuaishou", "login_status": "online"},
    ]
    stats = build_account_statistics(accounts)
    assert stats["total"] == 3
    assert stats["online"] == 2
    assert stats["offline"] == 1
    assert stats["by_platform"]["douyin"] == 2
    assert stats["by_platform"]["kuaishou"] == 1


@pytest.mark.asyncio
async def test_get_publish_statistics_does_not_call_find_records():
    repo = AsyncMock()
    repo.aggregate_today_publish_counts = AsyncMock(
        return_value={
            "today_count": 2,
            "today_success": 1,
            "today_failed": 1,
            "today_pending": 0,
            "today_running": 0,
        }
    )
    repo.count_active_publish_by_status = AsyncMock(
        return_value={"total": 10, "success": 7, "failed": 2, "pending": 1}
    )
    repo.aggregate_daily_publish_trend = AsyncMock(return_value=[{"date": "2026-05-22", "count": 2, "success": 1, "failed": 1}])
    repo.count_finished_publish_since = AsyncMock(
        return_value={"finished_total": 5, "finished_success": 4}
    )

    svc = DashboardService(
        user_id=1,
        account_manager=MagicMock(),
        publish_record_repository=repo,
    )
    result = await svc.get_publish_statistics()

    repo.find_records.assert_not_called()
    repo.aggregate_today_publish_counts.assert_awaited_once()
    repo.aggregate_daily_publish_trend.assert_awaited_once()
    assert result["today_count"] == 2
    assert result["success_rate_7d"] == 80.0
    assert result["finished_7d"] == 5


@pytest.mark.asyncio
async def test_load_fast_returns_partial_snapshot():
    account_manager = MagicMock()
    account_manager.get_accounts = AsyncMock(
        return_value=[{"platform": "douyin", "login_status": "online", "id": 1}]
    )
    repo = AsyncMock()
    repo.count_records = AsyncMock(return_value=3)

    svc = DashboardService(user_id=1, account_manager=account_manager, publish_record_repository=repo)
    snapshot, accounts = await svc.load_fast()

    assert snapshot.partial is True
    assert snapshot.account["total"] == 1
    assert snapshot.task["publish_tab_total"] == 3
    assert len(accounts) == 1
    repo.find_records.assert_not_called()


@pytest.mark.asyncio
async def test_load_slow_reuses_accounts_for_reminders():
    account_manager = MagicMock()
    account_manager.get_accounts = AsyncMock()
    repo = AsyncMock()
    repo.aggregate_today_publish_counts = AsyncMock(
        return_value={
            "today_count": 0,
            "today_success": 0,
            "today_failed": 0,
            "today_pending": 0,
            "today_running": 0,
        }
    )
    repo.count_active_publish_by_status = AsyncMock(
        return_value={"total": 0, "success": 0, "failed": 0, "pending": 0}
    )
    repo.aggregate_daily_publish_trend = AsyncMock(return_value=[])
    repo.count_finished_publish_since = AsyncMock(
        return_value={"finished_total": 0, "finished_success": 0}
    )
    repo.get_latest_publish_display_time_by_account_ids = AsyncMock(return_value={})

    accounts = [{"platform": "douyin", "login_status": "online", "id": 1, "platform_username": "a"}]
    svc = DashboardService(user_id=1, account_manager=account_manager, publish_record_repository=repo)
    snapshot = await svc.load_slow(accounts)

    account_manager.get_accounts.assert_not_awaited()
    assert snapshot.partial is False
    assert snapshot.account["online"] == 1


def test_dashboard_stats_cache_ttl():
    cache = DashboardStatsCache(ttl_seconds=0.05)
    snap = DashboardSnapshot(account={"total": 9}, loaded_at=time.monotonic())
    cache.set(snap, user_id=1)
    assert cache.get(1) is not None
    time.sleep(0.06)
    assert cache.get(1) is None


def test_dashboard_stats_cache_invalidate():
    cache = DashboardStatsCache()
    snap = DashboardSnapshot(account={"total": 1})
    cache.set(snap, user_id=1)
    cache.invalidate()
    assert cache.get(1) is None


def test_dashboard_stats_cache_persistent_round_trip(monkeypatch):
    from src.infrastructure.common.path_manager import PathManager

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(PathManager, "get_cache_dir", staticmethod(lambda: Path(tmp)))
        cache = DashboardStatsCache()
        snap = DashboardSnapshot(
            account={"total": 2},
            publish={"today_count": 1},
            task={"publish_tab_total": 3},
            reminders=[{"account_name": "demo"}],
            partial=False,
        )

        cache.set(snap, user_id=7)
        restored = cache.get_persistent(7)

        assert restored is not None
        assert restored.account["total"] == 2
        assert restored.publish["today_count"] == 1
        assert restored.reminders[0]["account_name"] == "demo"


def test_dashboard_stats_cache_persistent_stale_still_available(monkeypatch):
    from src.infrastructure.common.path_manager import PathManager

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(PathManager, "get_cache_dir", staticmethod(lambda: Path(tmp)))
        cache = DashboardStatsCache(persistent_ttl_seconds=0.001)
        snap = DashboardSnapshot(account={"total": 2}, partial=False)
        cache.set_complete_snapshot(snap, user_id=7)
        time.sleep(0.01)

        assert cache.get_persistent(7) is not None
        assert cache.get_persistent(7, allow_stale=False) is None


def test_dashboard_stats_cache_does_not_persist_partial(monkeypatch):
    from src.infrastructure.common.path_manager import PathManager

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(PathManager, "get_cache_dir", staticmethod(lambda: Path(tmp)))
        cache = DashboardStatsCache()
        cache.set(DashboardSnapshot(account={"total": 2}, partial=True), user_id=7)

        assert cache.get_persistent(7) is None


@pytest.mark.asyncio
async def test_get_account_publish_reminders_includes_offline_accounts():
    repo = AsyncMock()
    repo.get_latest_publish_display_time_by_account_ids = AsyncMock(
        return_value={1: "2026-05-20", 2: "2026-05-18"}
    )
    accounts = [
        {
            "id": 1,
            "platform": "douyin",
            "login_status": "online",
            "platform_username": "在线号",
        },
        {
            "id": 2,
            "platform": "wechat_video",
            "login_status": "offline",
            "platform_username": "视频号A",
        },
    ]
    svc = DashboardService(user_id=1, account_manager=MagicMock(), publish_record_repository=repo)
    rows = await svc.get_account_publish_reminders(accounts=accounts)

    assert len(rows) == 2
    assert rows[0]["is_online"] is True
    assert rows[0]["account_name"] == "在线号"
    assert rows[1]["is_online"] is False
    assert rows[1]["account_name"] == "视频号A"
    assert rows[1]["reminder_text"] == format_publish_reminder_text(
        compute_publish_reminder_days("2026-05-18")
    )
    assert rows[1]["is_overdue"] == is_latest_publish_overdue("2026-05-18")
    repo.get_latest_publish_display_time_by_account_ids.assert_awaited_once()
    called_ids = set(repo.get_latest_publish_display_time_by_account_ids.await_args.args[0])
    assert called_ids == {1, 2}


def test_snapshot_merge_keeps_fast_task():
    fast = DashboardSnapshot(
        account={"total": 1},
        task={"publish_tab_total": 5},
        partial=True,
    )
    slow = DashboardSnapshot(
        account={"total": 1},
        publish={"today_count": 2},
        reminders=[{"account_name": "x"}],
        partial=False,
    )
    merged = fast.merge(slow)
    assert merged.task["publish_tab_total"] == 5
    assert merged.publish["today_count"] == 2
    assert merged.partial is False
