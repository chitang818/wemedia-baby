"""
当前用户服务（开源包装层）

闭源版在 `src/proprietary/auth/current_user_service.py` 提供真实实现；
开源版保留最小实现（仅用于 UI 显示/不崩溃），不包含云端授权细节。
"""

from __future__ import annotations

from typing import Optional, Dict, Any


try:
    from src.proprietary.auth.current_user_service import CurrentUserService as _ImplCurrentUserService
    CurrentUserService = _ImplCurrentUserService
except Exception:
    class CurrentUserService:  # type: ignore[no-redef]
        _instance: Optional["CurrentUserService"] = None

        def __new__(cls) -> "CurrentUserService":
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

        def __init__(self) -> None:
            if hasattr(self, "_initialized") and self._initialized:
                return
            self._initialized = True
            self._user_id: Optional[int] = None
            self._username: Optional[str] = None
            self._level: str = "vip0"
            self._is_expired: bool = True

        def set_user(self, user_id: int, username: str, level: str = "vip0", is_expired: bool = True, **_: Any) -> None:
            self._user_id = user_id
            self._username = username
            self._level = level or "vip0"
            self._is_expired = bool(is_expired)

        def sync_from_cloud_data(self, data: Dict[str, Any]) -> None:
            # 开源版不做云端同步
            if data and data.get("username"):
                self.set_user(int(data.get("user_id") or 1), str(data.get("username")), level=str(data.get("level") or "vip0"))

        def clear_user(self) -> None:
            self._user_id = None
            self._username = None
            self._level = "vip0"
            self._is_expired = True

        def get_user_id(self) -> Optional[int]:
            return self._user_id

        def get_user_id_or_default(self, default: int = 1) -> int:
            return self._user_id if self._user_id is not None else default

        def get_token(self) -> Optional[str]:
            return None

        def get_user(self) -> Optional[Dict[str, Any]]:
            if self._user_id is None:
                return None
            return {"id": self._user_id, "username": self._username, "level": self._level, "is_expired": self._is_expired}

        def get_daily_max_publish_count(self) -> Optional[int]:
            return None

        def is_logged_in(self) -> bool:
            return self._user_id is not None

        def has_pro_permission(self) -> bool:
            return False
