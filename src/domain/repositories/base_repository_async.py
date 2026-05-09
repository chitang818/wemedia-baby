"""
基础 Repository（异步版本）- 基于 Tortoise ORM
功能：提供 Repository 基类，使用 Tortoise ORM 模型进行数据访问
"""

from typing import Any, Optional, Type, List, Dict
import logging

from tortoise.models import Model

from src.infrastructure.storage.retry import retry_on_locked

logger = logging.getLogger(__name__)


class BaseRepositoryAsync:
    """基础 Repository（异步版本）

    所有 Repository 的基类，提供通用的数据访问方法。
    子类需要设置 model_class 属性以指定操作的 ORM 模型。
    """

    # 子类必须覆写此属性
    model_class: Type[Model] = None

    def __init__(self):
        """初始化 Repository"""
        self.logger = logging.getLogger(self.__class__.__name__)

    def handle_error(self, error: Exception, operation: str) -> None:
        """处理错误

        Args:
            error: 异常对象
            operation: 操作名称
        """
        self.logger.error(
            f"Repository 操作失败: {operation}, 错误: {error}", exc_info=True
        )

    @retry_on_locked()
    async def _get_by_id(self, pk: int) -> Optional[Model]:
        """根据主键获取单条记录（带重试）

        Args:
            pk: 主键 ID

        Returns:
            ORM 模型实例，不存在返回 None
        """
        return await self.model_class.get_or_none(id=pk)

    @retry_on_locked()
    async def _get_all(self, **filters) -> List[Model]:
        """获取满足条件的所有记录（带重试）

        Args:
            **filters: 过滤条件

        Returns:
            ORM 模型实例列表
        """
        return await self.model_class.filter(**filters).all()

    @retry_on_locked()
    async def _create(self, **kwargs) -> Model:
        """创建一条记录（带重试）

        Args:
            **kwargs: 字段值

        Returns:
            新创建的 ORM 模型实例
        """
        return await self.model_class.create(**kwargs)

    @retry_on_locked()
    async def _delete(self, pk: int) -> bool:
        """根据主键删除一条记录（带重试）

        Args:
            pk: 主键 ID

        Returns:
            是否成功删除
        """
        deleted_count = await self.model_class.filter(id=pk).delete()
        return deleted_count > 0
