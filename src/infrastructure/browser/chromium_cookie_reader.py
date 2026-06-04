"""Read Chromium profile cookies without attaching to the browser."""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import shutil
import sqlite3
import tempfile
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)


class ChromiumCookieReadError(RuntimeError):
    """Raised when a Chromium cookie DB cannot be read safely."""


@dataclass(frozen=True)
class ChromiumCookie:
    name: str
    value: str
    domain: str
    path: str = "/"


class ChromiumCookieReader:
    """Best-effort Windows Chromium cookie reader for a closed user data dir."""

    COOKIE_DB_CANDIDATES = (
        "Default/Network/Cookies",
        "Default/Cookies",
    )

    def read_cookie_dict(
        self,
        user_data_dir: str | Path,
        *,
        domains: Iterable[str],
    ) -> dict[str, str]:
        cookies = self.read_cookies(user_data_dir, domains=domains)
        return {cookie.name: cookie.value for cookie in cookies if cookie.name and cookie.value}

    def read_cookies(
        self,
        user_data_dir: str | Path,
        *,
        domains: Iterable[str],
    ) -> list[ChromiumCookie]:
        profile_root = Path(user_data_dir)
        if not profile_root.exists():
            raise ChromiumCookieReadError(f"Chrome 用户目录不存在: {profile_root}")

        domain_filters = tuple(d.lower().lstrip(".") for d in domains if d)
        if not domain_filters:
            raise ChromiumCookieReadError("未指定 Cookie 域名过滤条件")

        master_key = self._load_master_key(profile_root)
        result: list[ChromiumCookie] = []
        seen: set[tuple[str, str, str]] = set()

        db_paths = [profile_root / rel for rel in self.COOKIE_DB_CANDIDATES]
        for db_path in db_paths:
            if not db_path.is_file():
                continue
            for cookie in self._read_cookie_db(db_path, master_key, domain_filters):
                key = (cookie.domain, cookie.path, cookie.name)
                if key in seen:
                    continue
                seen.add(key)
                result.append(cookie)

        return result

    def _read_cookie_db(
        self,
        db_path: Path,
        master_key: Optional[bytes],
        domain_filters: tuple[str, ...],
    ) -> list[ChromiumCookie]:
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(prefix="wemedia_chrome_cookies_", suffix=".sqlite", delete=False) as tmp:
                tmp_path = tmp.name
            shutil.copy2(db_path, tmp_path)
        except Exception as e:
            raise ChromiumCookieReadError(
                f"无法复制 Chrome Cookie 数据库，请先关闭该账号浏览器: {db_path}"
            ) from e

        cookies: list[ChromiumCookie] = []
        try:
            with sqlite3.connect(tmp_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT host_key, name, value, encrypted_value, path FROM cookies"
                ).fetchall()
            for row in rows:
                host = str(row["host_key"] or "")
                host_norm = host.lower().lstrip(".")
                if not any(host_norm == d or host_norm.endswith("." + d) for d in domain_filters):
                    continue
                name = str(row["name"] or "")
                value = str(row["value"] or "")
                encrypted = row["encrypted_value"]
                if not value and encrypted:
                    value = self._decrypt_cookie_value(bytes(encrypted), master_key)
                if name and value:
                    cookies.append(
                        ChromiumCookie(
                            name=name,
                            value=value,
                            domain=host,
                            path=str(row["path"] or "/"),
                        )
                    )
        except sqlite3.DatabaseError as e:
            raise ChromiumCookieReadError(f"Chrome Cookie 数据库读取失败: {db_path}") from e
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except OSError:
                    pass
        return cookies

    def _load_master_key(self, user_data_dir: Path) -> Optional[bytes]:
        local_state = user_data_dir / "Local State"
        if not local_state.is_file():
            return None
        try:
            data = json.loads(local_state.read_text(encoding="utf-8"))
            encrypted_key = data.get("os_crypt", {}).get("encrypted_key")
            if not encrypted_key:
                return None
            raw = base64.b64decode(encrypted_key)
            if raw.startswith(b"DPAPI"):
                raw = raw[5:]
            return self._dpapi_decrypt(raw)
        except Exception as e:
            logger.debug("读取 Chrome Local State 密钥失败: %s", e)
            return None

    def _decrypt_cookie_value(self, encrypted_value: bytes, master_key: Optional[bytes]) -> str:
        try:
            if encrypted_value.startswith((b"v10", b"v11")):
                if not master_key:
                    return ""
                nonce = encrypted_value[3:15]
                ciphertext = encrypted_value[15:]
                return AESGCM(master_key).decrypt(nonce, ciphertext, None).decode("utf-8", errors="ignore")
            return self._dpapi_decrypt(encrypted_value).decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug("Chrome Cookie 解密失败: %s", e)
            return ""

    @staticmethod
    def _dpapi_decrypt(data: bytes) -> bytes:
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32

        in_buffer = ctypes.create_string_buffer(data)
        in_blob = DATA_BLOB(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_char)))
        out_blob = DATA_BLOB()

        if not crypt32.CryptUnprotectData(
            ctypes.byref(in_blob),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(out_blob),
        ):
            raise ChromiumCookieReadError("Windows DPAPI 解密 Chrome Cookie 失败")
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32.LocalFree(out_blob.pbData)
