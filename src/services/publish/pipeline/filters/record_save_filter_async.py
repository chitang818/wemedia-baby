"""
记录保存过滤器（异步版本）
文件路径：src/business/publish_pipeline/filters/record_save_filter_async.py
功能：保存发布记录到数据库（异步）
"""

from typing import Optional
from src.infrastructure.common.pipeline.base_filter import BaseFilter, PublishContext
from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
from src.infrastructure.common.di.service_locator import ServiceLocator
import logging

logger = logging.getLogger(__name__)


class RecordSaveFilterAsync(BaseFilter):
    """记录保存过滤器（异步版本）"""
    run_after_failure = True
    
    def __init__(self, publish_record_repository: Optional[PublishRecordRepositoryAsync] = None):
        """初始化记录保存过滤器
        
        Args:
            publish_record_repository: 异步发布记录仓储服务（可选，默认从ServiceLocator获取）
        """
        super().__init__()
        self.service_locator = ServiceLocator()
        self.publish_record_repo = publish_record_repository or self.service_locator.get(PublishRecordRepositoryAsync)
    
    async def process(self, context: PublishContext) -> bool:
        """保存发布记录（异步）
        
        Args:
            context: 发布上下文
        
        Returns:
            如果保存成功返回True，否则返回False
        """
        try:
            publish_url = getattr(context, 'publish_url', None)
            diagnostic_path = getattr(context, 'diagnostic_path', None)
            failure_kind = getattr(context, 'failure_kind', None)
            diagnostic_update = {}
            if diagnostic_path is not None:
                diagnostic_update["diagnostic_path"] = diagnostic_path
            existing_id = getattr(context, 'publish_record_id', None)
            if existing_id is not None:
                try:
                    record_id = int(existing_id)
                except (TypeError, ValueError):
                    record_id = None
            else:
                record_id = None

            if record_id is not None:
                if publish_url:
                    await self.publish_record_repo.update_status(
                        record_id=record_id,
                        status='success',
                        publish_url=publish_url,
                        **diagnostic_update,
                    )
                else:
                    error_message = (
                        getattr(context, 'error_message', None)
                        or self.get_error()
                        or "发布失败"
                    )
                    await self.publish_record_repo.update_status(
                        record_id=record_id,
                        status='failed',
                        error_message=error_message,
                        failure_kind=failure_kind,
                        **diagnostic_update,
                    )
                self.logger.info(f"发布记录已更新（待发布任务）: ID={record_id}")
                return True

            # 判断文件类型
            file_type = 'video'
            if context.file_path.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                file_type = 'image'

            platform_account_id = None
            acc = getattr(context, "account", None)
            if isinstance(acc, dict):
                aid = acc.get("id")
                if isinstance(aid, int):
                    platform_account_id = aid
                elif isinstance(aid, str) and aid.isdigit():
                    platform_account_id = int(aid)
            
            # 无既有记录时新建（如批量直发等未先入待发布列表的场景）
            record_id = await self.publish_record_repo.create(
                user_id=context.user_id,
                platform_username=context.account_name,
                platform=context.platform,
                file_path=context.file_path,
                file_type=file_type,
                title=context.title,
                description=context.description,
                tags=context.tags if hasattr(context, 'tags') else None,
                platform_account_id=platform_account_id,
                failure_kind=failure_kind,
            )
            
            if publish_url:
                await self.publish_record_repo.update_status(
                    record_id=record_id,
                    status='success',
                    publish_url=publish_url,
                    **diagnostic_update,
                )
            else:
                # 优先取管道级 context.error_message（由平台过滤器设置），其次取本过滤器自身错误
                error_message = getattr(context, 'error_message', None) or self.get_error() or "发布失败"
                await self.publish_record_repo.update_status(
                    record_id=record_id,
                    status='failed',
                    error_message=error_message,
                    failure_kind=failure_kind,
                    **diagnostic_update,
                )
            
            self.logger.info(f"发布记录保存成功: ID={record_id}")
            return True
            
        except Exception as e:
            self.set_error(f"保存发布记录失败: {str(e)}")
            self.logger.error(self.get_error(), exc_info=True)
            return False

