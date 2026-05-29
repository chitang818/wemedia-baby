"""
媒体验证过滤器（异步版本）
文件路径：src/business/publish_pipeline/filters/media_validate_filter_async.py
功能：验证媒体文件有效性（异步）
"""

from src.infrastructure.common.pipeline.base_filter import BaseFilter, PublishContext
from src.services.common.media_validator import MediaValidator
from src.services.publish.pipeline.filters.media_validation_helpers import (
    validate_publish_media,
)
import logging

logger = logging.getLogger(__name__)


class MediaValidateFilterAsync(BaseFilter):
    """媒体验证过滤器（异步版本）"""
    
    def __init__(self, media_validator: MediaValidator):
        """初始化媒体验证过滤器
        
        Args:
            media_validator: 媒体验证器实例
        """
        super().__init__()
        self.media_validator = media_validator
    
    async def process(self, context: PublishContext) -> bool:
        """验证媒体文件（异步）
        
        Args:
            context: 发布上下文
        
        Returns:
            如果验证通过返回True，否则返回False
        """
        try:
            error = validate_publish_media(context, self.media_validator)
            if error:
                self.set_error(error)
                return False
            
            self.logger.info(f"媒体验证通过: {context.file_path}")
            return True
            
        except Exception as e:
            self.set_error(f"媒体验证失败: {str(e)}")
            self.logger.error(self.get_error(), exc_info=True)
            return False

