"""
[已废弃] 旧版插件接口 — 请使用 src.plugins.core.interfaces 中的新版接口
文件路径：src/infrastructure/plugins/plugin_interface.py

新版异步发布接口：src.plugins.core.interfaces.publish_plugin.PublishPluginInterface
新版登录接口：src.plugins.core.interfaces.login_plugin.LoginPluginInterface

本文件仅为向后兼容保留，新插件请勿继承此处的类。
"""
import warnings as _warnings
_warnings.warn(
    "src.infrastructure.plugins.plugin_interface 已废弃，"
    "请使用 src.plugins.core.interfaces 中的新版异步接口",
    DeprecationWarning,
    stacklevel=2,
)

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class PluginInterface(ABC):
    """插件接口 - 所有插件必须实现此接口"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        pass
    
    @property
    @abstractmethod
    def version(self) -> str:
        """插件版本"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """插件描述"""
        pass
    
    @property
    @abstractmethod
    def author(self) -> str:
        """插件作者"""
        pass
    
    @property
    def plugin_type(self) -> str:
        """插件类型（platform/publish/account等）"""
        return "generic"
    
    def initialize(self, context: Optional[Dict[str, Any]] = None) -> bool:
        """初始化插件
        
        Args:
            context: 初始化上下文（可选）
            
        Returns:
            是否初始化成功
        """
        return True
    
    def cleanup(self):
        """清理插件资源"""
        pass
    
    def get_config(self) -> Dict[str, Any]:
        """获取插件配置
        
        Returns:
            配置字典
        """
        return {}
    
    def set_config(self, config: Dict[str, Any]):
        """设置插件配置
        
        Args:
            config: 配置字典
        """
        pass


class PlatformPluginInterface(PluginInterface):
    """平台插件接口 - 用于平台相关功能"""
    
    @property
    def plugin_type(self) -> str:
        return "platform"
    
    @abstractmethod
    def get_platform_name(self) -> str:
        """获取平台名称"""
        pass
    
    @abstractmethod
    def get_platform_url(self) -> str:
        """获取平台URL"""
        pass
    
    @abstractmethod
    def validate_login(self, cookies: Dict[str, Any]) -> bool:
        """验证登录状态
        
        Args:
            cookies: Cookie字典
            
        Returns:
            是否已登录
        """
        pass
    
    def extract_username(self, cookies: Dict[str, Any]) -> Optional[str]:
        """从Cookie提取用户名
        
        Args:
            cookies: Cookie字典
            
        Returns:
            用户名，提取失败返回None
        """
        return None


class PublishPluginInterface(PluginInterface):
    """发布插件接口 - 用于发布相关功能"""
    
    @property
    def plugin_type(self) -> str:
        return "publish"
    
    @abstractmethod
    def can_publish(self, file_path: str) -> bool:
        """检查是否可以发布文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否可以发布
        """
        pass
    
    @abstractmethod
    def publish(self, file_path: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """发布文件
        
        Args:
            file_path: 文件路径
            metadata: 元数据（标题、描述等）
            
        Returns:
            发布结果字典
        """
        pass

