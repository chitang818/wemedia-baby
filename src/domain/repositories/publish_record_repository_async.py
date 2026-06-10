"""
发布记录 Repository（异步版本）- 基于 Tortoise ORM
功能：封装发布记录相关的数据访问操作
"""

from typing import Optional, List, Dict, Any, Set, Tuple
import logging
from datetime import datetime, date, timedelta

from tortoise import Tortoise
from tortoise.functions import Max

from .base_repository_async import BaseRepositoryAsync
from src.infrastructure.storage.orm_models.publish_record import PublishRecord
from src.infrastructure.storage.orm_models.platform_account import PlatformAccount
from src.infrastructure.storage.retry import retry_on_locked
from src.plugins.core.publish_failure_kind import (
    classify_publish_failure,
    is_blocking_failure_kind,
    normalize_failure_kind,
)
from src.utils.date_utils import format_schedule_time_st_str, merge_latest_publish_display_time

logger = logging.getLogger(__name__)

# 软删除：待发布侧（pending/failed/running）→ deleted_pending；已发布（success）→ deleted_success
STATUS_SOFT_DELETE_MAP = {
    "pending": "deleted_pending",
    "failed": "deleted_pending",
    "running": "deleted_pending",
    "success": "deleted_success",
}
STATUS_RESTORE_MAP = {
    "deleted_pending": "pending",
    "deleted_success": "success",
}
_DELETED_STATUSES = frozenset({"deleted_pending", "deleted_success"})


class PublishRecordRepositoryAsync(BaseRepositoryAsync):
    """发布记录 Repository（异步版本）- 基于 Tortoise ORM

    封装 publish_records 表的所有数据访问操作。
    """

    model_class = PublishRecord

    @retry_on_locked()
    async def create(
        self,
        user_id: int,
        platform_username: str,
        platform: str,
        file_path: str,
        file_type: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[str] = None,
        cover_path: Optional[str] = None,
        poi_info: Optional[str] = None,
        wechat_empty_location_open_picker: Optional[bool] = None,
        micro_app_info: Optional[str] = None,
        cart_info: Optional[str] = None,
        anchor_info: Optional[str] = None,
        music_info: Optional[str] = None,
        privacy_settings: Optional[str] = None,
        scheduled_publish_time: Optional[str] = None,
        platform_account_id: Optional[int] = None,
        task_source: Optional[str] = None,
        group_id: Optional[int] = None,
        diagnostic_path: Optional[str] = None,
        failure_kind: Optional[str] = None,
    ) -> int:
        """创建发布记录

        Args:
            user_id: 用户ID
            platform_username: 平台昵称
            platform: 平台名称
            file_path: 文件路径
            file_type: 文件类型（video/image）
            title ~ scheduled_publish_time: 可选的发布内容字段
            platform_account_id: 平台账号表主键（可选，用于列表展示账号组）
            task_source: 任务来源（account=账号创建/group=账号组创建/None=旧数据）
            group_id: 账号组 ID（task_source==group 时填入，避免查询时多跳路径）

        Returns:
            新创建的记录ID
        """
        try:
            record = await PublishRecord.create(
                user_id=user_id,
                platform_username=platform_username,
                platform=platform,
                platform_account_id=platform_account_id,
                group_id=group_id,
                file_path=file_path,
                file_type=file_type,
                title=title,
                description=description,
                tags=tags,
                cover_path=cover_path,
                poi_info=poi_info,
                wechat_empty_location_open_picker=wechat_empty_location_open_picker,
                micro_app_info=micro_app_info,
                cart_info=cart_info,
                anchor_info=anchor_info,
                music_info=music_info,
                privacy_settings=privacy_settings,
                scheduled_publish_time=scheduled_publish_time,
                task_source=task_source,
                diagnostic_path=diagnostic_path,
                failure_kind=normalize_failure_kind(failure_kind),
                status="pending",
            )
            return record.id
        except Exception as e:
            self.handle_error(e, "create")
            raise

    @retry_on_locked()
    async def update_status(
        self,
        record_id: int,
        status: str,
        publish_url: Optional[str] = None,
        error_message: Optional[str] = None,
        diagnostic_path: Optional[str] = None,
        failure_kind: Optional[str] = None,
    ) -> bool:
        """更新发布记录状态

        Args:
            record_id: 记录ID
            status: 状态（pending/running/success/failed）
            publish_url: 发布URL（可选）
            error_message: 错误信息（可选）

        Returns:
            是否成功
        """
        try:
            update_data = {"status": status, "updated_at": datetime.now()}
            if publish_url is not None:
                update_data["publish_url"] = publish_url
            if error_message is not None:
                update_data["error_message"] = error_message
            if failure_kind is not None:
                update_data["failure_kind"] = normalize_failure_kind(failure_kind)
            elif status == "failed" and error_message:
                update_data["failure_kind"] = classify_publish_failure(error_message)
            elif status in {"pending", "running", "success"}:
                update_data["failure_kind"] = None
            if diagnostic_path is not None:
                update_data["diagnostic_path"] = diagnostic_path

            updated = await PublishRecord.filter(id=record_id).update(**update_data)
            return updated > 0
        except Exception as e:
            self.handle_error(e, "update_status")
            return False

    @retry_on_locked()
    async def update_content(
        self,
        record_id: int,
        **kwargs,
    ) -> bool:
        """更新发布记录内容（用于编辑）

        Args:
            record_id: 记录ID
            **kwargs: 要更新的字段（如 title, description, tags 等）

        Returns:
            是否成功
        """
        try:
            kwargs["updated_at"] = datetime.now()
            updated = await PublishRecord.filter(id=record_id).update(**kwargs)
            return updated > 0
        except Exception as e:
            self.handle_error(e, "update_content")
            return False

    @retry_on_locked()
    async def delete_batch(self, record_ids: List[int]) -> bool:
        """批量删除发布记录

        Args:
            record_ids: 记录ID列表

        Returns:
            删除是否成功
        """
        if not record_ids:
            return True
        try:
            deleted = await PublishRecord.filter(id__in=record_ids).delete()
            self.logger.info(f"批量删除发布记录成功: {deleted} 条")
            return deleted > 0
        except Exception as e:
            self.handle_error(e, "delete_batch")
            return False

    @retry_on_locked()
    async def purge_deleted_older_than(self, days: int = 30) -> int:
        """物理删除回收站中超过指定天数的记录。

        Returns:
            被删除的记录数量
        """
        cutoff = datetime.now() - timedelta(days=days)
        try:
            deleted = await PublishRecord.filter(
                status__in=list(_DELETED_STATUSES),
                updated_at__lt=cutoff,
            ).delete()
            if deleted:
                self.logger.info("自动清理回收站：已永久删除 %d 条超过 %d 天的记录", deleted, days)
            return deleted
        except Exception as e:
            self.handle_error(e, "purge_deleted_older_than")
            return 0

    @retry_on_locked()
    async def soft_delete_batch(self, record_ids: List[int]) -> bool:
        """将记录移入回收站（更新 status，不物理删除）。"""
        if not record_ids:
            return True
        try:
            records = await PublishRecord.filter(id__in=record_ids).all()
            now = datetime.now()
            for r in records:
                cur = (r.status or "").strip()
                if cur in _DELETED_STATUSES:
                    continue
                new_st = STATUS_SOFT_DELETE_MAP.get(cur, "deleted_pending")
                await PublishRecord.filter(id=r.id).update(status=new_st, updated_at=now)
            return True
        except Exception as e:
            self.handle_error(e, "soft_delete_batch")
            return False

    @retry_on_locked()
    async def restore_batch(self, record_ids: List[int]) -> bool:
        """从回收站恢复：deleted_pending→pending，deleted_success→success。"""
        if not record_ids:
            return True
        try:
            records = await PublishRecord.filter(id__in=record_ids).all()
            now = datetime.now()
            for r in records:
                cur = (r.status or "").strip()
                restored = STATUS_RESTORE_MAP.get(cur)
                if not restored:
                    continue
                await PublishRecord.filter(id=r.id).update(status=restored, updated_at=now)
            return True
        except Exception as e:
            self.handle_error(e, "restore_batch")
            return False

    async def find_deleted_records(
        self,
        user_id: Optional[int] = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """回收站：status 为 deleted_pending / deleted_success 的记录。"""
        try:
            filters: Dict[str, Any] = {
                "status__in": ["deleted_pending", "deleted_success"],
            }
            if user_id is not None:
                filters["user_id"] = user_id
            records = await (
                PublishRecord.filter(**filters)
                .order_by("-updated_at")
                .offset(offset)
                .limit(limit)
                .all()
            )
            out = [self._to_dict(r) for r in records]
            await self._attach_account_group_names(out)
            return out
        except Exception as e:
            self.handle_error(e, "find_deleted_records")
            return []

    async def find_deleted_record_ids(
        self,
        user_id: Optional[int] = None,
    ) -> List[int]:
        """Return all recycle-bin record ids for bulk cleanup."""
        try:
            filters: Dict[str, Any] = {
                "status__in": ["deleted_pending", "deleted_success"],
            }
            if user_id is not None:
                filters["user_id"] = user_id
            rows = await PublishRecord.filter(**filters).values_list("id", flat=True)
            return [int(x) for x in rows if x is not None]
        except Exception as e:
            self.handle_error(e, "find_deleted_record_ids")
            return []

    async def find_records(
        self,
        user_id: Optional[int] = None,
        platform_username: Optional[str] = None,
        platform: Optional[str] = None,
        status: Optional[str] = None,
        status_in: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """获取发布记录列表

        Args:
            user_id: 用户ID（可选；不传或 None 时不过滤，返回本地全部记录，用于单用户模式）
            platform_username: 平台账号昵称（可选）
            platform: 平台名称（可选）
            status: 状态（可选，精确匹配单个状态）
            status_in: 状态列表（可选，匹配多个状态，优先于 status）
            limit: 返回记录数限制
            offset: 跳过的记录数，用于分页

        Returns:
            发布记录列表
        """
        try:
            filters: Dict[str, Any] = {}
            if user_id is not None:
                filters["user_id"] = user_id
            if platform_username:
                filters["platform_username"] = platform_username
            if platform:
                filters["platform"] = platform
            if status_in:
                filters["status__in"] = status_in
            elif status:
                filters["status"] = status

            records = await (
                PublishRecord.filter(**filters)
                .order_by("-created_at")
                .offset(offset)
                .limit(limit)
                .all()
            )
            out = [self._to_dict(r) for r in records]
            await self._attach_account_group_names(out)
            return out
        except Exception as e:
            self.handle_error(e, "find_records")
            return []

    async def count_records(
        self,
        user_id: Optional[int] = None,
        platform: Optional[str] = None,
        status_in: Optional[List[str]] = None,
    ) -> int:
        """统计符合条件的记录总数（用于分页 UI）。"""
        try:
            filters: Dict[str, Any] = {}
            if user_id is not None:
                filters["user_id"] = user_id
            if platform:
                filters["platform"] = platform
            if status_in:
                filters["status__in"] = status_in
            return await PublishRecord.filter(**filters).count()
        except Exception as e:
            self.handle_error(e, "count_records")
            return 0

    def _active_dashboard_queryset(self):
        """工作台统计用：排除回收站软删除记录。"""
        return PublishRecord.filter(status__not_in=list(_DELETED_STATUSES))

    @retry_on_locked()
    async def aggregate_today_publish_counts(self) -> Dict[str, int]:
        """今日发布各状态计数（SQL count，不拉全表）。"""
        try:
            today = date.today()
            today_start = datetime.combine(today, datetime.min.time())
            tomorrow_start = today_start + timedelta(days=1)
            conn = Tortoise.get_connection("default")
            result = await conn.execute_query(
                """
                SELECT
                    COUNT(*) AS today_count,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS today_success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS today_failed,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS today_pending,
                    SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS today_running
                FROM publish_records
                WHERE status NOT IN ('deleted_pending', 'deleted_success')
                  AND created_at >= ?
                  AND created_at < ?
                """,
                [
                    today_start.isoformat(sep=" ", timespec="seconds"),
                    tomorrow_start.isoformat(sep=" ", timespec="seconds"),
                ],
            )
            rows = result[1] if isinstance(result, tuple) and len(result) > 1 else []
            row = rows[0] if rows else {}
            if hasattr(row, "get"):
                values = (
                    row.get("today_count", 0),
                    row.get("today_success", 0),
                    row.get("today_failed", 0),
                    row.get("today_pending", 0),
                    row.get("today_running", 0),
                )
            else:
                values = tuple(row[:5]) if row else (0, 0, 0, 0, 0)
            return {
                "today_count": int(values[0] or 0),
                "today_success": int(values[1] or 0),
                "today_failed": int(values[2] or 0),
                "today_pending": int(values[3] or 0),
                "today_running": int(values[4] or 0),
            }
        except Exception as e:
            self.handle_error(e, "aggregate_today_publish_counts")
            return {
                "today_count": 0,
                "today_success": 0,
                "today_failed": 0,
                "today_pending": 0,
                "today_running": 0,
            }

    @retry_on_locked()
    async def count_active_publish_by_status(self) -> Dict[str, int]:
        """有效发布记录按状态计数（排除回收站）。"""
        try:
            conn = Tortoise.get_connection("default")
            result = await conn.execute_query(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN status IN ('pending', 'running') THEN 1 ELSE 0 END) AS pending
                FROM publish_records
                WHERE status NOT IN ('deleted_pending', 'deleted_success')
                """,
            )
            rows = result[1] if isinstance(result, tuple) and len(result) > 1 else []
            row = rows[0] if rows else {}
            if hasattr(row, "get"):
                values = (
                    row.get("total", 0),
                    row.get("success", 0),
                    row.get("failed", 0),
                    row.get("pending", 0),
                )
            else:
                values = tuple(row[:4]) if row else (0, 0, 0, 0)
            return {
                "total": int(values[0] or 0),
                "success": int(values[1] or 0),
                "failed": int(values[2] or 0),
                "pending": int(values[3] or 0),
            }
        except Exception as e:
            self.handle_error(e, "count_active_publish_by_status")
            return {"total": 0, "success": 0, "failed": 0, "pending": 0}

    @retry_on_locked()
    async def count_finished_publish_since(self, since: datetime) -> Dict[str, int]:
        """自 since 起已完成（success+failed）记录数，用于近 7 天成功率。"""
        try:
            conn = Tortoise.get_connection("default")
            result = await conn.execute_query(
                """
                SELECT
                    COUNT(*) AS finished_total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS finished_success
                FROM publish_records
                WHERE status IN ('success', 'failed')
                  AND created_at >= ?
                """,
                [since.isoformat(sep=" ", timespec="seconds")],
            )
            rows = result[1] if isinstance(result, tuple) and len(result) > 1 else []
            row = rows[0] if rows else {}
            if hasattr(row, "get"):
                values = (
                    row.get("finished_total", 0),
                    row.get("finished_success", 0),
                )
            else:
                values = tuple(row[:2]) if row else (0, 0)
            return {
                "finished_total": int(values[0] or 0),
                "finished_success": int(values[1] or 0),
            }
        except Exception as e:
            self.handle_error(e, "count_finished_publish_since")
            return {"finished_total": 0, "finished_success": 0}

    @retry_on_locked()
    async def aggregate_daily_publish_trend(self, days: int = 14) -> List[Dict[str, Any]]:
        """近 N 天按日+状态聚合（SQL GROUP BY，供趋势图）。"""
        if days < 1:
            days = 14
        try:
            today = date.today()
            since_day = today - timedelta(days=days - 1)
            since_dt = datetime.combine(since_day, datetime.min.time())
            conn = Tortoise.get_connection("default")
            result = await conn.execute_query(
                """
                SELECT date(created_at) AS day, status, COUNT(*) AS cnt
                FROM publish_records
                WHERE status NOT IN ('deleted_pending', 'deleted_success')
                  AND created_at >= ?
                GROUP BY date(created_at), status
                """,
                [since_dt.isoformat(sep=" ", timespec="seconds")],
            )
            rows = result[1] if isinstance(result, tuple) and len(result) > 1 else []
            buckets: Dict[str, Dict[str, int]] = {}
            for i in range(days):
                d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
                buckets[d] = {"count": 0, "success": 0, "failed": 0}
            for row in rows or []:
                if not row or len(row) < 3:
                    continue
                day_key = str(row[0])[:10]
                status = str(row[1])
                try:
                    cnt = int(row[2])
                except (TypeError, ValueError):
                    cnt = 0
                if day_key not in buckets:
                    continue
                buckets[day_key]["count"] += cnt
                if status == "success":
                    buckets[day_key]["success"] += cnt
                elif status == "failed":
                    buckets[day_key]["failed"] += cnt
            return [{"date": d, **buckets[d]} for d in sorted(buckets.keys())]
        except Exception as e:
            self.handle_error(e, "aggregate_daily_publish_trend")
            return []

    @retry_on_locked()
    async def list_active_publish_rows_for_duplicate_check(
        self,
        user_id: int,
        *,
        file_types: Tuple[str, ...] = ("video", "image"),
        exclude_record_id: Optional[int] = None,
    ) -> List[Tuple[int, str, str, str, str]]:
        """列出待发布/进行中的发布任务，用于「同素材标识+同平台+同账号」去重。

        Returns:
            (record_id, file_path, platform, platform_username, file_type) 列表
        """
        if not file_types:
            return []
        try:
            records = await (
                PublishRecord.filter(
                    user_id=user_id,
                    status__in=["pending", "running"],
                    file_type__in=list(file_types),
                ).all()
            )
            out: List[Tuple[int, str, str, str, str]] = []
            for r in records:
                if exclude_record_id is not None and int(r.id) == int(exclude_record_id):
                    continue
                out.append(
                    (
                        int(r.id),
                        str(r.file_path or ""),
                        str(r.platform or ""),
                        str(r.platform_username or ""),
                        str(r.file_type or ""),
                    )
                )
            return out
        except Exception as e:
            self.handle_error(e, "list_active_publish_rows_for_duplicate_check")
            return []

    @retry_on_locked()
    async def get_active_file_paths_for_accounts(
        self,
        user_id: int,
        platform_account_ids: List[int],
    ) -> Set[str]:
        """查询指定账号在发布列表中待发布/进行中的 file_path 集合。

        用于素材自动匹配时排除已分配的视频，避免重复发布。

        Args:
            user_id: 用户 ID
            platform_account_ids: 平台账号 ID 列表

        Returns:
            file_path 字符串集合（规范化为 os.path.normpath）
        """
        import os
        if not platform_account_ids:
            return set()
        try:
            records = await PublishRecord.filter(
                user_id=user_id,
                platform_account_id__in=platform_account_ids,
                status__in=["pending", "running", "failed"],
            ).only("file_path").all()
            return {
                os.path.normpath(str(r.file_path))
                for r in records
                if r.file_path
            }
        except Exception as e:
            self.handle_error(e, "get_active_file_paths_for_accounts")
            return set()

    async def count_today_success(self, user_id: int) -> int:
        """统计指定用户当日已成功发布的条数（用于 daily_max_publish_count 校验）

        Args:
            user_id: 用户ID

        Returns:
            当日 status=success 的记录数
        """
        try:
            today = date.today()
            start = datetime.combine(today, datetime.min.time())
            end = start + timedelta(days=1)
            return await PublishRecord.filter(
                user_id=user_id,
                status="success",
                created_at__gte=start,
                created_at__lt=end,
            ).count()
        except Exception as e:
            self.handle_error(e, "count_today_success")
            return 0

    async def find_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """根据 ID 获取发布记录

        Args:
            record_id: 记录ID

        Returns:
            发布记录字典，不存在返回 None
        """
        record = await PublishRecord.get_or_none(id=record_id)
        if not record:
            return None
        data = self._to_dict(record)
        await self._attach_account_group_names([data])
        return data

    async def get_latest_publish_display_time_by_account_ids(self, account_ids: List[int]) -> Dict[int, str]:
        """按账号批量查询账号管理「已发布最晚时间」展示值。

        对已成功的任务：同一账号下取
        max(MAX(定时任务的 scheduled_publish_time), MAX(立即发布任务的 updated_at))，
        再格式化为 YYYY-MM-DD HH:mm。立即发布任务无定时字段，成功时刻由 update_status 写入 updated_at。
        """
        if not account_ids:
            return {}
        try:
            ids = sorted({int(x) for x in account_ids})
            sched_rows = await (
                PublishRecord.filter(
                    platform_account_id__in=ids,
                    status="success",
                    scheduled_publish_time__not_isnull=True,
                )
                .group_by("platform_account_id")
                .annotate(max_sched=Max("scheduled_publish_time"))
                .values("platform_account_id", "max_sched")
            )
            imm_rows = await (
                PublishRecord.filter(
                    platform_account_id__in=ids,
                    status="success",
                    scheduled_publish_time__isnull=True,
                )
                .group_by("platform_account_id")
                .annotate(max_imm=Max("updated_at"))
                .values("platform_account_id", "max_imm")
            )

            sched_by_acc: Dict[int, datetime] = {}
            for row in sched_rows:
                pid = row.get("platform_account_id")
                ms = row.get("max_sched")
                if pid is not None and ms is not None:
                    sched_by_acc[int(pid)] = ms

            imm_by_acc: Dict[int, datetime] = {}
            for row in imm_rows:
                pid = row.get("platform_account_id")
                mi = row.get("max_imm")
                if pid is not None and mi is not None:
                    imm_by_acc[int(pid)] = mi

            out: Dict[int, str] = {}
            for aid in set(sched_by_acc.keys()) | set(imm_by_acc.keys()):
                merged = merge_latest_publish_display_time(
                    sched_by_acc.get(aid),
                    imm_by_acc.get(aid),
                )
                if merged:
                    out[aid] = merged
            return out
        except Exception as e:
            self.handle_error(e, "get_latest_publish_display_time_by_account_ids")
            return {}

    async def _attach_account_group_names(self, records: List[Dict[str, Any]]) -> None:
        """按 platform_account_id 批量填充 account_group_name（当前账号所属组名）。"""
        if not records:
            return
        ids: Set[int] = set()
        for r in records:
            pid = r.get("platform_account_id")
            if pid is None:
                continue
            try:
                ids.add(int(pid))
            except (TypeError, ValueError):
                continue
        if not ids:
            for r in records:
                r["account_group_name"] = ""
            return
        accounts = await PlatformAccount.filter(id__in=list(ids)).select_related("group")
        id_to_name: Dict[int, str] = {}
        for a in accounts:
            group = getattr(a, "group", None)
            id_to_name[a.id] = (group.group_name or "") if group is not None else ""
        for r in records:
            pid = r.get("platform_account_id")
            try:
                pid_int = int(pid) if pid is not None else None
            except (TypeError, ValueError):
                pid_int = None
            if pid_int is None:
                r["account_group_name"] = ""
            else:
                r["account_group_name"] = id_to_name.get(pid_int, "")

    async def get_publish_risk_summary(self, days: int = 30) -> Dict[str, Any]:
        """Return local publish risk statistics grouped by account and platform."""
        try:
            since = datetime.now() - timedelta(days=max(1, int(days)))
            records = await PublishRecord.filter(created_at__gte=since).all()
            by_account: Dict[str, Dict[str, Any]] = {}
            by_platform: Dict[str, Dict[str, Any]] = {}

            def _bucket(container: Dict[str, Dict[str, Any]], key: str) -> Dict[str, Any]:
                if key not in container:
                    container[key] = {
                        "total": 0,
                        "success": 0,
                        "failed": 0,
                        "risk_count": 0,
                        "consecutive_failures": 0,
                        "last_risk_at": None,
                    }
                return container[key]

            sorted_records = sorted(records, key=lambda r: r.created_at or datetime.min)
            for record in sorted_records:
                platform = record.platform or ""
                account_key = f"{platform}:{record.platform_username or ''}"
                failure_kind = getattr(record, "failure_kind", None)
                risk_hit = is_blocking_failure_kind(failure_kind)
                event_time = record.updated_at or record.created_at
                for container, key in ((by_account, account_key), (by_platform, platform)):
                    item = _bucket(container, key)
                    item["total"] += 1
                    if record.status == "success":
                        item["success"] += 1
                        item["consecutive_failures"] = 0
                    elif record.status == "failed":
                        item["failed"] += 1
                        item["consecutive_failures"] += 1
                    if risk_hit:
                        item["risk_count"] += 1
                        item["last_risk_at"] = event_time.isoformat() if event_time else None

            return {"days": days, "by_account": by_account, "by_platform": by_platform}
        except Exception as e:
            self.handle_error(e, "get_publish_risk_summary")
            return {"days": days, "by_account": {}, "by_platform": {}}

    @staticmethod
    def _to_dict(record: PublishRecord) -> Dict[str, Any]:
        """将 ORM 模型实例转换为字典（兼容旧格式）"""
        return {
            "id": record.id,
            "user_id": record.user_id,
            "platform_username": record.platform_username,
            "platform": record.platform,
            "platform_account_id": getattr(record, "platform_account_id", None),
            # group_id：账号组ID，任务来源为 group 时应有此字段，旧数据为 None
            "group_id": getattr(record, "group_id", None),
            "file_path": record.file_path,
            "file_type": record.file_type,
            "title": record.title,
            "description": record.description,
            "tags": record.tags,
            "cover_path": record.cover_path,
            "poi_info": record.poi_info,
            "wechat_empty_location_open_picker": getattr(
                record, "wechat_empty_location_open_picker", None
            ),
            "micro_app_info": record.micro_app_info,
            "cart_info": record.cart_info,
            "anchor_info": record.anchor_info,
            "music_info": getattr(record, "music_info", None),
            "privacy_settings": record.privacy_settings,
            "scheduled_publish_time": format_schedule_time_st_str(record.scheduled_publish_time),
            "status": record.status,
            "error_message": record.error_message,
            "failure_kind": getattr(record, "failure_kind", None),
            "diagnostic_path": getattr(record, "diagnostic_path", None),
            "publish_url": record.publish_url,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "task_source": getattr(record, "task_source", None),
        }
