"""
依赖注入模块
提供服务定位器和作用域管理
"""

from .service_locator import ServiceLocator, ServiceNotFoundError, Scope
from .scopes import Scope as ScopeEnum

__all__ = ['ServiceLocator', 'ServiceNotFoundError', 'Scope', 'ScopeEnum']

