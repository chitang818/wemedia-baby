"""
用户认证模块（开源包装层）
闭源版在 `src/proprietary/auth/user_auth_async.py` 提供真实实现。
"""

from __future__ import annotations

from typing import Optional, Dict, Any


try:
    from src.proprietary.auth.user_auth_async import UserAuthAsync as _ImplUserAuthAsync
    UserAuthAsync = _ImplUserAuthAsync
except Exception:
    class UserAuthAsync:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any):
            self.last_error_message: str = "开源版不提供媒小宝账号登录"
            self.last_error_code: int = 501

        async def register(self, *args: Any, **kwargs: Any) -> int:
            raise ValueError("开源版不提供注册功能")

        async def login(self, username: str, password: str) -> Optional[Dict[str, Any]]:
            self.last_error_message = "开源版不提供登录功能"
            self.last_error_code = 501
            return None
