from typing import Dict, Any, Optional
import json
import logging
from urllib.parse import urlparse

import aiohttp

from src.plugins.core.interfaces.login_plugin import LoginPluginInterface, LoginResult
from src.plugins.core.wait_helper import PluginWaitHelper
from .selectors import Selectors
from .scripts import LOGIN_DETECTION_SCRIPT

logger = logging.getLogger(__name__)


def is_channels_login_page_url(url: str) -> bool:
    """视频号助手显式登录页（含扫码页），与已登录后的 /platform 等区分。"""
    if not url or "channels.weixin.qq.com" not in url:
        return False
    lower = url.lower()
    if "login.html" in lower:
        return True
    try:
        path = (urlparse(lower).path or "").rstrip("/").lower()
        if path == "/login" or path.endswith("/login"):
            return True
    except Exception:
        pass
    return False

class WechatVideoLoginPlugin(LoginPluginInterface):
    @property
    def platform_id(self) -> str:
        return "wechat_video"
    
    @property
    def platform_name(self) -> str:
        """平台显示名称"""
        return "视频号"
    
    @property
    def login_url(self) -> str:
        # 视频号助手唯一扫码登录页（与站点入口 https://channels.weixin.qq.com/ 可能 302 不同，自动化应直达此页）
        return "https://channels.weixin.qq.com/login.html"

    @property
    def creator_home_url(self) -> str:
        return "https://channels.weixin.qq.com/platform"

    @property
    def cookie_domain(self) -> str:
        return ".weixin.qq.com"

    def _cookie_domain_matches(self, c: dict, expected: str) -> bool:
        """Cookie domain 是否匹配（浏览器可能返回带前导点的 domain，如 .channels.weixin.qq.com）"""
        domain = (c.get("domain") or "").strip().lstrip(".")
        return domain == expected.lstrip(".")

    async def check_login_by_cookies(self, context) -> bool:
        """纯 Cookie 快速检测登录状态（不依赖页面 DOM，适用于扫码后页面尚未跳转的场景）

        扫码确认后，微信会在浏览器中立即设置 wxuin + sessionid Cookie，
        但 login.html 页面的自动跳转可能延迟数秒甚至不发生。
        本方法只查 Cookie，无需等页面加载，用于 _monitor_until_login 的高频轮询。
        """
        try:
            cookies = await context.cookies()
            target_domain = "channels.weixin.qq.com"
            has_wxuin = any(
                c.get("name") == "wxuin" and self._cookie_domain_matches(c, target_domain)
                for c in cookies
            )
            has_sessionid = any(
                c.get("name") == "sessionid" and self._cookie_domain_matches(c, target_domain)
                for c in cookies
            )
            return has_wxuin and has_sessionid
        except Exception as e:
            if "closed" in (str(e) or "").lower():
                return False
            logger.debug(f"[{self.platform_name}] Cookie 快速检测异常: {e}")
            return False

    async def check_login_status(self, context) -> bool:
        """检查视频号登录状态

        改进：当页面仍停留在 login.html 时，不再短路返回 False，
        而是检查 Cookie 是否已包含 wxuin + sessionid（扫码后 Cookie 先于页面跳转就位）。
        """
        try:
            cookies = await context.cookies()
            target_domain = "channels.weixin.qq.com"
            has_wxuin = any(c.get("name") == "wxuin" and self._cookie_domain_matches(c, target_domain) for c in cookies)
            has_sessionid = any(c.get("name") == "sessionid" and self._cookie_domain_matches(c, target_domain) for c in cookies)

            pages = list(getattr(context, "pages", []) or [])
            for page in pages:
                try:
                    u = (page.url or "").strip()
                    # 如果在登录页上，不通过 DOM 脚本检测（login.html 没有登录态 DOM），
                    # 但不直接返回 False —— 继续用 Cookie 判断（扫码后 Cookie 先于跳转就位）
                    if "channels.weixin.qq.com" in u and is_channels_login_page_url(u):
                        continue
                except Exception:
                    pass
                try:
                    if page.is_closed():
                        continue
                    u = (page.url or "").strip()
                    if "channels.weixin.qq.com" not in u:
                        continue
                    result_json = await page.evaluate(LOGIN_DETECTION_SCRIPT)
                    result = json.loads(result_json)
                    return bool(result.get("loggedIn", False))
                except Exception as e:
                    logger.debug(f"[{self.platform_name}] 单页脚本检测登录状态异常: {e}")
                    continue

            # 降级策略：通过 Cookie 判断（无可用页或脚本失败时，或页面仍在 login.html）
            return has_wxuin and has_sessionid
            
        except Exception as e:
            # 浏览器/上下文已关闭时不再刷 ERROR，仅 DEBUG 并返回 False
            err_name = type(e).__name__
            if err_name == "TargetClosedError" or "closed" in (str(e) or "").lower():
                logger.debug(f"[{self.platform_name}] 浏览器已关闭，跳过登录检查")
                return False
            logger.error(f"[{self.platform_name}] 检查登录状态失败: {e}", exc_info=True)
            return False
    
    async def extract_user_info(self, context) -> LoginResult:
        """提取视频号账号信息"""
        nickname = None
        cookies = await context.cookies()
        cookie_dict = {c['name']: c['value'] for c in cookies}
        
        try:
            pages = list(getattr(context, "pages", []) or [])
            target_page = None

            def _page_url(p) -> str:
                try:
                    return (p.url or "").strip()
                except Exception:
                    return ""

            # 1) 已在创作者域且非显式登录页（多标签时避免误选仍停在 login.html 的标签）
            for page in pages:
                u = _page_url(page)
                if "channels.weixin.qq.com" not in u or is_channels_login_page_url(u):
                    continue
                if "/platform" in u:
                    target_page = page
                    break

            # 2) 任意非登录页的 channels 标签
            if not target_page:
                for page in pages:
                    u = _page_url(page)
                    if "channels.weixin.qq.com" in u and not is_channels_login_page_url(u):
                        target_page = page
                        break

            # 3) 约定业务页多为首个标签，优先于列表顺序上靠前的扫码页
            if not target_page and pages:
                u = _page_url(pages[0])
                if "channels.weixin.qq.com" in u:
                    target_page = pages[0]

            # 4) 任意 channels 页（通常为登录页，后续会 goto /platform）
            if not target_page:
                for page in pages:
                    u = _page_url(page)
                    if "channels.weixin.qq.com" in u:
                        target_page = page
                        break

            if not target_page:
                if pages:
                    target_page = pages[0]
                else:
                    target_page = await context.new_page()
            
            current_url = target_page.url
            logger.debug(f"[{self.platform_name}] 当前页面: {current_url}")

            # 若不在平台页：先等微信自动跳转（扫码后微信会把 login.html 自动导向 /platform），
            # 若超时再补充主动 goto 兜底。不应直接 goto，否则与微信自动跳转竞争导致两次网络请求互相覆盖。
            if "channels.weixin.qq.com/platform" not in current_url:
                try:
                    await target_page.wait_for_url("**/platform**", timeout=10000)
                    logger.debug(f"[{self.platform_name}] 页面已自动跳转至: {target_page.url}")
                except Exception:
                    # 未自动跳转，主动 goto 兜底
                    try:
                        await target_page.goto(
                            "https://channels.weixin.qq.com/platform",
                            wait_until="domcontentloaded",
                            timeout=20000,
                        )
                        logger.debug(f"[{self.platform_name}] 已主动跳转至创作者中心: {target_page.url}")
                    except Exception as e:
                        logger.warning(f"[{self.platform_name}] 跳转创作者中心失败: {e}")

            # 视频号昵称由 JS 渲染，优先等待核心用户信息 DOM 渲染
            try:
                await target_page.wait_for_selector(".account-info, .finder-nickname, .account-name", state="attached", timeout=10000)
                await PluginWaitHelper.wait_for_condition(
                    target_page,
                    lambda: self._login_script_has_username(target_page),
                    timeout_ms=3000,
                    poll_interval_ms=500,
                )
            except Exception:
                try:
                    await target_page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass

            # 通过脚本提取昵称
            try:
                result_json = await target_page.evaluate(LOGIN_DETECTION_SCRIPT)
                result = json.loads(result_json)
                
                if result.get("debug"):
                    logger.debug(f"[{self.platform_name}] 脚本调试信息: {result.get('debug')}")
                
                nickname = result.get("username")
                logger.info(f"[{self.platform_name}] 脚本提取昵称: {nickname}")
            except Exception as e:
                logger.debug(f"[{self.platform_name}] 脚本提取昵称失败: {e}")

            # 降级策略：通过 Playwright 选择器提取
            if not nickname:
                logger.info(f"[{self.platform_name}] 脚本提取失败，尝试 Patchright 原生提取")
                selectors = [
                    '.finder-nickname',
                    '.header-name',
                    '.account-name',
                    '.account-info .nickname',
                    '.account-info',
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
            error_message=None if success else "未能提取到账号昵称"
        )

    async def _login_script_has_username(self, page) -> bool:
        try:
            result_json = await page.evaluate(LOGIN_DETECTION_SCRIPT)
            result = json.loads(result_json)
            return bool(result.get("username"))
        except Exception:
            return False

    def _parse_platform_nickname_from_auth_data(self, inner: dict) -> Optional[str]:
        """
        从 auth_data 的 data 中解析「视频号昵称」（平台昵称），而非微信侧昵称。
        优先查找 finder 相关字段，若接口未返回视频号昵称则返回 None（不采用 userAttr.nickname）。
        """
        if not inner:
            return None
        # 常见可能的视频号昵称字段（接口文档不公开，兼容多种命名）
        finder_attr = inner.get("finderAttr") or inner.get("finder_attr") or {}
        if isinstance(finder_attr, dict):
            nick = finder_attr.get("nickname") or finder_attr.get("nickName")
            if nick and str(nick).strip():
                return str(nick).strip()
        for key in ("finderNickname", "finder_nickname", "accountName", "account_name", "channelName", "channel_name"):
            nick = inner.get(key)
            if nick and str(nick).strip():
                return str(nick).strip()
        return None

    async def verify_cookie_http(self, session, cookies: Dict[str, str], user_agent: Optional[str] = None) -> LoginResult:
        """
        通过 HTTP 请求验证视频号 Cookie 有效性（与抖音类似）。
        依据 WeMedia X-Ray 抓包：get_auth_info / auth_data 为 POST，返回 201，body 为 errCode/errMsg/data；
        errCode==0 表示已登录。昵称取「视频号昵称」（从 data 中 finder 相关字段解析），
        不采用 data.userAttr.nickname（微信侧昵称）；若接口未返回视频号昵称则 nickname 为 None。
        """
        cookie_str = '; '.join([f"{k}={v}" for k, v in cookies.items()])
        headers = {
            'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Cookie': cookie_str,
            'Referer': 'https://channels.weixin.qq.com/platform',
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'Origin': 'https://channels.weixin.qq.com',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        }
        # 1) 以 auth_data 为准（返回登录态更可靠）；get_auth_info 在已离线时仍可能返回 0，不单独采信
        auth_data_url = 'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/auth/auth_data'
        get_auth_info_url = 'https://channels.weixin.qq.com/cgi-bin/mmfinderassistant-bin/auth/get_auth_info'
        for api_url, is_primary in [(auth_data_url, True), (get_auth_info_url, False)]:
            try:
                async with session.post(
                    api_url,
                    headers=headers,
                    json={},
                    timeout=10,
                    allow_redirects=False
                ) as response:
                    if response.status not in (200, 201):
                        if response.status in (301, 302):
                            location = (response.headers.get('Location') or '').lower()
                            if 'login' in location:
                                return LoginResult(success=False, error_message="登录已失效（已跳转登录页）")
                        continue
                    try:
                        data = await response.json()
                    except Exception:
                        continue
                    err_code = data.get('errCode', data.get('errcode', -1))
                    if err_code not in (0, '0'):
                        err_msg = data.get('errMsg', data.get('errmsg', '')) or f"errCode={err_code}"
                        if is_primary:
                            return LoginResult(success=False, error_message=err_msg)
                        continue
                    # errCode==0：仅当 auth_data 成功时才判为在线；昵称仅取视频号昵称，不取微信昵称
                    if is_primary:
                        inner = (data.get('data') or {})
                        platform_nickname = self._parse_platform_nickname_from_auth_data(inner)
                        logger.info(f"[{self.platform_name}] HTTP 鉴权验证通过: auth_data")
                        return LoginResult(success=True, nickname=platform_nickname, error_message=None)
            except Exception as e:
                logger.debug(f"[{self.platform_name}] 鉴权请求异常 {api_url}: {e}")
                if isinstance(
                    e,
                    (aiohttp.ClientError, TimeoutError, OSError, ConnectionError),
                ):
                    return LoginResult(
                        success=False,
                        is_valid=False,
                        error_message=str(e) or type(e).__name__,
                    )
                if is_primary:
                    continue
                break

        # 2) 回退：请求平台首页，根据是否跳转登录页判断
        try:
            async with session.get(
                'https://channels.weixin.qq.com/platform',
                headers={k: v for k, v in headers.items() if k != 'Content-Type'},
                timeout=10,
                allow_redirects=False
            ) as response:
                if response.status in (301, 302):
                    location = (response.headers.get('Location') or '').lower()
                    if 'login' in location:
                        return LoginResult(success=False, error_message="登录已失效（已跳转登录页）")
                if response.status == 200:
                    logger.info(f"[{self.platform_name}] HTTP 平台页验证通过（未跳转登录）")
                    return LoginResult(success=True, nickname=None, error_message=None)
                return LoginResult(success=False, error_message=f"验证失败: HTTP {response.status}")
        except Exception as e:
            if isinstance(
                e,
                (aiohttp.ClientError, TimeoutError, OSError, ConnectionError),
            ):
                return LoginResult(
                    success=False,
                    is_valid=False,
                    error_message=str(e) or type(e).__name__,
                )
            return LoginResult(success=False, error_message=f"验证异常: {str(e)}")
