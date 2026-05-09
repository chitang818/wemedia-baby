"""
[已废弃] 平台发布过滤器（同步版本）— 基于旧版 PlatformAdapter 的死代码
当前所有平台发布由 PublishExecutor + PluginManager 完成，此文件不再被使用。
"""

from typing import Optional
from .. import Filter, PublishContext
from src.services.common.platform_adapter import PlatformAdapter, DouyinAdapter
import logging

logger = logging.getLogger(__name__)


class PlatformAdapterFactory:
    """平台适配器工厂"""
    
    @staticmethod
    def create_adapter(platform: str) -> Optional[PlatformAdapter]:
        """创建平台适配器
        
        Args:
            platform: 平台名称
            
        Returns:
            平台适配器实例，如果不支持返回None
        """
        if platform == 'douyin':
            return DouyinAdapter()
        # 其他平台适配器（Phase 7 实现）
        # elif platform == 'kuaishou':
        #     return KuaishouAdapter()
        # elif platform == 'xiaohongshu':
        #     return XiaohongshuAdapter()
        else:
            logger.warning(f"不支持的平台: {platform}")
            return None


class PlatformPublishFilter(Filter):
    """平台发布过滤器"""
    
    def __init__(self, adapter_factory: Optional[PlatformAdapterFactory] = None):
        """初始化平台发布过滤器
        
        Args:
            adapter_factory: 平台适配器工厂（可选，默认使用PlatformAdapterFactory）
        """
        super().__init__()
        self.adapter_factory = adapter_factory or PlatformAdapterFactory()
        self._error_message: Optional[str] = None
    
    def process(self, context: PublishContext) -> bool:
        """执行发布操作
        
        Args:
            context: 发布上下文
            
        Returns:
            如果发布成功返回True，否则返回False
        """
        try:
            # 获取平台适配器
            adapter = self.adapter_factory.create_adapter(context.platform)
            
            if not adapter:
                self._error_message = f"不支持的平台: {context.platform}"
                return False
            
            publish_type = getattr(context, 'publish_type', 'video')

            # 执行发布
            if publish_type == 'video':
                result = adapter.publish_video(
                    browser=context.browser,
                    cookie_data=context.cookie_data,
                    file_path=context.file_path,
                    title=context.title,
                    description=context.description,
                    tags=context.tags
                )
            elif publish_type == 'image':
                # 图片发布需要路径列表
                image_paths = [context.file_path]  # 单个图片转为列表
                result = adapter.publish_image(
                    browser=context.browser,
                    cookie_data=context.cookie_data,
                    image_paths=image_paths,
                    title=context.title,
                    description=context.description,
                    tags=context.tags
                )
            else:
                self._error_message = f"不支持的发布类型: {publish_type}"
                return False
            
            if result.get('success'):
                context.publish_url = result.get('publish_url')
                self.logger.info(f"发布成功: {context.publish_url}")
                return True
            else:
                self._error_message = result.get('error_message', '发布失败')
                return False
                
        except Exception as e:
            self._error_message = f"发布操作异常: {str(e)}"
            self.logger.error(self._error_message, exc_info=True)
            return False
    
    def get_error(self) -> Optional[str]:
        """获取错误信息"""
        return self._error_message

