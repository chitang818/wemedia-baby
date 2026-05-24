"""
当前用户服务（闭源实现）
原路径：src/services/auth/current_user_service.py
"""

from typing import Optional, Dict, Any
import logging
import threading

logger = logging.getLogger(__name__)


def _publish_current_user_changed(
    *,
    username: Optional[str],
    logged_in: bool,
    source: str,
) -> None:
    try:
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.infrastructure.common.event.event_bus import EventBus
        from src.infrastructure.common.event.events import CurrentUserChangedEvent

        locator = ServiceLocator()
        if not locator.is_registered(EventBus):
            return
        locator.get(EventBus).publish_sync(
            CurrentUserChangedEvent(
                username=username,
                logged_in=logged_in,
                source=source,
            )
        )
    except Exception as exc:
        logger.debug("发布 CurrentUserChangedEvent 失败（可忽略）: %s", exc)


class CurrentUserService:
    """当前用户服务（单例，线程安全）"""

    _instance: Optional["CurrentUserService"] = None
    _singleton_lock = threading.Lock()

    def __new__(cls) -> "CurrentUserService":
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self._lock = threading.RLock()
        self._user_id: Optional[int] = None
        self._username: Optional[str] = None
        self._level: str = "vip0"
        self._expire_time: Optional[int] = None
        self._is_expired: bool = True
        self._email: Optional[str] = None
        self._phone: Optional[str] = None
        self._wechat_id: Optional[str] = None
        self._max_login_accounts: Optional[int] = None
        self._max_account_groups: Optional[int] = None
        self._daily_max_publish_count: Optional[int] = None
        self._last_login_at: Optional[int] = None
        self._create_time: Optional[int] = None
        self._register_ip: Optional[str] = None
        self._last_login_ip: Optional[str] = None
        self._token: Optional[str] = None
        self.logger = logging.getLogger(__name__)

    def set_user(
        self,
        user_id: int,
        username: str,
        level: str = "vip0",
        expire_time: Optional[int] = None,
        is_expired: bool = True,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        wechat_id: Optional[str] = None,
        max_login_accounts: Optional[int] = None,
        max_account_groups: Optional[int] = None,
        daily_max_publish_count: Optional[int] = None,
        last_login_at: Optional[int] = None,
        create_time: Optional[int] = None,
        register_ip: Optional[str] = None,
        last_login_ip: Optional[str] = None,
        token: Optional[str] = None,
        source: str = "login",
    ) -> None:
        with self._lock:
            self._user_id = user_id
            self._username = username
            self._token = token
            self._level = level or "vip0"
            self._expire_time = expire_time
            self._is_expired = is_expired
            self._email = email
            self._phone = phone
            self._wechat_id = wechat_id
            self._max_login_accounts = max_login_accounts
            self._max_account_groups = max_account_groups
            self._daily_max_publish_count = daily_max_publish_count
            self._last_login_at = last_login_at
            self._create_time = create_time
            self._register_ip = register_ip
            self._last_login_ip = last_login_ip
        from src.utils.masking import mask_username
        self.logger.info("当前用户已设置: username=%s, level=%s, is_expired=%s", mask_username(username), level, is_expired)
        _publish_current_user_changed(username=username, logged_in=True, source=source)

    def sync_from_cloud_data(self, data: Dict[str, Any]) -> None:
        if not data:
            return
        username = (data.get("username") or "").strip()
        if not username:
            return
        user_id = data.get("user_id")
        if user_id is None:
            h = hash(username)
            user_id = abs(h) % (2**31 - 1) if h != 0 else 1
        self.set_user(
            user_id=int(user_id),
            username=username,
            level=data.get("level", "vip0"),
            expire_time=data.get("expire_time"),
            is_expired=data.get("is_expired", True),
            email=data.get("email"),
            phone=data.get("phone"),
            wechat_id=data.get("wechat_id"),
            max_login_accounts=data.get("max_login_accounts"),
            max_account_groups=data.get("max_account_groups"),
            daily_max_publish_count=data.get("daily_max_publish_count"),
            last_login_at=data.get("last_login_at"),
            create_time=data.get("create_time"),
            register_ip=data.get("register_ip"),
            last_login_ip=data.get("last_login_ip"),
            token=data.get("token"),
            source="sync",
        )
        from src.utils.masking import mask_username
        self.logger.info("已从云端同步账号权限: username=%s, level=%s", mask_username(username), data.get("level", "vip0"))

    def clear_user(self, source: str = "logout") -> None:
        with self._lock:
            self._user_id = None
            self._username = None
            self._level = "vip0"
            self._expire_time = None
            self._is_expired = True
            self._email = None
            self._phone = None
            self._wechat_id = None
            self._max_login_accounts = None
            self._max_account_groups = None
            self._daily_max_publish_count = None
            self._last_login_at = None
            self._create_time = None
            self._register_ip = None
            self._last_login_ip = None
            self._token = None
        self.logger.info("当前用户已清除")
        _publish_current_user_changed(username=None, logged_in=False, source=source)

    def get_user_id(self) -> Optional[int]:
        with self._lock:
            return self._user_id

    def get_token(self) -> Optional[str]:
        with self._lock:
            return self._token

    def get_user_id_or_default(self, default: int = 1) -> int:
        with self._lock:
            return self._user_id if self._user_id is not None else default

    def get_user(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._user_id is None:
                return None
            return {
                "id": self._user_id,
                "username": self._username,
                "email": self._email,
                "phone": self._phone,
                "wechat_id": self._wechat_id,
                "level": self._level,
                "member_level": self._level,
                "expire_time": self._expire_time,
                "is_expired": self._is_expired,
                "member_expire_at": self._expire_time if self._expire_time else None,
                "max_login_accounts": self._max_login_accounts,
                "max_account_groups": self._max_account_groups,
                "daily_max_publish_count": self._daily_max_publish_count,
                "last_login_at": self._last_login_at,
                "create_time": self._create_time,
                "register_ip": self._register_ip,
                "last_login_ip": self._last_login_ip,
            }

    def get_max_login_accounts(self) -> Optional[int]:
        with self._lock:
            return self._max_login_accounts

    def get_max_account_groups(self) -> Optional[int]:
        with self._lock:
            return self._max_account_groups

    def get_daily_max_publish_count(self) -> Optional[int]:
        with self._lock:
            return self._daily_max_publish_count

    def is_logged_in(self) -> bool:
        with self._lock:
            return self._user_id is not None

    def has_pro_permission(self) -> bool:
        with self._lock:
            return self._level == "vip1" and not self._is_expired

