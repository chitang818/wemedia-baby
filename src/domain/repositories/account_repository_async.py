"""
账号 Repository（异步版本）- 基于 Tortoise ORM
功能：封装平台账号相关的数据访问操作
"""

from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from .base_repository_async import BaseRepositoryAsync
from src.infrastructure.storage.orm_models.platform_account import PlatformAccount
from src.infrastructure.storage.retry import retry_on_locked

logger = logging.getLogger(__name__)


def _normalize_platform_username(value: str) -> str:
    """平台昵称规范化：去除前导 @，避免与抖音等平台展示格式混入存储。"""
    if not value or not isinstance(value, str):
        return value or ""
    return value.lstrip("@").strip() or value


class AccountRepositoryAsync(BaseRepositoryAsync):
    """账号 Repository（异步版本）- 基于 Tortoise ORM

    封装 platform_accounts 表的所有数据访问操作。
    """

    model_class = PlatformAccount

    @retry_on_locked()
    async def create(
        self,
        user_id: int,
        platform: str,
        platform_username: str = "",
        cookie_path: str = "",
        profile_folder_name: Optional[str] = None,
    ) -> int:
        """创建平台账号

        Args:
            user_id: 用户ID
            platform: 平台名称
            platform_username: 平台用户名（昵称）
            cookie_path: Cookie 文件路径
            profile_folder_name: 账号数据文件夹名称

        Returns:
            新创建的账号ID
        """
        platform_username = _normalize_platform_username(platform_username or "")
        # 保证新账号必有 profile_folder_name，避免后续打开浏览器/Cookie 路径报错
        if not (profile_folder_name and str(profile_folder_name).strip()):
            import uuid
            profile_folder_name = f"profile_{uuid.uuid4().hex[:12]}"
            self.logger.info(
                "创建账号时未提供 profile_folder_name，已生成: %s", profile_folder_name
            )
        try:
            account = await PlatformAccount.create(
                user_id=user_id,
                platform=platform,
                platform_username=platform_username,
                cookie_path=cookie_path,
                profile_folder_name=profile_folder_name,
            )
            self.logger.info(
                f"创建平台账号成功: {platform_username or '未指定'}, "
                f"平台: {platform}, ID: {account.id}"
            )
            return account.id
        except Exception as e:
            self.handle_error(e, "create")
            raise

    async def find_all(
        self,
        user_id: Optional[int] = None,
        platform: Optional[str] = None,
        *,
        raise_on_error: bool = False,
    ) -> List[Dict[str, Any]]:
        """查找所有账号

        Args:
            user_id: 用户ID（可选；不传或 None 时不过滤，返回本地全部账号，用于单用户模式）
            platform: 平台名称（可选，用于筛选）
            raise_on_error: 为 True 时异常上抛（适用于发布等关键路径），
                            为 False 时保持旧行为（静默返回空列表）

        Returns:
            账号字典列表
        """
        try:
            filters: Dict[str, Any] = {}
            if user_id is not None:
                filters["user_id"] = user_id
            if platform:
                filters["platform"] = platform

            accounts = await PlatformAccount.filter(**filters).order_by("created_at").all()
            return [self._to_dict(acc) for acc in accounts]
        except Exception as e:
            self.handle_error(e, "find_all")
            if raise_on_error:
                raise
            return []

    async def find_by_id(
        self,
        account_id: int,
        user_id: int = 0,
        *,
        raise_on_error: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """根据 ID 查找账号

        Args:
            account_id: 账号ID
            user_id: 用户ID（保留兼容，实际未参与查询）
            raise_on_error: 为 True 时异常上抛

        Returns:
            账号字典，不存在返回 None
        """
        try:
            account = await PlatformAccount.get_or_none(id=account_id)
            return self._to_dict(account) if account else None
        except Exception as e:
            self.handle_error(e, "find_by_id")
            if raise_on_error:
                raise
            return None

    @retry_on_locked()
    async def update_status(
        self,
        account_id: int,
        login_status: str,
        last_login_at: Optional[str] = None,
    ) -> bool:
        """更新账号登录状态

        Args:
            account_id: 账号ID
            login_status: 登录状态（online/offline）
            last_login_at: 最后登录时间（可选，ISO 格式字符串）

        Returns:
            是否成功
        """
        try:
            update_data = {"login_status": login_status}
            if last_login_at:
                update_data["last_login_at"] = last_login_at
            else:
                update_data["last_login_at"] = datetime.now()

            updated = await PlatformAccount.filter(id=account_id).update(**update_data)
            return updated > 0
        except Exception as e:
            self.handle_error(e, "update_status")
            return False

    @retry_on_locked()
    async def update_platform_username(
        self,
        account_id: int,
        platform_username: str,
    ) -> bool:
        """更新平台用户名

        Args:
            account_id: 账号ID
            platform_username: 平台用户名

        Returns:
            是否成功
        """
        platform_username = _normalize_platform_username(platform_username or "")
        try:
            updated = await PlatformAccount.filter(id=account_id).update(
                platform_username=platform_username
            )
            self.logger.info(
                f"更新平台用户名成功: 账号ID={account_id}, 用户名={platform_username}"
            )
            return updated > 0
        except Exception as e:
            self.handle_error(e, "update_platform_username")
            return False

    @retry_on_locked()
    async def update_group(
        self,
        account_id: int,
        group_id: Optional[int],
    ) -> bool:
        """更新账号的分组

        Args:
            account_id: 账号ID
            group_id: 账号组ID（None 表示从组中移除）

        Returns:
            是否成功
        """
        try:
            updated = await PlatformAccount.filter(id=account_id).update(
                group_id=group_id
            )
            return updated > 0
        except Exception as e:
            self.handle_error(e, "update_group")
            return False

    @retry_on_locked()
    async def update_cookie_path(self, account_id: int, cookie_path: str) -> bool:
        """更新账号的 Cookie 文件路径（静默更新/打开浏览器保存后需同步，否则验证器读不到）"""
        try:
            updated = await PlatformAccount.filter(id=account_id).update(
                cookie_path=cookie_path or ""
            )
            if updated:
                self.logger.debug(f"更新账号 cookie_path: account_id={account_id}")
            return updated > 0
        except Exception as e:
            self.handle_error(e, "update_cookie_path")
            return False

    @retry_on_locked()
    async def update_profile_folder_name(
        self, account_id: int, profile_folder_name: str, cookie_path: str = ""
    ) -> bool:
        """更新账号的 profile_folder_name（发现磁盘已有目录时回填，便于打开浏览器与 Cookie 路径）"""
        try:
            values = {"profile_folder_name": profile_folder_name or ""}
            if cookie_path is not None:
                values["cookie_path"] = cookie_path or ""
            updated = await PlatformAccount.filter(id=account_id).update(**values)
            if updated:
                self.logger.debug(
                    f"更新账号 profile_folder_name: account_id={account_id}, profile={profile_folder_name}"
                )
            return updated > 0
        except Exception as e:
            self.handle_error(e, "update_profile_folder_name")
            return False

    @retry_on_locked()
    async def mark_publish_quarantined(
        self,
        account_id: int,
        reason: str = "",
    ) -> bool:
        """Persistently quarantine an account after a publish risk signal."""
        try:
            updated = await PlatformAccount.filter(id=account_id).update(
                publish_risk_state="quarantined",
                publish_risk_reason=reason or "",
                publish_risk_at=datetime.now(),
            )
            return updated > 0
        except Exception as e:
            self.handle_error(e, "mark_publish_quarantined")
            return False

    @retry_on_locked()
    async def clear_publish_quarantine(self, account_id: int) -> bool:
        """Manually clear publish quarantine after user confirmation."""
        try:
            updated = await PlatformAccount.filter(id=account_id).update(
                publish_risk_state="normal",
                publish_risk_reason=None,
                publish_risk_at=None,
            )
            return updated > 0
        except Exception as e:
            self.handle_error(e, "clear_publish_quarantine")
            return False

    async def delete(self, account_id: int) -> bool:
        """删除账号

        Args:
            account_id: 账号ID

        Returns:
            是否成功
        """
        try:
            deleted = await PlatformAccount.filter(id=account_id).delete()
            if deleted:
                self.logger.info(f"删除平台账号: ID {account_id}")
            return deleted > 0
        except Exception as e:
            self.handle_error(e, "delete")
            return False

    async def exists(
        self,
        user_id: int,
        platform_username: str,
        platform: str,
    ) -> bool:
        """检查账号是否存在

        Args:
            user_id: 用户ID
            platform_username: 平台用户名
            platform: 平台名称

        Returns:
            是否存在
        """
        try:
            return await PlatformAccount.filter(
                user_id=user_id,
                platform_username=platform_username,
                platform=platform,
            ).exists()
        except Exception as e:
            self.logger.error(f"检查账号是否存在失败: {e}")
            return False

    async def find_by_group(self, group_id: int) -> List[Dict[str, Any]]:
        """查找指定组的所有账号

        Args:
            group_id: 账号组ID

        Returns:
            账号字典列表
        """
        try:
            accounts = await PlatformAccount.filter(
                group_id=group_id
            ).order_by("platform").all()
            return [self._to_dict(acc) for acc in accounts]
        except Exception as e:
            self.handle_error(e, "find_by_group")
            return []

    @staticmethod
    def _to_dict(account: PlatformAccount) -> Dict[str, Any]:
        """将 ORM 模型实例转换为字典

        保证输出格式与旧的 AsyncDataStorage 返回值兼容，
        确保上层代码无需修改即可使用。

        Args:
            account: PlatformAccount ORM 实例

        Returns:
            兼容旧格式的字典
        """
        return {
            "id": account.id,
            "user_id": account.user_id,
            "platform": account.platform,
            "account_name": account.platform_username,
            "cookie_path": account.cookie_path,
            "platform_username": account.platform_username,
            "login_status": account.login_status,
            "last_login_at": (
                account.last_login_at.isoformat() if account.last_login_at else None
            ),
            "profile_folder_name": account.profile_folder_name,
            "publish_risk_state": getattr(account, "publish_risk_state", "normal") or "normal",
            "publish_risk_reason": getattr(account, "publish_risk_reason", None),
            "publish_risk_at": (
                account.publish_risk_at.isoformat()
                if getattr(account, "publish_risk_at", None)
                else None
            ),
            "group_id": account.group_id,
            "created_at": (
                account.created_at.isoformat() if account.created_at else None
            ),
        }
