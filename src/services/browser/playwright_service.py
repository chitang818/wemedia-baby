# -*- coding: utf-8 -*-
"""
Playwright 浏览器服务
文件路径：src/services/browser/playwright_service.py
功能：管理 Playwright 浏览器实例，提供纯逻辑的浏览器控制服务，不包含UI代码
"""

import asyncio
import logging
import json
import os
from typing import Dict, List, Optional, Union, Callable, Any

from PySide6.QtCore import QObject, Signal

from src.infrastructure.browser.browser_factory import BrowserFactory
from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.plugins.core.plugin_manager import PluginManager
from src.services.account.account_info_updater import update_account_info_from_context
from src.services.account.login_status_verifier import verify_login_status
from config.feature_flags import USE_PLUGIN_SYSTEM

logger = logging.getLogger(__name__)


def _is_playwright_target_closed_error(exc: BaseException) -> bool:
    """浏览器/页面已关闭时 Playwright 抛出的错误，属于预期竞态，不应当作未处理异常刷屏。"""
    m = str(exc).lower()
    return "target page" in m and "closed" in m or "context or browser has been closed" in m


class PlaywrightBrowserService(QObject):
    """Playwright 浏览器服务 (Logic Only)
    
    负责底层浏览器生命周期管理、Cookie提取、自动化操作。
    通过信号与UI层通信。
    """
    
    # === Signals ===
    # 状态更新信号: (account_id, message)
    status_updated = Signal(str, str)
    
    # 消息提示信号: (level, title, message) level: info, success, warning, error
    message_signal = Signal(str, str, str)
    
    # 浏览器启动成功: (account_id, platform_username, platform, is_new)
    browser_launched = Signal(str, str, str, bool)
    
    # 浏览器已关闭: (account_id)
    browser_closed = Signal(str)
    
    # 检测到登录: (account_id, platform)
    login_detected = Signal(str, str)
    
    # 账号信息已保存/更新: (account_id)
    account_saved = Signal(str)
    
    # 账号昵称更新: (account_id, new_nickname)
    account_nickname_updated = Signal(str, str)
    # 账号登录状态更新: (account_id)，静默更新后通知列表刷新
    account_login_status_updated = Signal(str)

    def __init__(self, account_manager):
        super().__init__()
        self.account_manager = account_manager
        self.pw_browser_instance = None
        self._active_browsers = {}  # account_id -> browser_instance
        self._manual_close_notified = set()  # account_id -> already notified/cleaned
        
        # 临时状态存储
        self._current_save_callback = None
        self._current_temp_name = None
        self._pending_rename_target = None
        
        # 监听任务引用，防止被回收
        self._monitor_tasks = {}
        # 早期 Cookie 同步（fire-and-forget），关闭浏览器前必须 cancel，避免闭包后仍访问 context
        self._early_cookie_tasks: Dict[str, List[asyncio.Task]] = {}
        # per-account 锁：防止同一账号并发开启两个浏览器实例
        self._account_locks: Dict[str, asyncio.Lock] = {}
        self._browser_launch_semaphore = asyncio.Semaphore(
            self._read_browser_launch_concurrency()
        )

    def _create_background_task(
        self,
        coro,
        *,
        name: str,
        group: str = "browser",
    ) -> asyncio.Task:
        return get_async_task_registry().create_task(coro, name=name, group=group)

    @staticmethod
    def _read_browser_launch_concurrency() -> int:
        raw = os.environ.get("WMB_BROWSER_LAUNCH_CONCURRENCY", "2")
        try:
            return max(1, min(8, int(raw)))
        except (TypeError, ValueError):
            return 2

    async def verify_account_headless(self, account_id: str, platform: str) -> Dict[str, Any]:
        """无头模式验证账号状态"""
        logger.info(f"启动无头验证: {account_id} ({platform})")
        context = None
        browser_service = None
        try:
            # 1. 获取账号信息
            account = None
            if self.account_manager and str(account_id).isdigit():
                try:
                    account = await self.account_manager.get_account_by_id(int(account_id))
                except Exception as e:
                    logger.debug("获取账号信息失败: %s", e)
            
            platform_username = account.get('platform_username', f"user_{account_id}") if account else f"user_{account_id}"
            profile_folder_name = account.get('profile_folder_name') if account else None
            
            # 2. 启动浏览器 (Headless)
            browser_service = BrowserFactory.get_browser_service(
                account_id=str(account_id),
                platform=platform,
                platform_username=platform_username,
                profile_folder_name=profile_folder_name
            )
            
            context = await browser_service.launch(headless=True)
            if not context:
                raise Exception("无法启动浏览器上下文")
                
            # 3. 注入 Cookie
            if self.account_manager:
                try:
                    cookies = await self.account_manager.load_account_cookie(
                        account_id, merge_storage_state=True
                    )
                    if cookies:
                        pw_cookies = self._normalize_cookies_for_playwright(cookies, platform)
                        if pw_cookies:
                            await context.add_cookies(pw_cookies)
                except Exception as e:
                    logger.warning(f"加载Cookie失败: {e}")
            
            # 4. 验证逻辑
            success = await self._check_login_status(context, platform)
            nickname = None
            new_cookies = None
            
            if success:
                logger.info(f"无头验证成功: {account_id}")
                try:
                    new_pw_cookies = await context.cookies()
                    new_cookies = {c['name']: c['value'] for c in new_pw_cookies}
                    nickname = await self._extract_nickname(context, platform, new_cookies)
                    
                    if self.account_manager:
                         acc_id_int = int(account_id)
                         if new_cookies:
                             await self.account_manager.update_cookie(acc_id_int, new_cookies)
                         if nickname and nickname != platform_username:
                             await self.account_manager.update_platform_username(acc_id_int, nickname)
                             self.account_nickname_updated.emit(str(account_id), nickname)
                except Exception as db_e:
                    logger.warning(f"无头验证更新数据库失败: {db_e}")
            else:
                logger.warning(f"无头验证失败: {account_id}")
            
            return {
                'success': success,
                'nickname': nickname,
                'cookies': new_cookies,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"无头验证异常: {e}", exc_info=True)
            return {
                'success': False,
                'nickname': None,
                'cookies': None,
                'error': str(e)
            }
        finally:
            if browser_service:
                try:
                    if hasattr(browser_service, 'close'):
                        await browser_service.close()
                    elif hasattr(browser_service, 'stop'):
                        await browser_service.stop()
                except Exception as close_e:
                    logger.warning(f"无头浏览关闭异常: {close_e}")
    
    def get_browser_context_by_account(self, account_id: str) -> Optional[Any]:
        """获取指定账号已打开的浏览器上下文
        
        Args:
            account_id: 账号唯一标识 (字符串格式)
            
        Returns:
            若浏览器存在，则返回对应的 SimpleBrowserWrapper，包含 context 和 page；否则返回 None
        """
        browser = self._active_browsers.get(str(account_id))
        if browser:
            return browser
        return None

    async def open_browser_for_db_account(
        self,
        account_id: int,
        headless: Optional[bool] = None,
        *,
        maximize_for_publish: bool = False,
    ) -> Optional['SimpleBrowserWrapper']:
        # per-account 锁防止同账号并发开启两个浏览器
        _aid = str(account_id)
        if _aid not in self._account_locks:
            self._account_locks[_aid] = asyncio.Lock()
        async with self._account_locks[_aid]:
            async with self._browser_launch_semaphore:
                return await self._open_browser_for_db_account_impl(
                    account_id,
                    headless,
                    maximize_for_publish=maximize_for_publish,
                )

    async def _open_browser_for_db_account_impl(
        self,
        account_id: int,
        headless: Optional[bool] = None,
        *,
        maximize_for_publish: bool = False,
    ) -> Optional['SimpleBrowserWrapper']:
        """根据数据库账号ID打开浏览器（模块化方法，供账号库和发布执行器复用）
        
        完整流程：查询账号信息 → 获取平台URL → 启动浏览器 → 注入Cookie → 导航
        
        Args:
            account_id: 数据库中的账号ID（整数）
            headless: 是否无头模式。None 时默认 False（显示窗口）；发布流程传入与「显示浏览器」勾选一致
            maximize_for_publish: 为 True 时，有头模式下启动或复用浏览器后尝试最大化窗口（发布流程使用）
            
        Returns:
            浏览器包装实例 SimpleBrowserWrapper，失败时返回 None
        """
        if headless is None:
            headless = False  # 账号页等调用不传时默认显示浏览器
        # 同账号已打开浏览器时复用，并尝试置前、提示用户，避免“双击无反应”
        existing = self.get_browser_context_by_account(str(account_id))
        if existing:
            try:
                svc = getattr(existing, "browser_manager", None) or getattr(
                    existing, "service", None
                )
                if svc and not headless and hasattr(svc, "apply_browser_tab_layout"):
                    await svc.apply_browser_tab_layout(refresh_env_content=False)
                elif getattr(existing, "page", None):
                    await existing.page.bring_to_front()
                if maximize_for_publish and not headless:
                    if svc and hasattr(svc, "maximize_browser_window"):
                        await svc.maximize_browser_window()
                if svc and hasattr(svc, "pick_business_page_for_automation"):
                    bp = svc.pick_business_page_for_automation()
                    if bp is not None and not bp.is_closed():
                        existing.page = bp
                logger.debug("账号 %s 的浏览器已在运行中，复用现有实例", account_id)
            except Exception as e:
                logger.debug("置前/提示已开浏览器失败: %s", e)
            return existing
        # 1. 查询账号详情；若缺少 profile_folder_name 则从磁盘发现并回填，避免打不开浏览器、Cookie 文件不存在
        account = await self.account_manager.get_account_by_id(account_id)
        if not account:
            raise ValueError(f"账号ID {account_id} 在数据库中不存在")
        await self.account_manager.ensure_account_has_profile_folder(account_id)
        account = await self.account_manager.get_account_by_id(account_id)

        platform_username = account.get('platform_username', '')
        platform = account.get('platform', '')
        profile_folder_name = account.get('profile_folder_name')
        if not (profile_folder_name and profile_folder_name.strip()):
            self.message_signal.emit(
                "warning", "无法打开浏览器",
                "该账号缺少数据目录绑定（或该平台存在多个账号目录无法自动选择），请删除多余目录后重试或重新添加账号。"
            )
            return None
        logger.info(f"模块化开浏览器: account_id={account_id}, 用户名={platform_username}, 平台={platform}, headless={headless}")

        # 视频号：微信侧常见“单点登录/互踢”现象提醒
        # 现象：同时打开两个视频号账号窗口，后登录的账号可能导致先前窗口被要求重新登录（提示“当前账号在其他浏览器或设备登录”）。
        try:
            if platform == "wechat_video":
                other_open = []
                for aid, w in (self._active_browsers or {}).items():
                    if str(aid) == str(account_id):
                        continue
                    svc = getattr(w, "service", None) or getattr(w, "browser_manager", None)
                    p = getattr(svc, "platform", None)
                    if (p or "").strip().lower() == "wechat_video":
                        other_open.append(str(aid))
                if other_open and not headless:
                    self.message_signal.emit(
                        "warning",
                        "视频号多账号提示",
                        "检测到你已打开其它视频号账号的浏览器窗口。\n"
                        "微信视频号可能存在同一微信登录态互踢（后登录会让先登录掉线并要求重新扫码）。\n"
                        "如果出现掉线提示，建议不要同时登录多个视频号账号，或使用不同的微信号分别登录。",
                    )
        except Exception:
            pass
        
        # 2. 获取平台 URL
        # 视频号：若 DB 状态为 offline（Cookie 已失效），直接跳登录页，
        # 避免 goto /platform 被 302 到 login.html 后 browser_wrapper.page 绑定错误 page 对象。
        db_status_for_url = ""
        if self.account_manager:
            try:
                _acc_for_url = await self.account_manager.get_account_by_id(int(account_id))
                db_status_for_url = (_acc_for_url or {}).get("login_status", "") or ""
            except Exception:
                pass
        if platform == "wechat_video" and db_status_for_url == "offline":
            plugin = None
            try:
                plugin = PluginManager.get_login_plugin(platform)
            except Exception:
                pass
            platform_url = (plugin.login_url if plugin else None) or "https://channels.weixin.qq.com/login.html"
            logger.info("视频号账号离线，浏览器初始导航至登录页: %s", platform_url)
            # 离线账号：不注入过期 Cookie，避免监控逻辑将旧 Cookie 误判为新登录
            skip_cookies = True
        else:
            platform_url = self._get_platform_url(platform)
            skip_cookies = False
        
        # 3. 调用已有方法打开浏览器（传入 headless 供发布流程「显示浏览器」勾选生效）
        await self.open_browser_for_account(
            account_id=account_id,
            platform_username=platform_username,
            platform=platform,
            platform_url=platform_url,
            profile_folder_name=profile_folder_name,
            headless=headless,
            maximize_for_publish=maximize_for_publish,
            inject_cookies=not skip_cookies,
            _launch_slot_acquired=True,
        )
        
        # 4. 返回浏览器 wrapper
        return self.get_browser_context_by_account(str(account_id))

    def _get_platform_url(self, platform: str) -> str:
        """获取平台创作者页面 URL（优先插件，降级硬编码）
        
        Args:
            platform: 平台标识
            
        Returns:
            平台 URL
        """
        # 1. 优先从登录插件获取创作者中心落地页（已登录后的页面，第一屏直接呈现已登录态）
        try:
            plugin = PluginManager.get_login_plugin(platform)
            if plugin:
                url = getattr(plugin, 'creator_home_url', None) or getattr(plugin, 'login_url', None)
                if url:
                    return url
        except Exception as e:
            logger.debug(f"从插件获取平台URL失败: {e}")

        # 2. 降级到硬编码创作者中心 URL
        platform_urls = {
            'douyin': 'https://creator.douyin.com/',
            'xiaohongshu': 'https://creator.xiaohongshu.com/new/home',
            'kuaishou': 'https://cp.kuaishou.com/',
            'wechat_video': 'https://channels.weixin.qq.com/platform',
        }
        return platform_urls.get(platform, 'about:blank')

    async def open_browser_for_account(
        self,
        account_id: Union[int, str],
        platform_username: str,
        platform: str,
        platform_url: str,
        profile_folder_name: Optional[str] = None,
        headless: bool = False,
        *,
        maximize_for_publish: bool = False,
        inject_cookies: bool = True,
        _launch_slot_acquired: bool = False,
    ):
        """为已存在的账号打开 Playwright 浏览器"""
        if not _launch_slot_acquired:
            async with self._browser_launch_semaphore:
                return await self.open_browser_for_account(
                    account_id=account_id,
                    platform_username=platform_username,
                    platform=platform,
                    platform_url=platform_url,
                    profile_folder_name=profile_folder_name,
                    headless=headless,
                    maximize_for_publish=maximize_for_publish,
                    inject_cookies=inject_cookies,
                    _launch_slot_acquired=True,
                )

        await self._open_browser_base(
            account_id=str(account_id),
            platform_username=platform_username,
            platform=platform,
            platform_url=platform_url,
            inject_cookies=inject_cookies,
            is_new_account=False,
            profile_folder_name=profile_folder_name,
            headless=headless,
            maximize_for_publish=maximize_for_publish,
        )

    async def open_new_account_window(
        self,
        platform: str,
        on_save_callback: Callable[[str, str, Dict, str], Any] = None,
        platform_url: "Optional[str]" = None,
        fingerprint_config: "Optional[Dict[str, Any]]" = None,
        existing_account_id: "Optional[int]" = None,
        profile_folder_name: "Optional[str]" = None,
        on_login_detected_callback: "Optional[Callable]" = None,
    ):
        """打开新账号登录窗口（标准化流程）

        platform_url 可选：未传入时自动从登录插件的 login_url 获取，
        保证 URL 唯一来源，避免 PLATFORM_CONFIG 与插件之间不一致。

        新增「先占位、后更新」模式：
        - 若传入 existing_account_id 与 profile_folder_name，则使用传入的 profile，
          检测到登录后调用 on_login_detected_callback 更新该占位账号，不再新增账号。
        - 若未传入 existing_account_id，则保持原逻辑：内部生成 profile_id，
          检测到登录后调用 on_save_callback 新增账号。
        """
        import uuid

        # 优先使用调用方传入的 URL，否则从登录插件取
        if not platform_url:
            plugin = PluginManager.get_login_plugin(platform)
            if plugin and plugin.login_url:
                platform_url = plugin.login_url
                logger.info("open_new_account_window: 从插件获取 login_url=%s", platform_url)
            else:
                logger.warning("open_new_account_window: 插件 %s 不存在或无 login_url，无法打开浏览器", platform)
                self.message_signal.emit("error", "平台不支持", f"平台 {platform} 暂无登录插件，无法添加账号")
                return

        # 「先占位、后更新」模式：使用传入的 profile_folder_name
        if existing_account_id is not None and profile_folder_name:
            profile_id = profile_folder_name
            logger.info("开启新账号流程(占位模式): platform=%s, existing_account_id=%s, profile_id=%s, url=%s",
                        platform, existing_account_id, profile_id, platform_url)
            self._current_save_callback = None
            self._current_existing_account_id = existing_account_id
            self._current_on_login_detected_callback = on_login_detected_callback
        else:
            # 兼容旧流程：内部生成 profile_id
            profile_id = "profile_" + uuid.uuid4().hex[:12]
            logger.info("开启新账号流程: platform=%s, profile_id=%s, url=%s", platform, profile_id, platform_url)
            self._current_save_callback = on_save_callback
            self._current_existing_account_id = None
            self._current_on_login_detected_callback = None

        self._current_temp_name = profile_id
        self._save_completed = False
        self._browser_close_triggered = False  # 防重入：关闭浏览器只执行一次

        async with self._browser_launch_semaphore:
            await self._open_browser_base(
                account_id=profile_id,
                platform_username=profile_id,
                platform=platform,
                platform_url=platform_url,
                inject_cookies=False,
                is_new_account=True,
                fingerprint_config=fingerprint_config,
                profile_folder_name=profile_id,
            )


    async def _open_browser_base(
        self,
        account_id: str,
        platform_username: str,
        platform: str,
        platform_url: str,
        inject_cookies: bool,
        is_new_account: bool,
        fingerprint_config: Optional[Dict[str, Any]] = None,
        profile_folder_name: Optional[str] = None,
        headless: bool = False,
        maximize_for_publish: bool = False,
    ):
        try:
            logger.info(f"正在启动 Playwright 浏览器 for {platform_username}... (headless={headless})")
            
            # 1. 启动浏览器（headless 由发布页「显示浏览器」勾选或账号页默认显示决定）
            browser_service = BrowserFactory.get_browser_service(
                account_id=account_id,
                platform=platform,
                platform_username=platform_username,
                fingerprint_config=fingerprint_config,
                profile_folder_name=profile_folder_name
            )
            
            context = await browser_service.launch(
                headless=headless,
                maximize_window=maximize_for_publish,
            )
            if not context:
                raise Exception("无法启动浏览器服务")
            
            # ── Cookie 注入策略：Profile 优先，仅在 Profile 为空时才注入 cookies.json ──
            #
            # 背景：launch_persistent_context 已从磁盘 user_data 目录自动恢复所有 Cookie，
            # 效果等同于"用同一台电脑打开 Chrome"——不需要额外注入。
            # 若再执行 add_cookies(cookies.json)，反而会用可能已过期的旧值覆盖 Profile 里
            # 刚刚由平台刷新好的新 Token，导致登录状态失效，跳转到登录页。
            #
            # 仅在 Profile 为空（首次添加账号后迁移到新机器、或 user_data 被误删）时才注入，
            # 此时 Profile 里没有任何 Cookie，注入是唯一恢复途径。
            if inject_cookies and self.account_manager:
                profile_has_cookies = False
                try:
                    profile_has_cookies = browser_service.profile_manager._user_data_has_chrome_cookie_store()
                except Exception:
                    pass

                if profile_has_cookies:
                    logger.info(
                        "Profile 已有持久化 Cookie，跳过 cookies.json 注入，直接依赖 Profile 恢复登录态 (account_id=%s)",
                        account_id,
                    )
                else:
                    # Profile 为空：首次/迁移场景，从 cookies.json 注入作为 fallback
                    cookies = await self.account_manager.load_account_cookie(
                        account_id, merge_storage_state=True
                    )
                    if cookies:
                        pw_cookies = self._normalize_cookies_for_playwright(cookies, platform)
                        if pw_cookies:
                            try:
                                await context.add_cookies(pw_cookies)
                                logger.info(
                                    "Profile 为空，已从 cookies.json 注入 Cookie: %s 个 (account_id=%s)",
                                    len(pw_cookies),
                                    account_id,
                                )
                            except Exception as e:
                                logger.warning("注入 Cookie 失败: %s", e)
                    else:
                        logger.debug("Profile 为空且无 cookies.json，跳过注入 (account_id=%s)", account_id)
            elif not inject_cookies:
                # 离线账号：持久化上下文会从磁盘自动加载旧的过期 Cookie，
                # 必须主动清除，否则旧 Cookie 会干扰微信扫码登录流程（导致"登录失败"）
                try:
                    await context.clear_cookies()
                    logger.info("已清除持久化上下文中的旧 Cookie（离线账号，确保干净扫码环境）")
                except Exception as e:
                    logger.debug("清除旧 Cookie 失败（不影响流程）: %s", e)

            # ── 标签顺序策略：先环境页（标签1），再业务页（标签2）──
            # Chromium 底层规律：最后创建/导航的标签自动获得焦点。
            # 利用这一规律而非对抗它：
            #   1. 用 pages[0]（持久化 Context 自带的第一个标签）渲染环境信息页（同步完成）
            #   2. 再 new_page() + goto 业务页，Chromium 天然将焦点给业务页
            # 这样彻底消除了之前所有"切完业务页又被环境页抢走"的竞态。
            # 可通过设置页「显示环境标签页」开关关闭此行为（关闭后只有一个业务标签）。
            _show_env_tab = True
            try:
                from src.infrastructure.common.config.app_config_merge import get_app_config_for_read
                _show_env_tab = get_app_config_for_read().get("show_environment_info_tab", False)
            except Exception:
                pass
            if not headless and _show_env_tab and hasattr(browser_service, "open_environment_info_tab"):
                env_page = context.pages[0] if context.pages else None
                if env_page is not None:
                    await browser_service.open_environment_info_tab(
                        focus_tab=False,
                        reuse_page=env_page,
                    )
                    logger.info("有头模式：已在 pages[0] 渲染环境页，即将新建业务标签")

            # 新建业务标签（Chromium 将焦点切到该新标签——这正是我们想要的）
            # 若「显示环境标签页」已关闭：直接复用 pages[0] 作为业务页，不新建标签，保持只有一个标签
            if not headless and not _show_env_tab and context.pages:
                page = context.pages[0]
                logger.info("环境标签页已关闭，复用 pages[0] 作为业务标签（只保留一个标签）")
            else:
                page = await context.new_page()

            await page.goto(platform_url, wait_until="domcontentloaded", timeout=30000)

            # 抖音有 SSO 多跳重定向（creator.douyin.com → passport.bytedance.com → 回跳），
            # goto domcontentloaded 可能在中间重定向页就返回，此时 page.url 尚未稳定到创作者域。
            # 等待 URL 真正落地后再登记主业务页，确保 note_primary_work_page 使用最终页面。
            if platform == "douyin":
                try:
                    await page.wait_for_url("**/creator.douyin.com/**", timeout=10000)
                    logger.info("抖音：页面已稳定至创作者中心: %s", page.url)
                except Exception as e:
                    logger.debug("抖音：等待创作者中心 URL 超时（可能已在目标页）: %s | 当前: %s", e, page.url)

            if hasattr(browser_service, "note_primary_work_page"):
                browser_service.note_primary_work_page(page)

            if maximize_for_publish and not headless:
                await browser_service.maximize_browser_window()

            # 无头模式下没有环境标签需求，不调用 apply_browser_tab_layout

            new_wrapper = SimpleBrowserWrapper(browser_service, context, page)
            self._active_browsers[account_id] = new_wrapper
            logger.info(f"✓ 浏览器实例已存储: account_id={account_id}, total_browsers={len(self._active_browsers)}")
            # pw_browser_instance 仅用于「新账号添加」流程的临时句柄；已有账号打开/发布等场景严禁覆盖它，
            # 否则 close_browser 的 fallback 或新账号监听会误用到别的账号上下文，造成“串号/关错窗口”。
            if is_new_account:
                # 若覆盖时旧实例仍存活，说明上一个新账号添加流程未正常结束，记录警告以便排查。
                if self.pw_browser_instance and getattr(self.pw_browser_instance, "context", None) is not None:
                    logger.warning(
                        "[PlaywrightService] pw_browser_instance 被覆盖时旧实例仍存活 "
                        "(account_id=%s)，旧实例可能泄漏，请检查新账号添加流程是否正常关闭。",
                        account_id,
                    )
                self.pw_browser_instance = new_wrapper
            # 同一账号再次打开时允许手动关窗清理逻辑重新执行
            if str(account_id).isdigit():
                self._manual_close_notified.discard(str(account_id))

            # 4.1 监听用户手动关闭浏览器（context/page close），及时终止静默更新并输出日志
            self._attach_manual_close_watchers(account_id, platform, platform_username)
            # 4.2 监听并自动关闭平台弹出的额外标签（SSO 验证/广告等），保持业务只有一个标签
            self._attach_extra_tab_guard(context, platform)
            
            # 5. 发送启动成功信号 -> UI层响应此信号来弹出 Dialog
            self.browser_launched.emit(account_id, platform_username, platform, is_new_account)
            
            # 6. 启动对应的监听任务
            if is_new_account:
                task = self._create_background_task(
                    self._run_monitor_new_account_safe(account_id, platform),
                    name=f"browser.monitor_new.{account_id}",
                )
                self._monitor_tasks[account_id] = task
            else:
                db_login_status = ""
                if self.account_manager and str(account_id).isdigit():
                    try:
                        _acc = await self.account_manager.get_account_by_id(int(account_id))
                        db_login_status = (_acc or {}).get("login_status", "") or ""
                    except Exception:
                        pass
                task = self._create_background_task(
                    self._run_monitor_existing_safe(
                        account_id,
                        platform_username,
                        platform,
                        db_login_status,
                    ),
                    name=f"browser.monitor_existing.{account_id}",
                )
                self._monitor_tasks[account_id] = task
                # 早期 Cookie 同步：仅当 DB 状态为在线时执行（离线说明 Cookie 已失效，同步无意义）
                if self.account_manager and db_login_status != "offline":
                    intervals = None
                    try:
                        from src.infrastructure.common.config.app_config_merge import get_app_config_for_read

                        cfg = get_app_config_for_read()
                        intervals = cfg.get("cookie_early_sync_intervals")
                    except Exception:
                        intervals = None
                    if not isinstance(intervals, list) or not intervals:
                        # 1 秒先同步一次（减少 cancel 窗口），5 秒再同步一次（捕获平台 Token 刷新后的最新值）
                        intervals = [1.0, 5.0]
                    # 过滤非法值，避免 create_task 里抛异常
                    cleaned: list[float] = []
                    for x in intervals:
                        try:
                            v = float(x)
                            if 0 < v <= 30:
                                cleaned.append(v)
                        except Exception:
                            continue
                    if not cleaned:
                        cleaned = [2.0]
                    for d in cleaned:
                        t = self._create_background_task(
                            self._early_cookie_sync(account_id, context, delay=d),
                            name=f"browser.early_cookie_sync.{account_id}.{d:g}",
                        )
                        self._register_early_cookie_task(account_id, t)
            
        except Exception as e:
            logger.error(f"启动浏览器失败: {e}", exc_info=True)
            self.message_signal.emit("error", "启动失败", str(e))

    def _register_early_cookie_task(self, account_id: str, task: asyncio.Task) -> None:
        aid = str(account_id)
        bucket = self._early_cookie_tasks.setdefault(aid, [])
        bucket.append(task)

        def _cleanup(t: asyncio.Task) -> None:
            try:
                bucket.remove(t)
            except ValueError:
                pass

        task.add_done_callback(_cleanup)

    def _cancel_early_cookie_tasks(self, account_id: str) -> None:
        tasks = self._early_cookie_tasks.pop(str(account_id), [])
        for t in tasks:
            if not t.done():
                t.cancel()

    def _cancel_all_early_cookie_tasks(self) -> None:
        for aid in list(self._early_cookie_tasks.keys()):
            self._cancel_early_cookie_tasks(aid)

    # 各平台的业务域白名单：只有这些域的标签才允许存在，其余新弹出的标签自动关闭
    _PLATFORM_ALLOWED_DOMAINS: dict = {
        "douyin":       ["douyin.com", "bytedance.com"],
        "kuaishou":     ["kuaishou.com", "gifshow.com"],
        "wechat_video": ["weixin.qq.com", "qq.com", "tencent.com"],
    }

    def _attach_extra_tab_guard(self, context, platform: str) -> None:
        """监听 context 的新页面事件，自动关闭平台弹出的额外 SSO/广告标签。

        抖音/快手等平台在 Session 初始化时会通过 window.open 或 Service Worker
        弹出 summon.bytedance.com、lf-zt.douyin.com 等验证标签，
        这些标签在普通 Chrome 里会被弹窗拦截器静默屏蔽，
        但 Playwright 默认放行。此处在 Python 层面做同等拦截：
        新标签弹出后立即检查其 URL，若不属于当前平台业务域则关掉。
        """
        allowed = self._PLATFORM_ALLOWED_DOMAINS.get(platform, [])

        def _on_new_page(new_page) -> None:
            async def _check_and_close():
                try:
                    # 等页面 URL 稳定（最多 2 秒）
                    import asyncio as _asyncio
                    for _ in range(20):
                        url = (new_page.url or "").strip()
                        if url and url != "about:blank":
                            break
                        await _asyncio.sleep(0.1)
                    url = (new_page.url or "").strip().lower()
                    if not url or url == "about:blank":
                        return
                    is_allowed = any(domain in url for domain in allowed)
                    if not is_allowed:
                        logger.info(
                            "额外标签守卫：自动关闭非业务标签 url=%s (platform=%s)", url, platform
                        )
                        try:
                            await new_page.close()
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug("额外标签守卫异常（可忽略）: %s", e)

            try:
                self._create_background_task(
                    _check_and_close(),
                    name=f"browser.extra_tab_guard.{platform or 'unknown'}",
                )
            except Exception:
                pass

        try:
            context.on("page", _on_new_page)
            logger.debug("额外标签守卫已挂载: platform=%s, allowed=%s", platform, allowed)
        except Exception as e:
            logger.debug("挂载额外标签守卫失败（可忽略）: %s", e)

    def _attach_manual_close_watchers(self, account_id: str, platform: str, username: str) -> None:
        """监听 context/page 的关闭事件（用户手动关窗），并做清理与日志输出。"""
        try:
            wrapper = self.get_browser_context_by_account(str(account_id))
            if not wrapper:
                return
            ctx = getattr(wrapper, "context", None)
            pg = getattr(wrapper, "page", None)
            if not ctx:
                return

            def _schedule(reason: str):
                try:
                    async def _safe_manual_close():
                        try:
                            await self._on_manual_browser_closed(str(account_id), platform, username, reason)
                        except Exception as e:
                            if _is_playwright_target_closed_error(e):
                                logger.debug("手动关闭清理: 浏览器已断开，忽略: %s", e)
                            else:
                                logger.warning("手动关闭清理异常: %s", e, exc_info=True)

                    self._create_background_task(
                        _safe_manual_close(),
                        name=f"browser.manual_close.{account_id}",
                    )
                except Exception:
                    pass

            try:
                ctx.on("close", lambda: _schedule("context_closed"))
            except Exception:
                pass
            # 仅关「最后一个」标签页才视为用户关浏览器：避免站点关旧页开新页时误触发整段清理
            try:
                if pg:
                    def _on_initial_page_close():
                        async def _deferred_page_close():
                            for _ in range(5):
                                await asyncio.sleep(0.1)
                                try:
                                    w = self.get_browser_context_by_account(str(account_id))
                                    if not w:
                                        return
                                    c = getattr(w, "context", None)
                                    if not c:
                                        await self._on_manual_browser_closed(
                                            str(account_id), platform, username, "context_gone"
                                        )
                                        return
                                    try:
                                        pages = list(c.pages)
                                    except Exception:
                                        await self._on_manual_browser_closed(
                                            str(account_id), platform, username, "context_closed_after_page"
                                        )
                                        return
                                    alive = any(
                                        not p.is_closed()
                                        for p in pages
                                        if not getattr(p, "_error", None)
                                    )
                                    if alive:
                                        return
                                except Exception:
                                    return
                            await self._on_manual_browser_closed(
                                str(account_id), platform, username, "all_pages_closed"
                            )

                        try:
                            self._create_background_task(
                                _deferred_page_close(),
                                name=f"browser.deferred_page_close.{account_id}",
                            )
                        except Exception:
                            pass

                    pg.on("close", _on_initial_page_close)
            except Exception:
                pass
        except Exception:
            return

    async def _on_manual_browser_closed(self, account_id: str, platform: str, username: str, reason: str) -> None:
        """用户手动关闭浏览器时：终止静默更新、清理缓存、回填 cookie，并输出关闭日志。"""
        # 幂等：避免 context/page 多次 close 重复触发
        if account_id in self._manual_close_notified:
            return
        self._manual_close_notified.add(account_id)

        logger.info("检测到浏览器已手动关闭: account_id=%s, username=%s, platform=%s, reason=%s",
                    account_id, username, platform, reason)

        # 0) 在仍能从 _active_browsers 拿到 context 时，尽力同步 Cookie/昵称/状态（手动关窗不走 close_browser 的 _sync_before_close）
        if account_id.isdigit() and self.account_manager:
            browser_wrapper = self._active_browsers.get(account_id)
            if browser_wrapper and getattr(browser_wrapper, "context", None):
                try:
                    account = await self.account_manager.get_account_by_id(int(account_id))
                    if account:
                        await self.update_account_from_browser(
                            account_id,
                            account.get("platform_username") or "",
                            account.get("platform") or platform,
                            silent=True,
                        )
                except Exception as e:
                    logger.debug("手动关窗前同步账号信息失败(可忽略): %s", e)

        # 1) 终止静默更新任务与早期 Cookie 同步（手动关窗不会走 close_browser）
        self._cancel_early_cookie_tasks(account_id)
        task = self._monitor_tasks.pop(account_id, None)
        if task:
            try:
                task.cancel()
            except Exception:
                pass
            logger.info("已终止静默更新任务: account_id=%s", account_id)

        # 2) 清理活跃浏览器缓存（避免后续误认为仍打开）
        self._active_browsers.pop(account_id, None)
        if self.pw_browser_instance and getattr(self.pw_browser_instance, "context", None) is None:
            self.pw_browser_instance = None

        # 3) cookie 回填（不影响主流程）
        try:
            if account_id.isdigit():
                await self._try_reload_account_cookie_after_close(int(account_id), platform)
        except Exception:
            pass

        # 4) 发出关闭信号（UI 可刷新状态）
        try:
            self.browser_closed.emit(account_id)
        except Exception:
            pass

    async def close_browser(self, account_id: str):
        """关闭浏览器逻辑"""
        logger.info(f"正在关闭浏览器: {account_id}")
        # 0. 取消早期 Cookie 同步，避免 context 关闭后协程仍执行 Playwright API
        self._cancel_early_cookie_tasks(account_id)

        # 1. 停止监听任务（若当前就是该任务在调 close_browser，则不要取消自己，否则会在此后首个 await 处抛 CancelledError，导致浏览器未关就退出）
        _monitor_task = self._monitor_tasks.pop(account_id, None)
        if _monitor_task is not None and asyncio.current_task() != _monitor_task:
            _monitor_task.cancel()
            logger.debug(f"已取消监听任务: {account_id}")
        
        # 2. 关闭浏览器
        logger.info(f"当前活跃浏览器: {list(self._active_browsers.keys())}")
        browser = self._active_browsers.pop(account_id, None)
        logger.info(f"从字典中获取浏览器: browser={'找到' if browser else '未找到'}")
        # 禁止对“已有账号”使用 pw_browser_instance 兜底，避免误关其它账号窗口。
        # pw_browser_instance 仅用于新账号添加流程（temp_add_/profile_）的临时实例。
        if (
            not browser
            and self.pw_browser_instance
            and isinstance(account_id, str)
            and (account_id.startswith("temp_add_") or account_id.startswith("profile_"))
        ):
            browser = self.pw_browser_instance
            self.pw_browser_instance = None
            logger.info(f"使用新账号流程 fallback 浏览器实例: {account_id}")
        elif browser and self.pw_browser_instance is browser:
            self.pw_browser_instance = None  # 新账号等同一实例，关闭后清空避免悬空引用
             
        try:
            if browser:
                # 先导出 storage_state 快照（关闭后无 context 时仅作归档；业务侧 Cookie 以 cookies.json 为准）
                try:
                    if hasattr(browser, "service") and hasattr(browser.service, "save_state"):
                        await browser.service.save_state()
                except Exception as save_e:
                    logger.debug("关闭前保存 storage_state 失败: %s", save_e)
                # [关键] 在关闭前强制同步一次最新状态 (Cookie/LocalStorage)，失败不影响关闭
                try:
                    await self._sync_before_close(account_id)
                except Exception as sync_e:
                    logger.debug("关闭前状态同步异常(不影响关闭): %s", sync_e)

                logger.info(f"准备释放浏览器资源: {account_id}")
                try:
                    await asyncio.wait_for(browser.close(), timeout=5.0)
                    logger.info(f"✓ 浏览器资源释放成功: {account_id}")
                except asyncio.TimeoutError:
                    logger.error(f"✗ 浏览器释放资源超时: {account_id}，可能仍有残留进程")
                except Exception as e:
                    logger.error(f"✗ 关闭浏览器实例失败: {e}", exc_info=True)
                # 兜底：若包装类持有 context，直接关闭 context 确保窗口关闭（新账号流程等）
                if hasattr(browser, "context") and browser.context:
                    try:
                        await asyncio.wait_for(browser.context.close(), timeout=2.0)
                        logger.info(f"✓ 已兜底关闭 context: {account_id}")
                    except Exception as ctx_e:
                        logger.debug("兜底关闭 context 时异常: %s", ctx_e)
            else:
                logger.warning(f"未找到活跃浏览器实例: {account_id} (可能已手动关闭)")
        finally:
            # 3. 执行目录清理 (强制执行)
            # 即使释放资源超时或报错，也要尝试清理目录
            logger.info(f"执行最后的数据目录清理...")
            await asyncio.sleep(0.5)
            await self._handle_directory_cleanup(account_id)
        
        # 4. 发送关闭信号
        self.browser_closed.emit(account_id)
        logger.info(f"🎯 已发送浏览器关闭确认信号: {account_id}")

    async def _sync_before_close(self, account_id: str) -> None:
        """关闭前尽力同步账号状态（不抛异常，不阻塞关闭流程）。"""
        try:
            logger.info("关闭前执行状态同步: %s", account_id)
            if not self.account_manager:
                return
            if not isinstance(account_id, str) or not account_id.isdigit():
                # 临时账号 profile_xxx / temp_add_xxx 等不进行 DB 同步
                return
            account = await self.account_manager.get_account_by_id(int(account_id))
            if not account:
                return
            await self.update_account_from_browser(
                account_id,
                account.get("platform_username") or "",
                account.get("platform") or "",
                silent=True,
            )
        except Exception as e:
            logger.warning("关闭前同步状态失败 (不影响关闭流程): %s", e)

    async def shutdown(self):
        """应用退出时关闭所有活跃浏览器，避免残留进程。"""
        logger.info("PlaywrightBrowserService 开始 shutdown，关闭所有活跃浏览器...")
        self._cancel_all_early_cookie_tasks()
        # 1. 取消所有监听任务
        for account_id, task in list(self._monitor_tasks.items()):
            try:
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=0.2)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            except Exception as e:
                logger.debug("等待监控任务结束异常: %s", e)
        self._monitor_tasks.clear()

        # 2. 关闭前同步所有活跃账号的 Cookie/状态，确保强退时 cookies.json 不落后
        #    先同步再关闭：Chromium 持久化 Profile 由 context.close() 落盘，
        #    cookies.json / storage_state 由此处显式写入，两者保持一致。
        account_ids = list(self._active_browsers.keys())
        sync_tasks = []
        for account_id in account_ids:
            browser = self._active_browsers.get(account_id)
            if not browser:
                continue
            # save_state（写 storage_state.json）
            try:
                if hasattr(browser, "service") and hasattr(browser.service, "save_state"):
                    sync_tasks.append(
                        self._create_background_task(
                            browser.service.save_state(),
                            name=f"browser.shutdown_save_state.{account_id}",
                        )
                    )
            except Exception:
                pass
            # _sync_before_close（从 context.cookies() 写回 cookies.json）
            sync_tasks.append(
                self._create_background_task(
                    self._sync_before_close(account_id),
                    name=f"browser.shutdown_sync.{account_id}",
                )
            )
        if sync_tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*sync_tasks, return_exceptions=True), timeout=3.0)
                logger.info("shutdown: 所有账号状态同步完成")
            except asyncio.TimeoutError:
                logger.warning("shutdown: 状态同步超时（3s），继续退出")

        # 3. 关闭所有 _active_browsers 中的浏览器（短超时，不阻塞退出）
        for account_id in account_ids:
            browser = self._active_browsers.pop(account_id, None)
            if not browser:
                continue
            try:
                await asyncio.wait_for(browser.close(), timeout=2.0)
                logger.info(f"shutdown: 已关闭浏览器 account_id={account_id}")
            except asyncio.TimeoutError:
                logger.warning(f"shutdown: 关闭 account_id={account_id} 超时，继续退出")
            except Exception as e:
                logger.warning(f"shutdown: 关闭 account_id={account_id} 异常: {e}")

        # 4. 关闭临时实例 pw_browser_instance
        if self.pw_browser_instance:
            try:
                await asyncio.wait_for(self.pw_browser_instance.close(), timeout=2.0)
            except (asyncio.TimeoutError, Exception):
                pass
            self.pw_browser_instance = None

        logger.info("PlaywrightBrowserService shutdown 完成")

    async def _handle_directory_cleanup(self, account_id: str):
        """处理目录清理"""
        # 同时支持旧的 temp_add_ 和统一后的 profile_ 前缀
        if isinstance(account_id, str) and (account_id.startswith("temp_add_") or account_id.startswith("profile_")):
            temp_name = self._current_temp_name
            
            # 如果保存已完成，直接返回，保留目录
            if self._save_completed:
                logger.info(f"账号已保存，保留数据目录作为永久档案: {temp_name}")
                self._current_temp_name = None
                return

            # 未保存则清理 (用户取消操作)
            logger.info(f"账号未保存，准备清理临时目录: {temp_name}")
            
            if temp_name:
                try:
                    import shutil
                    import asyncio as _asyncio
                    from src.infrastructure.common.path_manager import PathManager

                    def _cleanup_temp_dir(name: str) -> None:
                        """同步目录清理，在线程池中执行以避免阻塞事件循环"""
                        data_dir = PathManager.get_app_data_dir() / "data"
                        if not data_dir.exists():
                            return
                        for platform_dir in data_dir.iterdir():
                            if platform_dir.is_dir():
                                temp_dir = platform_dir / name
                                if temp_dir.exists():
                                    try:
                                        shutil.rmtree(temp_dir, ignore_errors=True)
                                        logger.info(f"已清理废弃的临时目录: {temp_dir}")
                                    except Exception as ex:
                                        logger.warning(f"清理临时目录失败: {ex}")
                                    break

                    # iterdir + rmtree 均为同步磁盘操作，移到线程池避免阻塞事件循环
                    await _asyncio.to_thread(_cleanup_temp_dir, temp_name)
                except Exception as e:
                    logger.error(f"目录清理异常: {e}", exc_info=True)
                
                self._current_temp_name = None

    # === 业务逻辑 ===
    async def _run_monitor_new_account_safe(self, account_id: str, platform: str) -> None:
        """包装监听任务，避免 Playwright 关闭竞态导致未处理异常上报事件循环。"""
        try:
            await self._monitor_new_account_login(account_id, platform)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if _is_playwright_target_closed_error(e):
                logger.debug("新账号登录监听因浏览器关闭结束: %s", e)
            else:
                logger.warning("新账号登录监听异常: %s", e, exc_info=True)

    async def _run_monitor_existing_safe(self, account_id, username, platform, db_login_status: str = "") -> None:
        try:
            await self._monitor_existing_account_update(account_id, username, platform, db_login_status)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if _is_playwright_target_closed_error(e):
                logger.debug("已有账号静默更新因浏览器关闭结束: %s", e)
            else:
                logger.warning("已有账号静默更新异常: %s", e, exc_info=True)

    async def _monitor_new_account_login(self, account_id: str, platform: str):
        """监听新账号登录"""
        logger.info(f"开始监听登录: {account_id}")
        retry_count = 0
        while retry_count < 300:
            if not self.pw_browser_instance:
                break
            
            try:
                context = self.pw_browser_instance.context
                if await self._check_login_status(context, platform):
                    logger.info("检测到登录成功")
                    self.status_updated.emit(account_id, "检测到登录成功！\n正在自动提取账号信息...")
                    self.login_detected.emit(account_id, platform)
                    
                    await asyncio.sleep(2)
                    await self.handle_save_new_account(account_id, platform)
                    return
            except Exception as e:
                logger.debug("保存新账号或检查登录状态异常: %s", e)
            
            await asyncio.sleep(3)
            retry_count += 1

        # 监听结束仍未检测到登录时兜底关闭浏览器，避免浏览器一直不关闭
        if not self._save_completed and account_id in self._active_browsers:
            logger.info("新账号监听结束未检测到登录，关闭浏览器: %s", account_id)
            await self._close_new_account_browser(account_id)

    async def handle_save_new_account(self, temp_id: str, platform: str):
        """执行保存逻辑 (提取 -> 回调 -> 标记完成)。防重入：同一流程只执行一次回调，避免账号库重复创建。

        支持两种模式：
        1. 「先占位、后更新」模式：若存在 _current_existing_account_id 与 _current_on_login_detected_callback，
           则调用更新回调，不新增账号。
        2. 旧模式：调用 _current_save_callback 新增账号。
        """
        try:
            # 防重入：若本流程已执行过保存，直接返回，避免重复调用回调导致创建两个相同账号
            if self._save_completed:
                logger.debug("handle_save_new_account 已执行过，跳过重复保存 (temp_id=%s)", temp_id)
                return
            if not self.pw_browser_instance:
                self.message_signal.emit("warning", "警告", "浏览器未连接")
                return

            self.message_signal.emit("info", "提示", "正在提取账号信息...")
            context = self.pw_browser_instance.context

            cookies = await context.cookies()
            if not cookies:
                await asyncio.sleep(1)
                cookies = await context.cookies()
            if not cookies:
                raise Exception("未提取到 Cookie")

            cookie_dict = {c['name']: c['value'] for c in cookies}
            existing_id = getattr(self, "_current_existing_account_id", None)
            login_callback = getattr(self, "_current_on_login_detected_callback", None)
            nickname = await self._extract_nickname(
                context,
                platform,
                cookie_dict,
                account_id=existing_id,
                account_name=temp_id,
            )

            if not nickname:
                nickname = f"新账号_{platform}"
                logger.warning("未提取到昵称，使用默认值")

            # 先标记再回调，确保并发重入时只执行一次
            self._save_completed = True
            profile_name = self._current_temp_name or ""

            # 「先占位、后更新」模式
            if existing_id is not None and login_callback is not None:
                logger.info("更新占位账号: account_id=%s, nickname=%s, platform=%s, profile=%s",
                            existing_id, nickname, platform, profile_name)
                if asyncio.iscoroutinefunction(login_callback):
                    await login_callback(existing_id, nickname, platform, cookie_dict, profile_name)
                else:
                    login_callback(existing_id, nickname, platform, cookie_dict, profile_name)
                self.message_signal.emit("success", "登录成功", f"账号 {nickname} 已更新！")
                # 发出昵称/状态更新信号，供 UI 刷新
                self.account_nickname_updated.emit(str(existing_id), nickname)
                self.account_login_status_updated.emit(str(existing_id))
            else:
                # 旧模式：新增账号
                if not profile_name:
                    logger.warning("保存新账号时 _current_temp_name 为空，将导致 profile_folder_name 未写入 DB")
                else:
                    logger.info("保存新账号: nickname=%s, platform=%s, profile_folder_name=%s", nickname, platform, profile_name)
                if self._current_save_callback:
                    if asyncio.iscoroutinefunction(self._current_save_callback):
                        await self._current_save_callback(nickname, platform, cookie_dict, profile_name)
                    else:
                        self._current_save_callback(nickname, platform, cookie_dict, profile_name)
                self.message_signal.emit("success", "保存成功", f"账号 {nickname} 已保存！\n无需重命名，安全退出。")
                self.account_saved.emit(temp_id)

        except Exception as e:
            logger.error(f"保存失败: {e}", exc_info=True)
            self.message_signal.emit("error", "保存回调失败", str(e))
        finally:
            # 清理本次流程的临时状态
            self._current_existing_account_id = None
            self._current_on_login_detected_callback = None
            # 无论成功或失败，都要通过统一封装关闭浏览器（防重入）
            await asyncio.sleep(0.3)  # save 已 await 完成，0.3s 仅作 UX 缓冲
            await self._close_new_account_browser(temp_id)

    async def _close_new_account_browser(self, temp_id: str):
        """防重入地关闭新账号流程的浏览器；多路触发时只执行一次 close_browser。"""
        if getattr(self, "_browser_close_triggered", False):
            logger.debug("_close_new_account_browser: 已触发过，跳过重复关闭 (temp_id=%s)", temp_id)
            return
        self._browser_close_triggered = True
        try:
            await self.close_browser(temp_id)
        except Exception as e:
            logger.error("关闭新账号浏览器失败: %s", e, exc_info=True)

    async def update_account_from_browser(self, account_id: str, platform_username: str, platform: str, silent=False):
        """更新已有账号信息（委托 account_info_updater，与打开浏览器后的静默更新同一套逻辑）。

        仅当该 account_id 在 _active_browsers 中已有实例时执行；不使用全局 pw_browser_instance 兜底，避免误用其他账号上下文。
        """
        browser_wrapper = None
        try:
            browser_wrapper = self.get_browser_context_by_account(str(account_id))
            if not browser_wrapper:
                if not silent:
                    self.message_signal.emit("warning", "提示", "该账号的浏览器未连接或未打开，无法提取信息")
                return
            if not silent:
                self.message_signal.emit("info", "提示", "正在更新信息...")
            try:
                acc_id_int = int(account_id)
            except ValueError:
                logger.warning("account_id 不是有效整数: %s, 跳过更新", account_id)
                if not silent:
                    self.message_signal.emit("error", "失败", "账号 ID 无效")
                return
            context = browser_wrapper.context
            new_nickname, new_status = await update_account_info_from_context(
                context, acc_id_int, platform_username, platform, self.account_manager
            )
            if new_nickname is not None:
                self.account_nickname_updated.emit(str(account_id), new_nickname)
            if new_status is not None:
                self.account_login_status_updated.emit(str(account_id))
            if not silent:
                self.message_signal.emit("success", "成功", "账号信息已从浏览器成功更新")
        except Exception as e:
            err_msg = str(e)
            if "Target page, context or browser has been closed" in err_msg:
                err_msg = "浏览器或页面已关闭，无法从当前实例提取状态"
                self._active_browsers.pop(str(account_id), None)
                if browser_wrapper and self.pw_browser_instance == browser_wrapper:
                    self.pw_browser_instance = None
            if not silent:
                self.message_signal.emit("error", "失败", err_msg)

    async def _early_cookie_sync(self, account_id: str, context, delay: float = 1.0) -> None:
        """打开已有账号浏览器后延迟指定秒数将当前 context 的 Cookie 写回 cookies.json，使下次「刷新登录状态」可用。

        取消保护：若任务被 cancel（用户在延迟内关闭浏览器），捕获 CancelledError 后仍尝试同步一次，
        避免用户快速关闭浏览器时 cookies.json 完全错过本次更新。
        """
        cancelled = False
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            cancelled = True
            # 不立即 raise，先尝试做一次同步再退出

        if not self.account_manager:
            if cancelled:
                raise asyncio.CancelledError
            return
        try:
            acc_id_int = int(account_id)
        except ValueError:
            if cancelled:
                raise asyncio.CancelledError
            return
        try:
            cookies = await context.cookies()
        except Exception as e:
            if _is_playwright_target_closed_error(e):
                logger.debug("早期 Cookie 同步: 上下文已关闭，跳过: %s", e)
            else:
                logger.debug("早期 Cookie 同步: 获取 cookies 失败: %s", e)
            if cancelled:
                raise asyncio.CancelledError
            return
        if not cookies:
            if cancelled:
                raise asyncio.CancelledError
            return
        cookie_dict = {c.get("name"): c.get("value") for c in cookies if c.get("name")}
        if not cookie_dict:
            if cancelled:
                raise asyncio.CancelledError
            return
        try:
            await self.account_manager.update_cookie(acc_id_int, cookie_dict)
            logger.info(
                "早期 Cookie 同步完成: account_id=%s%s",
                account_id,
                "（取消后补救）" if cancelled else "",
            )
        except Exception as e:
            logger.warning("早期 Cookie 同步失败: %s", e)
        # 顺带导出 storage_state 快照
        try:
            wrapper = self.get_browser_context_by_account(str(account_id))
            if wrapper and hasattr(wrapper, "service") and hasattr(wrapper.service, "save_state"):
                await wrapper.service.save_state()
        except Exception as e:
            logger.debug("早期同步写入 storage_state 失败: %s", e)

        if cancelled:
            raise asyncio.CancelledError

    async def _try_reload_account_cookie_after_close(self, account_id: int, platform: str) -> None:
        """浏览器已关闭时，尝试从账号目录 cookies.json 再加载一次（确认 DB/内存侧与磁盘一致）。"""
        if not self.account_manager:
            return
        try:
            cookies = await self.account_manager.load_account_cookie(
                account_id, merge_storage_state=True
            )
            if cookies:
                logger.info("浏览器关闭后 Cookie 可用(已自动回填): account_id=%s", account_id)
        except Exception as e:
            logger.debug("静默更新失败后 Cookie 回填失败: %s", e)

    def _is_browser_closed(self, browser_wrapper) -> bool:
        """检查浏览器上下文是否已关闭。

        Playwright 的 BrowserContext 没有公开的 is_closed() 方法（Page 才有），
        所以不能用 getattr(ctx, "is_closed", fallback) 来判断。
        策略：尝试访问 ctx.pages，若抛异常说明连接已断开；
        若能拿到列表，说明 context 仍存活（即使所有 page 均 is_closed，窗口也可能仍在）。
        """
        try:
            ctx = getattr(browser_wrapper, "context", None)
            if ctx is None:
                return True
            # BrowserContext 没有 is_closed()，通过访问 pages 探测连接是否存活
            try:
                pages = list(ctx.pages)
            except Exception:
                return True
            # context 连接正常 → 视为浏览器仍在运行
            return False
        except Exception:
            return True

    async def _is_browser_closed_with_retry(
        self, browser_wrapper, retries: int = 6, delay: float = 0.12
    ) -> bool:
        """关签/导航瞬间可能出现「全部页已关、新页尚未挂上」的短窗口，短暂重试避免误判。"""
        for i in range(retries):
            if not self._is_browser_closed(browser_wrapper):
                return False
            if i < retries - 1:
                await asyncio.sleep(delay)
        return True

    def _context_shows_wechat_channels_login(self, browser_wrapper) -> bool:
        try:
            from src.plugins.pro.wechat_video.login_plugin import is_channels_login_page_url

            # 优先读包装器持有的首页引用（与 context.pages 列表偶发不一致时仍能拿到地址栏）
            pg0 = getattr(browser_wrapper, "page", None)
            if pg0:
                try:
                    if is_channels_login_page_url((pg0.url or "").strip()):
                        return True
                except Exception:
                    pass

            ctx = getattr(browser_wrapper, "context", None)
            if not ctx:
                return False
            try:
                _pages = list(ctx.pages)
            except Exception:
                return False
            for p in _pages:
                try:
                    if is_channels_login_page_url((p.url or "").strip()):
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    async def _refresh_page_before_profile_sync(self, browser_wrapper, platform: str) -> None:
        """登录刚成功时尽量让业务页就绪。视频号：直接导航 + DOM 等待（不等自动跳转、不等 networkidle）。"""
        try:
            if platform == "wechat_video":
                ctx = getattr(browser_wrapper, "context", None)
                svc = getattr(browser_wrapper, "service", None)
                if not ctx:
                    return
                target_url = "https://channels.weixin.qq.com/platform"
                picked = None
                main = getattr(browser_wrapper, "page", None)
                try:
                    if main and not main.is_closed():
                        picked = main
                except Exception:
                    picked = None
                if picked is None:
                    for p in list(getattr(ctx, "pages", []) or []):
                        try:
                            if not p.is_closed():
                                picked = p
                                break
                        except Exception:
                            continue
                if picked is None:
                    return

                # 检查当前 URL，不在创作者中心则直接 goto（不等自动跳转）
                try:
                    current_url = picked.url or ""
                except Exception:
                    current_url = ""

                if "channels.weixin.qq.com/platform" not in current_url:
                    try:
                        await picked.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                        logger.info("视频号：已导航至创作者中心: %s", picked.url)
                    except Exception as e:
                        logger.warning("视频号：导航创作者中心失败: %s", e)
                        return
                else:
                    logger.info("视频号：页面已在创作者中心: %s", current_url)

                # 等待关键 DOM 而非 networkidle（视频号后台有心跳，networkidle 经常超时）
                try:
                    await picked.wait_for_selector(
                        ".finder-nickname, .account-info, .account-name",
                        state="attached",
                        timeout=8000,
                    )
                    await asyncio.sleep(0.5)
                except Exception:
                    await asyncio.sleep(1.0)

                # 登记为主业务页
                if svc and hasattr(svc, "note_primary_work_page"):
                    svc.note_primary_work_page(picked)
                # 切到前台
                try:
                    if svc and hasattr(svc, "_cdp_bring_page_to_front"):
                        await svc._cdp_bring_page_to_front(picked)
                    elif svc and hasattr(svc, "focus_first_tab_for_ui"):
                        await svc.focus_first_tab_for_ui()
                except Exception as e:
                    logger.debug("视频号：切回业务标签失败(可忽略): %s", e)
                return
            ctx = getattr(browser_wrapper, "context", None)
            if not ctx:
                return
            page = None
            for p in list(getattr(ctx, "pages", []) or []):
                try:
                    if not p.is_closed():
                        page = p
                        break
                except Exception:
                    continue
            if page is None:
                page = await ctx.new_page()
            target = self._get_platform_url(platform)
            await page.goto(target, wait_until="domcontentloaded", timeout=20000)
            await asyncio.sleep(0.35)
        except Exception as e:
            logger.debug("刷新平台页以便同步昵称失败(可忽略): %s", e)

    async def _monitor_until_login(self, account_id, username, platform, browser_wrapper, acc_id_int):
        """账号离线时：高频轮询浏览器 Cookie，待用户手动登录后立即导航并更新账号信息。

        核心改进（修复视频号登录慢的 5 大根因）：
        1. 使用浏览器 Cookie 直接检测（而非 HTTP 鉴权），每 1.5 秒一轮
        2. 同时监听页面 URL 变化（微信可能自动跳转到 /platform）
        3. 检测到登录后立即主动导航到创作者中心（不等自动跳转）
        4. 导航后只等关键 DOM 而非 networkidle（视频号后台永远有心跳请求）
        5. 昵称提取与状态更新并行，不串行叠加等待
        """
        max_attempts = 200  # 1.5s × 200 = 300s = 5 分钟
        logger.info("开始登录监控（Cookie 高频检测模式）: %s", username)

        # ── 快照初始 Cookie 状态，防止旧的过期 Cookie 导致假阳性 ──
        initial_sessionid = None
        try:
            cookies_raw = await browser_wrapper.context.cookies()
            for c in (cookies_raw or []):
                if c.get("name") == "sessionid":
                    initial_sessionid = c.get("value")
                    break
            if initial_sessionid:
                logger.debug("登录监控: 记录初始 sessionid 快照 (长度=%d)，后续仅当值变化时才判定为新登录",
                             len(initial_sessionid))
        except Exception as e:
            logger.debug("登录监控: 获取初始 Cookie 快照失败: %s", e)

        for attempt in range(max_attempts):
            await asyncio.sleep(1.5)
            if self._is_browser_closed(browser_wrapper):
                logger.info("浏览器已关闭，停止登录监控: %s", username)
                return

            try:
                context = browser_wrapper.context

                # ── 检测登录 ──
                login_detected = False

                if platform == "wechat_video":
                    # 视频号：对比 sessionid 是否发生变化（防止旧 Cookie 假阳性）
                    try:
                        cookies_raw = await context.cookies()
                        current_sessionid = None
                        has_wxuin = False
                        has_sessionid = False
                        target_domain = "channels.weixin.qq.com"
                        for c in (cookies_raw or []):
                            name = c.get("name", "")
                            domain = (c.get("domain") or "").strip().lstrip(".")
                            if domain != target_domain.lstrip("."):
                                continue
                            if name == "wxuin":
                                has_wxuin = True
                            elif name == "sessionid":
                                has_sessionid = True
                                current_sessionid = c.get("value")
                        if has_wxuin and has_sessionid:
                            # 关键：只有 sessionid 的值与初始快照不同才是新登录
                            if initial_sessionid is None or current_sessionid != initial_sessionid:
                                login_detected = True
                                logger.info("检测到新的 sessionid（与初始快照不同），判定为新登录")
                            # else: sessionid 值没变，是旧的过期 Cookie，忽略
                    except Exception:
                        pass
                else:
                    login_detected = await self._check_login_status(context, platform)

                # 辅助检测：页面 URL 已跳转到 /platform（微信扫码后可能自动跳转）
                if not login_detected:
                    try:
                        page = getattr(browser_wrapper, "page", None)
                        if page and not page.is_closed():
                            u = (page.url or "").strip()
                            if "channels.weixin.qq.com/platform" in u:
                                login_detected = True
                                logger.info("检测到页面已自动跳转至创作者中心: %s", u)
                    except Exception:
                        pass

                if not login_detected:
                    continue

                logger.info("检测到用户已登录（Cookie 确认）: %s，正在处理...", username)

                # ── 第一步：立即主动导航到创作者中心（不等自动跳转！）──
                # 仅视频号需要在此处主动导航，其他平台（抖音/快手）登录后页面会自动跳转到正确位置
                page = getattr(browser_wrapper, "page", None)
                if platform == "wechat_video" and page and not page.is_closed():
                    current_url = ""
                    try:
                        current_url = (page.url or "").strip()
                    except Exception:
                        pass

                    if "channels.weixin.qq.com/platform" not in current_url:
                        try:
                            logger.info("登录确认，立即导航到创作者中心...")
                            await page.goto(
                                "https://channels.weixin.qq.com/platform",
                                wait_until="domcontentloaded",
                                timeout=15000,
                            )
                            logger.info("已导航到创作者中心: %s", page.url)
                        except Exception as e:
                            logger.warning("导航至创作者中心失败: %s", e)
                    else:
                        logger.info("页面已在创作者中心: %s", current_url)

                    # 等待昵称 DOM 元素出现（最多 8 秒，取代 networkidle）
                    try:
                        await page.wait_for_selector(
                            ".finder-nickname, .account-info, .account-name",
                            state="attached",
                            timeout=8000,
                        )
                        await asyncio.sleep(0.5)  # DOM 渲染缓冲
                    except Exception:
                        # DOM 未出现也继续（可能是页面结构变化），不阻塞后续更新
                        await asyncio.sleep(1.5)

                # 注册为主业务页并切到前台（所有平台通用）
                if page and not page.is_closed():
                    svc = getattr(browser_wrapper, "service", None) or getattr(browser_wrapper, "browser_manager", None)
                    if svc and hasattr(svc, "note_primary_work_page"):
                        svc.note_primary_work_page(page)
                    try:
                        if svc and hasattr(svc, "_cdp_bring_page_to_front"):
                            await svc._cdp_bring_page_to_front(page)
                    except Exception:
                        pass

                # ── 第二步：先立即保存 Cookie 和更新登录状态（用户即时看到"在线"） ──
                try:
                    cookies_raw = await context.cookies()
                    cookie_dict = {c["name"]: c["value"] for c in (cookies_raw or []) if c.get("name")}
                    if cookie_dict:
                        await self.account_manager.update_cookie(acc_id_int, cookie_dict)
                    await self.account_manager.update_account_login_status(acc_id_int, "online")
                    self.account_login_status_updated.emit(str(account_id))
                    logger.info("登录状态已更新为在线: %s", username)
                except Exception as e:
                    logger.warning("更新 Cookie/状态失败: %s", e)

                # ── 第三步：提取昵称（不阻塞状态更新） ──
                try:
                    new_nickname = await self._extract_nickname(context, platform, {})
                    if new_nickname and new_nickname != username:
                        await self.account_manager.update_platform_username(acc_id_int, new_nickname)
                        self.account_nickname_updated.emit(str(account_id), new_nickname)
                        logger.info("昵称已更新: %s -> %s", username, new_nickname)
                    elif not new_nickname:
                        logger.info("未提取到新昵称，保持原名: %s", username)
                except Exception as e:
                    logger.warning("提取昵称失败（不影响登录状态）: %s", e)

                logger.info("账号信息已更新(用户手动登录后): %s，登录状态=online", username)
                return

            except Exception as e:
                if "closed" in str(e).lower() or "Target page" in str(e):
                    logger.info("浏览器已关闭，停止登录监控: %s", username)
                    return
                logger.debug("登录监控检测异常: %s", e)
        logger.info("登录监控超时结束(未检测到登录): %s", username)

    async def _monitor_existing_account_update(self, account_id, username, platform, db_login_status: str = ""):
        """打开已有账号浏览器后的统一处理流程（适用于所有平台）。

        规则：
        A) DB 状态为 offline（Cookie 已失效）  → 直接进入登录监控，等用户手动登录后保存 Cookie 并更新状态。
        B) DB 状态为 online（或未知/空）       → 先用 HTTP 快速校验真实登录态：
           B-1) HTTP 在线 → 等待页面加载 → 更新 Cookie / 昵称 / 状态（静默更新）。
           B-2) HTTP 离线 → 更新 DB 为 offline → 进入登录监控。
           B-3) HTTP 校验不可用（网络等） → 不改状态，保持原样结束。
        """
        logger.info("启动已有账号任务: %s (DB状态=%s), 等待页面加载...", username, db_login_status or "?")
        browser_wrapper = self.get_browser_context_by_account(str(account_id))
        if not browser_wrapper or not self.account_manager:
            logger.info("无该账号已打开浏览器或账号管理器不可用，取消任务: account_id=%s", account_id)
            return

        try:
            acc_id_int = int(account_id)
        except ValueError:
            logger.warning("account_id 不是有效整数: %s", account_id)
            return

        # ── A) DB 已离线：Cookie 已失效，用户打开浏览器的目的就是重新登录，直接监控 ──
        if db_login_status == "offline":
            logger.info("账号当前DB状态为离线，直接进入登录监控: %s", username)
            # 等待页面加载完成以便用户看到登录界面
            try:
                page = getattr(browser_wrapper, "page", None)
                if page:
                    await page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            await asyncio.sleep(1.0)
            await self._monitor_until_login(account_id, username, platform, browser_wrapper, acc_id_int)
            return

        # ── B) DB 为 online 或未知：先用 HTTP 快速校验真实登录态 ──
        cookie_dict = {}
        try:
            cookie_dict = await self.account_manager.load_account_cookie(acc_id_int, merge_storage_state=True)
            if not isinstance(cookie_dict, dict):
                cookie_dict = {}
        except Exception as e:
            logger.debug("加载磁盘 Cookie 失败: %s", e)

        if not cookie_dict:
            # 无 Cookie 可校验，按离线处理
            logger.info("无可用 Cookie，按离线处理: %s，进入登录监控...", username)
            try:
                await self.account_manager.update_account_login_status(acc_id_int, "offline")
                self.account_login_status_updated.emit(str(account_id))
            except Exception:
                pass
            await self._wait_page_load(browser_wrapper)
            await self._monitor_until_login(account_id, username, platform, browser_wrapper, acc_id_int)
            return

        http_result = await verify_login_status(
            platform=platform,
            cookies=cookie_dict,
            account_id=acc_id_int,
            account_name=username,
            timeout=12,
        )

        # ── B-3) HTTP 校验不可用（网络/传输错误）──
        if not http_result.get("is_valid", True):
            logger.warning(
                "HTTP 登录校验未完成(网络问题等)，保持库中状态不变: %s，%s",
                username, http_result.get("error"),
            )
            # 仍等页面加载，尝试用浏览器侧静默更新
            await self._wait_page_load(browser_wrapper)
            await self._try_silent_update(account_id, username, platform, browser_wrapper, acc_id_int)
            return

        is_http_online = http_result.get("is_logged_in", False)

        if is_http_online:
            # ── B-1) HTTP 在线：等页面加载完后执行静默更新（Cookie / 昵称 / 状态） ──
            logger.info("HTTP 校验在线: %s，等待页面加载后执行静默更新...", username)
            await self._wait_page_load(browser_wrapper)
            await self._try_silent_update(account_id, username, platform, browser_wrapper, acc_id_int)
        else:
            # ── B-2) HTTP 离线：更新 DB 为 offline，取消早期同步，进入登录监控 ──
            logger.info("HTTP 校验已离线: %s (%s)，进入登录监控...", username, http_result.get("error", ""))
            self._cancel_early_cookie_tasks(str(account_id))
            try:
                await self.account_manager.update_account_login_status(acc_id_int, "offline")
                self.account_login_status_updated.emit(str(account_id))
            except Exception as e:
                logger.debug("更新离线状态失败: %s", e)
            await self._wait_page_load(browser_wrapper)
            await self._monitor_until_login(account_id, username, platform, browser_wrapper, acc_id_int)

    # ── 辅助方法 ──

    async def _wait_page_load(self, browser_wrapper, timeout: int = 8000) -> None:
        """等待浏览器页面加载完成。"""
        try:
            page = getattr(browser_wrapper, "page", None)
            if page and not page.is_closed():
                await page.wait_for_load_state("domcontentloaded", timeout=timeout)
                await asyncio.sleep(1.5)
            else:
                await asyncio.sleep(2.0)
        except Exception:
            await asyncio.sleep(2.0)

    async def _try_silent_update(self, account_id, username, platform, browser_wrapper, acc_id_int) -> None:
        """在线状态下执行一次静默更新（Cookie / 昵称 / 登录状态）。"""
        new_status = None
        try:
            new_nickname, new_status = await update_account_info_from_context(
                browser_wrapper.context, acc_id_int, username, platform, self.account_manager
            )
            if new_nickname is not None:
                self.account_nickname_updated.emit(str(account_id), new_nickname)
            if new_status is not None:
                self.account_login_status_updated.emit(str(account_id))
        except Exception as e:
            err_msg = str(e)
            if "closed" in err_msg.lower() or "Target page" in err_msg:
                await self._try_reload_account_cookie_after_close(acc_id_int, platform)
        status_text = new_status if new_status else "未变更"
        logger.info("静默更新完成: %s，登录状态=%s，任务结束 (浏览器保持开启)", username, status_text)
        # 静默更新会访问多标签 DOM，部分环境下 Chrome 前台可能停在非业务标签，收尾拉回业务页
        svc = getattr(browser_wrapper, "browser_manager", None) or getattr(browser_wrapper, "service", None)
        if svc and not getattr(svc, "_headless_mode", True) and hasattr(svc, "focus_first_tab_for_ui"):
            try:
                await svc.focus_first_tab_for_ui()
            except Exception:
                pass

    async def _check_login_status(self, context, platform) -> bool:
        """检查登录状态（委托给平台插件）"""
        try:
            if USE_PLUGIN_SYSTEM:
                plugin = PluginManager.get_login_plugin(platform)
                if plugin:
                    return await plugin.check_login_status(context)
            return False
        except Exception as e:
            logger.warning("检查登录状态异常: %s", e)
            return False

    async def _extract_nickname(
        self,
        context,
        platform,
        cookies,
        *,
        account_id: Optional[Union[int, str]] = None,
        account_name: str = "",
    ) -> Optional[str]:
        if USE_PLUGIN_SYSTEM:
            plugin = PluginManager.get_login_plugin(platform)
            if plugin:
                try:
                    res = await plugin.extract_user_info(context)
                    if res.nickname: return res.nickname
                except Exception as e:
                    logger.debug("提取用户信息异常: %s", e)
        if cookies:
            try:
                verify_account_id = int(account_id) if account_id is not None else 0
            except (TypeError, ValueError):
                verify_account_id = 0
            try:
                http_result = await verify_login_status(
                    platform=platform,
                    cookies=cookies,
                    account_id=verify_account_id,
                    account_name=account_name or str(account_id or ""),
                    timeout=12,
                )
                if (
                    http_result.get("is_valid", True)
                    and http_result.get("is_logged_in")
                ):
                    http_nick = http_result.get("username")
                    if isinstance(http_nick, str):
                        http_nick = http_nick.strip()
                    if http_nick:
                        logger.info(
                            "Nickname extracted from HTTP verification: account_id=%s, platform=%s",
                            account_id,
                            platform,
                        )
                        return http_nick
            except Exception as e:
                logger.debug("HTTP nickname fallback failed: %s", e)
        return None

    def _normalize_cookies_for_playwright(self, raw_cookies, platform, target_url: Optional[str] = None):
        """将数据库 Cookie 转为 Playwright add_cookies 格式。

        始终使用 domain+path 方式注入，确保 Cookie 对整个域（含所有子路径）生效，
        等同于本机 Chrome 使用同一 User Data Dir 打开浏览器时 Cookie 已在磁盘里的效果。
        """
        pw_cookies = []

        # 优先从插件获取正确的 cookie_domain；降级到平台 ID 推断
        fallback_domain = f".{platform}.com"
        try:
            plugin = PluginManager.get_login_plugin(platform)
            if plugin and hasattr(plugin, 'cookie_domain') and plugin.cookie_domain:
                fallback_domain = plugin.cookie_domain
        except Exception:
            pass

        if isinstance(raw_cookies, dict):
            for k, v in raw_cookies.items():
                if not k or v is None:
                    continue
                pw_cookies.append({'name': k, 'value': str(v), 'domain': fallback_domain, 'path': '/'})
        elif isinstance(raw_cookies, list):
            for c in raw_cookies:
                name, value = c.get('name'), c.get('value')
                if not name or value is None:
                    continue
                pw_cookies.append({
                    'name': name,
                    'value': str(value),
                    'domain': c.get('domain') or fallback_domain,
                    'path': c.get('path', '/'),
                })
        return pw_cookies

class SimpleBrowserWrapper:
    """浏览器包装类，封装浏览器服务、上下文和页面实例"""
    def __init__(self, service, context, page):
        self.service = service
        self.browser_manager = service  # 兼容发布执行器等调用方
        self.context = context
        self.page = page
    async def close(self):
        if hasattr(self.service, 'close'): await self.service.close()
        elif hasattr(self.service, 'stop'): await self.service.stop()
