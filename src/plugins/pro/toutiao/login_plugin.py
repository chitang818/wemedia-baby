from typing import Dict, Any, Optional
import json
import logging

from src.plugins.core.interfaces.login_plugin import LoginPluginInterface, LoginResult
from src.plugins.core.wait_helper import PluginWaitHelper
from .scripts import LOGIN_DETECTION_SCRIPT

logger = logging.getLogger(__name__)


class ToutiaoLoginPlugin(LoginPluginInterface):
    @property
    def platform_id(self) -> str:
        return "toutiao"

    @property
    def platform_name(self) -> str:
        return "头条号"

    @property
    def login_url(self) -> str:
        return "https://mp.toutiao.com/auth/page/login"

    @property
    def creator_home_url(self) -> str:
        return "https://mp.toutiao.com/profile_v4/index"

    @property
    def cookie_domain(self) -> str:
        return ".toutiao.com"

    async def check_login_status(self, context) -> bool:
        """检查头条号登录状态"""
        try:
            cookies = await context.cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}

            has_sessionid = 'sessionid' in cookie_dict
            has_sso = 'sso_uid_tt' in cookie_dict

            pages = context.pages
            if pages:
                page = pages[0]
                if "mp.toutiao.com" in page.url:
                    try:
                        result_json = await page.evaluate(LOGIN_DETECTION_SCRIPT)
                        result = json.loads(result_json)
                        is_logged_in = result.get("loggedIn", False)
                        return is_logged_in
                    except Exception as e:
                        logger.debug(f"[{self.platform_name}] 脚本检测登录状态异常: {e}")

            return has_sessionid or has_sso

        except Exception as e:
            logger.error(f"[{self.platform_name}] 检查登录状态失败: {e}", exc_info=True)
            return False

    async def extract_user_info(self, context) -> LoginResult:
        """提取头条号账号信息"""
        nickname = None
        cookies = await context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}

        try:
            pages = context.pages
            target_page = None

            for page in pages:
                if "mp.toutiao.com" in page.url:
                    target_page = page
                    break

            if not target_page:
                if pages:
                    target_page = pages[0]
                else:
                    target_page = await context.new_page()

            current_url = target_page.url
            logger.debug(f"[{self.platform_name}] 当前页面: {current_url}")

            if "mp.toutiao.com" not in current_url or "/login" in current_url or "/auth/" in current_url:
                try:
                    await target_page.goto(
                        "https://mp.toutiao.com/profile_v4/index",
                        wait_until="domcontentloaded", timeout=15000,
                    )
                except Exception as e:
                    logger.warning(f"[{self.platform_name}] 跳转失败: {e}")

            await PluginWaitHelper.wait_for_condition(
                target_page,
                lambda: self._login_script_has_username(target_page),
                timeout_ms=3000,
                poll_interval_ms=500,
            )

            # 通过脚本提取昵称
            try:
                result_json = await target_page.evaluate(LOGIN_DETECTION_SCRIPT)
                result = json.loads(result_json)
                if result.get("debug"):
                    logger.debug(f"[{self.platform_name}] 脚本调试信息: {result.get('debug')}")
                nickname = result.get("username")
                if nickname:
                    logger.info(f"[{self.platform_name}] 脚本提取昵称: {nickname}")
            except Exception as e:
                logger.debug(f"[{self.platform_name}] 脚本提取昵称失败: {e}")

            # 降级策略：通过 Playwright 选择器提取
            if not nickname:
                logger.info(f"[{self.platform_name}] 脚本提取失败，尝试 Playwright 原生提取")
                selectors = [
                    '.user-name', '.account-name', '.header-user-name',
                    'span[class*="nickname"]', 'div[class*="nickname"]',
                ]
                for sel in selectors:
                    try:
                        element = await target_page.query_selector(sel)
                        if element:
                            text = await element.inner_text()
                            if text and text.strip():
                                nickname = text.strip()
                                logger.info(f"[{self.platform_name}] 通过 {sel} 提取到昵称: {nickname}")
                                break
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"[{self.platform_name}] 提取用户信息失败: {e}", exc_info=True)

        success = nickname is not None
        if success:
            logger.info(f"[{self.platform_name}] 用户信息提取成功: {nickname}")
        else:
            logger.warning(f"[{self.platform_name}] 未能提取到昵称")

        return LoginResult(
            success=success,
            cookies=cookie_dict,
            nickname=nickname,
            error_message=None if success else "未能提取到账号昵称",
        )

    async def _login_script_has_username(self, page) -> bool:
        try:
            result_json = await page.evaluate(LOGIN_DETECTION_SCRIPT)
            result = json.loads(result_json)
            return bool(result.get("username"))
        except Exception:
            return False

    async def verify_cookie_http(
        self, session, cookies: Dict[str, str], user_agent: Optional[str] = None
    ) -> LoginResult:
        """通过 HTTP 请求验证头条号 Cookie 有效性。"""
        cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
        headers = {
            'User-Agent': user_agent or (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Cookie': cookie_str,
            'Referer': 'https://mp.toutiao.com/',
            'Origin': 'https://mp.toutiao.com',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept': 'application/json, text/plain, */*',
        }

        # 请求创作者中心首页，检查是否跳转到登录页
        try:
            async with session.get(
                'https://mp.toutiao.com/profile_v4/index',
                headers=headers,
                timeout=10,
                allow_redirects=False,
            ) as response:
                if response.status in (301, 302):
                    location = (response.headers.get('Location') or '').lower()
                    if 'login' in location or 'auth' in location:
                        return LoginResult(
                            success=False,
                            error_message="登录已失效（已跳转登录页）",
                        )
                if response.status == 200:
                    logger.info(f"[{self.platform_name}] HTTP 验证通过（未跳转登录）")
                    return LoginResult(success=True, nickname=None, error_message=None)
                return LoginResult(
                    success=False,
                    error_message=f"验证失败: HTTP {response.status}",
                )
        except Exception as e:
            return LoginResult(
                success=False,
                error_message=f"验证异常: {str(e)}",
            )
