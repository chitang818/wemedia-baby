# -*- coding: utf-8 -*-
"""
更新账号信息模块（插件式）
文件路径：src/services/account/account_info_updater.py
功能：从已打开的浏览器上下文中更新账号昵称、Cookie 及登录状态。
流程：先调用登录状态校验模块判定是否在线，若在线则更新登录状态、Cookie、平台昵称等。

与 Playwright 侧约定：打开已有账号浏览器后的静默更新、右键「更新账号信息」、关闭前同步均调用
``update_account_info_from_context``；手动入口仅在该账号已在 _active_browsers 中注册时触发，避免误用其他账号上下文。
"""

from typing import Optional, Any, Tuple, Dict
import logging

from src.services.account.login_status_verifier import verify_login_status

logger = logging.getLogger(__name__)


async def update_account_info_from_context(
    context: Any,
    account_id: int,
    platform_username: str,
    platform: str,
    account_manager: Any,
    *,
    reuse_http_verify_result: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    从当前浏览器上下文静默更新账号的 Cookie、昵称、登录状态。

    流程：先从 context 取 Cookie，调用登录状态校验模块判定是否在线；
    若在线则更新登录状态、Cookie、平台昵称；若离线则仅更新登录状态（及 Cookie 以保持同步）。

    Args:
        context: Playwright BrowserContext（已打开且已加载平台页）
        account_id: 账号 ID（整数）
        platform_username: 当前库中的平台昵称（用于对比是否变更）
        platform: 平台 ID（如 douyin, kuaishou）
        account_manager: AccountManagerAsync 实例，用于写回 Cookie/昵称/状态
        reuse_http_verify_result: 若调用方刚用同一套 Cookie 做过 ``verify_login_status`` 且已确认在线，
            传入其返回 dict 可跳过重复 HTTP 鉴权，加快手动登录后的更新。

    Returns:
        (new_nickname, new_status): 若昵称有更新则为新昵称否则 None；
        若登录状态有更新则为 "online"/"offline" 否则 None。供调用方发信号刷新 UI。
    """
    new_nickname: Optional[str] = None
    new_status: Optional[str] = None
    try:
        from config.feature_flags import USE_PLUGIN_SYSTEM
        if not USE_PLUGIN_SYSTEM or not account_manager:
            return (None, None)

        # 1. 从 context 取 Cookie，供校验与写回
        cookies_raw = await context.cookies()
        if not cookies_raw:
            logger.debug("静默更新: 无 Cookie，跳过 account_id=%s", account_id)
            return (None, None)
        cookie_dict = {c["name"]: c["value"] for c in cookies_raw}

        # 2. 登录态：优先复用调用方刚做过的 HTTP 校验（避免同一轮流程内二次请求，省数秒）
        if (
            reuse_http_verify_result is not None
            and reuse_http_verify_result.get("is_valid", True)
            and reuse_http_verify_result.get("is_logged_in")
        ):
            result = reuse_http_verify_result
            is_logged_in = True
            logger.debug(
                "静默更新: 复用本轮 HTTP 校验结果，跳过重复 verify (account_id=%s)",
                account_id,
            )
        else:
            result = await verify_login_status(
                platform=platform,
                cookies=cookie_dict,
                account_id=account_id,
                account_name=platform_username,
                timeout=15,
            )
            is_logged_in = result.get("is_logged_in", False)
        status = "online" if is_logged_in else "offline"

        # 3. 更新登录状态（与浏览器/插件校验结果一致，离线时也写 DB 并刷新 UI）
        try:
            await account_manager.update_account_login_status(account_id, status)
            new_status = status
            if status == "offline":
                logger.info("静默更新: 账号已判为离线，已更新登录状态 (account_id=%s)", account_id)
            else:
                logger.debug("静默更新: 登录状态 %s (account_id=%s)", status, account_id)
        except Exception as e:
            logger.warning("静默更新登录状态失败: %s", e)

        # 4. 若在线：更新 Cookie 与平台昵称
        if is_logged_in:
            try:
                await account_manager.update_cookie(account_id, cookie_dict)
                logger.debug("静默更新: Cookie 已同步 account_id=%s", account_id)
            except Exception as e:
                logger.debug("静默更新 Cookie 失败: %s", e)

            # 优先页面 extract_user_info；DOM 失败或与库一致时，用 HTTP 鉴权返回的昵称兜底
            try:
                from src.plugins.core.plugin_manager import PluginManager
                plugin = PluginManager.get_login_plugin(platform)
                if plugin:
                    res = await plugin.extract_user_info(context)
                    if res and res.nickname:
                        nick = (res.nickname or "").strip()
                        if nick and nick != platform_username:
                            await account_manager.update_platform_username(account_id, nick)
                            new_nickname = nick
                            logger.info("静默更新: 昵称 %s -> %s (account_id=%s)", platform_username, nick, account_id)
            except Exception as e:
                logger.debug("静默更新昵称失败: %s", e)

            if new_nickname is None:
                http_nick = result.get("username")
                if isinstance(http_nick, str):
                    http_nick = (http_nick.strip() or None)
                else:
                    http_nick = None
                if http_nick and http_nick != platform_username:
                    try:
                        await account_manager.update_platform_username(account_id, http_nick)
                        new_nickname = http_nick
                        logger.info(
                            "静默更新: 昵称取自 HTTP 鉴权 %s -> %s (account_id=%s)",
                            platform_username,
                            http_nick,
                            account_id,
                        )
                    except Exception as e:
                        logger.debug("静默更新 HTTP 昵称写库失败: %s", e)
        else:
            # 离线时仍写回 Cookie，便于下次校验使用；勿把登录状态强行改为 online
            try:
                await account_manager.update_cookie(
                    account_id, cookie_dict, update_status=False
                )
                logger.debug("静默更新: Cookie 已同步(离线) account_id=%s", account_id)
            except Exception as e:
                logger.debug("静默更新 Cookie 失败: %s", e)

        return (new_nickname, new_status)
    except Exception as e:
        err_msg = str(e) or ""
        if "closed" in err_msg.lower() or "Target page" in err_msg:
            logger.debug("静默更新账号信息异常(浏览器已关闭): %s", e)
        else:
            logger.warning("静默更新账号信息异常: %s", e)
        return (new_nickname, new_status)
