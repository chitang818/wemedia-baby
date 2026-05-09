"""
通用装饰器模块
文件路径：src/core/common/decorators.py
功能：提供重试、熔断、异常捕获等通用装饰器
"""

import logging
import functools
import asyncio
from typing import Callable, Any, Type, Union, Tuple

try:
    from tenacity import (
        retry, stop_after_attempt, wait_exponential, 
        retry_if_exception_type, before_sleep_log
    )
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    # 简单的重试占位符
    def retry(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def stop_after_attempt(n): pass
    def wait_exponential(**kwargs): pass
    def retry_if_exception_type(*args): pass
    def before_sleep_log(*args): pass

logger = logging.getLogger(__name__)

def safe_execute(
    error_return: Any = None,
    log_error: bool = True,
    error_msg: str = "执行失败"
) -> Callable:
    """安全执行装饰器 - 捕获所有异常并返回默认值
    
    Args:
        error_return: 发生异常时的返回值
        log_error: 是否记录错误日志
        error_msg: 错误日志前缀
        
    Returns:
        装饰器函数
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    logger.error(f"{error_msg}: {e}", exc_info=True)
                return error_return
                
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    logger.error(f"{error_msg}: {e}", exc_info=True)
                return error_return
                
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator

class ServiceException(Exception):
    """服务异常基类"""
    pass

def with_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0, 
    max_delay: float = 10.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = (Exception,)
) -> Callable:
    """重试装饰器 (封装 tenacity)
    
    Args:
        max_attempts: 最大尝试次数
        initial_delay: 初始延迟 (秒)
        max_delay: 最大延迟 (秒)
        exceptions: 需要重试的异常类型
        
    Returns:
        装饰器函数
    """
    if TENACITY_AVAILABLE:
        return retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=initial_delay, max=max_delay),
            retry=retry_if_exception_type(exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True
        )
    else:
        # 如果 tenacity 不可用，使用简单的重试逻辑
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                last_err = None
                delay = initial_delay
                for i in range(max_attempts):
                    try:
                        return await func(*args, **kwargs)
                    except exceptions as e:
                        last_err = e
                        logger.warning(
                            f"执行失败 (尝试 {i+1}/{max_attempts}): {e}. "
                            f"等待 {delay}秒后重试..."
                        )
                        if i < max_attempts - 1:
                            await asyncio.sleep(delay)
                            delay = min(delay * 2, max_delay)
                raise last_err

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                import time
                last_err = None
                delay = initial_delay
                for i in range(max_attempts):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_err = e
                        logger.warning(
                            f"执行失败 (尝试 {i+1}/{max_attempts}): {e}. "
                            f"等待 {delay}秒后重试..."
                        )
                        if i < max_attempts - 1:
                            time.sleep(delay)
                            delay = min(delay * 2, max_delay)
                raise last_err
                
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        return decorator
