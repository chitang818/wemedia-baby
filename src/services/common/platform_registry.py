"""
[已废弃] 平台注册中心 — 旧版 PlatformAdapter 路由

当前所有平台发布由 PluginManager + PublishPluginInterface 体系管理。
register() 从未在项目中被调用，本模块为死代码。
保留文件仅供参考，后续版本将移除。
"""

from typing import Dict, List, Type, Any, Optional
import logging
from .platform_adapter import PlatformAdapter

logger = logging.getLogger(__name__)

class PlatformRegistry:
    """平台注册中心 (Singleton)"""
    
    _adapters: Dict[str, Type[PlatformAdapter]] = {}
    _configs: Dict[str, Any] = {}
    _display_names: Dict[str, str] = {}
    
    @classmethod
    def register(cls, platform_name: str, adapter_cls: Type[PlatformAdapter], display_name: str = None):
        """注册平台适配器
        
        Args:
            platform_name: 平台唯一标识 (如 'douyin')
            adapter_cls: 适配器类
            display_name: 显示名称 (如 '抖音')
        """
        cls._adapters[platform_name] = adapter_cls
        if display_name:
            cls._display_names[platform_name] = display_name
        logger.info(f"已注册平台适配器: {platform_name} ({display_name})")

    @classmethod
    def get_adapter(cls, platform_name: str) -> Optional[PlatformAdapter]:
        """获取平台适配器实例
        
        Args:
            platform_name: 平台唯一标识
            
        Returns:
            适配器实例，如果未注册则返回 None
        """
        adapter_cls = cls._adapters.get(platform_name)
        if not adapter_cls:
            logger.warning(f"未找到平台适配器: {platform_name}")
            return None
            
        try:
            return adapter_cls()
        except Exception as e:
            logger.error(f"实例化平台适配器失败: {platform_name}, 错误: {e}", exc_info=True)
            return None

    @classmethod
    def get_all_platforms(cls) -> List[str]:
        """获取所有已注册的平台标识"""
        return list(cls._adapters.keys())
        
    @classmethod
    def get_platform_display_name(cls, platform_name: str) -> str:
        """获取平台显示名称"""
        return cls._display_names.get(platform_name, platform_name)
    
    @classmethod
    def get_registered_platforms_info(cls) -> List[Dict[str, str]]:
        """获取所有已注册平台的信息列表"""
        return [
            {"id": pid, "name": cls.get_platform_display_name(pid)}
            for pid in cls._adapters.keys()
        ]
