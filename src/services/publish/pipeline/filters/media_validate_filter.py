"""
媒体验证过滤器
文件路径：src/business/publish_pipeline/filters/media_validate_filter.py
功能：验证媒体文件有效性
"""

from typing import Optional
from pathlib import Path
from .. import Filter, PublishContext
from src.services.common.media_validator import MediaValidator
import logging

logger = logging.getLogger(__name__)


class MediaValidateFilter(Filter):
    """媒体验证过滤器"""
    
    def __init__(self, media_validator: MediaValidator):
        """初始化媒体验证过滤器
        
        Args:
            media_validator: 媒体验证器实例
        """
        super().__init__()
        self.media_validator = media_validator
        self._error_message: Optional[str] = None
    
    def process(self, context: PublishContext) -> bool:
        """验证媒体文件
        
        Args:
            context: 发布上下文
            
        Returns:
            如果验证通过返回True，否则返回False
        """
        try:
            file_path = Path(context.file_path)
            
            # 检查文件是否存在
            if not file_path.exists():
                self._error_message = f"文件不存在: {context.file_path}"
                return False
            
            # 验证文件格式
            if not self.media_validator.validate_format(
                context.file_path,
                context.file_type,
                context.platform
            ):
                self._error_message = f"文件格式不支持: {context.file_path}"
                return False
            
            # 验证文件大小
            if not self.media_validator.validate_size(
                context.file_path,
                context.file_type,
                context.platform
            ):
                self._error_message = f"文件大小超出限制: {context.file_path}"
                return False
            
            self.logger.info(f"媒体验证通过: {context.file_path}")
            return True
            
        except Exception as e:
            self._error_message = f"媒体验证失败: {str(e)}"
            self.logger.error(self._error_message, exc_info=True)
            return False
    
    def get_error(self) -> Optional[str]:
        """获取错误信息"""
        return self._error_message

