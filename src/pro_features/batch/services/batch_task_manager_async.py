from typing import List, Optional, Dict, Any
import logging
import json
from datetime import datetime

from src.domain.repositories.batch_task_repository_async import BatchTaskRepositoryAsync
from src.infrastructure.common.event.event_bus import EventBus
from src.infrastructure.common.event.events import BatchTaskStartedEvent, BatchTaskCompletedEvent
from src.infrastructure.common.di.service_locator import ServiceLocator
from src.utils.date_utils import get_current_datetime_str

logger = logging.getLogger(__name__)


class BatchTaskManagerAsync:
    """批量任务管理器（异步版本）"""
    
    def __init__(
        self,
        user_id: int,
        batch_task_repository: Optional[BatchTaskRepositoryAsync] = None,
        event_bus: Optional[EventBus] = None
    ):
        """
        初始化批量任务管理器。
        
        Args:
            user_id: 用户ID
            batch_task_repository: 批量任务数据仓库（可选，默认从服务定位器获取）
            event_bus: 事件总线（可选，默认从服务定位器获取）
        """
        self.user_id = user_id
        self.service_locator = ServiceLocator()
        self.batch_task_repo = batch_task_repository or self.service_locator.get(BatchTaskRepositoryAsync)
        self.event_bus = event_bus or self.service_locator.get(EventBus)
        self.logger = logging.getLogger(__name__)
    
    async def create_task(
        self,
        task_name: str,
        account_name: str,
        platform: str,
        task_type: str,
        script_config: Dict[str, Any],
        video_count: int,
        task_description: Optional[str] = None,
        retry_count: int = 3,
        delay_seconds: int = 5,
        max_concurrent: int = 1,
        priority: int = 0
    ) -> int:
        """创建批量发布任务。
        
        Args:
            task_name: 任务名称
            account_name: 账号名称
            platform: 发布平台
            task_type: 任务类型
            script_config: 发布脚本配置（字典格式）
            video_count: 视频数量
            task_description: 任务描述（可选）
            retry_count: 失败重试次数，默认3次
            delay_seconds: 任务间延迟秒数，默认5秒
            max_concurrent: 最大并发数，默认1
            priority: 优先级，数值越大越优先
        
        Returns:
            新创建任务的ID
        """
        # 将脚本配置序列化为JSON
        script_config_json = json.dumps(script_config, ensure_ascii=False)
        
        # 创建批量任务记录
        task_id = await self.batch_task_repo.create(
            user_id=self.user_id,
            task_name=task_name,
            platform_username=account_name,
            platform=platform,
            task_type=task_type,
            script_config=script_config_json,
            video_count=video_count,
            task_description=task_description,
            priority=priority,
            retry_count=retry_count,
            delay_seconds=delay_seconds,
            max_concurrent=max_concurrent
        )
        
        self.logger.info(
            f"[批量任务] 创建成功: task_id={task_id}, 任务名={task_name}, 平台={platform}"
        )
        
        # 发布任务开始事件
        if self.event_bus:
            event = BatchTaskStartedEvent(
                task_id=task_id,
                task_name=task_name,
                platform=platform
            )
            await self.event_bus.publish(event)
        
        return task_id
    
    async def get_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取批量任务列表。
        
        Args:
            status: 任务状态过滤（可选）
            limit: 最大返回数量，默认100
        
        Returns:
            任务字典列表
        """
        tasks = await self.batch_task_repo.find_tasks(
            user_id=self.user_id,
            status=status,
            limit=limit
        )
        return tasks
    
    async def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """根据ID查询批量任务详情。
        
        Args:
            task_id: 任务ID
        
        Returns:
            任务字典，若不存在则返回 None
        """
        # 根据ID从仓库查询任务
        task = await self.batch_task_repo.find_by_id(task_id)
        return task
    
    async def update_task_status(
        self,
        task_id: int,
        status: str,
        completed_count: Optional[int] = None,
        failed_count: Optional[int] = None
    ) -> bool:
        """更新批量任务状态。
        
        Args:
            task_id: 任务ID
            status: 新状态（pending/running/completed/failed/cancelled）
            completed_count: 已完成数量（可选）
            failed_count: 失败数量（可选）
        
        Returns:
            更新成功返回 True，失败返回 False
        """
        # 构建更新参数
        update_params = {
            "task_id": task_id,
            "status": status
        }
        
        if completed_count is not None:
            update_params["completed_count"] = completed_count
        
        if failed_count is not None:
            update_params["failed_count"] = failed_count
        
        # 任务开始时记录开始时间
        if status == "running":
            update_params["start_time"] = datetime.now().isoformat()
        
        # 任务结束时记录结束时间
        if status in ["completed", "failed", "cancelled"]:
            update_params["end_time"] = datetime.now().isoformat()
        
        success = await self.batch_task_repo.update_status(**update_params)
        
        if success:
            self.logger.info(
                f"[批量任务] 状态更新: task_id={task_id}, status={status}, "
                f"完成数={completed_count}, 失败数={failed_count}"
            )
            
            # 任务完成时发布完成事件
            if status == "completed" and self.event_bus:
                task = await self.get_task_by_id(task_id)
                if task:
                    event = BatchTaskCompletedEvent(
                        task_id=task_id,
                        task_name=task["task_name"],
                        platform=task["platform"],
                        completed_count=completed_count or 0,
                        failed_count=failed_count or 0
                    )
                    await self.event_bus.publish(event)
        
        return success

    def shutdown(self) -> None:
        """关闭批量任务管理器，释放相关资源。"""
        self.logger.info("[批量任务管理器] 正在关闭...")
