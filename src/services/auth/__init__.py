"""
用户认证业务模块（开源包装层）

- 闭源实现位于 `src/proprietary/auth/`（本地存在时自动启用）\n
- 开源仓库缺失闭源目录时，本模块保留可导入的占位实现，确保程序不崩溃。\n
"""

from .user_auth_async import UserAuthAsync
from .current_user_service import CurrentUserService

UserAuth = UserAuthAsync

__all__ = ["UserAuthAsync", "UserAuth", "CurrentUserService"]
