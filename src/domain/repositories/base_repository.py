"""
基础 Repository
文件路径：src/business/repositories/base_repository.py
功能：提供 Repository 基类，定义通用数据访问接口
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class BaseRepository(ABC):
    """Repository 基类
    
    所有 Repository 都应继承此类，提供：
    - 统一的数据访问接口
    - 错误处理
    - 日志记录
    """
    
    def __init__(self, data_storage):
        """初始化 Repository
        
        Args:
            data_storage: 数据存储服务实例
        """
        self.data_storage = data_storage
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def handle_error(self, error: Exception, operation: str):
        """统一错误处理
        
        Args:
            error: 异常对象
            operation: 操作名称
        """
        error_msg = f"{self.__class__.__name__}.{operation} 失败: {str(error)}"
        self.logger.error(error_msg, exc_info=error)
        raise

