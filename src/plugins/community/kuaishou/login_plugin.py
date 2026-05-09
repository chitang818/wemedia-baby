"""
快手登录插件
文件路径: src/plugins/community/kuaishou/login_plugin.py

基于 WeMedia X-Ray 发布分析报告 (20260306_200613) 实采的 Cookie 结构。

关键发现（X-Ray 确认）：
  - 登录后的会话 Cookie: userId, bUserId, kuaishou.web.cp.api_st, kuaishou.web.cp.api_ph
  - 注意: Cookie 名中是"点号"(kuaishou.web.cp.api_st) 而非"下划线"
  - did, kwfv1 是设备追踪 Cookie，登录前就存在，不能作为登录判据
"""
from typing import Dict, Optional
import json
import logging

from src.plugins.core.interfaces.login_plugin import LoginPluginInterface, LoginResult
from .scripts import LOGIN_DETECTION_SCRIPT

logger = logging.getLogger(__name__)

_SESSION_COOKIES = {
    "userId",
    "bUserId",
    "kuaishou.web.cp.api_st",
    "kuaishou.web.cp.api_ph",
}


class KuaishouLoginPlugin(LoginPluginInterface):
    """快手登录插件 — 基于创作者中心 (cp.kuaishou.com) 实际 Cookie 结构。"""

    @property
    def platform_id(self) -> str:
        return "kuaishou"

    @property
    def platform_name(self) -> str:
        return "快手"

    @property
    def login_url(self) -> str:
        return "https://cp.kuaishou.com/profile"

    @property
    def cookie_domain(self) -> str:
        return ".kuaishou.com"

    # ------------------------------------------------------------------
    # 登录状态检测
    # ------------------------------------------------------------------
    async def check_login_status(self, context) -> bool:
        """检查快手登录状态。

        检测策略（X-Ray 确认）：
          1. 优先通过页面脚本与 DOM 检测（防止残留的过期 Cookie 导致误判为在线）
          2. 作为备用：Cookie 中 userId + kuaishou.web.cp.api_st 同时存在（仅在页面未就绪时）
        """
        try:
            cookies = await context.cookies()
            cookie_names = {c["name"] for c in cookies}

            pages = context.pages
            if pages:
                page = pages[0]
                url = page.url
                
                # 1. 拦截明确的登录重定向页
                if "passport.kuaishou.com" in url or "/login" in url or "/signin" in url:
                    return False
                
                # 2. 如果处于快手域下，检测页面中的实际登录标识
                if "kuaishou.com" in url and "about:blank" not in url:
                    try:
                        # 防御性检测未登录页面的硬特征
                        is_unauth = await page.evaluate('''() => {
                            const text = document.body ? document.body.innerText : '';
                            return text.includes('扫码登录') || 
                                   text.includes('立即登录') ||
                                   document.querySelector('canvas[class*="qr"]') !== null ||
                                   document.querySelector('img[class*="qr"]') !== null;
                        }''')
                        if is_unauth:
                            # 即使 Cookie 还在，页面显示未登录即为掉线
                            if not hasattr(self, "_log_dropped"):
                                logger.info(f"[{self.platform_name}] 页面含有未登录特征，判定为已掉线（无视残留Cookie）")
                                self._log_dropped = True
                            return False
                        
                        # 执行综合脚本检测
                        result_json = await page.evaluate(LOGIN_DETECTION_SCRIPT)
                        result = json.loads(result_json)
                        if result.get("loggedIn", False):
                            logger.info(f"[{self.platform_name}] 脚本检测登录成功")
                            return True
                    except Exception as e:
                        logger.debug(f"[{self.platform_name}] 脚本检测失败: {e}")

            # 3. 兜底方案：在无头或页面未完全加载时，基于 Cookie 暂判
            # 如果走到这一步，说明前面的 DOM 拦截没有生效（可能是页面还没开始渲染）
            if "userId" in cookie_names and "kuaishou.web.cp.api_st" in cookie_names:
                logger.info(f"[{self.platform_name}] 检测到 userId + kuaishou.web.cp.api_st，暂判登录成功")
                return True

            matched = cookie_names & _SESSION_COOKIES
            if len(matched) >= 2:
                logger.info(f"[{self.platform_name}] 检测到会话 Cookie: {', '.join(sorted(matched))}，暂判登录成功")
                return True

            if not hasattr(self, "_poll_count"):
                self._poll_count = 0
            self._poll_count += 1
            if self._poll_count % 10 == 1:
                url_snippet = ""
                if pages:
                    url_snippet = f", URL={pages[0].url[:80]}"
                logger.info(
                    f"[{self.platform_name}] 登录检测第 {self._poll_count} 次: "
                    f"Cookie({len(cookie_names)}个)=[{', '.join(sorted(cookie_names)[:10])}]"
                    f"{url_snippet}"
                )

            return False
        except Exception as e:
            logger.warning(f"[{self.platform_name}] 登录检测异常: {e}")
            return False

    # ------------------------------------------------------------------
    # 用户信息提取
    # ------------------------------------------------------------------
    async def extract_user_info(self, context) -> LoginResult:
        """提取快手账号信息（昵称、用户ID）。"""
        nickname = None
        avatar_url = None
        user_id = None
        cookies = await context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        user_id = cookie_dict.get("userId")

        try:
            pages = context.pages
            if pages:
                page = pages[0]
                current_url = page.url

                if "kuaishou.com" in current_url:
                    try:
                        result_json = await page.evaluate(LOGIN_DETECTION_SCRIPT)
                        result = json.loads(result_json)
                        nickname = result.get("username")
                        if nickname:
                            logger.info(f"[{self.platform_name}] 脚本提取到昵称: {nickname}")
                    except Exception as e:
                        logger.debug(f"[{self.platform_name}] 脚本提取失败: {e}")

                    if not nickname:
                        selectors = [
                            "[class*='nickname']",
                            "[class*='user-name']",
                            ".user-info .name",
                            "[class*='userInfo'] span",
                        ]
                        for sel in selectors:
                            try:
                                loc = page.locator(sel).first
                                if await loc.count() > 0:
                                    text = await loc.inner_text()
                                    if text and text.strip() and len(text.strip()) < 30:
                                        nickname = text.strip()
                                        logger.info(f"[{self.platform_name}] 从 DOM 提取到昵称: {nickname}")
                                        break
                            except Exception:
                                continue

                    if not avatar_url:
                        try:
                            loc = page.locator("img[class*='avatar']").first
                            if await loc.count() > 0:
                                src = await loc.get_attribute("src")
                                if src:
                                    avatar_url = src.split("?")[0]
                        except Exception:
                            pass

        except Exception as e:
            logger.error(f"[{self.platform_name}] 提取用户信息失败: {e}", exc_info=True)

        has_session = bool(set(cookie_dict.keys()) & _SESSION_COOKIES)
        success = has_session

        if success and not nickname:
            logger.info(f"[{self.platform_name}] 有会话 Cookie，视为登录成功（未提取到昵称）")

        return LoginResult(
            success=success,
            cookies=cookie_dict,
            nickname=nickname,
            avatar_url=avatar_url,
            user_id=user_id,
            error_message=None if success else "未检测到会话 Cookie",
        )

    # ------------------------------------------------------------------
    # HTTP Cookie 验证（verify_account_status 使用基类默认实现）
    # ------------------------------------------------------------------
    async def verify_cookie_http(
        self, session, cookies: Dict[str, str], user_agent: Optional[str] = None
    ) -> LoginResult:
        """通过 HTTP 请求验证快手 Cookie 有效性。

        访问 cp.kuaishou.com/profile，检测是否被重定向到登录页，或者返回了包含未登录特征的页面。
        """
        # 前置判断：如果必备的身份标识都不存在，直接拦截
        if "userId" not in cookies or ("kuaishou.web.cp.api_st" not in cookies and "kuaishou.web.cp.api_ph" not in cookies):
            return LoginResult(
                success=False,
                error_message="缺失关键会话 Cookie（userId 或 api_st/ph）",
            )

        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers = {
            "User-Agent": user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cookie": cookie_str,
            "Referer": "https://cp.kuaishou.com/",
            "Origin": "https://cp.kuaishou.com",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        }

        try:
            async with session.get(
                "https://cp.kuaishou.com/profile",
                headers=headers,
                timeout=10,
                allow_redirects=False,
            ) as response:
                if response.status == 302:
                    location = response.headers.get("Location", "")
                    if "login" in location.lower() or "passport" in location.lower():
                        return LoginResult(
                            success=False,
                            error_message="Cookie 已失效（重定向到登录页）",
                        )
                    return LoginResult(success=True)

                if response.status == 200:
                    text = await response.text()
                    # 快手由于未登录也返回200，但页面包含了登录提示，进行拦截
                    if "立即登录" in text and "passport.kuaishou.com" in text:
                        return LoginResult(
                            success=False,
                            error_message="Cookie 已失效（检测到登录要求特征页面）",
                        )
                    # 保守判定为成功
                    return LoginResult(success=True)

                return LoginResult(
                    success=False,
                    error_message=f"HTTP 验证失败: 状态码 {response.status}",
                )
        except Exception as e:
            logger.warning(f"[{self.platform_name}] HTTP Cookie 验证异常: {e}")
            return LoginResult(
                success=False,
                error_message=f"HTTP 验证异常: {str(e)}",
            )
