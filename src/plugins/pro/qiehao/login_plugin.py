from typing import Dict, Any, Optional
import logging

from src.plugins.core.interfaces.login_plugin import LoginPluginInterface, LoginResult

logger = logging.getLogger(__name__)


class QiehaoLoginPlugin(LoginPluginInterface):
    @property
    def platform_id(self) -> str:
        return "qiehao"

    @property
    def platform_name(self) -> str:
        return "企鹅号"

    @property
    def login_url(self) -> str:
        return "https://om.qq.com/"

    @property
    def creator_home_url(self) -> str:
        return "https://om.qq.com/"

    @property
    def cookie_domain(self) -> str:
        return ".qq.com"

    async def check_login_status(self, context) -> bool:
        """检查企鹅号登录状态"""
        try:
            cookies = await context.cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}

            has_omtoken = 'omtoken' in cookie_dict
            has_uin = 'uin' in cookie_dict
            has_skey = 'skey' in cookie_dict
            has_omuid = 'omuid' in cookie_dict

            if has_omtoken or (has_uin and has_skey) or has_omuid:
                return True

            return False

        except Exception as e:
            logger.error(f"[{self.platform_name}] 检查登录状态失败: {e}", exc_info=True)
            return False

    async def extract_user_info(self, context) -> LoginResult:
        """提取企鹅号账号信息"""
        nickname = None
        cookies = await context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}

        try:
            pages = context.pages
            if pages:
                page = pages[0]

                selectors = [
                    'div[class*="user-name"]',
                    'span[class*="user-name"]',
                    'div[class*="nickname"]',
                    'span[class*="nickname"]',
                    'div[class*="account-name"]',
                    'a[class*="user-name"]',
                    'div[class*="header"] span[class*="name"]',
                ]

                for selector in selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            text = await element.inner_text()
                            if text and len(text.strip()) > 0:
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

        调用企鹅号后台 API 验证 Cookie 是否有效。
        """
        try:
            headers = {
                'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://om.qq.com/',
                'Origin': 'https://om.qq.com',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
            cookie_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
            headers['Cookie'] = cookie_str

            async with session.get(
                'https://om.qq.com/cgi-bin/user/get_user_info',
                headers=headers,
                timeout=10
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('ret') in (0, '0') or data.get('code') in (0, '0'):
                        user_data = data.get('data', {})
                        uname = user_data.get('nick', '') or user_data.get('name', '')
                        return LoginResult(
                            success=True,
                            nickname=uname,
                            error_message=None
                        )
                    return LoginResult(
                        success=False,
                        error_message="Cookie 已失效，企鹅号 API 返回未登录"
                    )
        except Exception as e:
            logger.warning(f"[{self.platform_name}] HTTP Cookie 验证异常: {e}")

        return LoginResult(
            success=False,
            error_message="HTTP Cookie 验证失败"
        )
