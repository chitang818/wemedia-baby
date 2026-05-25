"""
发布服务
文件路径：src/core/application/services/publish_service.py
功能：协调发布流程，使用发布管道执行发布
"""

from typing import List, Optional, Dict, Any
import logging

from src.infrastructure.common.di.service_locator import ServiceLocator, Scope
from src.infrastructure.common.pipeline.publish_pipeline import PublishPipeline, PublishRequest, PublishResult
from src.infrastructure.common.event.event_bus import EventBus
from src.domain import PublishTask

logger = logging.getLogger(__name__)


class PublishService:
    """发布服务 - 协调发布流程
    
    使用发布管道执行发布，发布事件到事件总线。
    """
    
    def __init__(
        self,
        pipeline: Optional[PublishPipeline] = None,
        event_bus: Optional[EventBus] = None
    ):
        """初始化发布服务
        
        Args:
            pipeline: 发布管道（可选，默认从ServiceLocator获取）
            event_bus: 事件总线（可选，默认从ServiceLocator获取）
        """
        self.service_locator = ServiceLocator()
        self.pipeline = pipeline or self.service_locator.get(PublishPipeline)
        self.event_bus = event_bus or self.service_locator.get(EventBus)
        self.logger = logging.getLogger(__name__)
    
    async def publish_single(
        self,
        user_id: int,
        account_name: str,
        platform: str,
        file_path: str,
        publish_type: str = "video",
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[str] = None,
        headless: bool = True,
        speed_rate: float = 1.0,
        pause_event: Any = None,
        cover_type: Optional[str] = None,
        cover_path: Optional[str] = None,
        scheduled_publish_time: Optional[Any] = None,
        privacy_settings: Optional[str] = None,
        close_browser_after: bool = True,
        poi_info: Optional[str] = None,
        wechat_empty_location_open_picker: Optional[bool] = None,
        cart_info: Optional[str] = None,
        anchor_info: Optional[str] = None,
        micro_app_info: Optional[str] = None,
        music_info: Optional[str] = None,
        publish_record_id: Optional[int] = None,
    ) -> PublishResult:
        """发布单个文件（异步）
        
        Args:
            user_id: 用户ID
            account_name: 账号名称
            platform: 平台名称
            file_path: 文件路径
            publish_type: 发布类型 (video 或 image)
            title: 标题（可选）
            description: 描述（可选）
            tags: 标签（可选）
            headless: 是否使用无头模式
            speed_rate: 发布速度倍率
            pause_event: 暂停控制事件
            close_browser_after: 发布完成后是否关闭浏览器（同账号连续发布时可 False 复用）
            poi_info, cart_info, anchor_info, micro_app_info: 扩展信息（如抖音「添加标签」；可选，透传至插件 metadata）
        
        Returns:
            发布结果
        """
        request = PublishRequest(
            user_id=user_id,
            account_name=account_name,
            platform=platform,
            file_path=file_path,
            publish_type=publish_type,
            title=title,
            description=description,
            tags=tags,
            headless=headless,
            speed_rate=speed_rate,
            pause_event=pause_event,
            cover_type=cover_type,
            cover_path=cover_path,
            scheduled_publish_time=scheduled_publish_time,
            privacy_settings=privacy_settings,
            close_browser_after=close_browser_after,
            poi_info=poi_info,
            wechat_empty_location_open_picker=wechat_empty_location_open_picker,
            cart_info=cart_info,
            anchor_info=anchor_info,
            micro_app_info=micro_app_info,
            music_info=music_info,
            publish_record_id=publish_record_id,
        )
        
        # 记录服务调用日志，明确输出发布类型是视频还是图文
        type_str = "图文" if publish_type == "image" else "视频"
        self.logger.info(f"执行 {platform} 平台的 {type_str}发布任务 (publish_type: {publish_type}) | 账号: {account_name} | 文件: {file_path}")

        # 发布开始事件
        from src.infrastructure.common.event.events import PublishStartedEvent
        await self.event_bus.publish(PublishStartedEvent(
            task_id=None,
            platform_username=account_name,
            platform=platform,
            file_path=file_path
        ))
        
        # 执行发布管道
        results = await self.pipeline.execute(request)
        result = results[0] if results else None
        
        if result:
            # 发布完成事件
            from src.infrastructure.common.event.events import PublishCompletedEvent
            await self.event_bus.publish(PublishCompletedEvent(
                task_id=None,
                platform_username=account_name,
                platform=platform,
                success=result.success,
                publish_url=result.publish_url,
                error_message=result.error_message
            ))
        
        return result
    
    async def publish_batch(
        self,
        requests: List[PublishRequest]
    ) -> List[PublishResult]:
        """批量发布（异步）
        
        Args:
            requests: 发布请求列表
        
        Returns:
            发布结果列表
        """
        # 执行批量发布管道
        results = await self.pipeline.execute_batch(requests)
        
        # 统计成功和失败数量
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count
        
        self.logger.info(f"批量发布完成: 总数={len(results)}, 成功={success_count}, 失败={failed_count}")
        
        return results
    
    async def resume_failed_tasks(
        self,
        user_id: int,
        platform: Optional[str] = None
    ) -> List[PublishResult]:
        """恢复失败的任务（异步）
        
        Args:
            user_id: 用户ID
            platform: 平台名称（可选）
        
        Returns:
            发布结果列表
        """
        return await self.pipeline.resume_failed_tasks(user_id, platform)

