"""
防抖和节流工具
文件路径：src/ui/utils/debounce_throttle.py
功能：提供防抖和节流装饰器，优化UI更新性能
"""

from typing import Callable, Any, Optional
from PySide6.QtCore import QTimer
import logging

logger = logging.getLogger(__name__)


def debounce(delay_ms: int = 300):
    """防抖装饰器
    
    在指定时间内，如果函数被多次调用，只执行最后一次调用。
    适用于搜索输入等场景。
    
    Args:
        delay_ms: 延迟时间（毫秒）
    
    Example:
        @debounce(300)
        def on_search_text_changed(text):
            # 搜索逻辑
            pass
    """
    def decorator(func: Callable) -> Callable:
        timer: Optional[QTimer] = None
        
        def wrapper(*args, **kwargs):
            nonlocal timer
            
            # 如果已有定时器，停止它
            if timer is not None:
                timer.stop()
            
            # 创建新的定时器
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: func(*args, **kwargs))
            timer.start(delay_ms)
        
        return wrapper
    return decorator


def throttle(delay_ms: int = 100):
    """节流装饰器
    
    在指定时间内，函数最多执行一次。
    适用于频繁触发的事件，如滚动、拖拽等。
    
    Args:
        delay_ms: 延迟时间（毫秒）
    
    Example:
        @throttle(100)
        def on_table_update():
            # 更新表格
            pass
    """
    def decorator(func: Callable) -> Callable:
        last_call_time = 0
        timer: Optional[QTimer] = None
        pending_args = None
        pending_kwargs = None
        
        def wrapper(*args, **kwargs):
            nonlocal last_call_time, timer, pending_args, pending_kwargs
            
            current_time = QTimer().remainingTime() if timer else 0
            elapsed = current_time - last_call_time if last_call_time > 0 else delay_ms
            
            if elapsed >= delay_ms:
                # 立即执行
                last_call_time = current_time
                func(*args, **kwargs)
                
                # 清除待执行的调用
                if timer:
                    timer.stop()
                    timer = None
                    pending_args = None
                    pending_kwargs = None
            else:
                # 保存参数，延迟执行
                pending_args = args
                pending_kwargs = kwargs
                
                if timer is None:
                    timer = QTimer()
                    timer.setSingleShot(True)
                    timer.timeout.connect(lambda: _execute_pending())
                    timer.start(delay_ms - elapsed)
        
        def _execute_pending():
            nonlocal last_call_time, timer, pending_args, pending_kwargs
            if pending_args is not None:
                last_call_time = QTimer().remainingTime() if timer else 0
                func(*pending_args, **pending_kwargs)
                timer = None
                pending_args = None
                pending_kwargs = None
        
        return wrapper
    return decorator


class Debouncer:
    """防抖器类 - 用于需要手动管理的防抖场景"""
    
    def __init__(self, delay_ms: int = 300, callback: Optional[Callable] = None):
        """初始化防抖器
        
        Args:
            delay_ms: 延迟时间（毫秒）
            callback: 回调函数
        """
        self.delay_ms = delay_ms
        self.callback = callback
        self.timer: Optional[QTimer] = None
    
    def call(self, *args, **kwargs):
        """调用函数（带防抖）
        
        Args:
            *args: 位置参数
            **kwargs: 关键字参数
        """
        if self.timer:
            self.timer.stop()
        
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        
        if self.callback:
            self.timer.timeout.connect(lambda: self.callback(*args, **kwargs))
        else:
            # 如果没有回调，保存参数供后续使用
            self._pending_args = args
            self._pending_kwargs = kwargs
        
        self.timer.start(self.delay_ms)
    
    def cancel(self):
        """取消待执行的调用"""
        if self.timer:
            self.timer.stop()
            self.timer = None


class Throttler:
    """节流器类 - 用于需要手动管理的节流场景"""
    
    def __init__(self, delay_ms: int = 100, callback: Optional[Callable] = None):
        """初始化节流器
        
        Args:
            delay_ms: 延迟时间（毫秒）
            callback: 回调函数
        """
        self.delay_ms = delay_ms
        self.callback = callback
        self.timer: Optional[QTimer] = None
        self.last_call_time = 0
        self.pending_args = None
        self.pending_kwargs = None
    
    def call(self, *args, **kwargs):
        """调用函数（带节流）
        
        Args:
            *args: 位置参数
            **kwargs: 关键字参数
        """
        from PySide6.QtCore import QElapsedTimer
        
        current_time = QElapsedTimer()
        current_time.start()
        elapsed = current_time.elapsed() - self.last_call_time if self.last_call_time > 0 else self.delay_ms
        
        if elapsed >= self.delay_ms:
            # 立即执行
            self.last_call_time = current_time.elapsed()
            if self.callback:
                self.callback(*args, **kwargs)
            
            # 清除待执行的调用
            if self.timer:
                self.timer.stop()
                self.timer = None
                self.pending_args = None
                self.pending_kwargs = None
        else:
            # 保存参数，延迟执行
            self.pending_args = args
            self.pending_kwargs = kwargs
            
            if self.timer is None:
                self.timer = QTimer()
                self.timer.setSingleShot(True)
                self.timer.timeout.connect(self._execute_pending)
                self.timer.start(self.delay_ms - elapsed)
    
    def _execute_pending(self):
        """执行待执行的调用"""
        from PySide6.QtCore import QElapsedTimer
        
        if self.pending_args is not None and self.callback:
            current_time = QElapsedTimer()
            current_time.start()
            self.last_call_time = current_time.elapsed()
            self.callback(*self.pending_args, **self.pending_kwargs)
            self.timer = None
            self.pending_args = None
            self.pending_kwargs = None
    
    def cancel(self):
        """取消待执行的调用"""
        if self.timer:
            self.timer.stop()
            self.timer = None
            self.pending_args = None
            self.pending_kwargs = None

