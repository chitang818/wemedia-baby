"""
用户认证模块（闭源实现）
原路径：src/services/auth/user_auth_async.py
"""

from typing import Optional, Dict, Any
import logging

from src.domain.repositories.user_repository_async import UserRepositoryAsync
from .auth_config import is_cloud_auth_enabled
from .auth_api_client import login as cloud_login, register as cloud_register
from .current_user_service import CurrentUserService

logger = logging.getLogger(__name__)


class UserAuthAsync:
    """用户认证服务（异步版本）"""

    def __init__(self, user_repository: Optional[UserRepositoryAsync] = None):
        self.user_repository = user_repository or UserRepositoryAsync()
        self.logger = logging.getLogger(__name__)
        self.current_user = CurrentUserService()
        self.last_error_message: str = ""

    async def register(
        self,
        username: str,
        password: str,
        email: str = "",
        phone: Optional[str] = None,
        wechat_id: Optional[str] = None,
    ) -> int:
        self.last_error_message = ""
        if not is_cloud_auth_enabled():
            self.last_error_message = "请配置认证服务地址以使用注册功能"
            raise ValueError(self.last_error_message)
        try:
            result = await cloud_register(username, password, email, phone=phone, wechat_id=wechat_id)
        except Exception as e:
            self.last_error_message = f"注册请求失败: {e}"
            raise ValueError(self.last_error_message) from e
        if not result.get("success"):
            self.last_error_message = result.get("msg", "注册失败")
            raise ValueError(self.last_error_message)
        user_id = result.get("user_id") or 0
        login_result = await cloud_login(username, password)
        if login_result.get("success") and login_result.get("data"):
            d = dict(login_result["data"])
            d["level"] = "vip0"
            d["email"] = email or d.get("email")
            d["phone"] = phone or d.get("phone")
            d["wechat_id"] = wechat_id or d.get("wechat_id")
            self.current_user.sync_from_cloud_data(d)
        return user_id

    async def login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        self.last_error_message = ""
        self.last_error_code: int = 0
        if is_cloud_auth_enabled():
            try:
                result = await cloud_login(username, password)
                if result.get("success") and result.get("data"):
                    d = result["data"]
                    self.current_user.sync_from_cloud_data(d)
                    return {
                        "id": d.get("user_id"),
                        "username": d.get("username"),
                        "email": "",
                        "member_level": d.get("level", "vip0"),
                        "member_expire_at": d.get("expire_time"),
                        "level": d.get("level", "vip0"),
                        "is_expired": d.get("is_expired", True),
                        "max_login_accounts": d.get("max_login_accounts"),
                        "max_account_groups": d.get("max_account_groups"),
                        "daily_max_publish_count": d.get("daily_max_publish_count"),
                    }
                self.last_error_message = result.get("msg", "登录失败")
                self.last_error_code = int(result.get("code") or 0)
                return None
            except Exception as e:
                self.logger.warning("云端登录异常，回退本地: %s", e)
                self.last_error_message = str(e)
        if await self.user_repository.verify_password(username, password):
            user = await self.user_repository.get_by_username(username)
            if user:
                await self.user_repository.update_last_login(user["id"])
                self.current_user.set_user(
                    user_id=user["id"],
                    username=user.get("username", username),
                    level="vip0",
                    is_expired=True,
                    email=user.get("email"),
                )
                return user
        self.last_error_message = "用户名或密码错误"
        return None

