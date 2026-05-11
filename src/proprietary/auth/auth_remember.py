"""
记住我（闭源实现）
原路径：src/services/auth/auth_remember.py
"""

import base64
import json
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_REMEMBER_FILE = "auth_remember.json"
_REMEMBER_KEY_NAME = "remember_me_key"


def _get_remember_path() -> Path:
    from src.infrastructure.common.path_manager import PathManager

    config_dir = PathManager.get_config_dir()
    return config_dir / _REMEMBER_FILE


def _encrypt_password(password: str) -> str:
    """使用 Fernet + keyring 加密密码，返回 Base64 编码的密文。"""
    from src.infrastructure.common.security.encryption import EncryptionManager

    encrypted = EncryptionManager.encrypt_data(password.encode("utf-8"), _REMEMBER_KEY_NAME)
    return base64.b64encode(encrypted).decode("ascii")


def _decrypt_password(enc: str) -> Optional[str]:
    """解密 Fernet 密文，返回明文密码。失败返回 None。"""
    from src.infrastructure.common.security.encryption import EncryptionManager

    try:
        encrypted = base64.b64decode(enc.encode("ascii"))
        return EncryptionManager.decrypt_data(encrypted, _REMEMBER_KEY_NAME).decode("utf-8")
    except Exception:
        return None


def _try_legacy_base64(enc: str) -> Optional[str]:
    """尝试用旧的纯 Base64 方式解码（向后兼容），失败返回 None。"""
    try:
        return base64.b64decode(enc.encode("ascii")).decode("utf-8")
    except Exception:
        return None


def save_remember_me(username: str, password: str) -> None:
    try:
        path = _get_remember_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "remember_me": True,
            "username": username.strip(),
            "password": _encrypt_password(password),
            "enc_version": 2,
        }
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        from src.utils.masking import mask_username
        logger.debug("已保存记住我: username=%s", mask_username(username))
    except Exception as e:
        logger.warning("保存记住我失败: %s", e)


def clear_remember_me() -> None:
    try:
        path = _get_remember_path()
        if path.exists():
            path.unlink()
            logger.debug("已清除记住我")
    except Exception as e:
        logger.warning("清除记住我失败: %s", e)


def get_remembered_credentials() -> Tuple[bool, Optional[str], Optional[str]]:
    try:
        path = _get_remember_path()
        if not path.exists():
            return False, None, None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data.get("remember_me"):
            return False, None, None
        username = data.get("username", "")
        enc = data.get("password", "")
        if not username or not enc:
            return True, (username or None), None

        enc_version = data.get("enc_version", 1)
        password = None
        if enc_version >= 2:
            password = _decrypt_password(enc)
        if password is None:
            password = _try_legacy_base64(enc)
            if password is not None:
                save_remember_me(username, password)

        if password is None:
            return True, username, None
        return True, username, password
    except Exception as e:
        logger.warning("读取记住我失败: %s", e)
        return False, None, None


async def try_auto_login_async() -> bool:
    remembered, username, password = get_remembered_credentials()
    if not remembered or not username or not password:
        return False
    from .user_auth_async import UserAuthAsync

    user_auth = UserAuthAsync()
    try:
        user_info = await user_auth.login(username, password)
        if user_info:
            from src.utils.masking import mask_username
            logger.info("自动登录成功: username=%s", mask_username(username))
            return True
        err = (getattr(user_auth, "last_error_message", None) or "").strip()
        err_code = int(getattr(user_auth, "last_error_code", 0) or 0)
        invalid_cred = err_code in (403, 404) or any(k in err for k in ("密码错误", "用户名或密码错误", "账号不存在"))
        if invalid_cred:
            clear_remember_me()
        else:
            from src.utils.masking import mask_username
            logger.warning("自动登录失败但保留记住我凭证: username=%s, err=%s, code=%s", mask_username(username), err, err_code)
        return False
    except Exception as e:
        from src.utils.masking import mask_username
        logger.warning("自动登录异常（保留记住我凭证）: username=%s, err=%s", mask_username(username), e)
        return False

