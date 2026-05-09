from typing import Dict, Any, Optional
import json
import logging

from src.plugins.core.interfaces.login_plugin import LoginPluginInterface, LoginResult

logger = logging.getLogger(__name__)


class WeiboLoginPlugin(LoginPluginInterface):
    @property
    def platform_id(self) -> str:
        return "weibo"

    @property
    def platform_name(self) -> str:
        return "新浪微博"

    @property
    def login_url(self) -> str:
        return "https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog"

    @property
    def creator_home_url(self) -> str:
        return "https://weibo.com"

    @property
    def cookie_domain(self) -> str:
        return ".weibo.com"

    async def check_login_status(self, context) -> bool:
        """检查新浪微博登录状态"""
        try:
            cookies = await context.cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}

            if 'SUB' in cookie_dict and 'SUBP' in cookie_dict:
                return True

            return False

        except Exception as e:
            logger.error(f"[{self.platform_name}] 检查登录状态失败: {e}", exc_info=True)
            return False

    async def extract_user_info(self, context) -> LoginResult:
        """提取新浪微博账号信息"""
        nickname = None
        cookies = await context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}

        try:
            pages = context.pages
            if pages:
                page = pages[0]

                # 尝试通过 JS 脚本检测登录态并提取用户名
                try:
                    from .scripts import LOGIN_DETECTION_SCRIPT
                    result_str = await page.evaluate(LOGIN_DETECTION_SCRIPT)
                    result = json.loads(result_str)
                    if result.get("username"):
                        nickname = result["username"]
                        logger.info(f"[{self.platform_name}] 通过 JS 脚本提取到昵称: {nickname}")
                except Exception as e:
                    logger.debug(f"[{self.platform_name}] JS 脚本提取失败: {e}")

                # 回退到 DOM 选择器方式
                if not nickname:
                    selectors = [
                        'a[class*="name"] span',
                        'span[class*="screen_name"]',
                        'a[class*="ALink_none"] span',
                        'div[class*="Nav_user"] span',
                        'a[href*="/profile"] span',
                        'span[class*="userName"]',
                    ]

                    for selector in selectors:
                        try:
                            element = await page.query_selector(selector)
                            if element:
                                text = await element.inner_text()
                                if text and len(text.strip()) > 0 and '登录' not in text and '注册' not in text:
                                    nickname = text.strip()
                                    logger.info(f"[{self.platform_name}] 通过 {selector} 提取到昵称: {nickname}")
                                    break
                        except Exception:
                            continue

        except Exception as e:
            logger.error(f"[{self.platform_name}] 提取用户信息失败: {e}", exc_info=True)

        success = nickname is not None
        return LoginResult(
            success=success,
            cookies=cookie_dict,
            nickname=nickname,
            error_message=None if success else "未能提取到账号昵称"
        )

    async def verify_cookie_http(self, session, cookies: Dict[str, str], user_agent: Optional[str] = None) -> LoginResult:
        """
        通过 HTTP 验证 Cookie 有效性。

        调用微博 API https://weibo.com/ajax/profile/info 来验证。
        """
        try:
            headers = {
                'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://weibo.com',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
            cookie_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
            headers['Cookie'] = cookie_str

            # 微博 AJAX API 获取当前登录用户信息
            async with session.get(
                'https://weibo.com/ajax/login/status',
                headers=headers,
                timeout=10
            ) as resp:
                if resp.status != 200:
                    return LoginResult(
                        success=False,
                        error_message=f"HTTP 验证失败: 状态码 {resp.status}",
                    )
                data = await resp.json()
                if data.get('ok') in (1, '1'):
                    user_info = data.get('data', {})
                    uname = user_info.get('screen_name', '') or user_info.get('name', '')
                    return LoginResult(
                        success=True,
                        nickname=uname,
                        error_message=None
                    )
                return LoginResult(
                    success=False,
                    error_message=data.get('msg') or data.get('message') or "Cookie 已失效，微博 API 返回未登录",
                )
        except Exception as e:
            logger.warning(f"[{self.platform_name}] HTTP Cookie 验证异常: {e}")

        return LoginResult(
            success=False,
            error_message="HTTP Cookie 验证失败"
        )
