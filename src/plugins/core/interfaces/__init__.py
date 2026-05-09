"""
插件接口定义模块
"""
from .login_plugin import LoginPluginInterface, LoginResult
from .publish_plugin import PublishPluginInterface, PublishResult, FormField

__all__ = [
    'LoginPluginInterface', 
    'LoginResult',
    'PublishPluginInterface',
    'PublishResult', 
    'FormField'
]
