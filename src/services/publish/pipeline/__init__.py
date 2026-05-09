"""
发布管道模块
文件路径：src/business/publish_pipeline/__init__.py
功能：实现管道-过滤器模式的发布流程
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PublishContext:
    """发布上下文 - 在管道中传递的数据"""
    user_id: int
    account_name: str
    platform: str
    file_path: str
    file_type: str  # video/image
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    account_data: Optional[Dict[str, Any]] = None
    cookie_data: Optional[Dict[str, Any]] = None
    browser: Optional[Any] = None
    error_message: Optional[str] = None
    publish_url: Optional[str] = None
    success: bool = False


class Filter(ABC):
    """过滤器基类"""
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def process(self, context: PublishContext) -> bool:
        """处理上下文
        
        Args:
            context: 发布上下文
        
        Returns:
            bool: 如果处理成功返回True，否则返回False
        """
        pass
    
    def get_error(self) -> Optional[str]:
        """获取错误信息
        
        Returns:
            错误信息，如果没有错误返回None
        """
        return None


class PublishPipeline:
    """发布管道 - 串联多个过滤器执行发布流程"""
    
    def __init__(self):
        """初始化发布管道"""
        self.filters: List[Filter] = []
        self.logger = logging.getLogger(__name__)
    
    def add_filter(self, filter_instance: Filter) -> None:
        """添加过滤器
        
        Args:
            filter_instance: 过滤器实例
        """
        self.filters.append(filter_instance)
        self.logger.debug(f"添加过滤器: {filter_instance.__class__.__name__}")
    
    def execute(self, context: PublishContext) -> bool:
        """执行发布流程
        
        Args:
            context: 发布上下文
        
        Returns:
            如果发布成功返回True，否则返回False
        """
        self.logger.info(
            f"开始执行发布流程: 账号={context.account_name}, "
            f"平台={context.platform}, 文件={context.file_path}"
        )
        
        # 依次执行每个过滤器
        for filter_instance in self.filters:
            try:
                if not filter_instance.process(context):
                    error = filter_instance.get_error()
                    context.error_message = error or "过滤器处理失败"
                    context.success = False
                    self.logger.error(
                        f"过滤器处理失败: {filter_instance.__class__.__name__}, "
                        f"错误: {context.error_message}"
                    )
                    return False
            except Exception as e:
                context.error_message = f"过滤器执行异常: {str(e)}"
                context.success = False
                self.logger.error(
                    f"过滤器执行异常: {filter_instance.__class__.__name__}, "
                    f"错误: {e}",
                    exc_info=True
                )
                return False
        
        # 所有过滤器执行成功
        context.success = True
        self.logger.info(
            f"发布流程执行成功: 账号={context.account_name}, "
            f"平台={context.platform}"
        )
        return True

__all__ = ['PublishContext', 'Filter', 'PublishPipeline']

