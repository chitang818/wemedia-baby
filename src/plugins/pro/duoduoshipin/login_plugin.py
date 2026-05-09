from typing import Dict, Any, Optional
import logging

from src.plugins.core.interfaces.login_plugin import LoginPluginInterface, LoginResult

logger = logging.getLogger(__name__)


class DuoduoshipinLoginPlugin(LoginPluginInterface):
    @property
    def platform_id(self) -> str:
        return "duoduoshipin"

    @property
    def platform_name(self) -> str:
        return "多多视频"

    @property
    def login_url(self) -> str:
        return "https://live.pinduoduo.com/login/anchor"

    @property
    def creator_home_url(self) -> str:
        return "https://live.pinduoduo.com/creator/index"

    @property
    def cookie_domain(self) -> str:
        return ".pinduoduo.com"

    async def check_login_status(self, context) -> bool:
        """检查多多视频登录状态"""
        try:
            cookies = await context.cookies()
            cookie_dict = {c['name']: c['value'] for c in cookies}

            has_pass_id = 'PASS_ID' in cookie_dict
            has_access_token = 'PDDAccessToken' in cookie_dict
            has_user_id = 'pdd_user_id' in cookie_dict

            if has_pass_id and (has_access_token or has_user_id):
                return True

            return False

        except Exception as e:
            logger.error(f"[{self.platform_name}] 检查登录状态失败: {e}", exc_info=True)
            return False

    async def extract_user_info(self, context) -> LoginResult:
        """提取多多视频账号信息"""
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
                    'div[class*="username"]',
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

        调用多多视频创作者中心 API 验证 Cookie 是否有效。
        """
        try:
            headers = {
                'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://live.pinduoduo.com/',
                'Origin': 'https://live.pinduoduo.com',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
            cookie_str = '; '.join([f'{k}={v}' for k, v in cookies.items()])
            headers['Cookie'] = cookie_str

            async with session.get(
                'https://live.pinduoduo.com/api/creator/userInfo',
                headers=headers,
                timeout=10
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get('success') or data.get('result'):
                        user_data = data.get('result', {})
                        uname = user_data.get('nickName', '') or user_data.get('nick', '')
                        return LoginResult(
                            success=True,
                            nickname=uname,
                            error_message=None
                        )
                    return LoginResult(
                        success=False,
                        error_message="Cookie 已失效，多多视频 API 返回未登录"
                    )
        except Exception as e:
            logger.warning(f"[{self.platform_name}] HTTP Cookie 验证异常: {e}")

        return LoginResult(
            success=False,
            error_message="HTTP Cookie 验证失败"
        )
