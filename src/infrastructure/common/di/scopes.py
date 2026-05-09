"""
作用域定义
文件路径：src/core/common/di/scopes.py
功能：定义服务作用域枚举
"""

from enum import Enum


class Scope(Enum):
    """服务作用域枚举
    
    定义服务的生命周期管理方式：
    - SINGLETON: 整个应用生命周期唯一实例
    - PROTOTYPE: 每次获取都新建实例
    - REQUEST: 在一次请求上下文中唯一（可模拟）
    """
    
    SINGLETON = "singleton"  # 整个应用生命周期唯一
    PROTOTYPE = "prototype"  # 每次获取都新建实例
    REQUEST = "request"      # 在一次请求上下文中唯一（可模拟）

