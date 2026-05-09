"""
数据统计服务
文件路径：src/services/workspace/dashboard_service.py
功能：提供工作台数据统计
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 回收站软删除状态：不计入「今日发布」与按日趋势，避免主数字与成功/失败/待执行对不上
_SKIP_DASHBOARD_STATUSES = frozenset({"deleted_pending", "deleted_success"})


def _parse_created_at(raw: Optional[str]) -> Optional[datetime]:
    """将 created_at（ISO 或 YYYY-MM-DD HH:MM:SS）解析为 datetime 对象"""
    if not raw or not raw.strip():
        return None
    try:
        if 'T' in raw:
            return datetime.fromisoformat(raw.replace('Z', '+00:00')).replace(tzinfo=None)
        if len(raw) >= 19:
            return datetime.strptime(raw[:19], '%Y-%m-%d %H:%M:%S')
        return datetime.strptime(raw[:10], '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


class DashboardService:
    """数据统计服务（async-first）"""
    
    def __init__(
        self,
        user_id: int,
        account_manager=None,
        batch_task_manager=None,
        publish_record_repository=None
    ):
        from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
        from src.infrastructure.common.di.service_locator import ServiceLocator
        
        self.user_id = user_id
        self.publish_record_repo = publish_record_repository or ServiceLocator().get(PublishRecordRepositoryAsync)
        self.account_manager = account_manager
        self.batch_task_manager = batch_task_manager
        self.logger = logging.getLogger(__name__)
    
    async def get_account_statistics(self) -> Dict[str, Any]:
        try:
            accounts = await self.account_manager.get_accounts()
            
            total = len(accounts)
            
            platform_stats = {}
            for account in accounts:
                platform = account.get('platform', 'unknown')
                platform_stats[platform] = platform_stats.get(platform, 0) + 1
            
            # 与账号库表格一致：仅 login_status 精确为 'online' 计为在线
            online = sum(1 for acc in accounts if acc.get("login_status") == "online")
            offline = total - online
            
            return {
                'total': total,
                'online': online,
                'offline': offline,
                'by_platform': platform_stats
            }
        except Exception as e:
            self.logger.error(f"获取账号统计失败: {e}", exc_info=True)
            return {
                'total': 0,
                'online': 0,
                'offline': 0,
                'by_platform': {}
            }
    
    async def get_publish_statistics(self, days: int = 14) -> Dict[str, Any]:
        try:
            records = await self.publish_record_repo.find_records(
                user_id=None,
                limit=10000
            )
            
            # 全局汇总排除回收站记录，与发布列表「有效任务」语义一致
            active_records = [r for r in records if r.get('status') not in _SKIP_DASHBOARD_STATUSES]
            total = len(active_records)
            success = sum(1 for r in active_records if r.get('status') == 'success')
            failed = sum(1 for r in active_records if r.get('status') == 'failed')
            pending = sum(1 for r in active_records if r.get('status') in ('pending', 'running'))
            
            # ── 今日发布统计（正确解析 ISO 时间戳再做日期对比）──
            today = datetime.now().date()
            today_records = []
            for r in active_records:
                dt = _parse_created_at(r.get('created_at'))
                if dt and dt.date() == today:
                    today_records.append(r)
            
            today_count = len(today_records)
            today_success = sum(1 for r in today_records if r.get('status') == 'success')
            today_failed = sum(1 for r in today_records if r.get('status') == 'failed')
            today_pending = sum(1 for r in today_records if r.get('status') == 'pending')
            today_running = sum(1 for r in today_records if r.get('status') == 'running')
            
            # ── 近 N 天按日聚合（用于趋势图）──
            daily_stats = self._build_daily_stats(active_records, days)
            
            # ── 按平台统计 ──
            platform_stats = {}
            for record in active_records:
                platform = record.get('platform', 'unknown')
                if platform not in platform_stats:
                    platform_stats[platform] = {
                        'total': 0,
                        'success': 0,
                        'failed': 0
                    }
                platform_stats[platform]['total'] += 1
                if record.get('status') == 'success':
                    platform_stats[platform]['success'] += 1
                elif record.get('status') == 'failed':
                    platform_stats[platform]['failed'] += 1
            
            # ── 最近活动 ──
            recent_records = sorted(
                active_records,
                key=lambda x: x.get('created_at', ''),
                reverse=True
            )[:10]
            
            # ── 近 7 天成功率（仅统计已完成记录 success+failed，排除 pending/running）──
            cutoff_7d = datetime.now() - timedelta(days=7)
            records_7d_finished = []
            for r in active_records:
                dt = _parse_created_at(r.get('created_at'))
                if dt and dt >= cutoff_7d and r.get('status') in ('success', 'failed'):
                    records_7d_finished.append(r)
            
            finished_7d_total = len(records_7d_finished)
            finished_7d_success = sum(1 for r in records_7d_finished if r.get('status') == 'success')
            success_rate_7d = (finished_7d_success / finished_7d_total * 100) if finished_7d_total > 0 else 0
            
            return {
                'total': total,
                'success': success,
                'failed': failed,
                'pending': pending,
                'today_count': today_count,
                'today_success': today_success,
                'today_failed': today_failed,
                'today_pending': today_pending,
                'today_running': today_running,
                'daily_stats': daily_stats,
                'by_platform': platform_stats,
                'recent_records': recent_records,
                'success_rate_7d': round(success_rate_7d, 1),
                'finished_7d': finished_7d_total,
            }
        except Exception as e:
            self.logger.error(f"获取发布统计失败: {e}", exc_info=True)
            return {
                'total': 0,
                'success': 0,
                'failed': 0,
                'pending': 0,
                'today_count': 0,
                'today_success': 0,
                'today_failed': 0,
                'today_pending': 0,
                'today_running': 0,
                'daily_stats': [],
                'by_platform': {},
                'recent_records': [],
                'success_rate_7d': 0,
                'finished_7d': 0,
            }
    
    def _parse_record_date(self, created_at: Optional[str]) -> Optional[str]:
        """从 created_at 解析出日期字符串 yyyy-MM-dd"""
        dt = _parse_created_at(created_at)
        return dt.strftime('%Y-%m-%d') if dt else None
    
    def _build_daily_stats(self, records: List[Dict], days: int) -> List[Dict[str, Any]]:
        """按日聚合最近 days 天的发布数量（含成功/失败明细）"""
        today = datetime.now().date()
        buckets: Dict[str, Dict[str, int]] = {}
        for i in range(days):
            d = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            buckets[d] = {'count': 0, 'success': 0, 'failed': 0}
        for r in records:
            d = self._parse_record_date(r.get('created_at'))
            if d and d in buckets:
                buckets[d]['count'] += 1
                st = r.get('status')
                if st == 'success':
                    buckets[d]['success'] += 1
                elif st == 'failed':
                    buckets[d]['failed'] += 1
        return [
            {'date': d, **buckets[d]}
            for d in sorted(buckets.keys())
        ]
    
    async def get_task_statistics(self) -> Dict[str, Any]:
        """获取任务统计（批量任务 + 发布记录中的待执行记录）"""
        batch_total = 0
        batch_by_status = {}
        batch_completion_rate = 0.0

        # 1) 批量任务统计（Pro 功能，可能不可用）
        if self.batch_task_manager:
            try:
                tasks = await self.batch_task_manager.get_tasks()
                batch_total = len(tasks)
                for task in tasks:
                    status = task.get('status', 'unknown')
                    batch_by_status[status] = batch_by_status.get(status, 0) + 1
                completed = batch_by_status.get('completed', 0)
                batch_completion_rate = (completed / batch_total * 100) if batch_total > 0 else 0
            except Exception as e:
                self.logger.error(f"获取批量任务统计失败: {e}", exc_info=True)

        # 2) 待发布页签：与 publish_records_page（待发布列表）一致 —— pending + failed，user_id=None
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
            self.logger.error(f"获取待发布页任务统计失败: {e}", exc_info=True)

        total_pending = (
            batch_by_status.get("pending", 0)
            + batch_by_status.get("running", 0)
            + publish_tab_total
        )

        return {
            'total': batch_total,
            'by_status': batch_by_status,
            'completion_rate': round(batch_completion_rate, 2),
            # 与待发布列表一致（pending+failed）；副标题「等待」= publish_waiting，「执行中」= publish_executing_ui
            'publish_tab_total': publish_tab_total,
            'publish_waiting': publish_waiting,
            'publish_executing_ui': publish_executing_ui,
            # 兼容旧键：此前按库表 pending/running 拆分，现由 publish_tab_total + UI 执行中覆盖语义
            'publish_pending': publish_waiting,
            'publish_running': publish_executing_ui,
            'total_pending': total_pending,
        }
    
    async def get_dashboard_data(self) -> Dict[str, Any]:
        return {
            'account': await self.get_account_statistics(),
            'publish': await self.get_publish_statistics(),
            'task': await self.get_task_statistics()
        }
