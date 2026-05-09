from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict

@dataclass
class LoginResult:
    """登录结果数据类"""
    success: bool
    cookies: Optional[Dict] = None
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    user_id: Optional[str] = None
    error_message: Optional[str] = None
    is_valid: bool = True # 默认有效

@dataclass
class AccountVerificationContext:
    """账号验证上下文"""
    account_id: int
    account_name: str
    platform: str
    cookies: Dict[str, str]
    user_agent: Optional[str] = None
    http_session: Optional[object] = None # aiohttp.ClientSession
    service_locator: Optional[object] = None # ServiceLocator

class LoginPluginInterface(ABC):
    """登录插件抽象接口

    ## 添加账号流程的标准化接入

    主软件的「添加账号」流程只依赖以下三项接口，新增平台只需实现这三项即可接入，
    无需修改任何主流程代码：

    1. ``login_url`` (property)
       打开浏览器时导航到此 URL（创作者中心或扫码登录页）。

    2. ``check_login_status(context)`` (async)
       主软件每 3 秒轮询一次，返回 True 表示用户已完成登录，可以提取信息。

    3. ``extract_user_info(context)`` (async)
       检测到登录后调用一次，返回 LoginResult；主流程取其中的 nickname。
       注意：Cookie 由主流程统一通过 ``context.cookies()`` 提取，插件无需处理。

    其他接口（verify_cookie_http / verify_account_status）用于「刷新登录状态」
    等场景，与添加账号流程无关。
    """

    @property
    @abstractmethod
    def platform_id(self) -> str:
        """平台标识 (如: douyin, kuaishou)"""
        pass

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """平台显示名称 (如: 抖音, 快手)"""
        pass

    @property
    @abstractmethod
    def login_url(self) -> str:
        """[添加账号] 核心接入能力 1/3：创作者中心登录 URL

        添加账号时，主软件打开浏览器并导航到此 URL。
        请确保此 URL 能让用户直接完成登录操作（如扫码页、账号密码页）。
        """
        pass

    @property
    def creator_home_url(self) -> str:
        """已登录后的创作者中心落地页 URL。

        打开已有账号浏览器时导航到此 URL，确保第一屏直接呈现已登录状态。
        子类应覆盖此属性返回对应平台创作者中心首页（区别于 login_url 的扫码/登录页）。
        """
        return self.login_url

    @property
    def check_url(self) -> str:
        """用于 HTTP 验证的 URL，默认同登录页"""
        return self.login_url

    @property
    def cookie_domain(self) -> str:
        """
        Cookie域名
        默认实现为 .{platform_id}.com，子类可覆盖
        """
        return f".{self.platform_id}.com"

    @abstractmethod
    async def check_login_status(self, context) -> bool:
        """[添加账号] 核心接入能力 2/3：检测用户是否已完成登录

        添加账号时，主软件每 3 秒调用此方法一次，直到返回 True。
        返回 True 后，主流程立即调用 extract_user_info 提取账号信息。

        实现要点：
        - 优先基于 Cookie 判断（快速稳定）；可用 DOM/脚本检测作为辅助。
        - 注意 Cookie 的 domain 可能带有前导点（如 .example.com），比较时需容错。
        - 捕获所有异常并返回 False，避免异常导致监听循环中断。

        Args:
            context: Playwright BrowserContext

        Returns:
            True 表示用户已登录，False 表示尚未登录。
        """
        pass

    @abstractmethod
    async def verify_cookie_http(self, session, cookies: Dict[str, str], user_agent: Optional[str] = None) -> LoginResult:
        """
        [已过时] 请使用 verify_account_status
        通过纯 HTTP 请求验证 Cookie 有效性（用于「刷新登录状态」场景，与添加账号无关）
        """
        pass

    async def verify_account_status(self, context: AccountVerificationContext) -> LoginResult:
        """
        验证账号状态（用于「刷新登录状态」场景，与添加账号无关）
        默认实现调用 verify_cookie_http，子类可重写以实现更复杂的逻辑 (如 Headless)
        """
        if context.http_session:
             return await self.verify_cookie_http(
                 context.http_session,
                 context.cookies,
                 context.user_agent
             )
        return LoginResult(success=False, error_message="缺少 HTTP Session")

    @abstractmethod
    async def extract_user_info(self, context) -> LoginResult:
        """[添加账号] 核心接入能力 3/3：提取用户信息（昵称、头像等）

        check_login_status 返回 True 后，主流程调用此方法一次。
        主流程取 LoginResult.nickname 作为账号显示名称。
        Cookie 由主流程统一通过 context.cookies() 提取，此方法无需处理 Cookie。

        Args:
            context: Playwright BrowserContext

        Returns:
            LoginResult（至少填写 nickname）
        """
        pass

    async def wait_for_login(self, context, timeout: int = 900) -> LoginResult:
        """
        等待用户登录完成 (默认实现：轮询检测)

        Args:
            context: 浏览器上下文
            timeout: 超时时间(秒)，默认15分钟
        """
        import asyncio
        check_interval = 3
        max_attempts = timeout // check_interval

        for _ in range(max_attempts):
            try:
                if await self.check_login_status(context):
                    return await self.extract_user_info(context)
            except Exception:
                pass
            await asyncio.sleep(check_interval)

        return LoginResult(success=False, error_message="登录超时，请重试")
