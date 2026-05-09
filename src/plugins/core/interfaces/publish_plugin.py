from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class FormField:
    """表单字段定义"""
    name: str              # 字段名 (用于提交数据)
    label: str             # 显示标签
    field_type: str        # 字段类型: text, textarea, select, checkbox, file, datetime
    required: bool = True  # 是否必填
    options: List[Dict] = None  # 选项列表 (select类型用) [{'label': 'A', 'value': 'a'}]
    max_length: int = None # 最大长度
    default: Any = None    # 默认值
    placeholder: str = None # 占位符

@dataclass
class PublishResult:
    """发布结果数据类"""
    success: bool
    publish_url: Optional[str] = None
    error_message: Optional[str] = None
    failed_step: Optional[str] = None  # 失败时所在步骤名，便于主程序/UI 单独展示

class PublishPluginInterface(ABC):
    """发布插件抽象接口"""

    @property
    @abstractmethod
    def platform_id(self) -> str:
        """平台标识"""
        pass

    @abstractmethod
    def get_form_schema(self, content_type: str = "video") -> List[FormField]:
        """
        返回发布表单字段定义 (供UI动态渲染)
        Args:
            content_type: 内容类型 (video/image)
        """
        pass

    @abstractmethod
    async def publish(
        self,
        context,
        file_path: str,
        metadata: Dict[str, Any]
    ) -> PublishResult:
        """
        执行发布操作
        Args:
            context: 浏览器上下文
            file_path: 文件路径
            metadata: 表单数据字典
        """
        pass

    # ===== 可选的辅助方法 (子类可根据需要覆盖) =====
    
    async def select_topic(self, page, topic: str) -> bool:
        """选择话题"""
        return False

    async def set_schedule(self, page, schedule_time: str) -> bool:
        """设置定时发布"""
        return False

    async def set_location(self, page, location: str) -> bool:
        """设置位置信息"""
        return False

    async def set_shopping_link(self, page, link: str) -> bool:
        """设置购物车链接"""
        return False
