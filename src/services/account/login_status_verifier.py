"""
登录状态校验模块（独立）
文件路径：src/services/account/login_status_verifier.py
功能：仅负责调度各平台登录插件检查登录状态，不加载 Cookie、不写 DB、不关心批量与进度。

与账号页状态的关系（简要）：
- 本模块只返回 is_logged_in 等字段；是否写库由调用方决定。
- 写库与通知账号库 UI 请统一走 AccountManagerAsync.update_account_login_status：
  - 单点场景（发布列表前置检测掉线、浏览器静默更新、Playwright 判离线等）使用默认 publish_event=True，
    会发布 AccountUpdatedEvent，账号管理页通过 AccountOperationsService 订阅后 _schedule_reload。
  - 批量 HTTP 验证（AccountVerifier）使用 publish_event=False，避免 N 次事件风暴；表格由验证进度信号逐行更新，
    结束时页面仍会 reload 一次。
- AccountVerifier.verify_accounts_batch 内部已改为通过 account_manager.update_account_login_status(..., publish_event=False)。
"""

from typing import Dict, Any, Optional
import asyncio
import logging

import aiohttp

logger = logging.getLogger(__name__)


async def verify_login_status(
    platform: str,
    cookies: Dict[str, str],
    account_id: int,
    account_name: str,
    user_agent: Optional[str] = None,
    http_session: Optional[aiohttp.ClientSession] = None,
    timeout: int = 15,
) -> Dict[str, Any]:
    """
    通过平台插件校验账号登录状态（单一职责：调度插件）。

    Args:
        platform: 平台 ID (如 douyin, kuaishou)
        cookies: Cookie 字典
        account_id: 账号 ID
        account_name: 账号名称（平台昵称）
        user_agent: 可选 UA
        http_session: 可选 aiohttp 会话，不传则本函数内创建并在调用后关闭
        timeout: 插件验证超时秒数，默认 15

    Returns:
        与 AccountVerifier.verify_account_by_http 兼容的 result 字典：
        account_id, account_name, platform, is_valid, is_logged_in, username, error, method
    """
    result = {
        "account_id": account_id,
        "account_name": account_name,
        "platform": platform,
        "is_valid": False,
        "is_logged_in": False,
        "username": None,
        "error": None,
        "method": "http_plugin",
        "status_code": None,
    }
    own_session = None
    session = http_session

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            result["error"] = "事件循环不可用，跳过登录校验（应用可能正在退出）"
            result["is_valid"] = False
            logger.info(
                "账号 %s (ID: %s, 平台: %s) 校验跳过：事件循环不可用，应用可能正在退出",
                account_name, account_id, platform,
            )
            return result

        from src.plugins.core.plugin_manager import PluginManager
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.plugins.core.interfaces.login_plugin import AccountVerificationContext

        plugin = PluginManager.get_login_plugin(platform)
        if not plugin:
            result["error"] = f"不支持的平台或插件缺失: {platform}"
            return result

        if session is None or session.closed:
            own_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
            session = own_session

        context = AccountVerificationContext(
            account_id=account_id,
            account_name=account_name,
            platform=platform,
            cookies=cookies,
            user_agent=user_agent,
            http_session=session,
            service_locator=ServiceLocator(),
        )

        try:
            login_result = await asyncio.wait_for(
                plugin.verify_account_status(context),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            result["error"] = "插件验证超时（15秒无响应）"
            result["is_valid"] = False
            logger.warning(
                "账号 %s (ID: %s, 平台: %s) 插件验证超时",
                account_name, account_id, platform,
            )
            return result

        result["is_valid"] = login_result.is_valid
        result["is_logged_in"] = login_result.success
        result["username"] = login_result.nickname
        result["error"] = login_result.error_message

        if login_result.success:
            logger.info(
                "账号 %s (ID: %s, 平台: %s) 通过插件验证有效",
                account_name, account_id, platform,
            )
        else:
            logger.warning(
                "账号 %s (ID: %s, 平台: %s) 插件验证失效: %s",
                account_name, account_id, platform, login_result.error_message,
            )
    except Exception as e:
        result["error"] = f"插件验证异常: {str(e)}"
        result["is_valid"] = False
        logger.error(
            "验证账号 %s (ID: %s) 插件执行异常: %s",
            account_name, account_id, e,
            exc_info=True,
        )
    finally:
        if own_session and not own_session.closed:
            await own_session.close()

    return result
