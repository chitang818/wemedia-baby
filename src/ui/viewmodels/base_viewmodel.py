"""
基础视图模型
文件路径：src/ui/viewmodels/base_viewmodel.py
功能：提供视图模型基类，支持数据绑定和信号机制
"""

from typing import Any, Optional
from PySide6.QtCore import QObject, Signal, Property
import logging

from ...core.common.di.service_locator import ServiceLocator

logger = logging.getLogger(__name__)


class BaseViewModel(QObject):
    """基础视图模型类
    
    所有视图模型都应继承此类，提供：
    - 信号机制支持
    - 服务定位器访问
    - 统一的错误处理
    """
    
    # 通用信号
    errorOccurred = Signal(str)  # 错误信号
    loadingChanged = Signal(bool)  # 加载状态变化信号
    
    def __init__(self, parent: Optional[QObject] = None):
        """初始化视图模型
        
        Args:
            parent: 父对象
        """
        super().__init__(parent)
        self._loading = False
        self._service_locator = ServiceLocator()
    
    @Property(bool, notify=loadingChanged)
    def loading(self) -> bool:
        """加载状态"""
        return self._loading
    
    def set_loading(self, value: bool):
        """设置加载状态"""
        if self._loading != value:
            self._loading = value
            self.loadingChanged.emit(value)
    
    def get_service(self, service_type: type) -> Any:
        """获取服务
        
        Args:
            service_type: 服务类型
            
        Returns:
            服务实例
        """
        try:
            return self._service_locator.get(service_type)
        except Exception as e:
            logger.error(f"获取服务失败: {service_type}, 错误: {e}")
            self.errorOccurred.emit(f"获取服务失败: {str(e)}")
            return None
    
    def handle_error(self, error: Exception, context: str = ""):
        """统一错误处理
        
        Args:
            error: 异常对象
            context: 上下文信息
        """
        error_msg = f"{context}: {str(error)}" if context else str(error)
        logger.error(error_msg, exc_info=error)
        self.errorOccurred.emit(error_msg)

