"""
账号组 Repository（异步版本）- 基于 Tortoise ORM
功能：封装账号组（account_groups）相关的数据访问操作
"""

from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from .base_repository_async import BaseRepositoryAsync
from src.infrastructure.storage.orm_models.account_group import AccountGroup as AccountGroupORM
from src.infrastructure.storage.orm_models.platform_account import PlatformAccount
from src.infrastructure.storage.retry import retry_on_locked

logger = logging.getLogger(__name__)


class AccountGroupRepositoryAsync(BaseRepositoryAsync):
    """账号组 Repository（异步版本）- 基于 Tortoise ORM

    封装 account_groups 表的所有数据访问操作。
    """

    model_class = AccountGroupORM

    @retry_on_locked()
    async def create(
        self,
        user_id: int,
        group_name: str,
        description: Optional[str] = None,
    ) -> int:
        """创建账号组

        Args:
            user_id: 用户ID
            group_name: 组名称
            description: 描述（可选）

        Returns:
            新创建的账号组ID

        Raises:
            ValueError: 同名组已存在
        """
        # 检查是否已存在同名账号组
        exists = await AccountGroupORM.filter(
            user_id=user_id, group_name=group_name
        ).exists()
        if exists:
            raise ValueError(f"账号组 '{group_name}' 已存在")

        group = await AccountGroupORM.create(
            user_id=user_id,
            group_name=group_name,
            description=description,
        )
        self.logger.info(f"创建账号组成功: {group_name}, ID: {group.id}")
        return group.id

    async def find_all(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取账号组列表

        Args:
            user_id: 用户ID（可选；不传或 None 时不过滤，返回本地全部账号组，用于单用户模式）

        Returns:
            账号组字典列表
        """
        filters: Dict[str, Any] = {}
        if user_id is not None:
            filters["user_id"] = user_id
        groups = await AccountGroupORM.filter(**filters).order_by("-created_at").all()
        return [self._to_dict(g) for g in groups]

    async def find_by_id(self, group_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取账号组

        Args:
            group_id: 账号组ID

        Returns:
            账号组字典，不存在返回 None
        """
        group = await AccountGroupORM.get_or_none(id=group_id)
        return self._to_dict(group) if group else None

    async def find_by_name(
        self, user_id: int, group_name: str
    ) -> Optional[Dict[str, Any]]:
        """根据名称获取账号组

        Args:
            user_id: 用户ID
            group_name: 组名称

        Returns:
            账号组字典，不存在返回 None
        """
        group = await AccountGroupORM.get_or_none(
            user_id=user_id, group_name=group_name
        )
        return self._to_dict(group) if group else None

    @retry_on_locked()
    async def update(
        self,
        group_id: int,
        group_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        """更新账号组信息

        Args:
            group_id: 账号组ID
            group_name: 新名称（可选）
            description: 新描述（可选）

        Returns:
            是否成功
        """
        update_fields = {"updated_at": datetime.now()}

        if group_name is not None:
            update_fields["group_name"] = group_name
        if description is not None:
            update_fields["description"] = description

        if len(update_fields) <= 1:
            # 只有 updated_at，没有实际更新
            return False

        updated = await AccountGroupORM.filter(id=group_id).update(**update_fields)
        return updated > 0

    @retry_on_locked()
    async def delete(self, group_id: int) -> bool:
        """删除账号组（同时解除组内账号关联）

        Args:
            group_id: 账号组ID

        Returns:
            是否成功
        """
        # 先解除组内账号的关联
        await PlatformAccount.filter(group_id=group_id).update(group_id=None)

        # 删除账号组
        deleted = await AccountGroupORM.filter(id=group_id).delete()
        return deleted > 0

    @retry_on_locked()
    async def add_account(self, group_id: int, account_id: int) -> None:
        """将账号添加到账号组

        Args:
            group_id: 账号组ID
            account_id: 账号ID
        """
        await PlatformAccount.filter(id=account_id).update(group_id=group_id)

    @retry_on_locked()
    async def remove_account(self, account_id: int) -> None:
        """将账号从账号组中移除

        Args:
            account_id: 账号ID
        """
        await PlatformAccount.filter(id=account_id).update(group_id=None)

    async def find_accounts_by_group(self, group_id: int) -> List[Dict[str, Any]]:
        """获取账号组内的所有账号

        Args:
            group_id: 账号组ID

        Returns:
            账号字典列表
        """
        accounts = await PlatformAccount.filter(
            group_id=group_id
        ).order_by("platform").all()
        return [self._account_to_dict(a) for a in accounts]

    async def find_ungrouped_accounts(self, user_id: int) -> List[Dict[str, Any]]:
        """获取未分组的账号

        Args:
            user_id: 用户ID

        Returns:
            未分组账号列表
        """
        accounts = await PlatformAccount.filter(
            user_id=user_id, group_id__isnull=True
        ).order_by("-created_at").all()
        return [self._account_to_dict(a) for a in accounts]

    async def check_platform_conflict(
        self, group_id: int, platform: str
    ) -> Optional[Dict[str, Any]]:
        """检查账号组内是否已有同平台账号

        Args:
            group_id: 账号组ID
            platform: 平台名称

        Returns:
            已存在的同平台账号字典，不存在返回 None
        """
        account = await PlatformAccount.get_or_none(
            group_id=group_id, platform=platform
        )
        return self._account_to_dict(account) if account else None

    @staticmethod
    def _to_dict(group: AccountGroupORM) -> Dict[str, Any]:
        """将 ORM 模型实例转换为字典"""
        return {
            "id": group.id,
            "group_id": group.id,
            "user_id": group.user_id if hasattr(group, "user_id") else None,
            "group_name": group.group_name,
            "description": group.description,
            "created_at": group.created_at.isoformat() if group.created_at else None,
            "updated_at": group.updated_at.isoformat() if group.updated_at else None,
        }

    @staticmethod
    def _account_to_dict(account: PlatformAccount) -> Dict[str, Any]:
        """将账号 ORM 模型转换为字典（简化版）"""
        return {
            "id": account.id,
            "user_id": account.user_id if hasattr(account, "user_id") else None,
            "platform": account.platform,
            "platform_username": account.platform_username,
            "login_status": account.login_status,
            "last_login_at": account.last_login_at.isoformat() if account.last_login_at else None,
            "created_at": account.created_at.isoformat() if account.created_at else None,
            "group_id": account.group_id if hasattr(account, "group_id") else None,
        }
