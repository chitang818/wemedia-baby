"""
记住我模块（开源包装层）
闭源版在 `src/proprietary/auth/auth_remember.py` 提供真实实现。
"""

from __future__ import annotations

from typing import Optional, Tuple, Any


try:
    from src.proprietary.auth.auth_remember import (
        save_remember_me,
        clear_remember_me,
        get_remembered_credentials,
        try_auto_login_async,
    )
except Exception:
    def save_remember_me(username: str, password: str) -> None:
        return None

    def clear_remember_me() -> None:
        return None

    def get_remembered_credentials() -> Tuple[bool, Optional[str], Optional[str]]:
        return False, None, None

    async def try_auto_login_async() -> bool:
        return False
