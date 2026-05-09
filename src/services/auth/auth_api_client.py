"""
认证 API 客户端（开源包装层）

闭源版在 `src/proprietary/auth/auth_api_client.py` 提供真实实现。
开源版（无闭源目录）下，这些接口会返回“不可用”的结果，避免泄露服务端校验细节。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Callable


def _load_impl() -> tuple[
    Callable[[str, str], "Any"],
    Callable[[str], "Any"],
    Callable[[str, str, bool], "Any"],
    Callable[[str, str, str, Optional[str], Optional[str]], "Any"],
]:
    try:
        from src.proprietary.auth.auth_api_client import login, refresh_user_info, publish_check, register
        return login, refresh_user_info, publish_check, register
    except Exception:
        async def _not_available_login(username: str, password: str) -> Dict[str, Any]:
            return {"success": False, "code": 501, "msg": "开源版不提供云端登录", "data": None}

        async def _not_available_refresh(token: str) -> Dict[str, Any]:
            return {"success": False, "msg": "开源版不提供云端刷新", "data": None}

        async def _not_available_publish_check(token: str, platform: str, is_pro_platform: bool) -> Dict[str, Any]:
            return {"success": False, "allowed": True, "reason": "开源版跳过服务端校验"}

        async def _not_available_register(
            username: str,
            password: str,
            email: str = "",
            phone: Optional[str] = None,
            wechat_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            return {"success": False, "code": 501, "msg": "开源版不提供云端注册", "user_id": None}

        return _not_available_login, _not_available_refresh, _not_available_publish_check, _not_available_register


login, refresh_user_info, publish_check, register = _load_impl()

