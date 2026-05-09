from typing import Any, Dict, Optional
import json
import logging

from src.plugins.core.interfaces.login_plugin import LoginPluginInterface, LoginResult
from .selectors import Selectors

logger = logging.getLogger(__name__)


class DouyinLoginPlugin(LoginPluginInterface):
    """抖音登录插件。掉线原因由 LoginResult.error_message 提供，主程序已写入任务失败原因。"""

    @property
    def platform_id(self) -> str:
        return "douyin"
    
    @property
    def platform_name(self) -> str:
        return "抖音"
    
    @property
    def login_url(self) -> str:
        return "https://creator.douyin.com/"
    
    async def check_login_status(self, context) -> bool:
        """检查登录状态。

        多标签（创作者中心 + 环境信息 about:blank）时不能用 pages[0]：与快手/视频号一致，优先创作者域标签再做 DOM。
        """
        try:
            cookies = await context.cookies()
            has_session = any(c["name"] in Selectors.REQUIRED_COOKIES for c in cookies)

            pages = list(getattr(context, "pages", []) or [])

            def _safe_url(p) -> str:
                try:
                    return (p.url or "").strip()
                except Exception:
                    return ""

            ordered = []
            for p in pages:
                u = _safe_url(p)
                if "creator.douyin.com" in u:
                    ordered.append(p)
            for p in pages:
                if p in ordered:
                    continue
                u = _safe_url(p)
                if "douyin.com" in u or "amemv.com" in u:
                    ordered.append(p)

            for page in ordered:
                u = _safe_url(page)
                if "douyin.com" not in u and "amemv.com" not in u:
                    continue
                if not has_session:
                    return False

                indicators = Selectors.USER_INFO["NICKNAME"] + Selectors.USER_INFO["AVATAR"]
                for selector in indicators:
                    try:
                        if await page.locator(selector).count() > 0:
                            return True
                    except Exception:
                        continue

                for keyword in ["/manage/", "/content/", "/home"]:
                    if keyword in u:
                        return True
            return False
        except Exception as e:
            logger.warning(f"抖音登录检测失败: {e}")
            return False
    
    async def extract_user_info(self, context) -> LoginResult:
        """提取用户信息"""
        nickname = None
        cookies = await context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}
        
        try:
            pages = list(getattr(context, "pages", []) or [])
            page = None
            for p in pages:
                try:
                    u = (p.url or "").strip()
                except Exception:
                    continue
                if "creator.douyin.com" in u:
                    page = p
                    break
            if page is None:
                for p in pages:
                    try:
                        u = (p.url or "").strip()
                    except Exception:
                        continue
                    if "douyin.com" in u:
                        page = p
                        break
            if page is None and pages:
                page = pages[0]
            if pages and page is not None:
                current_url = page.url
                
                # 确保在相关页面
                if "douyin.com" in current_url:
                    # 1. 尝试使用 Playwright Python 端原生选择器提取昵称
                    
                    # 优先查找特定的元素，如 .name-_lSSDc 或者 class^="name-" 且包含文本的div
                    high_priority_selectors = [
                        "div.name-_lSSDc",
                        "div[class^='name-']",
                        ".user-info .name"
                    ]
                    
                    # 全部的候选选择器
                    all_selectors = high_priority_selectors + Selectors.USER_INFO["NICKNAME"]
                    
                    for selector in all_selectors:
                        try:
                            loc = page.locator(selector)
                            count = await loc.count()
                            if count > 0:
                                # 可能匹配到多个，取第一个可见且符合逻辑的
                                for i in range(count):
                                    text = await loc.nth(i).inner_text()
                                    if text and "登录" not in text:
                                        text = text.strip()
                                        if text:
                                            nickname = text
                                            break
                                if nickname:
                                    break
                        except Exception:
                            continue
                            
                    # 2. 如果页面较新结构变动，作为备用：通过精简的一段 JS 从全局变量中安全提取
                    if not nickname:
                        logger.info("DOM 提取昵称兜底：尝试从全局变量对象提取")
                        extract_js = '''() => {
                            for (let varName of ['__INITIAL_STATE__', '__USER_INFO__', 'USER_INFO', 'userInfo']) {
                                if (window[varName] && window[varName].nickname) {
                                    return window[varName].nickname;
                                }
                            }
                            return null;
                        }'''
                        nickname = await page.evaluate(extract_js)
        except Exception as e:
            logger.warning(f"提取用户信息异常: {e}")
            
        success = nickname is not None
        return LoginResult(
            success=success,
            cookies=cookie_dict,
            nickname=nickname,
            error_message=None if success else "未能提取到昵称"
        )
    
    def _douyin_pc_user_api_success(self, data: Dict[str, Any]) -> bool:
        """创作者 PC 用户信息接口业务成功（兼容数值 0 与字符串 \"0\"）。"""
        code = data.get("status_code")
        if code in (0, "0"):
            return True
        if data.get("code") in (0, "0"):
            return True
        return False

    def _extract_douyin_pc_user_payload(self, data: Dict[str, Any]) -> tuple:
        """从接口 JSON 中取出 user_info 块与昵称、uid（兼容 data 嵌套）。"""
        user_info = data.get("user_info") if isinstance(data.get("user_info"), dict) else {}
        inner = data.get("data")
        if isinstance(inner, dict):
            if not user_info:
                user_info = inner.get("user_info") if isinstance(inner.get("user_info"), dict) else {}
            if not user_info:
                u = inner.get("user")
                if isinstance(u, dict):
                    user_info = u
                elif not inner.get("user_info"):
                    user_info = inner
        nickname = (user_info.get("nickname") or user_info.get("unique_id") or "").strip() or None
        uid = (
            data.get("uid")
            or user_info.get("uid")
            or user_info.get("user_id")
            or user_info.get("sec_user_id")
        )
        return user_info, nickname, uid

    async def verify_cookie_http(self, session, cookies: Dict[str, str], user_agent: Optional[str] = None) -> LoginResult:
        """通过 HTTP 请求验证抖音 Cookie"""
        cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
        headers = {
            'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Cookie': cookie_str,
            'Referer': 'https://creator.douyin.com/',
            'Origin': 'https://creator.douyin.com',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate'  # 禁用 br 压缩，避免 aiohttp 解码失败
        }
        
        try:
            # 访问用户信息 API
            api_url = 'https://creator.douyin.com/aweme/v1/creator/pc/user/info/'
            async with session.get(api_url, headers=headers, timeout=5, allow_redirects=False) as response:
                if response.status != 200:
                    return LoginResult(success=False, error_message=f"验证失败: HTTP {response.status}")

                data = await response.json()
                if not isinstance(data, dict):
                    return LoginResult(success=False, error_message="验证失败: 响应非 JSON 对象")

                if not self._douyin_pc_user_api_success(data):
                    sc = data.get("status_code")
                    sm = data.get("status_msg") or data.get("message") or ""
                    detail = f"API status_code={sc}" + (f" ({sm})" if sm else "")
                    return LoginResult(success=False, error_message=f"验证失败: {detail}")

                _ui, nickname, uid = self._extract_douyin_pc_user_payload(data)
                if nickname:
                    return LoginResult(success=True, nickname=nickname)
                if uid:
                    return LoginResult(success=True, nickname=None)

                return LoginResult(success=False, error_message="验证失败: 业务成功但缺少用户信息字段")
        except Exception as e:
            return LoginResult(success=False, error_message=f"异常: {str(e)}")
