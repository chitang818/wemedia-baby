"""
小红书登录插件
文件路径: src/plugins/pro/xiaohongshu/login_plugin.py

基于 WeMedia X-Ray DOM 分析报告 (20260306_180442) 实际采集的选择器和 Cookie。

关键发现（X-Ray 确认）：
  - creator.xiaohongshu.com 平台 **不使用** web_session Cookie
  - 真正的登录凭证是: customer-sso-sid, access-token-creator.xiaohongshu.com,
    galaxy_creator_session_id
  - 昵称在 div.user-info 元素中，文本格式为 "{昵称}退出登录"
  - 头像在 img.user_avatar 中
  - 用户ID在 Cookie x-user-id-creator.xiaohongshu.com 中
"""
from typing import Dict, Any, Optional
import logging
import re

from src.plugins.core.interfaces.login_plugin import LoginPluginInterface, LoginResult
from .selectors import Selectors

logger = logging.getLogger(__name__)

# 创作者平台登录后才会出现的 Cookie（X-Ray 实采确认，a1/webId/gid 为追踪 Cookie 不算）
_SESSION_COOKIES = {
    "customer-sso-sid",
    "access-token-creator.xiaohongshu.com",
    "galaxy_creator_session_id",
    "galaxy.creator.beaker.session.id",
    "x-user-id-creator.xiaohongshu.com",
}


class XiaohongshuLoginPlugin(LoginPluginInterface):
    """小红书登录插件 — 基于创作者服务平台 (creator.xiaohongshu.com) 实际 DOM。"""

    @property
    def platform_id(self) -> str:
        return "xiaohongshu"

    @property
    def platform_name(self) -> str:
        return "小红书"

    @property
    def login_url(self) -> str:
        return "https://creator.xiaohongshu.com/login"

    @property
    def creator_home_url(self) -> str:
        return "https://creator.xiaohongshu.com/new/home"

    @property
    def cookie_domain(self) -> str:
        return ".xiaohongshu.com"

    # ------------------------------------------------------------------
    # 登录状态检测（轮询调用，每 3 秒一次）
    # ------------------------------------------------------------------
    async def check_login_status(self, context) -> bool:
        """检查小红书登录状态。

        检测策略（基于 X-Ray 分析确认）：
          1. Cookie: customer-sso-sid / access-token / galaxy_creator_session_id
             任一存在即视为已登录。
             注意：creator 平台不使用 web_session，a1/gid/webId 是追踪 Cookie，
             访问登录页即设置，不能作为登录判据。
          2. URL: 页面从 /login 跳转到创作者管理页（且无 401 重定向）
        """
        try:
            cookies = await context.cookies()
            cookie_names = {c["name"] for c in cookies}

            # ── 信号 1: 检测真实的会话 Cookie ──
            matched = cookie_names & _SESSION_COOKIES
            if matched:
                logger.info(
                    f"[{self.platform_name}] 检测到会话 Cookie: "
                    f"{', '.join(sorted(matched))}，登录成功"
                )
                return True

            # ── 信号 2: URL 已跳转到非登录页 ──
            pages = context.pages
            if pages:
                page = pages[0]
                url = page.url
                if (
                    "creator.xiaohongshu.com" in url
                    and "/login" not in url
                    and "redirectReason" not in url
                ):
                    logger.info(
                        f"[{self.platform_name}] URL 已跳转到非登录页: {url}，视为登录成功"
                    )
                    return True

            # ── 诊断日志 ──
            if not hasattr(self, "_poll_count"):
                self._poll_count = 0
            self._poll_count += 1
            if self._poll_count % 10 == 1:
                url_snippet = ""
                if pages:
                    url_snippet = f", URL={pages[0].url[:80]}"
                logger.info(
                    f"[{self.platform_name}] 登录检测第 {self._poll_count} 次: "
                    f"Cookie({len(cookie_names)}个)=[{', '.join(sorted(cookie_names)[:15])}]"
                    f"{url_snippet}"
                )

            return False
        except Exception as e:
            logger.warning(f"[{self.platform_name}] 登录检测失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 用户信息提取（登录成功后调用一次）
    # ------------------------------------------------------------------
    async def extract_user_info(self, context) -> LoginResult:
        """提取小红书账号信息（昵称、头像、用户ID）。

        X-Ray 实采确认的 DOM 结构：
          - div.user-info → 文本 "萧关郎退出登录"，昵称 = 去掉 "退出登录"
          - img.user_avatar → src 含 xhscdn.com 头像
          - div.others.description-text → "小红书账号: 9402628224还没有简介"
          - Cookie x-user-id-creator.xiaohongshu.com → 用户ID
          - localStorage USER_INFO → JSON 含 nickname
        """
        import asyncio

        nickname = None
        avatar_url = None
        user_id = None
        cookies = await context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        # 从 Cookie 直接提取 user_id
        user_id = cookie_dict.get("x-user-id-creator.xiaohongshu.com")
        if user_id:
            logger.info(f"[{self.platform_name}] 从 Cookie 提取到 user_id: {user_id}")

        try:
            pages = context.pages
            if pages:
                page = pages[0]
                current_url = page.url

                # 如果当前在登录页，先跳转到创作者首页
                if "/login" in current_url:
                    try:
                        await page.goto(
                            "https://creator.xiaohongshu.com/new/home",
                            wait_until="domcontentloaded",
                            timeout=15000,
                        )
                        await asyncio.sleep(2)
                        current_url = page.url
                        logger.info(f"[{self.platform_name}] 已跳转到创作者首页: {current_url}")
                    except Exception as nav_e:
                        logger.warning(f"[{self.platform_name}] 跳转到首页失败: {nav_e}")

                    if "/login" in current_url or "redirectReason" in current_url:
                        logger.warning(
                            f"[{self.platform_name}] 跳转首页被 401 拒绝，Cookie 无效，中止提取"
                        )
                        return LoginResult(
                            success=False,
                            cookies=cookie_dict,
                            error_message="Cookie 无效，服务器返回 401",
                        )

                if "xiaohongshu.com" in current_url:
                    # ── 1. 提取头像 ──
                    try:
                        loc = page.locator("img.user_avatar")
                        if await loc.count() > 0:
                            src = await loc.first.get_attribute("src")
                            if src and "xhscdn.com" in src:
                                avatar_url = src.split("?")[0]
                                logger.info(f"[{self.platform_name}] 提取到头像: {avatar_url[:60]}…")
                    except Exception:
                        pass

                    # ── 2. 从 div.user-info 提取昵称（X-Ray: 文本 "萧关郎退出登录"） ──
                    try:
                        loc = page.locator("div.user-info")
                        if await loc.count() > 0:
                            text = await loc.first.inner_text()
                            if text:
                                text = text.replace("退出登录", "").strip()
                                text = text.split("\n")[0].strip()
                                if text and len(text) < 30 and "创作服务平台" not in text:
                                    nickname = text
                                    logger.info(f"[{self.platform_name}] 从 user-info 提取到昵称: {nickname}")
                    except Exception:
                        pass

                    # ── 3. 兜底: 从 localStorage USER_INFO 提取 ──
                    if not nickname:
                        try:
                            js_result = await page.evaluate("""() => {
                                try {
                                    const raw = localStorage.getItem('USER_INFO');
                                    if (raw) {
                                        const obj = JSON.parse(raw);
                                        return obj.nickname || obj.name || null;
                                    }
                                } catch(e) {}
                                return null;
                            }""")
                            if js_result:
                                nickname = js_result
                                logger.info(f"[{self.platform_name}] 从 localStorage 提取到昵称: {nickname}")
                        except Exception as e:
                            logger.debug(f"[{self.platform_name}] localStorage 提取失败: {e}")

                    # ── 4. 兜底: 从账号信息区提取小红书号 ──
                    if not nickname and not user_id:
                        try:
                            loc = page.locator("div.others.description-text")
                            if await loc.count() > 0:
                                text = await loc.first.inner_text()
                                if text and "小红书账号" in text:
                                    match = re.search(r"小红书账号[:：]\s*(\d+)", text)
                                    if match:
                                        xhs_id = match.group(1)
                                        user_id = user_id or xhs_id
                                        nickname = nickname or f"小红书用户_{xhs_id[-4:]}"
                                        logger.info(f"[{self.platform_name}] 提取到小红书号: {xhs_id}")
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
    # HTTP Cookie 验证（verify_account_status 使用基类默认实现，
    # 自动调用此方法做真正的 HTTP 请求验证）
    # ------------------------------------------------------------------
    async def verify_cookie_http(
        self, session, cookies: Dict[str, str], user_agent: Optional[str] = None
    ) -> LoginResult:
        """通过 HTTP 请求验证 Cookie 有效性。

        使用 X-Ray 确认的 API: /api/galaxy/creator/home/personal_info
        """
        cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
        headers = {
            "User-Agent": user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Cookie": cookie_str,
            "Referer": "https://creator.xiaohongshu.com/",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://creator.xiaohongshu.com",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

        try:
            api_url = "https://creator.xiaohongshu.com/api/galaxy/creator/home/personal_info"
            async with session.get(
                api_url, headers=headers, timeout=8, allow_redirects=False
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    ok = bool(data.get("success")) or data.get("code") in (0, "0")
                    if ok:
                        user_info = data.get("data", {})
                        nickname = user_info.get("nickname") or user_info.get("name")
                        return LoginResult(success=True, nickname=nickname)
                    return LoginResult(
                        success=False,
                        error_message=f"API 返回非成功状态: {data.get('msg', 'unknown')}",
                    )
                if response.status in (401, 403):
                    return LoginResult(
                        success=False,
                        error_message="Cookie 已失效（HTTP 401/403）",
                    )
                return LoginResult(
                    success=False,
                    error_message=f"HTTP 验证失败: 状态码 {response.status}",
                )
        except Exception as e:
            logger.debug(f"[{self.platform_name}] HTTP Cookie 验证异常: {e}")
            return LoginResult(
                success=False,
                error_message=f"HTTP 验证异常: {str(e)}",
            )
