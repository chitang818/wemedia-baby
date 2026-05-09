"""
用户 Repository（异步版本）- 基于 Tortoise ORM
功能：封装用户相关的数据访问操作
"""

from typing import Optional, Dict, Any
import logging
from datetime import datetime

from .base_repository_async import BaseRepositoryAsync
from src.infrastructure.storage.orm_models.user import User
from src.infrastructure.storage.retry import retry_on_locked
from src.infrastructure.common.security.encryption import hash_password, verify_password

logger = logging.getLogger(__name__)


class UserRepositoryAsync(BaseRepositoryAsync):
    """用户 Repository（异步版本）- 基于 Tortoise ORM

    封装 users 表的所有数据访问操作。
    """

    model_class = User

    async def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """根据用户名获取用户信息

        Args:
            username: 用户名

        Returns:
            用户信息字典，如果不存在返回 None
        """
        user = await User.get_or_none(username=username)
        return self._to_dict(user) if user else None

    async def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """根据用户 ID 获取用户信息

        Args:
            user_id: 用户ID

        Returns:
            用户信息字典，如果不存在返回 None
        """
        user = await User.get_or_none(id=user_id)
        return self._to_dict(user) if user else None

    async def verify_password(self, username: str, password: str) -> bool:
        """验证用户密码

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            密码正确返回 True
        """
        user = await User.get_or_none(username=username)
        if not user:
            return False
        return verify_password(password, user.password_hash)

    @retry_on_locked()
    async def update_password(self, username: str, new_password: str) -> bool:
        """更新用户密码

        Args:
            username: 用户名
            new_password: 新明文密码

        Returns:
            更新是否成功
        """
        password_hash = hash_password(new_password)
        updated = await User.filter(username=username).update(
            password_hash=password_hash
        )
        return updated > 0

    @retry_on_locked()
    async def update_last_login(self, user_id: int) -> bool:
        """更新用户最后登录时间

        Args:
            user_id: 用户ID

        Returns:
            更新是否成功
        """
        updated = await User.filter(id=user_id).update(
            last_login_at=datetime.now()
        )
        return updated > 0

    @retry_on_locked()
    async def update_trial_count(self, user_id: int, trial_count: int) -> bool:
        """更新用户试用次数

        Args:
            user_id: 用户ID
            trial_count: 新的试用次数

        Returns:
            更新是否成功
        """
        updated = await User.filter(id=user_id).update(trial_count=trial_count)
        return updated > 0

    @staticmethod
    def _to_dict(user: User) -> Dict[str, Any]:
        """将 ORM 模型实例转换为字典（不含敏感字段）"""
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "trial_count": user.trial_count,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        }
