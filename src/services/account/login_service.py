"""
登录服务
文件路径：src/services/account/login_service.py
功能：统一管理浏览器登录流程，包括账号凭证保存、指纹持久化、登录状态检测
"""

from typing import Dict, Any, Optional, Callable, List
import logging
import asyncio

logger = logging.getLogger(__name__)


class LoginService:
    """登录服务 - 集成 UndetectedBrowserManager 与账号管理
    
    职责:
    1. 启动浏览器并导航到登录页面
    2. 监听登录状态变化
    3. 登录成功后保存凭证（cookies.json；关闭时另可导出 storage_state 快照）
    4. 触发 UI 刷新回调
    """
    
    # 各平台打开浏览器时优先进入的 URL（多为登录页或门户；视频号为唯一扫码页 login.html）
    PLATFORM_URLS = {
        'douyin': 'https://creator.douyin.com/',
        'kuaishou': 'https://cp.kuaishou.com/',
        'xiaohongshu': 'https://creator.xiaohongshu.com/',
        'wechat_video': 'https://channels.weixin.qq.com/login.html'
    }
    
    # 各平台的登录成功检测URL模式
    PLATFORM_LOGIN_SUCCESS_PATTERNS = {
        'douyin': ['creator.douyin.com/creator-micro'],
        'kuaishou': ['cp.kuaishou.com/article'],
        'xiaohongshu': ['creator.xiaohongshu.com/creator'],
        'wechat_video': ['channels.weixin.qq.com/platform']
    }
    
    def __init__(
        self,
        account_id: str,
        platform: str,
        account_manager=None,
        on_login_success: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        on_login_failed: Optional[Callable[[str], None]] = None
    ):
        """初始化登录服务
        
        Args:
            account_id: 账号ID/名称
            platform: 平台ID (douyin/kuaishou/xiaohongshu/wechat_video)
            account_manager: 账号管理器实例（可选）
            on_login_success: 登录成功回调 (account_id, user_info)
            on_login_failed: 登录失败回调 (error_message)
        """
        self.account_id = account_id
        self.platform = platform
        self.account_manager = account_manager
        self.on_login_success = on_login_success
        self.on_login_failed = on_login_failed
        
        self._browser_manager = None
        self._context = None
        self._page = None
        self._is_closed = False
        self._login_detected = False
    
    async def start_login(self, headless: bool = False) -> bool:
        """启动登录流程
        
        Args:
            headless: 是否无头模式 (登录通常需要有头模式)
            
        Returns:
            True 如果启动成功
        """
        try:
            # 平台启用校验：避免绕过 UI 直接调用登录
            try:
                from src.utils.plugin_settings import is_platform_enabled
                if not is_platform_enabled(self.platform):
                    if self.on_login_failed:
                        self.on_login_failed("该平台已在 设置-插件配置 中禁用，请先启用后再登录。")
                    return False
            except Exception:
                pass

            # 懒加载 BrowserFactory
            from src.infrastructure.browser.browser_factory import BrowserFactory
            
            # 获取平台URL
            platform_url = self.PLATFORM_URLS.get(self.platform)
            if not platform_url:
                logger.error(f"不支持的平台: {self.platform}")
                if self.on_login_failed:
                    self.on_login_failed(f"不支持的平台: {self.platform}")
                return False
            
            # 创建浏览器管理器
            # 传递 platform 和 platform_username 以使用新的目录结构
            self._browser_manager = BrowserFactory.get_browser_service(
                account_id=self.account_id, 
                platform=self.platform, 
                platform_username=self.account_id # 在这里 account_id 即为 username
            )
            
            # 启动浏览器
            logger.info(f"启动浏览器进行登录: account_id={self.account_id}, platform={self.platform}")
            self._context = await self._browser_manager.launch(headless=headless)
            
            if not self._context:
                logger.error("浏览器启动失败")
                if self.on_login_failed:
                    self.on_login_failed("浏览器启动失败")
                return False
            
            # 使用首个可用标签作为业务页；launch 不再预开环境信息标签
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = await self._context.new_page()
            await self._page.goto(platform_url, wait_until='domcontentloaded', timeout=60000)
            if self._browser_manager and hasattr(self._browser_manager, "note_primary_work_page"):
                self._browser_manager.note_primary_work_page(self._page)
            if not headless and self._browser_manager and hasattr(
                self._browser_manager, "apply_browser_tab_layout"
            ):
                await self._browser_manager.apply_browser_tab_layout(refresh_env_content=False)

            logger.info(f"已导航到: {platform_url}")
            return True
            
        except Exception as e:
            logger.error(f"启动登录失败: {e}", exc_info=True)
            if self.on_login_failed:
                self.on_login_failed(str(e))
            return False
    
    async def check_login_status(self) -> bool:
        """检测当前是否已登录
        
        Returns:
            True 如果检测到已登录
        """
        if self._is_closed or not self._page:
            return False
        
        try:
            current_url = self._page.url
            
            # 检查URL模式
            success_patterns = self.PLATFORM_LOGIN_SUCCESS_PATTERNS.get(self.platform, [])
            for pattern in success_patterns:
                if pattern in current_url:
                    logger.info(f"检测到登录成功 (URL匹配): {current_url}")
                    return True
            
            # 平台特定的Cookie检测
            if self.platform == 'douyin':
                return await self._check_douyin_login()
            
            return False
            
        except Exception as e:
            logger.debug(f"检测登录状态时出错: {e}")
            return False
    
    async def _check_douyin_login(self) -> bool:
        """抖音平台专用登录检测
        
        Returns:
            True 如果已登录
        """
        try:
            # 获取所有Cookie
            cookies = await self._context.cookies()
            
            # 检查关键登录Cookie
            cookie_dict = {c['name']: c['value'] for c in cookies}
            key_cookies = ['sessionid', 'sessionid_ss', 'sid_tt', 'sid_guard', 'uid_tt']
            
            found_keys = [k for k in key_cookies if k in cookie_dict and cookie_dict[k]]
            
            if len(found_keys) >= 2:
                logger.info(f"抖音登录Cookie检测成功: {found_keys}")
                return True
            
            return False
            
        except Exception as e:
            logger.debug(f"抖音登录检测失败: {e}")
            return False
    
    async def save_credentials(self) -> bool:
        """保存登录凭证
        
        Returns:
            True 如果保存成功
        """
        if not self._browser_manager or not self._context:
            logger.warning("无法保存凭证: 浏览器未启动")
            return False
        
        try:
            # 使用 ProfileManager 保存 storage_state
            await self._browser_manager.save_state()
            logger.info(f"已保存登录凭证: account_id={self.account_id}")
            return True
            
        except Exception as e:
            logger.error(f"保存凭证失败: {e}", exc_info=True)
            return False
    
    async def get_cookies(self) -> List[Dict[str, Any]]:
        """获取当前 Context 的所有 Cookie
        
        Returns:
            Cookie 列表
        """
        if not self._context:
            return []
        
        try:
            return await self._context.cookies()
        except Exception as e:
            logger.error(f"获取Cookie失败: {e}")
            return []
    
    async def extract_user_info(self) -> Optional[Dict[str, Any]]:
        """从页面提取用户信息
        
        Returns:
            用户信息字典 (nickname, uid 等)
        """
        if not self._page or self._is_closed:
            return None
        
        try:
            # 使用插件系统提取
            from src.plugins.core.plugin_manager import PluginManager
            
            plugin = PluginManager.get_login_plugin(self.platform)
            if plugin:
                # 注意: plugin.extract_user_info 需要 context 参数，但这里的 check_login_status 上下文中
                # self._page 是可用的。
                # LoginPluginInterface.extract_user_info 接收 context (BrowserContext)
                if self._context:
                   result = await plugin.extract_user_info(self._context)
                   if result.success and result.nickname:
                       return {
                            'nickname': result.nickname,
                            'source': 'plugin'
                       }
            
            return None
            
        except Exception as e:
            logger.debug(f"提取用户信息失败: {e}")
            return None
    
    async def on_login_complete(self) -> bool:
        """登录完成后的处理流程
        
        1. 保存凭证
        2. 提取用户信息
        3. 触发成功回调
        
        Returns:
            True 如果所有步骤成功
        """
        if self._login_detected:
            return True  # 避免重复处理
        
        try:
            # 保存凭证
            saved = await self.save_credentials()
            if not saved:
                logger.warning("保存凭证失败，但继续处理")
            
            # 提取用户信息
            user_info = await self.extract_user_info() or {}
            
            # 更新账号管理器（如果提供）
            if self.account_manager and user_info.get('nickname'):
                try:
                    # 更新平台昵称
                    pass  # 根据实际 API 调用
                except Exception as e:
                    logger.warning(f"更新账号信息失败: {e}")
            
            # 标记已检测
            self._login_detected = True
            
            # 触发回调
            if self.on_login_success:
                self.on_login_success(self.account_id, user_info)
            
            logger.info(f"登录流程完成: account_id={self.account_id}, user_info={user_info}")
            return True
            
        except Exception as e:
            logger.error(f"登录完成处理失败: {e}", exc_info=True)
            return False
    
    async def close(self):
        """关闭浏览器和清理资源"""
        self._is_closed = True
        
        if self._browser_manager:
            try:
                await self._browser_manager.close()
                logger.debug(f"已关闭浏览器: account_id={self.account_id}")
            except Exception as e:
                logger.warning(f"关闭浏览器时出错: {e}")
        
        self._browser_manager = None
        self._context = None
        self._page = None
    
    @property
    def is_logged_in(self) -> bool:
        """是否已检测到登录"""
        return self._login_detected
    
    @property
    def page(self):
        """获取当前页面对象"""
        return self._page
    
    @property
    def context(self):
        """获取当前浏览器上下文"""
        return self._context
