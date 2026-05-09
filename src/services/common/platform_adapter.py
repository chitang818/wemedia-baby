"""
[已废弃] 平台适配器模块 — 旧版发布接口

当前所有平台发布已迁移至 src.plugins.core.interfaces.publish_plugin.PublishPluginInterface。
PlatformRegistry 中无任何注册的适配器，此接口不再被实际调用。
保留文件仅供参考，后续版本将移除。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class PlatformAdapter(ABC):
    """平台适配器基类"""
    
    def __init__(self, platform_name: str):
        """初始化平台适配器
        
        Args:
            platform_name: 平台名称
        """
        self.platform_name = platform_name
        self.logger = logging.getLogger(f"{__name__}.{platform_name}")
    
    @abstractmethod
    def publish_video(
        self,
        browser: Any,
        cookie_data: Dict[str, Any],
        file_path: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list] = None
    ) -> Dict[str, Any]:
        """发布视频
        
        Args:
            browser: 浏览器实例
            cookie_data: Cookie数据
            file_path: 视频文件路径
            title: 标题（可选）
            description: 描述（可选）
            tags: 标签列表（可选）
        
        Returns:
            发布结果字典，包含success, publish_url, error_message等字段
        """
        pass
    
    @abstractmethod
    def publish_image(
        self,
        browser: Any,
        cookie_data: Dict[str, Any],
        image_paths: list,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list] = None
    ) -> Dict[str, Any]:
        """发布图文
        
        Args:
            browser: 浏览器实例
            cookie_data: Cookie数据
            image_paths: 图片文件路径列表
            title: 标题（可选）
            description: 描述（可选）
            tags: 标签列表（可选）
        
        Returns:
            发布结果字典，包含success, publish_url, error_message等字段
        """
        pass


class DouyinAdapter(PlatformAdapter):
    """抖音平台适配器"""
    
    def __init__(self):
        """初始化抖音适配器"""
        super().__init__("douyin")
        # 加载抖音配置
        self._load_config()
    
    def _load_config(self) -> None:
        """加载抖音平台配置（内置资源路径，不依赖当前工作目录）。"""
        from src.infrastructure.common.bundled_config import read_bundled_json

        self.config = read_bundled_json("config/platforms/douyin.json")
        if not self.config:
            self.logger.warning("抖音内置平台配置不存在或无效，使用默认配置")
    
    def publish_video(
        self,
        browser: Any,
        cookie_data: Dict[str, Any],
        file_path: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list] = None
    ) -> Dict[str, Any]:
        """发布视频到抖音
        
        Args:
            browser: 浏览器实例
            cookie_data: Cookie数据
            file_path: 视频文件路径
            title: 标题（可选）
            description: 描述（可选）
            tags: 标签列表（可选）
        
        Returns:
            发布结果字典
        """
        self.logger.info(f"开始发布视频到抖音: {file_path}")
        
        try:
            # 注入Cookie
            browser.inject_cookie_from_dict(cookie_data, domain=".douyin.com")
            
            # 加载发布页面
            publish_url = self.config.get("publish_url", "https://creator.douyin.com/creator-micro/content/upload")
            browser.load_url(publish_url)
            
            # 等待页面加载
            # 这里需要实现等待逻辑
            
            # 上传视频文件
            # 这里需要根据实际页面元素选择器实现上传逻辑
            
            # 填写标题和描述
            if title:
                # browser.simulate_input("input.title-input", title)
                pass
            
            if description:
                # browser.simulate_input("textarea.description", description)
                pass
            
            # 提交发布
            # browser.simulate_click("button.submit-publish")
            
            # 等待发布完成
            # 这里需要实现等待和结果检测逻辑
            
            # 返回结果
            return {
                "success": True,
                "publish_url": "",  # 需要从页面提取
                "error_message": None
            }
        
        except Exception as e:
            self.logger.error(f"发布视频失败: {e}", exc_info=True)
            return {
                "success": False,
                "publish_url": None,
                "error_message": str(e)
            }
    
    def publish_image(
        self,
        browser: Any,
        cookie_data: Dict[str, Any],
        image_paths: list,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list] = None
    ) -> Dict[str, Any]:
        """发布图文到抖音
        
        Args:
            browser: 浏览器实例
            cookie_data: Cookie数据
            image_paths: 图片文件路径列表
            title: 标题（可选）
            description: 描述（可选）
            tags: 标签列表（可选）
        
        Returns:
            发布结果字典
        """
        self.logger.info(f"开始发布图文到抖音: {len(image_paths)}张图片")
        
        # 实现图文发布逻辑（类似视频发布）
        return {
            "success": False,
            "publish_url": None,
            "error_message": "图文发布功能待实现"
        }

