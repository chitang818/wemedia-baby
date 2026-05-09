"""
插件管理器
文件路径：src/infrastructure/plugins/plugin_manager.py
功能：管理插件的加载、注册、卸载等

重要更新 (2026-01-21):
    为兼容 Nuitka 打包，已废弃动态 importlib 加载方式。
    所有插件必须通过静态导入注册。

    平台规则与选择器数据为内置资源：见仓库根目录 config/platforms/、
    config/selectors/ 及清单 config/selectors_manifest.json（随安装包分发）。
"""

import importlib
import inspect
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Type, Any
import logging

from .plugin_interface import PluginInterface, PlatformPluginInterface, PublishPluginInterface

logger = logging.getLogger(__name__)


class PluginManager:
    """插件管理器 - 负责插件的加载和管理"""
    
    def __init__(self, plugin_dir: Optional[str] = None):
        """初始化插件管理器
        
        Args:
            plugin_dir: 插件目录路径，None 使用默认路径
        """
        if plugin_dir is None:
            plugin_dir = "plugins"
        
        self.plugin_dir = Path(plugin_dir)
        self.plugins: Dict[str, PluginInterface] = {}
        self.plugin_types: Dict[str, List[str]] = {
            "platform": [],
            "publish": [],
            "generic": []
        }
        self.logger = logging.getLogger(__name__)
        
        # 确保插件目录存在
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
    
    def load_plugin(self, plugin_path: str) -> bool:
        """加载插件
        
        ⚠️ 已废弃：此方法使用动态 importlib，不兼容 Nuitka 打包。
        请使用 load_builtin_plugins() 或手动注册插件。
        
        Args:
            plugin_path: 插件文件路径或模块路径
            
        Returns:
            是否加载成功
        """
        warnings.warn(
            "load_plugin() 已废弃，不兼容 Nuitka 打包。"
            "请使用 load_builtin_plugins() 或手动注册插件。",
            DeprecationWarning,
            stacklevel=2
        )
        
        try:
            # 如果是文件路径，转换为模块路径
            if plugin_path.endswith('.py'):
                # 从文件路径转换为模块路径
                plugin_path = plugin_path.replace('/', '.').replace('\\', '.').replace('.py', '')
            
            # 导入模块
            module = importlib.import_module(plugin_path)
            
            # 查找插件类（实现PluginInterface的类）
            plugin_class = None
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, PluginInterface) and 
                    obj is not PluginInterface and
                    obj is not PlatformPluginInterface and
                    obj is not PublishPluginInterface):
                    plugin_class = obj
                    break
            
            if plugin_class is None:
                self.logger.warning(f"模块中未找到插件类: {plugin_path}")
                return False
            
            # 实例化插件
            plugin = plugin_class()
            
            # 初始化插件
            if not plugin.initialize():
                self.logger.error(f"插件初始化失败: {plugin.name}")
                return False
            
            # 注册插件
            self.register_plugin(plugin)
            
            self.logger.info(f"插件加载成功: {plugin.name} v{plugin.version}")
            return True
            
        except Exception as e:
            self.logger.error(f"加载插件失败 {plugin_path}: {e}", exc_info=True)
            return False
    
    def register_plugin(self, plugin: PluginInterface):
        """注册插件
        
        Args:
            plugin: 插件实例
        """
        plugin_name = plugin.name
        
        # 检查是否已注册
        if plugin_name in self.plugins:
            self.logger.warning(f"插件已注册，将替换: {plugin_name}")
            self.unregister_plugin(plugin_name)
        
        # 注册插件
        self.plugins[plugin_name] = plugin
        
        # 按类型分类
        plugin_type = plugin.plugin_type
        if plugin_type not in self.plugin_types:
            self.plugin_types[plugin_type] = []
        
        if plugin_name not in self.plugin_types[plugin_type]:
            self.plugin_types[plugin_type].append(plugin_name)
        
        self.logger.debug(f"插件已注册: {plugin_name} (类型: {plugin_type})")
    
    def unregister_plugin(self, plugin_name: str) -> bool:
        """注销插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            是否成功注销
        """
        if plugin_name not in self.plugins:
            return False
        
        plugin = self.plugins[plugin_name]
        
        # 清理插件
        try:
            plugin.cleanup()
        except Exception as e:
            self.logger.error(f"清理插件失败 {plugin_name}: {e}")
        
        # 从类型列表中移除
        plugin_type = plugin.plugin_type
        if plugin_type in self.plugin_types:
            if plugin_name in self.plugin_types[plugin_type]:
                self.plugin_types[plugin_type].remove(plugin_name)
        
        # 从插件列表中移除
        del self.plugins[plugin_name]
        
        self.logger.info(f"插件已注销: {plugin_name}")
        return True
    
    def get_plugin(self, plugin_name: str) -> Optional[PluginInterface]:
        """获取插件
        
        Args:
            plugin_name: 插件名称
            
        Returns:
            插件实例，不存在返回None
        """
        return self.plugins.get(plugin_name)
    
    def get_plugins_by_type(self, plugin_type: str) -> List[PluginInterface]:
        """根据类型获取插件列表
        
        Args:
            plugin_type: 插件类型
            
        Returns:
            插件列表
        """
        plugin_names = self.plugin_types.get(plugin_type, [])
        return [self.plugins[name] for name in plugin_names if name in self.plugins]
    
    def get_all_plugins(self) -> List[PluginInterface]:
        """获取所有插件
        
        Returns:
            插件列表
        """
        return list(self.plugins.values())
    
    async def load_builtin_plugins(self):
        """加载内置插件（静态导入，兼容 Nuitka 打包）
        
        这是推荐的插件加载方式。所有支持的平台在此处静态导入。
        
        如需添加新平台，请：
        1. 在 builtin_plugins/ 目录下创建新的插件文件
        2. 在此方法中添加静态导入
        """
        try:
            # 静态导入内置插件（Nuitka 兼容）
            from .builtin_plugins import douyin_plugin, kuaishou_plugin
            
            # 加载抖音插件
            if hasattr(douyin_plugin, 'DouyinPlugin'):
                plugin = douyin_plugin.DouyinPlugin()
                if plugin.initialize():
                    self.register_plugin(plugin)
                    self.logger.info(f"抖音插件加载成功: {plugin.name} v{plugin.version}")
            
            # 加载快手插件（如果存在）
            if hasattr(kuaishou_plugin, 'KuaishouPlugin'):
                plugin = kuaishou_plugin.KuaishouPlugin()
                if plugin.initialize():
                    self.register_plugin(plugin)
                    self.logger.info(f"快手插件加载成功: {plugin.name} v{plugin.version}")
            
            self.logger.info(f"内置插件加载完成，共 {len(self.plugins)} 个插件")
        except Exception as e:
            self.logger.error(f"加载内置插件失败: {e}", exc_info=True)
    
    def load_plugins_from_directory(self, directory: Optional[str] = None):
        """从目录加载所有插件
        
        ⚠️ 已废弃：此方法使用动态 importlib，不兼容 Nuitka 打包。
        请使用 load_builtin_plugins() 或手动注册插件。
        
        Args:
            directory: 插件目录，None 使用默认目录
        """
        warnings.warn(
            "load_plugins_from_directory() 已废弃，不兼容 Nuitka 打包。"
            "请使用 load_builtin_plugins() 或手动注册插件。",
            DeprecationWarning,
            stacklevel=2
        )
        
        if directory is None:
            directory = self.plugin_dir
        else:
            directory = Path(directory)
        
        if not directory.exists():
            self.logger.warning(f"插件目录不存在: {directory}")
            return
        
        # 查找所有Python文件
        for plugin_file in directory.glob("*.py"):
            if plugin_file.name.startswith("__"):
                continue
            
            try:
                # 构建模块路径
                module_path = f"src.infrastructure.plugins.{plugin_file.stem}"
                self.load_plugin(module_path)
            except Exception as e:
                self.logger.error(f"加载插件文件失败 {plugin_file}: {e}")
    
    def shutdown(self):
        """关闭插件管理器，清理所有插件"""
        plugin_names = list(self.plugins.keys())
        for plugin_name in plugin_names:
            self.unregister_plugin(plugin_name)
        
        self.logger.info("插件管理器已关闭")

