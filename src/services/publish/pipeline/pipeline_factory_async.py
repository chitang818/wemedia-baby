"""
发布管道工厂（异步版本）
文件路径：src/business/publish_pipeline/pipeline_factory_async.py
功能：创建配置好的发布管道（异步版本）
"""

from typing import Optional
from src.infrastructure.common.pipeline.publish_pipeline import PublishPipeline
from src.infrastructure.common.di.service_locator import ServiceLocator
from src.services.publish.pipeline.filters.permission_check_filter_async import PermissionCheckFilterAsync
from src.services.publish.pipeline.filters.media_validate_filter_async import MediaValidateFilterAsync
from src.services.publish.pipeline.filters.account_load_filter_async import AccountLoadFilterAsync
from src.infrastructure.common.pipeline.filters.execution_filter import PublishExecutionFilter
from src.services.publish.pipeline.filters.record_save_filter_async import RecordSaveFilterAsync
from src.services.account.account_manager_async import AccountManagerAsync
from src.services.common.media_validator import MediaValidator
from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
import logging

logger = logging.getLogger(__name__)


class PipelineFactoryAsync:
    """发布管道工厂（异步版本）"""
    
    @staticmethod
    async def create_pipeline(
        user_id: int,
        account_manager: Optional[AccountManagerAsync] = None,
        permission_controller: Optional[object] = None,
        media_validator: Optional[MediaValidator] = None
    ) -> PublishPipeline:
        """创建配置好的发布管道（异步）
        
        Args:
            user_id: 用户ID
            account_manager: 账号管理器（可选，默认从ServiceLocator获取）
            permission_controller: 权限控制器（可选，默认从ServiceLocator获取）
            media_validator: 媒体验证器（可选，默认创建）
        
        Returns:
            配置好的发布管道实例
        """
        pipeline = PublishPipeline(max_concurrent=3)
        service_locator = ServiceLocator()
        
        # 获取所需服务
        if account_manager is None:
            from src.infrastructure.common.event.event_bus import EventBus
            event_bus = service_locator.get(EventBus)
            
            # AccountManagerAsync 已迁移为 Repository 模式
            account_manager = AccountManagerAsync(
                user_id=user_id,
                event_bus=event_bus
            )
        
        if permission_controller is None:
            # 闭源订阅模块可能不存在（开源版），此时 permission_controller 传 None，
            # PermissionCheckFilterAsync 会自动跳过订阅/云端校验。
            try:
                from src.services.subscription.permission_controller_async import (
                    PermissionControllerAsync as PermissionController,
                )
                permission_controller = PermissionController()
            except Exception:
                permission_controller = None
        
        if media_validator is None:
            media_validator = MediaValidator()

        publish_record_repo = service_locator.get_optional(PublishRecordRepositoryAsync)
        if publish_record_repo is None:
            publish_record_repo = PublishRecordRepositoryAsync()
        
        # 添加过滤器（按顺序）
        pipeline.add_filter(PermissionCheckFilterAsync(permission_controller))
        pipeline.add_filter(MediaValidateFilterAsync(media_validator))
        pipeline.add_filter(AccountLoadFilterAsync(account_manager))
        pipeline.add_filter(PublishExecutionFilter())
        pipeline.add_filter(RecordSaveFilterAsync(publish_record_repo))
        
        logger.info("发布管道创建成功，已注册5个过滤器（异步版本）")
        return pipeline

