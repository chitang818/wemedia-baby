"""
发布管道过滤器基类
文件路径：src/core/common/pipeline/base_filter.py
功能：定义过滤器接口和基类
"""

from abc import ABC, abstractmethod
from typing import Optional, Protocol, Any
from dataclasses import dataclass


@dataclass
class PublishContext:
    """发布上下文
    
    在管道中传递的上下文数据。
    """
    user_id: int
    account_name: str
    platform: str
    file_path: str
    file_type: str = "video" # video or image (旧字段保留供兼容)
    publish_type: str = "video" # 新增：明确的发布大类（video/image）
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    account: Optional[Any] = None  # Account实体
    headless: bool = True  # 是否无头模式
    speed_rate: float = 1.0  # 发布速度倍率 (1.0=正常, >1.0=慢速)
    pause_event: Any = None  # 暂停控制事件 (asyncio.Event)
    error_message: Optional[str] = None
    cover_type: Optional[str] = None  # 封面类型: "first_frame", "custom", "ai"
    cover_path: Optional[str] = None  # 本地封面图片路径（custom 时使用）
    scheduled_publish_time: Optional[Any] = None  # 定时发布时间 (datetime 或 str)
    privacy_settings: Optional[str] = None  # 扩展属性 (如视频号原创、私密等配置JSON)
    close_browser_after: bool = True  # 本次发布完成后是否关闭浏览器（同账号连续发布时可设为 False 复用）
    # 抖音扩展信息（发布列表任务写入库，步骤6 可选自动填页）
    poi_info: Optional[str] = None
    wechat_empty_location_open_picker: Optional[bool] = None
    cart_info: Optional[str] = None
    anchor_info: Optional[str] = None
    micro_app_info: Optional[str] = None
    music_info: Optional[str] = None  # 音乐配置 JSON，含 music_type(random/specific) 和 music_name


@dataclass
class PublishRequest:
    """发布请求"""
    user_id: int
    account_name: str
    platform: str
    file_path: str
    publish_type: str = "video" # 新增：明确的发布大类（video/image）
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[str] = None
    headless: bool = True  # 是否无头模式
    speed_rate: float = 1.0  # 发布速度倍率
    pause_event: Any = None  # 暂停控制事件 (asyncio.Event)
    cover_type: Optional[str] = None  # 封面类型: "first_frame", "custom", "ai"
    cover_path: Optional[str] = None  # 本地封面图片路径（custom 时使用）
    scheduled_publish_time: Optional[Any] = None  # 定时发布时间
    privacy_settings: Optional[str] = None  # 扩展属性 (如视频号原创、私密等配置JSON)
    close_browser_after: bool = True  # 本次发布完成后是否关闭浏览器（同账号连续发布时可设为 False 复用）
    poi_info: Optional[str] = None
    wechat_empty_location_open_picker: Optional[bool] = None
    cart_info: Optional[str] = None
    anchor_info: Optional[str] = None
    micro_app_info: Optional[str] = None
    music_info: Optional[str] = None  # 音乐配置 JSON，含 music_type(random/specific) 和 music_name


@dataclass
class PipelineResult:
    """管道层发布结果（与插件层 PublishResult 区分，避免同名混淆）"""
    success: bool
    task_id: Optional[int] = None
    publish_url: Optional[str] = None
    error_message: Optional[str] = None
    execution_time: float = 0.0


# 向后兼容别名：旧代码中 `from base_filter import PublishResult` 仍可用
PublishResult = PipelineResult


@dataclass
class PublishResponse:
    """发布响应"""
    results: list[PipelineResult]
    total_count: int
    success_count: int
    failed_count: int


class IPublishFilter(Protocol):
    """发布过滤器接口"""
    
    async def process(self, context: PublishContext) -> bool:
        """处理上下文
        
        Args:
            context: 发布上下文
        
        Returns:
            如果处理成功返回True，否则返回False
        """
        ...
    
    def get_error(self) -> Optional[str]:
        """获取错误信息
        
        Returns:
            错误信息，如果没有错误返回None
        """
        ...


class BaseFilter(ABC):
    """发布过滤器基类"""
    
    def __init__(self):
        """初始化过滤器"""
        self._error: Optional[str] = None
    
    @abstractmethod
    async def process(self, context: PublishContext) -> bool:
        """处理上下文（异步）
        
        Args:
            context: 发布上下文
        
        Returns:
            如果处理成功返回True，否则返回False
        """
        return False
    
    def get_error(self) -> Optional[str]:
        """获取错误信息
        
        Returns:
            错误信息，如果没有错误返回None
        """
        return self._error
    
    def set_error(self, error: str) -> None:
        """设置错误信息
        
        Args:
            error: 错误信息
        """
        self._error = error

