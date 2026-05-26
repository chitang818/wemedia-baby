"""
数据统计服务
文件路径：src/services/workspace/dashboard_service.py
功能：提供工作台数据统计（SQL 聚合 + 分阶段加载）
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from time import monotonic
from typing import Any, Dict, List, Optional

from src.services.workspace.dashboard_snapshot import DashboardSnapshot
from src.services.workspace.dashboard_stats_cache import get_dashboard_stats_cache
from src.utils.date_utils import (
    compute_publish_reminder_days,
    format_publish_reminder_text,
    is_latest_publish_overdue,
)

logger = logging.getLogger(__name__)


def build_account_statistics(accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
    """由账号列表推导工作台账号统计（避免重复查库）。"""
    total = len(accounts)
    platform_stats: Dict[str, int] = {}
    for account in accounts:
        platform = account.get("platform", "unknown")
        platform_stats[platform] = platform_stats.get(platform, 0) + 1
    online = sum(1 for acc in accounts if acc.get("login_status") == "online")
    return {
        "total": total,
        "online": online,
        "offline": total - online,
        "by_platform": platform_stats,
    }


class DashboardService:
    """数据统计服务（async-first，SQL 聚合）"""

    def __init__(
        self,
        user_id: int,
        account_manager=None,
        batch_task_manager=None,
        publish_record_repository=None,
    ):
        from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
        from src.infrastructure.common.di.service_locator import ServiceLocator

        self.user_id = user_id
        self.publish_record_repo = publish_record_repository or ServiceLocator().get(
            PublishRecordRepositoryAsync
        )
        self.account_manager = account_manager
        self.batch_task_manager = batch_task_manager
        self.logger = logging.getLogger(__name__)
        self._stats_cache = get_dashboard_stats_cache()

    async def fetch_accounts(self) -> List[Dict[str, Any]]:
        try:
            if not self.account_manager:
                return []
            return await self.account_manager.get_accounts() or []
        except Exception as e:
            self.logger.error("获取账号列表失败: %s", e, exc_info=True)
            return []

    async def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计（批量任务 + 待发布页签）。"""
        batch_total = 0
        batch_by_status: Dict[str, int] = {}
        batch_completion_rate = 0.0

        if self.batch_task_manager:
            try:
                tasks = await self.batch_task_manager.get_tasks()
                batch_total = len(tasks)
                for task in tasks:
                    status = task.get("status", "unknown")
                    batch_by_status[status] = batch_by_status.get(status, 0) + 1
                completed = batch_by_status.get("completed", 0)
                batch_completion_rate = (completed / batch_total * 100) if batch_total > 0 else 0
            except Exception as e:
                self.logger.error("获取批量任务统计失败: %s", e, exc_info=True)

        publish_tab_total = 0
        publish_waiting = 0
        publish_executing_ui = 0
        try:
            from src.services.publish.publish_queue_ui_state import get_publish_queue_executing_count

            publish_tab_total = await self.publish_record_repo.count_records(
                user_id=None,
                status_in=["pending", "failed"],
            )
            publish_executing_ui = get_publish_queue_executing_count()
            publish_waiting = max(0, publish_tab_total - publish_executing_ui)
        except Exception as e:
            self.logger.error("获取待发布页任务统计失败: %s", e, exc_info=True)

        total_pending = (
            batch_by_status.get("pending", 0)
            + batch_by_status.get("running", 0)
            + publish_tab_total
        )

        return {
            "total": batch_total,
            "by_status": batch_by_status,
            "completion_rate": round(batch_completion_rate, 2),
            "publish_tab_total": publish_tab_total,
            "publish_waiting": publish_waiting,
            "publish_executing_ui": publish_executing_ui,
            "publish_pending": publish_waiting,
            "publish_running": publish_executing_ui,
            "total_pending": total_pending,
        }

    async def get_publish_statistics(self, days: int = 14) -> Dict[str, Any]:
        """发布统计（SQL 聚合，不拉全表）。"""
        try:
            today_counts, status_counts, daily_stats, finished_7d = await asyncio.gather(
                self.publish_record_repo.aggregate_today_publish_counts(),
                self.publish_record_repo.count_active_publish_by_status(),
                self.publish_record_repo.aggregate_daily_publish_trend(days=days),
                self.publish_record_repo.count_finished_publish_since(
                    datetime.now() - timedelta(days=7)
                ),
            )
            finished_total = int(finished_7d.get("finished_total", 0) or 0)
            finished_success = int(finished_7d.get("finished_success", 0) or 0)
            success_rate_7d = (
                (finished_success / finished_total * 100) if finished_total > 0 else 0.0
            )
            return {
                "total": int(status_counts.get("total", 0) or 0),
                "success": int(status_counts.get("success", 0) or 0),
                "failed": int(status_counts.get("failed", 0) or 0),
                "pending": int(status_counts.get("pending", 0) or 0),
                "today_count": int(today_counts.get("today_count", 0) or 0),
                "today_success": int(today_counts.get("today_success", 0) or 0),
                "today_failed": int(today_counts.get("today_failed", 0) or 0),
                "today_pending": int(today_counts.get("today_pending", 0) or 0),
                "today_running": int(today_counts.get("today_running", 0) or 0),
                "daily_stats": daily_stats,
                "by_platform": {},
                "success_rate_7d": round(success_rate_7d, 1),
                "finished_7d": finished_total,
            }
        except Exception as e:
            self.logger.error("获取发布统计失败: %s", e, exc_info=True)
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "pending": 0,
                "today_count": 0,
                "today_success": 0,
                "today_failed": 0,
                "today_pending": 0,
                "today_running": 0,
                "daily_stats": [],
                "by_platform": {},
                "success_rate_7d": 0,
                "finished_7d": 0,
            }

    async def get_account_publish_reminders(
        self,
        accounts: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """全部账号发布提醒（含离线；可复用已拉取的账号列表）。"""
        try:
            if accounts is None:
                accounts = await self.fetch_accounts()
            account_list = list(accounts or [])
            if not account_list:
                return []

            account_ids: List[int] = []
            for a in account_list:
                aid = a.get("id")
                if aid is not None:
                    try:
                        account_ids.append(int(aid))
                    except (TypeError, ValueError):
                        pass

            latest_map: Dict[int, str] = {}
            if account_ids:
                latest_map = await self.publish_record_repo.get_latest_publish_display_time_by_account_ids(
                    account_ids
                )

            rows: List[Dict[str, Any]] = []
            for a in account_list:
                aid = a.get("id")
                if aid is None:
                    continue
                try:
                    aid_int = int(aid)
                except (TypeError, ValueError):
                    continue

                is_online = a.get("login_status") == "online"
                account_name = (
                    (a.get("platform_username") or a.get("account_name") or "").strip()
                    or "未命名"
                )
                latest_raw = latest_map.get(aid_int)
                latest_publish_time = latest_raw if latest_raw else "-"
                remaining_days = compute_publish_reminder_days(latest_publish_time)
                reminder_text = format_publish_reminder_text(remaining_days)
                is_overdue = is_latest_publish_overdue(latest_publish_time)

                rows.append({
                    "account_id": aid_int,
                    "account_name": account_name,
                    "latest_publish_time": latest_publish_time,
                    "remaining_days": remaining_days,
                    "reminder_text": reminder_text,
                    "is_overdue": is_overdue,
                    "is_online": is_online,
                    "login_status": "online" if is_online else "offline",
                })

            rows.sort(
                key=lambda r: (
                    not r["is_online"],
                    r["remaining_days"] is None,
                    r["remaining_days"] if r["remaining_days"] is not None else 0,
                    r["account_name"],
                )
            )
            return rows
        except Exception as e:
            self.logger.error("获取账号发布提醒失败: %s", e, exc_info=True)
            return []

    async def get_online_account_publish_reminders(
        self,
        accounts: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """兼容旧名：返回全部账号发布提醒。"""
        return await self.get_account_publish_reminders(accounts=accounts)

    async def load_fast(self) -> tuple[DashboardSnapshot, List[Dict[str, Any]]]:
        """快路径：账号 + 任务（一次账号查询）。"""
        accounts, task_stats = await asyncio.gather(
            self.fetch_accounts(),
            self.get_task_statistics(),
        )
        account_stats = build_account_statistics(accounts)
        snapshot = DashboardSnapshot(
            account=account_stats,
            publish={},
            task=task_stats,
            reminders=[],
            loaded_at=monotonic(),
            partial=True,
        )
        return snapshot, accounts

    async def load_slow(self, accounts: List[Dict[str, Any]]) -> DashboardSnapshot:
        """慢路径：发布 SQL 聚合 + 最近发布提醒。"""
        publish_stats, reminders = await asyncio.gather(
            self.get_publish_statistics(),
            self.get_account_publish_reminders(accounts=accounts),
        )
        account_stats = build_account_statistics(accounts)
        return DashboardSnapshot(
            account=account_stats,
            publish=publish_stats,
            task={},
            reminders=reminders,
            loaded_at=monotonic(),
            partial=False,
        )

    async def load_full(self) -> DashboardSnapshot:
        """完整加载并写入缓存。"""
        fast, accounts = await self.load_fast()
        slow = await self.load_slow(accounts)
        merged = fast.merge(slow)
        merged = DashboardSnapshot(
            account=merged.account,
            publish=merged.publish,
            task=fast.task,
            reminders=merged.reminders,
            loaded_at=monotonic(),
            partial=False,
        )
        self._stats_cache.set(merged, user_id=self.user_id)
        return merged

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """兼容旧调用：完整加载。"""
        snapshot = await self.load_full()
        return snapshot.to_legacy_dict()

    def get_cached_snapshot(self) -> Optional[DashboardSnapshot]:
        return self._stats_cache.get(self.user_id)

    def get_persistent_snapshot(self) -> Optional[DashboardSnapshot]:
        return self._stats_cache.get_persistent(self.user_id)

    def invalidate_cache(self) -> None:
        self._stats_cache.invalidate()

    def cache_snapshot(self, snapshot: DashboardSnapshot) -> None:
        self._stats_cache.set(snapshot, user_id=self.user_id)
