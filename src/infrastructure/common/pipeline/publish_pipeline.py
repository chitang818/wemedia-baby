"""
发布管道模块（优化版）
文件路径：src/infrastructure/common/pipeline/publish_pipeline.py
功能：提供发布流程的管道-过滤器模式实现，支持并行执行、断点续传、动态过滤器
"""

import asyncio
import time
from typing import List, Optional, Type
import logging

from .base_filter import (
    BaseFilter,
    IPublishFilter,
    PublishRequest,
    PublishResponse,
    PipelineResult,
    PublishContext
)

# 向后兼容：旧代码 from ...publish_pipeline import PublishResult 仍可用
PublishResult = PipelineResult

logger = logging.getLogger(__name__)


class PublishPipeline:
    """发布管道 - 使用管道-过滤器模式执行发布流程（优化版）
    
    支持：
    - 并行执行（使用asyncio.Semaphore控制并发数）
    - 断点续传（从数据库恢复未完成任务）
    - 动态过滤器（执行前可插入过滤器）
    """
    
    def __init__(self, max_concurrent: int = 2, data_storage=None):
        """初始化发布管道
        
        Args:
            max_concurrent: 最大并发数（默认5）
            data_storage: 数据存储服务（可选，用于任务恢复）
        """
        self.filters: List[IPublishFilter] = []
        self.max_concurrent = max(1, min(2, int(max_concurrent or 2)))
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self.data_storage = data_storage  # 用于任务恢复
        self.logger = logging.getLogger(__name__)
    
    def add_filter(self, filter_instance: IPublishFilter) -> None:
        """添加过滤器
        
        Args:
            filter_instance: 过滤器实例
        """
        self.filters.append(filter_instance)
        self.logger.debug(f"添加过滤器: {type(filter_instance).__name__}")
    
    def remove_filter(self, filter_type: Type[IPublishFilter]) -> None:
        """移除过滤器
        
        Args:
            filter_type: 过滤器类型
        """
        self.filters = [f for f in self.filters if not isinstance(f, filter_type)]
        self.logger.debug(f"移除过滤器: {filter_type.__name__}")
    
    def insert_filter(
        self,
        filter_instance: IPublishFilter,
        position: int
    ) -> None:
        """在指定位置插入过滤器（动态过滤器）
        
        Args:
            filter_instance: 过滤器实例
            position: 插入位置
        """
        self.filters.insert(position, filter_instance)
        self.logger.debug(f"插入过滤器: {type(filter_instance).__name__} at position {position}")

    async def _run_failure_finalizers(
        self,
        context: PublishContext,
        failed_filter: IPublishFilter,
        start_index: int,
    ) -> None:
        """实际发布失败后继续执行记录类收尾过滤器，保留失败可观测性。"""
        if not getattr(failed_filter, "allow_failure_finalizers", False):
            return
        for finalizer in self.filters[start_index:]:
            if not getattr(finalizer, "run_after_failure", False):
                continue
            try:
                ok = await finalizer.process(context)
                if not ok:
                    self.logger.error(
                        "失败收尾过滤器处理失败: %s, 错误: %s",
                        type(finalizer).__name__,
                        finalizer.get_error(),
                    )
            except Exception as e:
                self.logger.error(
                    "失败收尾过滤器执行异常: %s, 错误: %s",
                    type(finalizer).__name__,
                    e,
                    exc_info=True,
                )
    
    async def execute(
        self,
        request: PublishRequest
    ) -> List[PipelineResult]:
        """执行发布管道（异步，支持并行执行）
        
        Args:
            request: 发布请求
        
        Returns:
            发布结果列表（支持批量发布，返回多个结果）
        """
        async with self.semaphore:
            start_time = time.time()
            context = PublishContext(
                user_id=request.user_id,
                account_name=request.account_name,
                platform=request.platform,
                file_path=request.file_path,
                publish_type=getattr(request, 'publish_type', 'video'),
                title=request.title,
                description=request.description,
                tags=request.tags,
                headless=request.headless,
                speed_rate=request.speed_rate,
                pause_event=request.pause_event,
                cover_type=getattr(request, 'cover_type', None),
                cover_path=getattr(request, 'cover_path', None),
                scheduled_publish_time=getattr(request, 'scheduled_publish_time', None),
                privacy_settings=getattr(request, 'privacy_settings', None),
                close_browser_after=getattr(request, 'close_browser_after', True),
                poi_info=getattr(request, 'poi_info', None),
                wechat_empty_location_open_picker=getattr(
                    request, "wechat_empty_location_open_picker", None
                ),
                cart_info=getattr(request, 'cart_info', None),
                anchor_info=getattr(request, 'anchor_info', None),
                micro_app_info=getattr(request, 'micro_app_info', None),
                music_info=getattr(request, 'music_info', None),
                publish_record_id=getattr(request, 'publish_record_id', None),
            )
            
            try:
                for index, filter_instance in enumerate(self.filters):
                    success = await filter_instance.process(context)
                    if not success:
                        error = filter_instance.get_error() or "过滤器处理失败"
                        context.error_message = error
                        self.logger.error(f"过滤器处理失败: {type(filter_instance).__name__}, 错误: {error}")
                        await self._run_failure_finalizers(
                            context,
                            filter_instance,
                            index + 1,
                        )
                        
                        return [PipelineResult(
                            success=False,
                            error_message=error,
                            diagnostic_path=getattr(context, "diagnostic_path", None),
                            failure_kind=getattr(context, "failure_kind", None),
                            execution_time=time.time() - start_time
                        )]
                
                execution_time = time.time() - start_time
                return [PipelineResult(
                    success=True,
                    publish_url=context.publish_url if hasattr(context, 'publish_url') else None,
                    diagnostic_path=getattr(context, "diagnostic_path", None),
                    failure_kind=None,
                    execution_time=execution_time
                )]
            
            except Exception as e:
                self.logger.error(f"发布管道执行失败: {e}", exc_info=True)
                return [PipelineResult(
                    success=False,
                    error_message=str(e),
                    failure_kind=None,
                    execution_time=time.time() - start_time
                )]
    
    async def execute_batch(
        self,
        requests: List[PublishRequest]
    ) -> List[PipelineResult]:
        """批量执行发布管道（异步，并行执行）
        
        Args:
            requests: 发布请求列表
        
        Returns:
            发布结果列表
        """
        tasks = [self.execute(request) for request in requests]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)
        
        results = []
        for result in results_list:
            if isinstance(result, Exception):
                results.append(PipelineResult(
                    success=False,
                    error_message=str(result)
                ))
            else:
                results.extend(result)
        
        return results
    
    async def resume_failed_tasks(
        self,
        user_id: int,
        platform: Optional[str] = None
    ) -> List[PipelineResult]:
        """恢复失败的任务（断点续传）
        
        Args:
            user_id: 用户ID
            platform: 平台名称（可选）
        
        Returns:
            发布结果列表
        """
        # 从数据库获取未完成的任务（status=pending或running）
        # 这里需要注入DataStorage依赖
        # 为了简化，这里只提供接口，具体实现需要注入依赖
        
        # 从数据库恢复未完成的任务
        self.logger.info(f"恢复失败任务: user_id={user_id}, platform={platform}")
        
        if not self.data_storage:
            self.logger.warning("未配置数据存储服务，无法恢复任务")
            return []
        
        try:
            # 从数据库获取未完成的发布记录（pending + running）。存储层接口按单 status 查询，故分两次调用；若后续存储支持 status_in 可合并为一次查询。
            pending_records = await self.data_storage.get_publish_records(
                user_id=user_id,
                platform=platform,
                status='pending',
                limit=100
            )
            running_records = await self.data_storage.get_publish_records(
                user_id=user_id,
                platform=platform,
                status='running',
                limit=100
            )
            # 合并未完成的任务
            failed_records = pending_records + running_records
            
            if not failed_records:
                self.logger.info("没有需要恢复的任务")
                return []
            
            self.logger.info(f"找到 {len(failed_records)} 个未完成的任务，开始恢复...")
            
            # 将数据库记录转换为 PublishRequest
            requests = []
            for record in failed_records:
                request = PublishRequest(
                    user_id=record.get('user_id'),
                    account_name=record.get('platform_username'),
                    platform=record.get('platform'),
                    file_path=record.get('file_path'),
                    title=record.get('title', ''),
                    description=record.get('description'),
                    tags=record.get('tags', '').split(',') if record.get('tags') else [],
                    headless=False,
                    speed_rate=1.0,
                    scheduled_publish_time=record.get('scheduled_publish_time'),
                    privacy_settings=record.get('privacy_settings'),
                    poi_info=record.get('poi_info'),
                    wechat_empty_location_open_picker=record.get(
                        'wechat_empty_location_open_picker'
                    ),
                    cart_info=record.get('cart_info'),
                    anchor_info=record.get('anchor_info'),
                    micro_app_info=record.get('micro_app_info'),
                    music_info=record.get('music_info'),
                )
                requests.append(request)
            
            # 批量执行恢复的任务
            results = await self.execute_batch(requests)
            
            self.logger.info(f"任务恢复完成，成功: {sum(1 for r in results if r.success)}, 失败: {sum(1 for r in results if not r.success)}")
            return results
            
        except Exception as e:
            self.logger.error(f"恢复任务失败: {e}", exc_info=True)
            return []
