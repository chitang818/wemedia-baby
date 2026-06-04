"""Synchronize Xiaohongshu account state from a detached Chrome profile."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from src.infrastructure.browser.chromium_cookie_reader import (
    ChromiumCookieReadError,
    ChromiumCookieReader,
)
from src.infrastructure.browser.detached_chrome_launcher import DetachedChromeLauncher
from src.services.account.xhs_profile_identity_reader import XhsProfileIdentityReader

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class XhsProfileSyncResult:
    account_id: int
    success: bool
    status: str
    nickname: Optional[str] = None
    error: Optional[str] = None
    profile_in_use: bool = False


class XhsProfileSyncService:
    """Reads XHS cookies from a closed Chrome profile and updates account DB state."""

    XHS_DOMAINS = ("xiaohongshu.com",)
    SESSION_COOKIES = {
        "customer-sso-sid",
        "access-token-creator.xiaohongshu.com",
        "galaxy_creator_session_id",
        "galaxy.creator.beaker.session.id",
    }

    def __init__(
        self,
        account_manager: Any,
        *,
        cookie_reader: Optional[ChromiumCookieReader] = None,
        identity_reader: Optional[XhsProfileIdentityReader] = None,
    ) -> None:
        self.account_manager = account_manager
        self.cookie_reader = cookie_reader or ChromiumCookieReader()
        self.identity_reader = identity_reader or XhsProfileIdentityReader()

    async def sync_account(self, account_id: int) -> XhsProfileSyncResult:
        if not self.account_manager:
            return XhsProfileSyncResult(account_id, False, "offline", error="账号管理器不可用")

        await self.account_manager.ensure_account_has_profile_folder(account_id)
        account = await self.account_manager.get_account_by_id(account_id)
        if not account:
            return XhsProfileSyncResult(account_id, False, "offline", error="账号不存在")

        platform = str(account.get("platform") or "")
        if platform != "xiaohongshu":
            return XhsProfileSyncResult(account_id, False, "offline", error="仅支持小红书账号")

        username = str(account.get("platform_username") or "")
        profile_folder_name = str(account.get("profile_folder_name") or "").strip()
        if not profile_folder_name:
            return XhsProfileSyncResult(account_id, False, "offline", error="账号缺少 Profile 目录")

        user_data_dir = DetachedChromeLauncher.get_user_data_dir(
            platform=platform,
            platform_username=username,
            profile_folder_name=profile_folder_name,
        )

        if DetachedChromeLauncher.is_profile_in_use(user_data_dir):
            return XhsProfileSyncResult(
                account_id,
                False,
                str(account.get("login_status") or "offline"),
                error="请先关闭该小红书账号的 Chrome 窗口，再同步登录状态",
                profile_in_use=True,
            )

        try:
            cookies = await self._read_profile_cookies(user_data_dir)
        except ChromiumCookieReadError as e:
            logger.warning("读取小红书 Chrome Profile Cookie 失败: %s", e)
            return XhsProfileSyncResult(account_id, False, "offline", error=str(e))

        if not cookies:
            await self.account_manager.update_account_login_status(account_id, "offline")
            return XhsProfileSyncResult(
                account_id,
                False,
                "offline",
                error="未读取到小红书登录 Cookie，请确认已在普通 Chrome 中完成登录",
            )

        profile_identity = await self._read_profile_identity(user_data_dir)

        if self._has_session_cookie(cookies):
            await self.account_manager.update_cookie(account_id, cookies)
            nickname = self._normalize_real_nickname(profile_identity.nickname)
            if nickname and nickname != username:
                await self.account_manager.update_platform_username(account_id, nickname)
            return XhsProfileSyncResult(account_id, True, "online", nickname=nickname)

        await self.account_manager.update_account_login_status(account_id, "offline")
        return XhsProfileSyncResult(
            account_id,
            False,
            "offline",
            error="未读取到小红书创作者平台关键登录 Cookie，请确认已在普通 Chrome 中完成登录",
        )

    async def _read_profile_cookies(self, user_data_dir: Path) -> dict[str, str]:
        import asyncio

        return await asyncio.to_thread(
            self.cookie_reader.read_cookie_dict,
            user_data_dir,
            domains=self.XHS_DOMAINS,
        )

    async def _read_profile_identity(self, user_data_dir: Path):
        import asyncio

        try:
            return await asyncio.to_thread(self.identity_reader.read_identity, user_data_dir)
        except Exception as e:
            logger.debug("读取小红书 Chrome Profile 本地身份信息失败: %s", e)
            from src.services.account.xhs_profile_identity_reader import XhsProfileIdentity

            return XhsProfileIdentity()

    def _normalize_real_nickname(self, value: Any) -> Optional[str]:
        if not isinstance(value, str):
            return None
        nickname = value.strip()
        if not nickname:
            return None
        if nickname.startswith("小红书用户_"):
            return None
        blocked = ("待登录", "登录", "创作服务平台", "http://", "https://", "{", "}")
        if any(item in nickname for item in blocked):
            return None
        if len(nickname) > 40:
            return None
        return nickname

    def _has_session_cookie(self, cookies: dict[str, str]) -> bool:
        return bool(set(cookies.keys()) & self.SESSION_COOKIES)
