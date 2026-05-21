"""
哔哩哔哩登录插件
文件路径: src/plugins/pro/bilibili/login_plugin.py

基于 WeMedia X-Ray DOM 分析报告 (20260306_193101) 实际采集的选择器和 Cookie。

关键发现（X-Ray 确认）：
  - 登录 Cookie: SESSDATA + DedeUserID（在 .bilibili.com 域名下）
  - 创作者首页 DOM 上 **没有** nickname 相关的选择器可用
    (.header-upload-entry .nickname / .mini-avatar .nickname / div[class*='uname'] 全部未找到)
  - 昵称、头像、user_id 需通过 API /x/web-interface/nav 获取
  - 头像 DOM: img.custom-lazy-img.up-avatar（仅在 member.bilibili.com 可用）
"""
from typing import Dict, Optional
import logging

from src.plugins.core.interfaces.login_plugin import LoginPluginInterface, LoginResult

logger = logging.getLogger(__name__)

_SESSION_COOKIES = {"SESSDATA", "DedeUserID", "bili_jct", "DedeUserID__ckMd5"}

_NAV_API = "https://api.bilibili.com/x/web-interface/nav"


class BilibiliLoginPlugin(LoginPluginInterface):
    """哔哩哔哩登录插件 — 基于创作者中心 (member.bilibili.com) 实际 DOM。"""

    @property
    def platform_id(self) -> str:
        return "bilibili"

    @property
    def platform_name(self) -> str:
        return "哔哩哔哩"

    @property
    def login_url(self) -> str:
        return "https://passport.bilibili.com/login"

    @property
    def creator_home_url(self) -> str:
        return "https://member.bilibili.com/platform/home"

    @property
    def cookie_domain(self) -> str:
        return ".bilibili.com"

    # ------------------------------------------------------------------
    # 登录状态检测
    # ------------------------------------------------------------------
    async def check_login_status(self, context) -> bool:
        """检查哔哩哔哩登录状态。

        检测策略（X-Ray 确认）：
          1. Cookie: SESSDATA + DedeUserID 同时存在
          2. URL: 页面从 passport 登录页跳转到 member 创作者页面
        """
        try:
            cookies = await context.cookies()
            cookie_names = {c["name"] for c in cookies}

            if "SESSDATA" in cookie_names and "DedeUserID" in cookie_names:
                logger.info(f"[{self.platform_name}] 检测到 SESSDATA + DedeUserID，登录成功")
                return True

            pages = context.pages
            if pages:
                url = pages[0].url
                if "member.bilibili.com" in url and "passport" not in url:
                    logger.info(f"[{self.platform_name}] URL 已跳转到创作者中心: {url}，视为登录成功")
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
            logger.warning(f"[{self.platform_name}] 登录检测失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 用户信息提取
    # ------------------------------------------------------------------
    async def extract_user_info(self, context) -> LoginResult:
        """提取哔哩哔哩账号信息（昵称、头像、用户ID）。

        X-Ray 确认：创作者首页 DOM 上没有 nickname 选择器可用，
        需通过浏览器内 fetch 调用 /x/web-interface/nav API 获取。
        """
        import asyncio

        nickname = None
        avatar_url = None
        user_id = None
        cookies = await context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        user_id = cookie_dict.get("DedeUserID")

        try:
            pages = context.pages
            if pages:
                page = pages[0]
                current_url = page.url

                # 如果在登录页，先跳转到创作者首页
                if "passport.bilibili.com" in current_url:
                    try:
                        await page.goto(
                            "https://member.bilibili.com/platform/home",
                            wait_until="domcontentloaded",
                            timeout=15000,
                        )
                        await asyncio.sleep(2)
                        current_url = page.url
                        logger.info(f"[{self.platform_name}] 已跳转到创作者首页: {current_url}")
                    except Exception as nav_e:
                        logger.warning(f"[{self.platform_name}] 跳转到首页失败: {nav_e}")

                    if "passport" in current_url or "login" in current_url:
                        logger.warning(f"[{self.platform_name}] 跳转失败，仍在登录页，Cookie 可能无效")
                        return LoginResult(
                            success=False,
                            cookies=cookie_dict,
                            error_message="跳转创作者中心失败，Cookie 无效",
                        )

                # ── 1. 通过浏览器内 fetch API 获取用户信息 ──
                try:
                    api_result = await page.evaluate(f"""async () => {{
                        try {{
                            const resp = await fetch('{_NAV_API}', {{
                                credentials: 'include'
                            }});
                            const data = await resp.json();
                            if (data.code === 0 && data.data && data.data.isLogin) {{
                                return {{
                                    nickname: data.data.uname || '',
                                    avatar: data.data.face || '',
                                    user_id: String(data.data.mid || ''),
                                }};
                            }}
                        }} catch(e) {{}}
                        return null;
                    }}""")
                    if api_result:
                        nickname = api_result.get("nickname")
                        avatar_url = api_result.get("avatar")
                        api_uid = api_result.get("user_id")
                        if api_uid:
                            user_id = api_uid
                        logger.info(
                            f"[{self.platform_name}] 从 API 提取到: "
                            f"昵称={nickname}, user_id={user_id}"
                        )
                except Exception as e:
                    logger.debug(f"[{self.platform_name}] API 提取失败: {e}")

                # ── 2. 兜底: 从 DOM 提取头像 ──
                if not avatar_url:
                    try:
                        loc = page.locator("img.up-avatar, img[class*='avatar']")
                        if await loc.count() > 0:
                            src = await loc.first.get_attribute("src")
                            if src and "hdslb.com" in src:
                                avatar_url = src.split("@")[0]
                                if avatar_url.startswith("//"):
                                    avatar_url = "https:" + avatar_url
                                logger.info(f"[{self.platform_name}] 从 DOM 提取到头像: {avatar_url[:60]}…")
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"[{self.platform_name}] 提取用户信息失败: {e}", exc_info=True)

        has_session = "SESSDATA" in cookie_dict and "DedeUserID" in cookie_dict
        success = has_session

        if success and not nickname:
            logger.info(f"[{self.platform_name}] 有会话 Cookie，视为登录成功（未提取到昵称）")

        return LoginResult(
            success=success,
            cookies=cookie_dict,
            nickname=nickname,
            avatar_url=avatar_url,
            user_id=user_id,
            error_message=None if success else "未检测到 SESSDATA / DedeUserID",
        )

    # ------------------------------------------------------------------
    # HTTP Cookie 验证（verify_account_status 使用基类默认实现，
    # 自动调用此方法做真正的 HTTP 请求验证）
    # ------------------------------------------------------------------
    async def verify_cookie_http(
        self, session, cookies: Dict[str, str], user_agent: Optional[str] = None
    ) -> LoginResult:
        """通过 HTTP 请求验证 Cookie 有效性。

        使用 X-Ray 确认的 API: https://api.bilibili.com/x/web-interface/nav
        """
        try:
            headers = {
                "User-Agent": user_agent
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
                "Referer": "https://www.bilibili.com",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }

            async with session.get(
                _NAV_API, headers=headers, timeout=10
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("code") in (0, "0") and data.get("data", {}).get("isLogin"):
                        nav_data = data["data"]
                        return LoginResult(
                            success=True,
                            nickname=nav_data.get("uname", ""),
                            avatar_url=nav_data.get("face", ""),
                            user_id=str(nav_data.get("mid", "")),
                        )
                    return LoginResult(
                        success=False,
                        error_message="Cookie 已失效，B站 API 返回未登录",
                    )
                return LoginResult(
                    success=False,
                    error_message=f"HTTP 验证失败: 状态码 {resp.status}",
                )
        except Exception as e:
            logger.warning(f"[{self.platform_name}] HTTP Cookie 验证异常: {e}")
            return LoginResult(
                success=False,
                error_message=f"HTTP 验证异常: {str(e)}",
            )
