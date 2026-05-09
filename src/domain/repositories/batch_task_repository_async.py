"""
批量任务 Repository（异步版本）- 基于 Tortoise ORM
功能：封装批量任务相关的数据访问操作
"""

from typing import Optional, List, Dict, Any
import logging
from datetime import datetime

from .base_repository_async import BaseRepositoryAsync
from src.infrastructure.storage.orm_models.batch_task import BatchTask
from src.infrastructure.storage.retry import retry_on_locked

logger = logging.getLogger(__name__)


class BatchTaskRepositoryAsync(BaseRepositoryAsync):
    """批量任务 Repository（异步版本）- 基于 Tortoise ORM

    封装 batch_tasks 表的所有数据访问操作。
    """

    model_class = BatchTask

    @retry_on_locked()
    async def create(
        self,
        user_id: int,
        task_name: str,
        platform_username: str,
        platform: str,
        task_type: str,
        script_config: str,
        video_count: int,
        task_description: Optional[str] = None,
        priority: int = 0,
        retry_count: int = 3,
        delay_seconds: int = 5,
        max_concurrent: int = 1,
    ) -> int:
        """创建批量任务

        Args:
            user_id ~ max_concurrent: 任务配置字段

        Returns:
            新创建的任务ID
        """
        try:
            task = await BatchTask.create(
                user_id=user_id,
                task_name=task_name,
                task_description=task_description,
                platform_username=platform_username,
                platform=platform,
                task_type=task_type,
                script_config=script_config,
                video_count=video_count,
                status="pending",
                priority=priority,
                retry_count=retry_count,
                delay_seconds=delay_seconds,
                max_concurrent=max_concurrent,
            )
            self.logger.info(
                f"创建批量任务成功: {task_name}, 平台: {platform}, ID: {task.id}"
            )
            return task.id
        except Exception as e:
            self.handle_error(e, "create")
            raise

    async def find_tasks(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取批量任务列表

        Args:
            user_id: 用户ID
            status: 任务状态（可选）
            limit: 返回数量限制

        Returns:
            任务列表
        """
        try:
            filters = {"user_id": user_id}
            if status:
                filters["status"] = status
            tasks = await (
                BatchTask.filter(**filters)
                .order_by("-created_at")
                .limit(limit)
                .all()
            )
            return [self._to_dict(t) for t in tasks]
        except Exception as e:
            self.handle_error(e, "find_tasks")
            return []

    async def find_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取批量任务"""
        task = await BatchTask.get_or_none(id=task_id)
        return self._to_dict(task) if task else None

    @retry_on_locked()
    async def update_status(
        self,
        task_id: int,
        status: str,
        completed_count: Optional[int] = None,
        failed_count: Optional[int] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> bool:
        """更新批量任务状态

        Args:
            task_id: 任务ID
            status: 任务状态
            completed_count ~ end_time: 可选的更新字段

        Returns:
            更新是否成功
        """
        try:
            update_data = {
                "status": status,
                "updated_at": datetime.now(),
            }
            if completed_count is not None:
                update_data["completed_count"] = completed_count
            if failed_count is not None:
                update_data["failed_count"] = failed_count
            if start_time is not None:
                update_data["start_time"] = start_time
            if end_time is not None:
                update_data["end_time"] = end_time

            updated = await BatchTask.filter(id=task_id).update(**update_data)
            return updated > 0
        except Exception as e:
            self.handle_error(e, "update_status")
            return False

    @staticmethod
    def _to_dict(task: BatchTask) -> Dict[str, Any]:
        """将 ORM 模型实例转换为字典（兼容旧格式）"""
        return {
            "id": task.id,
            "user_id": task.user_id,
            "task_name": task.task_name,
            "task_description": task.task_description,
            "platform_username": task.platform_username,
            "platform": task.platform,
            "task_type": task.task_type,
            "script_config": task.script_config,
            "video_count": task.video_count,
            "status": task.status,
            "completed_count": task.completed_count,
            "failed_count": task.failed_count,
            "start_time": task.start_time.isoformat() if task.start_time else None,
            "end_time": task.end_time.isoformat() if task.end_time else None,
            "priority": task.priority,
            "retry_count": task.retry_count,
            "delay_seconds": task.delay_seconds,
            "max_concurrent": task.max_concurrent,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }
