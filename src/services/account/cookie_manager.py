"""
Cookie管理模块
文件路径：src/services/account/cookie_manager.py
功能：提供Cookie的加密存储和加载功能（Fernet 加密，无 user_id 绑定）
"""

import base64
import os
import json
import hashlib
import logging
from typing import Any, Dict, Optional

from src.infrastructure.common.path_manager import PathManager

logger = logging.getLogger(__name__)

COOKIE_FILENAME = "cookies.json"
_COOKIE_KEY_NAME = "cookie_store_key"
_ENCRYPTED_PREFIX = b"FERNET:"

# 各平台会话 Cookie 名（用于 merge 时避免从过期的 storage_state 复活登录态）
_PLATFORM_SESSION_COOKIE_NAMES: Dict[str, frozenset] = {
    "kuaishou": frozenset({
        "userId",
        "bUserId",
        "kuaishou.web.cp.api_st",
        "kuaishou.web.cp.api_ph",
    }),
    "douyin": frozenset({
        "sessionid",
        "sessionid_ss",
        "sid_tt",
        "uid_tt",
        "sid_guard",
    }),
}


def _session_cookie_names_for_platform(platform: str) -> frozenset:
    names = _PLATFORM_SESSION_COOKIE_NAMES.get(platform or "")
    if names:
        return names
    return frozenset({
        "sessionid",
        "session_id",
        "token",
        "auth_token",
        "access_token",
        "userId",
        "sid",
    })


def flat_cookies_have_session(flat_cookies: Dict[str, Any], platform: str) -> bool:
    """扁平 Cookie 是否仍含该平台会话关键字段（用于判断是否允许从 storage_state 补全会话项）。"""
    names = _session_cookie_names_for_platform(platform)
    keys = set(flat_cookies or {})
    if platform == "kuaishou":
        has_user = "userId" in keys
        has_token = "kuaishou.web.cp.api_st" in keys or "kuaishou.web.cp.api_ph" in keys
        return has_user and has_token
    return bool(keys & names)


def normalize_to_flat_cookie_dict(data: Any) -> Dict[str, str]:
    """将 cookies.json 常见形态（扁平 dict、Playwright 列表、含 cookies 数组的 dict）转为 name->value。"""
    if data is None:
        return {}
    if isinstance(data, list):
        out: Dict[str, str] = {}
        for c in data:
            if not isinstance(c, dict):
                continue
            n, v = c.get("name"), c.get("value")
            if n and v is not None:
                out[str(n)] = v if isinstance(v, str) else str(v)
        return out
    if isinstance(data, dict):
        inner = data.get("cookies")
        if isinstance(inner, list):
            return normalize_to_flat_cookie_dict(inner)
        out: Dict[str, str] = {}
        for k, v in data.items():
            if k == "cookies" or v is None:
                continue
            if isinstance(v, (dict, list)):
                continue
            out[str(k)] = v if isinstance(v, str) else str(v)
        return out
    return {}


class CookieManager:
    """Cookie管理器 — 负责Cookie的本地JSON存储和加载

    Cookie 存储为 Fernet 加密文件（兼容旧明文 JSON 读取），不绑定用户 ID。
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def _encrypt_content(plain_text: str) -> bytes:
        """Fernet 加密后加 FERNET: 前缀。"""
        try:
            from src.infrastructure.common.security.encryption import EncryptionManager
            encrypted = EncryptionManager.encrypt_data(plain_text.encode("utf-8"), _COOKIE_KEY_NAME)
            return _ENCRYPTED_PREFIX + base64.b64encode(encrypted)
        except Exception as e:
            logger.error("Cookie 加密失败，已拒绝明文落盘: %s", e)
            raise RuntimeError("Cookie 加密失败，无法安全保存 Cookie。") from e

    @staticmethod
    def _decrypt_content(raw: bytes) -> str:
        """解密 Fernet 内容；若非加密格式则原样返回。"""
        if raw.startswith(_ENCRYPTED_PREFIX):
            try:
                from src.infrastructure.common.security.encryption import EncryptionManager
                encrypted = base64.b64decode(raw[len(_ENCRYPTED_PREFIX):])
                return EncryptionManager.decrypt_data(encrypted, _COOKIE_KEY_NAME).decode("utf-8")
            except Exception as e:
                logger.warning("Cookie 解密失败: %s", e)
                return ""
        return raw.decode("utf-8")

    # ── 写入 ──────────────────────────────────────────────

    def save_cookie(
        self,
        platform_username: str,
        platform: str,
        cookie_data: Dict[str, Any],
        profile_folder_name: Optional[str] = None
    ) -> str:
        """保存Cookie（明文JSON）

        Returns:
            Cookie文件路径

        Raises:
            ValueError: 参数无效
            OSError: 文件保存失败
        """
        if not platform_username or not platform:
            raise ValueError("平台用户名和平台名称不能为空")
        if not (profile_folder_name and profile_folder_name.strip()):
            raise ValueError("profile_folder_name 不能为空")

        account_dir = PathManager.get_platform_account_dir(platform, platform_username, profile_folder_name)
        cookie_file = str(account_dir / COOKIE_FILENAME)

        try:
            os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
            plain_json = json.dumps(cookie_data, ensure_ascii=False, indent=2)
            new_content = self._encrypt_content(plain_json)
            new_hash = hashlib.md5(new_content).hexdigest()
            if os.path.exists(cookie_file):
                try:
                    with open(cookie_file, 'rb') as f:
                        existing = f.read()
                    existing_hash = hashlib.md5(existing).hexdigest()
                    if existing_hash == new_hash:
                        self.logger.debug(
                            "Cookie内容未变化，跳过写盘: 账号=%s, 平台=%s",
                            platform_username, platform,
                        )
                        return cookie_file
                except Exception:
                    pass
            import tempfile
            dir_name = os.path.dirname(cookie_file)
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            try:
                with os.fdopen(fd, 'wb') as tmp_f:
                    tmp_f.write(new_content)
                    tmp_f.flush()
                    os.fsync(tmp_f.fileno())
                os.replace(tmp_path, cookie_file)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            self.logger.info(
                "保存Cookie成功: 账号=%s, 平台=%s, 路径=%s",
                platform_username, platform, cookie_file,
            )
            return cookie_file
        except Exception as e:
            self.logger.error("保存Cookie失败: %s", e)
            raise

    # ── 读取 ──────────────────────────────────────────────

    def load_cookie(
        self,
        platform_username: str,
        platform: str,
        profile_folder_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """从账号目录下的 cookies.json 加载 Cookie。"""
        if not platform_username or not platform:
            self.logger.warning("平台用户名或平台名称为空")
            return None

        has_profile = profile_folder_name and str(profile_folder_name).strip()
        if not has_profile:
            self.logger.warning(
                "Cookie路径不可用(缺少 profile_folder_name): 账号=%s, 平台=%s",
                platform_username, platform,
            )
            return None

        try:
            account_dir = PathManager.get_platform_account_dir(platform, platform_username, profile_folder_name)
        except ValueError as e:
            self.logger.warning("无法解析账号目录: %s", e)
            return None

        cookies_path = account_dir / COOKIE_FILENAME
        data = self._read_json(str(cookies_path))
        if data:
            self.logger.info(
                "加载Cookie成功(cookies.json): 账号=%s, 平台=%s", platform_username, platform,
            )
            return data

        self.logger.warning(
            "Cookie文件不存在: 账号=%s, 平台=%s, 目录=%s, 请先双击打开该账号浏览器并登录",
            platform_username, platform, account_dir,
        )
        return None

    # ── 辅助方法 ──────────────────────────────────────────

    def delete_cookie(
        self,
        platform_username: str,
        platform: str,
        profile_folder_name: Optional[str] = None
    ) -> bool:
        """删除Cookie文件"""
        if not (profile_folder_name and profile_folder_name.strip()):
            self.logger.debug("delete_cookie: 缺少 profile_folder_name，跳过")
            return False

        account_dir = PathManager.get_platform_account_dir(platform, platform_username, profile_folder_name)
        fpath = str(account_dir / COOKIE_FILENAME)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
                self.logger.info("删除Cookie文件: %s", fpath)
                return True
            except Exception as e:
                self.logger.error("删除Cookie文件失败: %s", e)
        return False

    def cookie_exists(
        self,
        platform_username: str,
        platform: str,
        profile_folder_name: Optional[str] = None
    ) -> bool:
        """检查是否存在 cookies.json"""
        if not (profile_folder_name and profile_folder_name.strip()):
            return False
        account_dir = PathManager.get_platform_account_dir(platform, platform_username, profile_folder_name)
        return os.path.exists(str(account_dir / COOKIE_FILENAME))

    def get_cookie_path(
        self,
        platform_username: str,
        platform: str,
        profile_folder_name: Optional[str] = None
    ) -> str:
        """获取Cookie文件路径（返回 cookies.json 的路径）"""
        if not (profile_folder_name and profile_folder_name.strip()):
            return ""
        account_dir = PathManager.get_platform_account_dir(platform, platform_username, profile_folder_name)
        return str(account_dir / COOKIE_FILENAME)

    def merge_storage_state_into_flat_cookies(
        self,
        platform_username: str,
        platform: str,
        profile_folder_name: Optional[str],
        flat_cookies: Dict[str, Any],
    ) -> Dict[str, str]:
        """将 browser/storage_state.json 中尚未出现在 flat_cookies 里的项并入（仅补充 name）。

        持久化 Chromium Profile 里可能仍有完整登录态，而 cookies.json 只是某次导出的子集；
        「刷新登录状态」仅读 cookies.json 做 HTTP 校验时会误判离线，故校验前合并 Playwright 快照。

        约束（避免浏览器内退出后误判在线）：
        - cookies.json 比 storage_state.json 新时，以 cookies.json 为准，不再合并；
        - cookies.json 已无会话 Cookie 时，不从 storage_state 补全会话类 Cookie。
        """
        merged: Dict[str, str] = {}
        for k, v in (flat_cookies or {}).items():
            if k and v is not None:
                merged[str(k)] = v if isinstance(v, str) else str(v)

        if not (platform_username and platform and profile_folder_name and str(profile_folder_name).strip()):
            return merged

        try:
            account_dir = PathManager.get_platform_account_dir(platform, platform_username, profile_folder_name)
        except ValueError:
            return merged

        cookies_path = account_dir / COOKIE_FILENAME
        state_path = account_dir / "browser" / "storage_state.json"
        if not state_path.is_file():
            return merged

        if cookies_path.is_file():
            try:
                cookie_mtime = cookies_path.stat().st_mtime
                state_mtime = state_path.stat().st_mtime
                if cookie_mtime >= state_mtime:
                    logger.debug(
                        "HTTP 校验跳过 storage_state 合并: cookies.json 不早于快照 (%s)",
                        state_path,
                    )
                    return merged
            except OSError:
                pass

        allow_session_merge = flat_cookies_have_session(merged, platform)
        session_names = _session_cookie_names_for_platform(platform)

        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("读取 storage_state 失败: %s — %s", state_path, e)
            return merged

        cookies = state.get("cookies") if isinstance(state, dict) else None
        if not isinstance(cookies, list):
            return merged

        added = 0
        skipped_session = 0
        for c in cookies:
            if not isinstance(c, dict):
                continue
            name = c.get("name")
            if not name or name in merged:
                continue
            if not allow_session_merge and name in session_names:
                skipped_session += 1
                continue
            val = c.get("value")
            if val is None:
                continue
            merged[name] = val if isinstance(val, str) else str(val)
            added += 1

        if added:
            logger.debug("HTTP 校验合并 storage_state: 补充 %s 个 Cookie (%s)", added, state_path)
        if skipped_session:
            logger.debug(
                "HTTP 校验跳过 storage_state 中 %s 个会话 Cookie（cookies.json 已无会话）",
                skipped_session,
            )

        return merged

    # ── 内部工具 ──────────────────────────────────────────

    @classmethod
    def _read_json(cls, path: str) -> Optional[dict]:
        """读取 Cookie 文件（自动检测加密/明文格式），失败返回 None。"""
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'rb') as f:
                raw = f.read()
            if not raw:
                return None
            text = cls._decrypt_content(raw)
            if not text:
                return None
            data = json.loads(text)
            if isinstance(data, dict) and data:
                return data
            return None
        except FileNotFoundError:
            logger.debug("Cookie 文件不存在: %s", path)
        except json.JSONDecodeError as e:
            logger.warning("Cookie 文件 JSON 解析失败（可能已损坏）: %s — %s", path, e)
        except Exception as e:
            logger.error("读取 Cookie 文件时发生未知错误: %s — %s", path, e, exc_info=True)
        return None
