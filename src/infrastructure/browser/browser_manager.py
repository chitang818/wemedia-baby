"""
账号绑定的浏览器管理器
文件路径：src/infrastructure/browser/browser_manager.py
功能：统一管理 Playwright 浏览器生命周期，支持账号级环境隔离与指纹持久化
"""

import os
import re
import asyncio
import logging
import json
import html
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import random

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

from .profile_manager import ProfileManager
from .hardware_profiles import DEFAULT_WEBGL_RENDERER, default_webgl_vendor
from src.infrastructure.common.path_manager import PathManager

logger = logging.getLogger(__name__)

# 环境信息标签页 HTML 内注入，用于在多标签/持久化恢复场景下可靠识别该页（不依赖标签顺序）
_ENV_INFO_TAB_META_SELECTOR = 'meta[name="wemedia-baby-env"][content="1"]'


def _get_configured_chrome_path() -> Optional[str]:
    """读取 app_config 中保存的 chrome_executable_path（若存在且有效）。"""
    try:
        from src.infrastructure.common.config.app_config_merge import get_app_config_for_read

        cfg = get_app_config_for_read()
        p = cfg.get("chrome_executable_path")
        if isinstance(p, str) and p.strip():
            p2 = p.strip().strip('"')
            if os.path.exists(p2):
                return p2
    except Exception:
        pass
    return None


# UA 模板列表 (主版本号占位符 {VERSION})
UA_TEMPLATES = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{VERSION}.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{VERSION}.0.6099.109 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{VERSION}.0.6099.130 Safari/537.36",
]


class UndetectedBrowserManager:
    """账号绑定的浏览器管理器
    
    核心职责：
    1. 管理 Playwright Browser/Context 生命周期
    2. 自动加载账号凭证和指纹配置
    3. 注入抗检测脚本
    4. 支持有头/无头模式切换
    """
    _warmup_done = False
    _warmup_lock: Optional[asyncio.Lock] = None
    _warmup_lock_init = threading.Lock()
    _chrome_major_cache: Optional[str] = None  # 进程级 Chrome 主版本号缓存

    # 账号信息标签页标题用：平台展示名
    _ACCOUNT_INFO_TAB_PLATFORM_LABELS: Dict[str, str] = {
        "douyin": "抖音",
        "kuaishou": "快手",
        "xiaohongshu": "小红书",
        "wechat_video": "视频号",
        "toutiao": "头条",
        "bilibili": "哔哩哔哩",
        "weibo": "微博",
        "baijiahao": "百家号",
        "qiehao": "企鹅号",
        "duoduoshipin": "多多视频",
    }

    @classmethod
    async def ensure_warmup(cls) -> None:
        """按需预热：进程内仅执行一次，在首次需要 Playwright 的入口前调用。"""
        if cls._warmup_lock is None:
            with cls._warmup_lock_init:
                if cls._warmup_lock is None:
                    cls._warmup_lock = asyncio.Lock()
        async with cls._warmup_lock:
            if cls._warmup_done:
                return
            await cls.warmup_environment()
            cls._warmup_done = True

    @classmethod
    async def warmup_environment(cls):
        """预热浏览器环境 (后台静默执行)

        主要目的：
        1. 预加载 Playwright 库到内存
        2. 确保 driver 进程可启动
        3. 减少用户首次点击时的等待时间

        注意：不再使用 async with async_playwright() 立即关闭的方式，
        那样会导致 Node.js 驱动进程因管道关闭抛出 EPIPE 错误崩溃整个程序。
        改为仅做库导入预热，触发模块加载与解压即可。
        """
        try:
            logger.info("[BrowserManager] 开始环境预热...")
            import time
            start_time = time.time()

            # 仅导入并访问 async_playwright 对象，触发 Playwright 库与驱动解压，
            # 不实际 start()，避免启动后立即关闭导致 Node.js 端 EPIPE 崩溃。
            from playwright.async_api import async_playwright as _ap
            _ = _ap  # 触发模块加载
            # 短暂让出事件循环，确保任何待处理的异步任务完成
            await asyncio.sleep(0)

            elapsed = time.time() - start_time
            logger.info(f"[BrowserManager] 环境预热完成，耗时: {elapsed:.2f}s")
        except Exception as e:
            logger.warning(f"[BrowserManager] 环境预热失败 (不影响正常使用): {e}")

    # 全局已注册 PID 集合：launch 时注册、close 时反注册
    _registered_pids: set = set()
    _registered_pids_lock = threading.Lock()

    @classmethod
    def register_pid(cls, pid: int) -> None:
        with cls._registered_pids_lock:
            cls._registered_pids.add(pid)

    @classmethod
    def unregister_pid(cls, pid: int) -> None:
        with cls._registered_pids_lock:
            cls._registered_pids.discard(pid)

    @classmethod
    def cleanup_all_processes(cls, exclude_pids: Optional[set] = None):
        """强力清理所有残留的浏览器进程 (Process Guardian)
        
        优先使用已注册 PID 精准清理，仅在需要时 fallback 到全机扫描。

        Args:
            exclude_pids: 需要排除、不得强杀的 PID 集合。
        """
        try:
            import psutil
            
            data_root = str(PathManager.get_app_data_dir()).lower().replace("\\", "/")
            _excl = set(exclude_pids) if exclude_pids else set()
            cleaned_count = 0

            # 阶段 1：精准清理已注册的 PID
            with cls._registered_pids_lock:
                known_pids = set(cls._registered_pids)
            
            for pid in known_pids:
                if pid in _excl:
                    continue
                try:
                    proc = psutil.Process(pid)
                    name = proc.name().lower()
                    if not any(x in name for x in ['chrome', 'msedge', 'chromium']):
                        continue
                    cmdline = " ".join(proc.cmdline() or []).lower().replace("\\", "/")
                    if data_root in cmdline:
                        logger.warning(f"[Process Guardian] 精准清理已注册进程 PID={pid} ({name})")
                        try:
                            proc.terminate()
                            try:
                                proc.wait(timeout=0.5)
                            except psutil.TimeoutExpired:
                                proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        cleaned_count += 1
                        cls.unregister_pid(pid)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    cls.unregister_pid(pid)
                    continue

            # 阶段 2：Fallback 全机扫描——仅请求 pid+name，lazily 获取 cmdline
            logger.debug(f"[Process Guardian] 全量扫描，特征路径: {data_root}, 排除PIDs: {_excl}")
            
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    pid = proc.info.get('pid')
                    if pid and pid in _excl:
                        continue
                    if pid in known_pids:
                        continue

                    name = proc.info.get('name', '').lower()
                    if not any(x in name for x in ['chrome', 'msedge', 'chromium']):
                        continue
                        
                    cmdline_list = proc.cmdline()
                    cmdline = " ".join(cmdline_list or []).lower().replace("\\", "/")
                    
                    if data_root in cmdline:
                        logger.warning(f"[Process Guardian] 发现残留进程 PID={pid} ({name}), 正在清理...")
                        try:
                            proc.terminate()
                            try:
                                proc.wait(timeout=0.5)
                            except psutil.TimeoutExpired:
                                proc.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        cleaned_count += 1
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            if cleaned_count > 0:
                logger.info(f"[Process Guardian] 清理完成，共结束 {cleaned_count} 个残留进程")
            else:
                logger.debug("[Process Guardian] 系统干净，未发现残留进程")
                
        except ImportError:
            logger.warning("[Process Guardian] 未安装 psutil，跳过进程清理")
        except Exception as e:
            logger.error(f"[Process Guardian] 清理过程异常: {e}", exc_info=True)

    def __init__(
        self, 
        account_id: str, 
        platform: str = "", 
        account_name: str = "",
        fingerprint_config: Optional[Dict[str, Any]] = None,  # 新增参数
        profile_folder_name: Optional[str] = None
    ):
        """初始化
        
        Args:
            account_id: 账号唯一标识
            platform: 平台名称 (如 douyin)
            account_name: 账号名称 (用于生成文件夹名)
            fingerprint_config: 指纹配置,None则随机生成
            profile_folder_name: 持久化使用的唯一 UUID 文件夹
        """
        self.account_id = account_id
        self.platform = platform
        self.account_name = account_name
        self.profile_manager = ProfileManager(
            account_id, 
            platform, 
            account_name,
            fingerprint_config=fingerprint_config,  # 传递指纹配置
            profile_folder_name=profile_folder_name
        )
        
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.user_data_dir: Optional[Path] = None  # 新增：记录用户数据目录
        
        self._browser_version: Optional[str] = None
        self._chrome_pid: Optional[int] = None
        # 有头/无头（用于判断是否允许打开环境信息标签）
        self._headless_mode: bool = True
        # 手动打开的环境信息页，关闭后或重启浏览器会重建
        self._environment_info_page: Optional[Page] = None
        # 自动化/发布使用的业务页（goto 后登记）；不依赖「第几个标签」，避免持久化会话里标签顺序与 about:blank 环境页抢前台
        self._primary_work_page: Optional[Page] = None

        logger.info(f"### [V9] UndetectedBrowserManager 加载成功 ### account={account_name}, platform={platform}")
    
    async def launch(
        self,
        headless: bool = True,
        *,
        maximize_window: bool = False,
    ) -> Optional[BrowserContext]:
        """启动浏览器并返回 Context (Persistent)

        有头/无头均**不在此函数内**创建「环境信息」标签，避免在业务页 `goto` 完成前聚焦、引发错切标签。
        环境信息标签由调用方在 **`goto` 成功并 `note_primary_work_page` 之后** 通过
        `apply_browser_tab_layout`（内部受 ``show_environment_info_tab`` 控制）统一处理标签与聚焦业务页。

        Args:
            headless: 无头模式
            maximize_window: 有头模式下是否通过 CDP 将宿主窗口最大化（发布流程建议开启）
        """
        try:
            self.playwright = await async_playwright().start()
            
            # 如果已有 context，先关闭避免冲突
            if self.context:
                try:
                    logger.info("检测到已有浏览器实例，先关闭...")
                    await self.context.close()
                    self.context = None
                    self.browser = None
                    self._environment_info_page = None
                except Exception as e:
                    logger.warning(f"关闭旧浏览器实例时出错: {e}")
            
            # 启动参数
            args = self._get_launch_args()
            _wx_channels = (self.platform or "").strip().lower() == "wechat_video"
            
            # 仅使用本地 Chrome
            channel = "chrome"
            executable_path = _get_configured_chrome_path()
            
            # 获取用户数据目录（登录态仅依赖 Chromium 持久化目录，不再从旧版 storage_state 启动时灌 Cookie）
            self.user_data_dir = self.profile_manager.get_user_data_dir()
            logger.info(f"正在启动浏览器 (Persistent Context): channel={channel}, user_data_dir={self.user_data_dir}")

            # 启动前主动清理残留进程：防止上一次任务的 Chrome 进程还锁着 user_data_dir，
            # 导致新 Chrome 因"另一个程序正在使用此文件"而立即退出（TargetClosedError）
            await self._force_kill_browser_process()

            # 启动前修正 Local State 退出类型，防止 Chrome 检测到上次异常退出后弹出「要恢复页面吗？」InfoBar
            await asyncio.to_thread(self._reset_chrome_exit_type, self.user_data_dir)
            
            # 获取指纹配置
            fingerprint = self.profile_manager.get_fingerprint()
            try:
                ua_major = None
                _ua_for_log = fingerprint.get("user_agent") or ""
                m = re.search(r"Chrome/(\d+)\.", _ua_for_log)
                if m:
                    ua_major = m.group(1)
                langs = fingerprint.get("languages")
                if not isinstance(langs, list):
                    langs = []
                logger.info(
                    "[FingerprintSummary] chrome=%s platform=%s locale=%s languages=%s screen=%sx%s hc=%s mem=%s cpu=%s webgl=%s",
                    ua_major or "?",
                    fingerprint.get("platform", "Win32"),
                    fingerprint.get("locale", "zh-CN"),
                    ",".join([str(x) for x in langs[:3]]),
                    fingerprint.get("screen_width", 1920),
                    fingerprint.get("screen_height", 1080),
                    fingerprint.get("hardware_concurrency", 4),
                    fingerprint.get("device_memory", 8),
                    (fingerprint.get("cpu_model") or "")[:40],
                    (fingerprint.get("webgl_vendor") or "")[:32],
                )
            except Exception:
                pass
            
            # 1. 动态生成/获取 User Agent（优先对齐本机 Chrome 版本，进程级缓存避免重复注册表查询）
            user_agent = fingerprint.get("user_agent")
            detected_major: Optional[str] = UndetectedBrowserManager._chrome_major_cache
            if detected_major is None:
                try:
                    from src.utils.chrome_installer import detect_chrome
                    installed, info = await asyncio.to_thread(detect_chrome)
                    version = (info or {}).get("version") if installed else None
                    if isinstance(version, str) and version.strip():
                        m = re.match(r"^(\d+)", version.strip())
                        if m:
                            detected_major = m.group(1)
                    UndetectedBrowserManager._chrome_major_cache = detected_major
                except Exception as e:
                    logger.debug("检测本机 Chrome 版本失败（将回退随机 UA）: %s", e)

            def _ua_major(ua: str) -> Optional[str]:
                try:
                    m = re.search(r"Chrome/(\d+)\.", ua or "")
                    return m.group(1) if m else None
                except Exception:
                    return None

            current_major = _ua_major(user_agent or "")
            # aggressive 策略：只要检测到 Chrome 主版本号，就尽量让 UA 对齐（首次生成或不一致时更新）
            need_regen = (not user_agent) or (detected_major is not None and detected_major != current_major)

            if need_regen:
                template = random.choice(UA_TEMPLATES)
                version_major = detected_major or str(random.randint(120, 131))
                user_agent = template.replace("{VERSION}", version_major)
                fingerprint["user_agent"] = user_agent
                # save_fingerprint 是同步文件写入，移到线程池避免阻塞事件循环
                await asyncio.to_thread(self.profile_manager.save_fingerprint, fingerprint)
                if detected_major:
                    logger.info("已对齐并绑定 User-Agent: Chrome/%s (ua=%s)", detected_major, user_agent)
                else:
                    logger.info("已生成并绑定新 User-Agent(未检测到Chrome版本): %s", user_agent)
            else:
                logger.debug("加载已有 User-Agent: %s", user_agent)

            # 准备启动选项
            # 请求头对齐（尽力而为）：Accept-Language 与 fingerprint.languages/locale 一致
            extra_headers = None
            try:
                fp = self.profile_manager.get_fingerprint()
                langs = fp.get("languages")
                if isinstance(langs, list) and langs:
                    # Accept-Language 形如：zh-CN,zh;q=0.9,en;q=0.8
                    parts = []
                    for i, lang in enumerate(langs[:3]):
                        if not isinstance(lang, str) or not lang.strip():
                            continue
                        if i == 0:
                            parts.append(lang.strip())
                        elif i == 1:
                            parts.append(f"{lang.strip()};q=0.9")
                        else:
                            parts.append(f"{lang.strip()};q=0.8")
                    if parts:
                        extra_headers = {"Accept-Language": ", ".join(parts)}
            except Exception:
                extra_headers = None

            # 视频号「定时发表」始终按北京时间语义；指纹若随代理 IP 调成其它时区，
            # JS 的 new Date(y,m,d,h,mi) 会按浏览器时区构造绝对时间，易出现任务 12:xx 而列表 20:xx 等偏差。
            tz_id = fingerprint.get("timezone_id", "Asia/Shanghai")
            if self.platform == "wechat_video":
                if tz_id != "Asia/Shanghai":
                    logger.info(
                        "[BrowserManager] 视频号：指纹时区 %s 已覆盖为 Asia/Shanghai，"
                        "保证定时发表与后台一致",
                        tz_id,
                    )
                tz_id = "Asia/Shanghai"

            # 视频号扫码登录：微信侧常对「无沙箱 / 禁用扩展 / 测试型启动参数」做风控，易在已扫码后出现「登录失败，稍后重试」。
            # "--disable-popup-blocking" 是 Playwright 的默认注入参数，会关闭 Chrome 的弹窗拦截器，
            # 导致网站 JS（如抖音）通过 window.open() 弹出的认证/广告标签能直接显示。
            # 将其加入 ignore_default_args，使 Chrome 保持和普通用户浏览器一致的默认弹窗拦截行为。
            # "--disable-blink-features=AutomationControlled" 是 Playwright 对正式版 Chrome（channel=chrome）
            # 自动注入的参数，但正式版 Chrome 不支持该参数，会在页面顶部显示黄色「不受支持的命令行标记」警告横幅。
            # 将其加入 ignore_default_args 后，Playwright 不再自动注入，警告消失。
            # navigator.webdriver 的隐藏已由 _inject_stealth_scripts() 中的 JS 注入替代。
            _ignore_playwright_defaults = [
                "--enable-automation",
                "--no-sandbox",
                "--disable-popup-blocking",
                "--disable-blink-features=AutomationControlled",
            ]
            if _wx_channels:
                _ignore_playwright_defaults.extend(
                    [
                        "--disable-extensions",
                        "--disable-component-extensions-with-background-pages",
                    ]
                )
                logger.info(
                    "[BrowserManager] 视频号：使用加强版浏览器启动参数（Chromium 沙箱、允许扩展、弱化自动化默认项）以降低扫码风控误杀"
                )

            context_permissions = ["geolocation", "notifications"]
            if self.platform == "douyin":
                # 抖音创作者图文音乐面板会探测媒体/音频环境。保留真实 Chrome 的媒体权限模型，
                # 避免被脚本伪造的 mediaDevices / permissions 误伤音乐选择状态。
                context_permissions.extend(["microphone", "camera"])

            launch_options = {
                "user_data_dir": self.user_data_dir,
                "headless": headless,
                "args": args,
                "channel": channel,
                "executable_path": executable_path,
                "user_agent": user_agent, # 注入 User-Agent
                "viewport": None, # 关键：禁用视口限制
                "no_viewport": True, # 显式禁用视口模拟，防止 Playwright 施加默认 1280x720 限制
                "locale": fingerprint.get("locale", "zh-CN"),
                "timezone_id": tz_id,
                "permissions": context_permissions,
                "ignore_https_errors": True,
                # "device_scale_factor": 1.0, # 移除，跟随系统
                "ignore_default_args": _ignore_playwright_defaults,
            }
            # 不论任何平台，统一强制开启沙箱（防止 Playwright 默认自动注入 --no-sandbox 引起不支持警告）
            launch_options["chromium_sandbox"] = True
            
            if extra_headers:
                launch_options["extra_http_headers"] = extra_headers
            
            # 使用 launch_persistent_context（沙箱启动失败时回退 no-sandbox，避免少数环境完全打不开）
            try:
                self.context = await self.playwright.chromium.launch_persistent_context(**launch_options)
            except Exception as e:
                # 若显式传入沙箱为 True 但因为权限等启动失败，降级退回无沙箱模式
                if not launch_options.get("chromium_sandbox"):
                    raise
                logger.warning(
                    "[BrowserManager] Chromium 沙箱模式启动失败，回退为 --no-sandbox: %s",
                    e,
                )
                launch_options.pop("chromium_sandbox", None)
                launch_options["args"] = [
                    "--no-sandbox",
                ] + self._stealth_chrome_args_common()
                self.context = await self.playwright.chromium.launch_persistent_context(**launch_options)
            
            # 兼容性设置：让 self.browser 指向 context 
            self.browser = self.context 

            # 指纹 virtual_geo：对浏览器上下文固定 Geolocation
            try:
                from .virtual_geo import build_playwright_geolocation

                _fp_geo = self.profile_manager.get_fingerprint()
                _spec = build_playwright_geolocation(_fp_geo)
                if _spec and self.context:
                    await self.context.set_geolocation(_spec)
                    logger.info(
                        "已应用 virtual_geo 至浏览器 Geolocation: lat=%s lon=%s",
                        _spec.get("latitude"),
                        _spec.get("longitude"),
                    )
            except Exception as e:
                logger.warning("应用虚拟定位至浏览器失败（不阻止启动）: %s", e)
            
            # 注入抗检测脚本
            await self._inject_stealth_scripts()
            self._headless_mode = bool(headless)

            if maximize_window and not headless:
                await self.maximize_browser_window()

            # 提取 Chromium 进程 PID 并注册到 ProcessSupervisor，
            # 使 atexit 钩子在崩溃恢复时能精准 terminate 已知进程
            try:
                self._chrome_pid = await self._extract_chrome_pid()
                if self._chrome_pid:
                    from .process_supervisor import ProcessSupervisor
                    ProcessSupervisor.register(self._chrome_pid)
                    self._save_pid_file(self._chrome_pid)
            except Exception as _pid_err:
                logger.debug("提取/注册 Chrome PID 失败（不影响启动）: %s", _pid_err)

            logger.info(f"浏览器启动成功 (Persistent, headless={headless})")
            return self.context
            
        except Exception as e:
            logger.error(f"浏览器启动失败: {e}", exc_info=True)
            await self.close()
            return None

    def pick_business_page_for_automation(self) -> Optional[Page]:
        """返回当前宜作为 goto/点击 的 Page（与 focus 规则一致，不切换可见标签）。"""
        return self._pick_business_page_for_focus()

    async def refresh_environment_page_ref(self) -> None:
        """根据环境页内嵌 meta 标记同步 `_environment_info_page`，避免 about:blank 顺序误判导致焦点落到环境标签。"""
        if not self.context or self._headless_mode:
            return
        pages = list(self.context.pages)
        for p in pages:
            if p.is_closed():
                continue
            try:
                u = (p.url or "").strip().lower()
                if u not in ("about:blank", ""):
                    continue
                has_meta = False
                try:
                    has_meta = await p.locator(_ENV_INFO_TAB_META_SELECTOR).count() > 0
                except Exception:
                    try:
                        has_meta = bool(
                            await p.evaluate(
                                """() => !!document.querySelector('meta[name="wemedia-baby-env"][content="1"]')"""
                            )
                        )
                    except Exception:
                        has_meta = False
                if has_meta:
                    self._environment_info_page = p
                    return
            except Exception:
                continue
        inferred = self._infer_environment_page_ref(pages)
        if inferred is not None:
            self._environment_info_page = inferred
        elif len(pages) > 1:
            self._environment_info_page = pages[1]

    async def _cdp_bring_page_to_front(self, page: Page) -> bool:
        """用 CDP 将指定页面对应为 Chrome 里当前可见标签（多标签时比 page.bring_to_front 可靠）。"""
        if not self.context or page is None or page.is_closed():
            return False
        try:
            session = await self.context.new_cdp_session(page)
            await session.send("Page.bringToFront")
            return True
        except Exception as e:
            logger.debug("[BrowserManager] CDP Page.bringToFront 失败，回退 Playwright: %s", e)
            try:
                await page.bring_to_front()
                return True
            except Exception:
                return False

    async def focus_first_tab_for_ui(self) -> None:
        """将业务页切到 Chrome 前台（按登记页、平台 URL、https 优先；不依赖「第一个标签」）。"""
        if not self.context or self._headless_mode:
            return
        await self.refresh_environment_page_ref()
        target = self._pick_business_page_for_focus()
        if target is None:
            return
        await self._bring_page_to_front_twice(target)

    def _infer_environment_page_ref(self, pages: List[Page]) -> Optional[Page]:
        """推断「环境信息」标签：不得把即将用于 goto 的首个 about:blank 业务页误判为环境页。

        规则：排除已是创作者等业务 URL 的标签、排除 _primary_work_page；在剩余 about:blank 中取
        **下标最大** 者（本模块先占用 context 首标签再 new_page 环境页，故环境页多为右侧/后开）。
        若已存在业务 URL 标签，则环境页应为「非业务」的 blank（通常仅一个）。
        """
        if not pages:
            return None
        needles = self._creator_url_needles()
        primary = self._primary_work_page

        def is_business_url(u: str) -> bool:
            ul = u.strip().lower()
            if not ul.startswith("http"):
                return False
            if needles and any(n in ul for n in needles):
                return True
            return False

        has_business = False
        blank_indexed: List[Tuple[int, Page]] = []
        for i, p in enumerate(pages):
            if p.is_closed():
                continue
            u = (p.url or "").strip().lower()
            if is_business_url(u):
                has_business = True
                continue
            if primary is not None and p == primary:
                continue
            if u in ("about:blank", ""):
                blank_indexed.append((i, p))

        if not blank_indexed:
            return pages[1] if len(pages) > 1 else None

        blank_indexed.sort(key=lambda x: x[0])
        # 多 blank 且尚无业务 URL：取后开的（避免首标签业务空白被当成环境页）
        if not has_business:
            return blank_indexed[-1][1]
        # 已有业务页：环境页应为「非业务」blank，通常一个；若多个取下标最大
        return blank_indexed[-1][1]

    async def _ensure_env_tab_as_second(self) -> None:
        """有头模式：保证存在环境信息标签（用于展示绑定账号）；缺省时创建，已有时同步引用。"""
        if not self.context or self._headless_mode:
            return
        pages = list(self.context.pages)
        if not pages:
            return
        if len(pages) >= 2:
            if self._environment_info_page is None or self._environment_info_page.is_closed():
                inferred = self._infer_environment_page_ref(pages)
                self._environment_info_page = inferred if inferred is not None else pages[1]
            return
        await self.open_environment_info_tab(focus_tab=False)

    async def apply_browser_tab_layout(self, *, refresh_env_content: bool = False) -> None:
        """有头模式：按系统设置决定是否保留「环境信息」标签，并把业务页置于前台。

        与 `PlaywrightBrowserService._launch_browser_core` 一致：仅当配置
        ``show_environment_info_tab`` 为真时才创建/刷新环境标签；关闭该选项时
        不得因「复用已开浏览器」路径再次打开环境页（否则首任务单标签、后续任务
        会多出第二个标签，与设置不符）。
        """
        if not self.context or self._headless_mode:
            return
        show_env_tab = False
        try:
            from src.infrastructure.common.config.app_config_merge import get_app_config_for_read

            show_env_tab = bool(get_app_config_for_read().get("show_environment_info_tab", False))
        except Exception:
            show_env_tab = False
        await self.refresh_environment_page_ref()
        if show_env_tab:
            if refresh_env_content:
                await self.open_environment_info_tab(focus_tab=False)
            else:
                await self._ensure_env_tab_as_second()
        await self.focus_first_tab_for_ui()

    async def maximize_browser_window(self) -> None:
        """通过 Chrome DevTools Protocol 将浏览器主窗口最大化。

        无头模式或无可用页面时静默跳过；失败仅打日志，不中断流程。
        """
        if not self.context:
            return
        pages = self.context.pages
        if not pages:
            return
        page = pages[0]
        try:
            session = await self.context.new_cdp_session(page)
            info = await session.send("Browser.getWindowForTarget", {})
            wid = info.get("windowId")
            if wid is None:
                logger.debug("[BrowserManager] CDP getWindowForTarget 未返回 windowId")
                return
            await session.send(
                "Browser.setWindowBounds",
                {"windowId": wid, "bounds": {"windowState": "maximized"}},
            )
            logger.info("[BrowserManager] 已请求浏览器窗口最大化 (CDP)")
        except Exception as e:
            logger.warning("[BrowserManager] CDP 最大化窗口失败（忽略）: %s", e)

    def _stealth_chrome_args_common(self) -> List[str]:
        """各平台共用的抗检测 / 隐私相关启动参数（不含是否使用沙箱、test-type）。
        
        注意：不再传 --ignore-certificate-errors 命令行参数——稳定版 Chrome 会将其标记为「不受支持的命令行标记」
        并在页面顶部显示安全警告横幅。HTTPS 错误忽略由 Playwright launch_options 中的 ignore_https_errors=True
        在协议层处理，不经由命令行，不触发安全提示。
        """
        return [
            "--disable-dev-shm-usage",
            "--webrtc-ip-handling-policy=default_public_interface_only",
            "--disable-webrtc-hw-encoding",
            "--disable-webrtc-hw-decoding",
            "--start-maximized",
            # 三重防护：禁止 Chrome 在上次非正常退出后弹出「要恢复页面吗？」InfoBar / 对话框，
            # 避免该弹窗遮挡发布页操作区域（如音乐选择列表）导致点击失效。
            # 配合启动前 _reset_chrome_exit_type() 修正 Local State 实现彻底屏蔽。
            "--no-first-run",
            "--disable-session-crashed-bubble",
            "--disable-infobars",
            # --disable-blink-features=AutomationControlled 已移除：
            # 稳定版 Chrome 会将其标记为「不受支持的命令行标记」并显示黄色警告横幅。
            # navigator.webdriver 的隐藏改由 _inject_stealth_scripts() 中的 JS 注入替代。
        ]

    @staticmethod
    def _reset_chrome_exit_type(user_data_dir: str) -> None:
        """在浏览器启动前将 Chrome Local State 中的退出类型重置为正常，
        防止 Chrome 检测到上次异常退出后弹出「要恢复页面吗？」InfoBar。
        
        同时清理 Default/Preferences 中的 profile.exit_type，双重保险。
        适用于所有平台（抖音、快手、视频号等），因此放在通用浏览器管理器中。
        """
        if not user_data_dir:
            return

        targets = [
            (Path(user_data_dir) / "Local State", ["profile", "exit_type"]),
            (Path(user_data_dir) / "Default" / "Preferences", ["profile", "exit_type"]),
        ]

        for file_path, key_path in targets:
            if not file_path.exists():
                continue
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 定位到目标键，若值已经是 "Normal" 则跳过写入
                node = data
                for key in key_path[:-1]:
                    node = node.get(key, {})
                    if not isinstance(node, dict):
                        node = {}
                        break

                last_key = key_path[-1]
                if node.get(last_key) == "Normal":
                    continue

                # 找到并修正
                node2 = data
                for key in key_path[:-1]:
                    node2 = node2.setdefault(key, {})
                node2[last_key] = "Normal"

                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

                logger.info("[BrowserManager] 已重置 %s 中的退出类型为 Normal，防止「恢复页面」弹窗", file_path.name)
            except Exception as e:
                logger.debug("[BrowserManager] 修正 %s 退出类型失败（不影响启动）: %s", file_path.name, e)

    def _get_launch_args(self) -> List[str]:
        """获取浏览器启动参数"""
        return self._stealth_chrome_args_common()
    
    async def _inject_stealth_scripts(self):
        """注入抗检测脚本"""
        if not self.context:
            return
        
        # 获取指纹配置
        fingerprint = self.profile_manager.get_fingerprint()

        # 指纹开关（尽力读取配置；默认开启）
        fp_cfg = {}
        try:
            from src.infrastructure.common.config.app_config_merge import get_app_config_for_read

            fp_cfg = get_app_config_for_read()
        except Exception:
            fp_cfg = {}
        uach_enabled = bool(fp_cfg.get("fingerprint_ua_ch_enabled", True))
        languages_enabled = bool(fp_cfg.get("fingerprint_languages_enabled", True))
        patch_audio_context = self.platform != "douyin"
        patch_media_devices = self.platform != "douyin"
        patch_permissions = self.platform != "douyin"
        
        # 提取所有指纹参数 (提供默认值以防旧配置缺失)
        hardware_concurrency = fingerprint.get("hardware_concurrency", 4)
        device_memory = fingerprint.get("device_memory", 8)
        webgl_vendor = fingerprint.get("webgl_vendor") or default_webgl_vendor()
        webgl_renderer = fingerprint.get("webgl_renderer") or DEFAULT_WEBGL_RENDERER
        
        # Screen 参数
        screen_width = fingerprint.get("screen_width", 1920)
        screen_height = fingerprint.get("screen_height", 1080)
        screen_avail_width = fingerprint.get("screen_avail_width", 1920)
        screen_avail_height = fingerprint.get("screen_avail_height", 1040)
        screen_color_depth = fingerprint.get("screen_color_depth", 24)
        screen_pixel_depth = fingerprint.get("screen_pixel_depth", 24)
        
        # AudioContext 种子
        audio_context_seed = fingerprint.get("audio_context_seed", 12345)
        
        # Battery 参数
        battery_charging = str(fingerprint.get("battery_charging", True)).lower()
        battery_level = fingerprint.get("battery_level", 1.0)
        
        # Navigator 扩展
        platform = fingerprint.get("platform", "Win32")
        max_touch_points = fingerprint.get("max_touch_points", 0)
        vendor = fingerprint.get("vendor", "Google Inc.")
        vendor_sub = fingerprint.get("vendor_sub", "")
        product_sub = fingerprint.get("product_sub", "20030107")
        
        # Connection 参数
        connection_type = fingerprint.get("connection_effective_type", "4g")
        connection_downlink = fingerprint.get("connection_downlink", 10)
        connection_rtt = fingerprint.get("connection_rtt", 50)
        
        # Canvas 种子
        canvas_noise_seed = fingerprint.get("canvas_noise_seed", 12345)
        # Canvas 噪声强度（UI 层语义映射到脚本强度等级 1/2/3）
        strength_raw = fingerprint.get("canvas_noise_strength", fingerprint.get("canvas_noise", None))
        canvas_noise_strength_level = 1
        try:
            if strength_raw is not None:
                s = float(strength_raw)
                if s <= 0.00015:
                    canvas_noise_strength_level = 1
                elif s <= 0.0004:
                    canvas_noise_strength_level = 2
                else:
                    canvas_noise_strength_level = 3
        except Exception:
            canvas_noise_strength_level = 1
        
        # 读取外部 JS 模板文件（须列入 scripts/build/data_dirs.json，否则打包后缺失）
        try:
            script_path = PathManager.get_resource_path(
                "src/resources/scripts/stealth/stealth.js"
            )
            
            if not script_path.exists():
                logger.error(f"抗检测脚本文件未找到: {script_path}")
                return

            stealth_template = script_path.read_text(encoding="utf-8")

            # languages/UA-CH 数据（JSON 注入，避免字符串转义问题）
            languages = fingerprint.get("languages", ["zh-CN", "zh", "en"])
            if not isinstance(languages, list) or not languages:
                languages = ["zh-CN", "zh", "en"]
            languages_json = json.dumps(languages, ensure_ascii=False)
            ua_ch_obj = fingerprint.get("ua_ch") if uach_enabled else None
            if not isinstance(ua_ch_obj, dict):
                ua_ch_obj = {}
            ua_ch_json = json.dumps(ua_ch_obj, ensure_ascii=False)

            # 执行变量替换
            stealth_script = stealth_template.replace("__HARDWARE_CONCURRENCY__", str(hardware_concurrency)) \
                .replace("__DEVICE_MEMORY__", str(device_memory)) \
                .replace("__SCREEN_WIDTH__", str(screen_width)) \
                .replace("__SCREEN_HEIGHT__", str(screen_height)) \
                .replace("__SCREEN_AVAIL_WIDTH__", str(screen_avail_width)) \
                .replace("__SCREEN_AVAIL_HEIGHT__", str(screen_avail_height)) \
                .replace("__SCREEN_COLOR_DEPTH__", str(screen_color_depth)) \
                .replace("__SCREEN_PIXEL_DEPTH__", str(screen_pixel_depth)) \
                .replace("__WEBGL_VENDOR__", str(webgl_vendor)) \
                .replace("__WEBGL_RENDERER__", str(webgl_renderer)) \
                .replace("__PLATFORM__", str(platform)) \
                .replace("__MAX_TOUCH_POINTS__", str(max_touch_points)) \
                .replace("__VENDOR__", str(vendor)) \
                .replace("__VENDOR_SUB__", str(vendor_sub)) \
                .replace("__PRODUCT_SUB__", str(product_sub)) \
                .replace("__BATTERY_CHARGING__", battery_charging) \
                .replace("__BATTERY_LEVEL__", str(battery_level)) \
                .replace("__CONNECTION_TYPE__", str(connection_type)) \
                .replace("__CONNECTION_DOWNLINK__", str(connection_downlink)) \
                .replace("__CONNECTION_RTT__", str(connection_rtt)) \
                .replace("__AUDIO_CONTEXT_SEED__", str(audio_context_seed)) \
                .replace("__PATCH_AUDIO_CONTEXT__", "true" if patch_audio_context else "false") \
                .replace("__PATCH_MEDIA_DEVICES__", "true" if patch_media_devices else "false") \
                .replace("__PATCH_PERMISSIONS__", "true" if patch_permissions else "false") \
                .replace("__CANVAS_NOISE_SEED__", str(canvas_noise_seed)) \
                .replace("__CANVAS_NOISE_STRENGTH__", str(canvas_noise_strength_level))

            # 可选注入：languages / UA-CH
            stealth_script = stealth_script.replace(
                "__LANGUAGES_JSON__", languages_json if languages_enabled else '["zh-CN","zh","en"]'
            ).replace(
                "__UA_CH_JSON__", ua_ch_json if uach_enabled else "{}"
            )

        except Exception as e:
            logger.error(f"加载抗检测脚本失败: {e}", exc_info=True)
            return
        
        await self.context.add_init_script(stealth_script)
        logger.info(
            "高级抗检测脚本已注入 (WebRTC/MediaDevices/Permissions/Intl/CDP/Headless)，"
            "媒体补丁: audio=%s mediaDevices=%s permissions=%s",
            patch_audio_context,
            patch_media_devices,
            patch_permissions,
        )

    def _clear_persistent_context_refs(self, reason: str = "") -> None:
        """Playwright 侧上下文已关闭时清空本地引用，避免上层继续操作已断开的 Context。"""
        if reason:
            logger.debug("清空浏览器上下文引用: %s", reason)
        self.context = None
        self.browser = None
        self._environment_info_page = None
        self._primary_work_page = None

    def note_primary_work_page(self, page: Optional[Page]) -> None:
        """在业务 URL goto 成功后调用，供后续聚焦/排障时优先使用该标签（而非 pages[0]）。"""
        self._primary_work_page = page

    def _creator_url_needles(self) -> List[str]:
        """当前平台创作者站点 URL 片段，用于从多标签中识别业务页。"""
        k = (self.platform or "").strip().lower()
        mapping: Dict[str, List[str]] = {
            # 抖音勿用宽泛的 douyin.com：www / 活动页等易被当成「业务页」导致焦点错切；创作者域单独列出
            "douyin": ["creator.douyin.com"],
            "kuaishou": ["cp.kuaishou.com", "kuaishou.com", "www.kuaishou.com"],
            "xiaohongshu": ["creator.xiaohongshu.com", "xiaohongshu.com"],
            "wechat_video": ["channels.weixin.qq.com"],
            "toutiao": ["mp.toutiao.com", "toutiao.com"],
            "duoduoshipin": ["video.pinduoduo.com", "yangkeduo.com"],
        }
        return list(mapping.get(k, []))

    def _iter_open_pages(self) -> List[Page]:
        if not self.context:
            return []
        return [p for p in self.context.pages if not p.is_closed()]

    def _pick_business_page_for_focus(self) -> Optional[Page]:
        """挑选应置于前台的业务页：已登记且仍存活 > 平台域名匹配 https > 任意 https > 第一个非环境引用页。"""
        env = self._environment_info_page
        pages = self._iter_open_pages()
        if not pages:
            return None

        pw = self._primary_work_page
        if pw is not None and not pw.is_closed():
            try:
                if self._environment_info_page is not None and pw is self._environment_info_page:
                    self._primary_work_page = None
                else:
                    # 勿用 `pw in context.pages`：Playwright 对同一标签列举时可能返回新的 Page 包装，
                    # 与 goto 时保留的引用非同一 Python 对象，误判会清空主业务页并错焦到环境标签。
                    _ = pw.url
                    return pw
            except Exception:
                self._primary_work_page = None

        needles = self._creator_url_needles()
        for p in pages:
            if env is not None and p == env:
                continue
            u = (p.url or "").strip().lower()
            if needles and u.startswith("http") and any(n in u for n in needles):
                return p
        for p in pages:
            if env is not None and p == env:
                continue
            u = (p.url or "").strip().lower()
            if u.startswith("https://") or u.startswith("http://"):
                return p
        for p in pages:
            if env is not None and p == env:
                continue
            return p
        return pages[0]

    async def _bring_page_to_front_twice(self, page: Optional[Page]) -> None:
        if page is None or page.is_closed():
            return
        for _ in range(2):
            try:
                await self._cdp_bring_page_to_front(page)
            except Exception:
                break
            await asyncio.sleep(0.07)

    async def _render_env_content(self, info_page: Page, html_doc: str, *, focus_business_after: bool = True) -> None:
        """写入环境信息页内容。

        关键：调用 set_content 前先对页面做一次 goto("about:blank")。
        原因：launch_persistent_context 启动时 pages[0] 是 Chrome 内置新标签页
        （chrome://new-tab-page），它是一个特殊 WebUI 页面。
        直接对它调用 set_content 时，Playwright 内部会先触发一次"文档替换式导航"，
        Chrome 的 WebUI → 普通文档的切换会在 UI 上产生一个短暂的中间状态，
        表现为第三个标签一闪而过。
        先 goto("about:blank") 把它变成普通空白文档，再 set_content 就不会有这个问题。
        """
        try:
            if info_page is None or info_page.is_closed():
                return
            # 仅当当前 URL 是 Chrome 内置页时才做预导航，避免对已稳定的普通页重复 goto
            current_url = (info_page.url or "").strip().lower()
            if current_url not in ("about:blank", "about:srcdoc", "") and not current_url.startswith("http"):
                try:
                    await info_page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
                except Exception:
                    pass
            await info_page.set_content(html_doc, wait_until="domcontentloaded", timeout=15000)
            # set_content 完成后 meta 已写入，刷新引用可精确匹配环境页
            await self.refresh_environment_page_ref()
            if focus_business_after and not self._headless_mode:
                await asyncio.sleep(0.05)
                pw = self._primary_work_page
                if pw is not None and not pw.is_closed():
                    await self._cdp_bring_page_to_front(pw)
        except Exception as e:
            logger.debug("[BrowserManager] 后台渲染环境页失败（可忽略）: %s", e)

    async def open_environment_info_tab(self, *, focus_tab: bool = True, reuse_page: Optional[Page] = None) -> bool:
        """打开或刷新「环境信息」标签页（仅在有头模式下；无头模式不需要环境页，调用直接返回 False）。

        不再请求外网出口 IP、IP 地理库或页面 W3C 定位，避免启动阻塞十余秒。

        Args:
            focus_tab: True 切到环境标签；False 写入内容后不切换焦点（新建流程下焦点由后续业务页 goto 接管）。
            reuse_page: 传入时直接复用该 Page 作为环境页，不再调用 context.new_page()。
                        用于「先环境页后业务页」的顺序策略：调用方把 pages[0] 传入，
                        set_content 完成后再 new_page() + goto 业务页，Chromium 天然聚焦业务页。

        Returns:
            是否成功打开/刷新。
        """
        if not self.context or self._headless_mode:
            logger.debug("跳过环境信息页（无头或未就绪）: context=%s headless=%s", bool(self.context), self._headless_mode)
            return False
        try:
            pages_before = list(self.context.pages)
            if not pages_before:
                return False

            fp = self.profile_manager.get_fingerprint()
            plat_key = (self.platform or "").strip().lower()
            plat_label = self._ACCOUNT_INFO_TAB_PLATFORM_LABELS.get(plat_key, self.platform or "—")
            nick = (self.account_name or self.account_id or "—").strip() or "—"
            tab_title = f"[{plat_label}] {nick}"

            user_agent = fp.get("user_agent") or ""
            chrome_m = re.search(r"Chrome/([\d.]+)", user_agent)
            chrome_ver = chrome_m.group(1) if chrome_m else "—"

            langs = fp.get("languages")
            if not isinstance(langs, list):
                langs = []
            langs_str = " / ".join(str(x) for x in langs) if langs else "—"

            strength_raw = fp.get("canvas_noise_strength", fp.get("canvas_noise", None))
            canvas_level = 1
            canvas_level_label = "低"
            try:
                if strength_raw is not None:
                    s = float(strength_raw)
                    if s <= 0.00015:
                        canvas_level = 1
                        canvas_level_label = "低"
                    elif s <= 0.0004:
                        canvas_level = 2
                        canvas_level_label = "中"
                    else:
                        canvas_level = 3
                        canvas_level_label = "高"
            except Exception:
                canvas_level = 1

            data_dir = str(self.user_data_dir or self.profile_manager.get_user_data_dir())

            # ua_ch 中提取浏览器版本（已与 UA 对齐，不单独展示）
            ua_ch = fp.get("ua_ch") or {}
            ua_ch_plat = ua_ch.get("platform", fp.get("platform", "Windows"))
            ua_ch_arch = ua_ch.get("architecture", "x86")
            ua_ch_bits = ua_ch.get("bitness", "64")

            # 确定环境信息页：
            # - reuse_page 不为 None：复用调用方传入的页面（如 pages[0]），不新建标签，不抢焦点
            # - 否则：若已有记录且仍存活则复用，已关闭或没有记录时才 new_page()
            # 注意：new_page() 会让 Chrome 切到新标签，若当前流程是「先环境页后业务页」
            # 则焦点由后续业务页 goto 天然接管，无需在此补偿。
            if reuse_page is not None and not reuse_page.is_closed():
                info_page = reuse_page
                self._environment_info_page = info_page
                logger.debug("[BrowserManager] 环境页：复用传入的 reuse_page（不新建标签）")
            else:
                info_page = self._environment_info_page
                if info_page is None or info_page.is_closed():
                    info_page = await self.context.new_page()
                    self._environment_info_page = info_page

            from .virtual_geo import build_playwright_geolocation, coalesce_virtual_geo

            proxy_ip = "本机直连"

            vg = coalesce_virtual_geo(fp)
            if vg["enabled"]:
                _bits: List[str] = []
                if vg["label"]:
                    _bits.append(vg["label"])
                if vg["latitude"] is not None and vg["longitude"] is not None:
                    _bits.append(f"（{float(vg['latitude']):.6f}°, {float(vg['longitude']):.6f}°）")
                env_loc_main = " ".join(_bits) if _bits else "已启用，请补充名称与经纬度"
                env_loc_dim = "指纹内配置的固定坐标。"
            else:
                env_loc_main = "未启用"
                env_loc_dim = "未启用时由系统决定。"

            if build_playwright_geolocation(fp):
                browser_geo_main = "已应用虚拟坐标"
            elif vg["enabled"]:
                browser_geo_main = "已开启，请补全有效经纬度后生效"
            else:
                browser_geo_main = "未固定（随系统）"

            def esc(s: Any) -> str:
                return html.escape(str(s), quote=True)

            # 平台对应图标颜色
            plat_colors = {
                "douyin": "#161823", "kuaishou": "#ff6600", "xiaohongshu": "#fe2c55",
                "wechat_video": "#07c160", "bilibili": "#fb7299", "toutiao": "#e8321c",
                "weibo": "#e6162d", "baijiahao": "#2468f2", "qiehao": "#0aa5ff",
                "duoduoshipin": "#e02020",
            }
            plat_color = plat_colors.get(plat_key, "#1a73e8")

            html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="wemedia-baby-env" content="1"/>
<title>{esc(tab_title)}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial,
                 "Microsoft YaHei", sans-serif;
    background: #f0f2f5;
    color: #1f2937;
    min-height: 100vh;
  }}

  /* ── 顶部 Banner ── */
  .banner {{
    background: linear-gradient(135deg, #1e3a5f 0%, #2563eb 100%);
    padding: 28px 48px 24px;
    display: flex;
    align-items: center;
    gap: 20px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.15);
  }}
  .banner-avatar {{
    width: 56px; height: 56px;
    border-radius: 50%;
    background: {esc(plat_color)};
    display: flex; align-items: center; justify-content: center;
    font-size: 1.5rem; font-weight: 700; color: #fff;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
  }}
  .banner-info {{ flex: 1; }}
  .banner-title {{
    font-size: 1.5rem; font-weight: 600; color: #fff; line-height: 1.2;
  }}
  .banner-sub {{
    margin-top: 5px; font-size: 0.9rem;
    color: rgba(255,255,255,0.7);
    display: flex; align-items: center; gap: 8px;
  }}
  .banner-tag {{
    background: rgba(255,255,255,0.18);
    border: 1px solid rgba(255,255,255,0.3);
    border-radius: 20px;
    padding: 1px 10px;
    font-size: 0.8rem;
    color: #fff;
  }}
  .banner-status {{
    display: flex; flex-direction: column; align-items: flex-end; gap: 6px;
  }}
  .status-dot {{
    display: flex; align-items: center; gap: 6px;
    font-size: 0.85rem; color: rgba(255,255,255,0.85);
  }}
  .status-dot::before {{
    content: '';
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    background: #4ade80;
    box-shadow: 0 0 6px #4ade80;
  }}

  /* ── 主体网格布局 ── */
  .page-body {{
    padding: 28px 48px 48px;
    display: grid;
    grid-template-columns: 340px 1fr;
    grid-template-rows: auto auto auto;
    gap: 20px;
  }}

  /* ── 卡片通用 ── */
  .card {{
    background: #fff;
    border-radius: 14px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07), 0 4px 16px rgba(0,0,0,0.04);
    overflow: hidden;
  }}
  .card-header {{
    padding: 14px 22px;
    border-bottom: 1px solid #f3f4f6;
    display: flex; align-items: center; gap: 10px;
  }}
  .card-header-icon {{
    width: 28px; height: 28px;
    border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.9rem;
  }}
  .card-header h2 {{
    font-size: 0.95rem; font-weight: 600; color: #374151;
  }}
  .card-body {{ padding: 6px 0; }}

  /* ── 信息行 ── */
  .info-row {{
    display: flex;
    align-items: flex-start;
    padding: 11px 22px;
    border-bottom: 1px solid #f9fafb;
    gap: 12px;
  }}
  .info-row:last-child {{ border-bottom: none; }}
  .info-label {{
    width: 120px; min-width: 120px;
    font-size: 0.85rem; color: #6b7280; font-weight: 500;
    padding-top: 1px;
  }}
  .info-value {{
    flex: 1;
    font-size: 0.9rem; color: #1f2937;
    word-break: break-all;
    line-height: 1.5;
  }}

  /* ── 标签/徽章 ── */
  .chip {{
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px;
    font-size: 0.8rem; font-weight: 500;
  }}
  .chip-blue  {{ background: #eff6ff; color: #1d4ed8; }}
  .chip-green {{ background: #f0fdf4; color: #15803d; }}
  .chip-orange {{ background: #fff7ed; color: #c2410c; }}
  .chip-gray  {{ background: #f3f4f6; color: #4b5563; }}

  /* ── 大指标卡 (account + network 竖向并排) ── */
  .left-col {{
    grid-column: 1;
    grid-row: 1 / 3;
    display: flex; flex-direction: column; gap: 20px;
  }}

  /* ── 指纹环境（占右列上下两行）── */
  .right-top {{ grid-column: 2; grid-row: 1; }}
  .right-bottom {{ grid-column: 2; grid-row: 2; }}

  /* ── 指纹分组：两列网格 ── */
  .fp-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
  }}
  .fp-grid .info-row {{ border-right: none; }}

  /* ── 特殊大字显示 ── */
  .big-val {{
    font-size: 1.05rem; font-weight: 600; color: #111827;
  }}
  .dim {{ color: #9ca3af; font-size: 0.8rem; margin-left: 4px; }}

  /* ── 底部说明 ── */
  .foot {{
    grid-column: 1 / 3;
    text-align: center;
    font-size: 0.82rem; color: #9ca3af;
    padding: 8px 0;
  }}
</style>
</head>
<body>

<!-- 顶部 Banner -->
<div class="banner">
  <div class="banner-avatar">{esc(plat_label[0] if plat_label else "?")}</div>
  <div class="banner-info">
    <div class="banner-title">{esc(nick)}</div>
    <div class="banner-sub">
      <span class="banner-tag">{esc(plat_label)}</span>
      <span>独立浏览器环境</span>
    </div>
  </div>
  <div class="banner-status">
    <div class="status-dot">浏览器运行中</div>
    <div style="font-size:0.82rem;color:rgba(255,255,255,0.55);">Chrome {esc(chrome_ver)}</div>
  </div>
</div>

<!-- 主体 -->
<div class="page-body">

  <!-- ── 左列 ── -->
  <div class="left-col">

    <!-- 账号信息卡（绑定账号：与网页内当前登录态可能不一致，见下方说明） -->
    <div class="card">
      <div class="card-header">
        <div class="card-header-icon" style="background:#eff6ff;">👤</div>
        <h2>账号信息</h2>
      </div>
      <div class="card-body">
        <div class="info-row" style="background:#fffbeb;border-radius:8px;padding:10px 12px;margin-bottom:10px;border:1px solid #fde68a;">
          <div class="info-label" style="align-self:flex-start;">绑定说明</div>
          <div class="info-value" style="font-size:0.84rem;color:#92400e;line-height:1.55;">
            下方「账号名称」为<strong>媒小宝为本浏览器数据目录绑定的账号</strong>。若创作者网页已登出或您改登了<strong>其他账号</strong>，会与绑定不一致，易造成<strong>串号</strong>；请对照本页名称操作，必要时仅在对应账号条目下打开浏览器。
          </div>
        </div>
        <div class="info-row">
          <div class="info-label">平台</div>
          <div class="info-value"><span class="chip chip-blue">{esc(plat_label)}</span></div>
        </div>
        <div class="info-row">
          <div class="info-label">绑定账号名称</div>
          <div class="info-value big-val">{esc(nick)}</div>
        </div>
        <div class="info-row">
          <div class="info-label">账号 ID</div>
          <div class="info-value" style="color:#6b7280;">{esc(self.account_id)}</div>
        </div>
        <div class="info-row">
          <div class="info-label">数据目录</div>
          <div class="info-value" style="font-size:0.8rem;color:#9ca3af;">{esc(data_dir)}</div>
        </div>
      </div>
    </div>

    <!-- 网络与环境（不探测外网 IP / 不做页面定位，保证快速打开） -->
    <div class="card">
      <div class="card-header">
        <div class="card-header-icon" style="background:#f0fdf4;">🌐</div>
        <h2>网络与环境</h2>
      </div>
      <div class="card-body">
        <div class="info-row">
          <div class="info-label">连接方式</div>
          <div class="info-value"><span class="chip chip-green">{esc(proxy_ip)}</span></div>
        </div>
        <div class="info-row">
          <div class="info-label">虚拟坐标（指纹）</div>
          <div class="info-value">
            <span class="big-val">{esc(env_loc_main)}</span>
            <span class="chip chip-gray" style="margin-left:8px;">{esc(browser_geo_main)}</span>
            <div class="dim" style="margin-top:4px;">{esc(env_loc_dim)}</div>
          </div>
        </div>
        <div class="info-row">
          <div class="info-label">网络类型</div>
          <div class="info-value">
            <span class="chip chip-blue">{esc(fp.get('connection_effective_type', '4g').upper())}</span>
            <span class="dim">下行 {esc(fp.get('connection_downlink', '—'))} Mbps / 延迟 {esc(fp.get('connection_rtt', '—'))} ms</span>
          </div>
        </div>
      </div>
    </div>

  </div>

  <!-- ── 右上：浏览器与系统 ── -->
  <div class="card right-top">
    <div class="card-header">
      <div class="card-header-icon" style="background:#fefce8;">🖥️</div>
      <h2>浏览器与系统</h2>
    </div>
    <div class="card-body fp-grid">
      <div class="info-row">
        <div class="info-label">浏览器版本</div>
        <div class="info-value"><span class="big-val">Chrome {esc(chrome_ver)}</span></div>
      </div>
      <div class="info-row">
        <div class="info-label">操作系统</div>
        <div class="info-value">{esc(ua_ch_plat)} {esc(ua_ch_arch)}-{esc(ua_ch_bits)}bit</div>
      </div>
      <div class="info-row">
        <div class="info-label">语言 / 地区</div>
        <div class="info-value">{esc(fp.get('locale', 'zh-CN'))} &nbsp;<span class="dim">{esc(langs_str)}</span></div>
      </div>
      <div class="info-row">
        <div class="info-label">时区</div>
        <div class="info-value">{esc(fp.get('timezone_id', 'Asia/Shanghai'))}</div>
      </div>
      <div class="info-row">
        <div class="info-label">屏幕分辨率</div>
        <div class="info-value">{esc(fp.get('screen_width', '—'))} × {esc(fp.get('screen_height', '—'))} <span class="dim">色深 {esc(fp.get('screen_color_depth', '—'))} bit</span></div>
      </div>
      <div class="info-row">
        <div class="info-label">可用区域</div>
        <div class="info-value">{esc(fp.get('screen_avail_width', '—'))} × {esc(fp.get('screen_avail_height', '—'))}</div>
      </div>
    </div>
  </div>

  <!-- ── 右下：硬件与防检测 ── -->
  <div class="card right-bottom">
    <div class="card-header">
      <div class="card-header-icon" style="background:#fdf4ff;">🔒</div>
      <h2>硬件模拟 &amp; 防检测</h2>
    </div>
    <div class="card-body fp-grid">
      <div class="info-row">
        <div class="info-label">CPU 核心数</div>
        <div class="info-value"><span class="big-val">{esc(fp.get('hardware_concurrency', '—'))}</span> 核</div>
      </div>
      <div class="info-row">
        <div class="info-label">CPU 型号</div>
        <div class="info-value" style="font-size:0.88rem;">{esc(fp.get('cpu_model') or '—')}</div>
      </div>
      <div class="info-row">
        <div class="info-label">内存容量</div>
        <div class="info-value"><span class="big-val">{esc(fp.get('device_memory', '—'))}</span> GB</div>
      </div>
      <div class="info-row">
        <div class="info-label">显卡厂商</div>
        <div class="info-value">{esc(fp.get('webgl_vendor', '—'))}</div>
      </div>
      <div class="info-row">
        <div class="info-label">显卡型号</div>
        <div class="info-value" style="font-size:0.82rem;">{esc(fp.get('webgl_renderer', '—'))}</div>
      </div>
      <div class="info-row">
        <div class="info-label">Canvas 保护</div>
        <div class="info-value">
          <span class="chip {'chip-green' if canvas_level == 1 else ('chip-orange' if canvas_level == 2 else 'chip-orange')}">{esc(canvas_level_label)}强度</span>
          <span class="dim">种子 {esc(fp.get('canvas_noise_seed', '—'))}</span>
        </div>
      </div>
      <div class="info-row">
        <div class="info-label">音频保护</div>
        <div class="info-value"><span class="chip chip-green">已开启</span> <span class="dim">种子 {esc(fp.get('audio_context_seed', '—'))}</span></div>
      </div>
    </div>
  </div>

  <!-- 底部提示 -->
  <div class="foot">本标签用于辨认绑定账号与环境指纹；日常发布、自动任务在<strong>创作者中心</strong>标签。打开本账号浏览器时会展示本页，可在浏览器内刷新本标签。</div>

</div>
</body>
</html>"""

            self._environment_info_page = info_page

            if focus_tab:
                # 用户主动查看环境页：先切到该标签，后台写入内容
                await self._bring_page_to_front_twice(info_page)
                asyncio.create_task(self._render_env_content(info_page, html_doc, focus_business_after=False))
            elif reuse_page is not None:
                # 「先环境页后业务页」新建流程：同步写入内容，调用方完成后会 new_page() + goto 业务页，
                # Chromium 天然将焦点切到业务页，此处不需要任何焦点操作。
                await self._render_env_content(info_page, html_doc, focus_business_after=False)
            else:
                # 刷新/复用已有环境页：后台写入，set_content 完成后补偿焦点拉回业务页
                asyncio.create_task(self._render_env_content(info_page, html_doc, focus_business_after=True))

            logger.info("已打开/刷新环境信息标签页: title=%s", tab_title)
            return True
        except Exception as e:
            logger.warning("打开环境信息标签页失败: %s", e, exc_info=True)
            err = str(e).lower()
            if (
                "has been closed" in err
                or "target page" in err
                or "target closed" in err
                or "browser has been closed" in err
            ):
                self._clear_persistent_context_refs("环境信息页流程中检测到上下文已关闭")
            return False

    async def save_state(self) -> bool:
        """将当前 Context 导出为 storage_state.json，供关闭后与账号库 cookies.json 同步等流程使用。"""
        if not self.context:
            logger.warning("无法保存状态：Context 不存在")
            return False
        
        return await self.profile_manager.save_storage_state(self.context)
    
    async def close(self):
        """关闭浏览器并清理资源：先优雅关闭避免「页面已崩溃」，超时再强杀。

        使用 try/finally 结构保证：即使外层 asyncio.wait_for 对本协程下发 CancelledError，
        playwright.stop() 和 _force_kill_browser_process() 也能通过 asyncio.shield 确保执行，
        避免连续任务中浏览器进程持续残留导致内存累积。
        """
        logger.info(f"[BrowserManager] 启动关闭流程: {self.account_id}")

        # 注销已注册的 Chrome PID 并清理 PID 文件
        _pid = self._chrome_pid
        self._chrome_pid = None
        if _pid is not None:
            try:
                from .process_supervisor import ProcessSupervisor
                ProcessSupervisor.unregister(_pid)
            except Exception:
                pass
        self._remove_pid_file()

        # 1. 先优雅关闭 context，用户不会看到「页面已崩溃」
        graceful_ok = False
        try:
            if self.context:
                try:
                    logger.info(f"[BrowserManager] 步骤1: 优雅关闭 Context...")
                    await asyncio.wait_for(self.context.close(), timeout=3.0)
                    graceful_ok = True
                except asyncio.TimeoutError:
                    logger.warning("[BrowserManager] 优雅关闭 context 超时，将强制结束进程")
                except asyncio.CancelledError:
                    logger.warning("[BrowserManager] 关闭 context 被取消，将继续清理 Playwright 实例")
                    raise
                except Exception as e:
                    err_msg = str(e).strip().lower()
                    if "closed" in err_msg or "has been closed" in err_msg or "target page" in err_msg:
                        logger.debug("[BrowserManager] 关闭 context 时目标已关闭: %s", e)
                        graceful_ok = True
                    else:
                        logger.warning("[BrowserManager] 关闭 context 时异常: %s", e)
                self.context = None
                self.browser = None
                self._environment_info_page = None
        finally:
            # 步骤2和步骤3用 finally + shield 确保：即使外层 CancelledError 也会被执行，
            # 防止 Playwright 驱动进程和 Chromium 进程在取消路径下持续残留
            pw = self.playwright
            self.playwright = None
            if pw is not None:
                try:
                    logger.info(f"[BrowserManager] 步骤2: 停止 Playwright 实例...")
                    # asyncio.shield 保护 playwright.stop() 不被外层取消中断
                    await asyncio.wait_for(asyncio.shield(pw.stop()), timeout=2.0)
                except Exception as e:
                    err_msg = str(e).strip().lower()
                    if "closed" in err_msg or "target" in err_msg:
                        logger.debug("[BrowserManager] 停止 playwright 时目标已关闭: %s", e)
                    else:
                        logger.warning("[BrowserManager] 停止 playwright 时异常: %s", e)

            # 仅当优雅关闭失败时才扫描并强杀残留进程
            # 优雅关闭成功时 Playwright 已正常退出 Chromium，无需再做全量 psutil 扫描（耗时1-2秒）
            if not graceful_ok:
                try:
                    await asyncio.shield(self._force_kill_browser_process())
                except Exception as e:
                    logger.warning(f"[BrowserManager] 进程清理出错: {e}")
            else:
                logger.debug("[BrowserManager] 优雅关闭成功，跳过全量进程扫描")

            logger.info(f"[BrowserManager] ✓ 浏览器清理流程圆满结束: {self.account_id}")

    async def _extract_chrome_pid(self) -> Optional[int]:
        """从刚启动的持久化上下文中提取 Chromium 主进程 PID。"""
        if not self.user_data_dir:
            return None
        target = str(self.user_data_dir).lower().replace("\\", "/")

        def _find_pid(target_path: str) -> Optional[int]:
            try:
                import psutil
            except ImportError:
                return None
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    name = proc.info.get('name', '').lower()
                    if not any(x in name for x in ['chrome', 'msedge', 'chromium']):
                        continue
                    cmdline = " ".join(proc.info.get('cmdline') or []).lower().replace("\\", "/")
                    if target_path in cmdline and '--type=' not in cmdline:
                        return proc.info['pid']
                except Exception:
                    continue
            return None

        pid = await asyncio.to_thread(_find_pid, target)
        if pid:
            logger.info("[BrowserManager] 已捕获 Chrome 主进程 PID=%d", pid)
        return pid

    def _pid_file_path(self) -> Optional[Path]:
        """返回 profile 目录下的 chrome.pid 文件路径。"""
        if not self.user_data_dir:
            return None
        return Path(self.user_data_dir).parent / "chrome.pid"

    def _save_pid_file(self, pid: int) -> None:
        """将 Chrome PID 写入文件，供下次 launch 精准 kill。同时注册到全局 PID 集合。"""
        BrowserManager.register_pid(pid)
        p = self._pid_file_path()
        if p:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(str(pid), encoding="utf-8")
            except Exception:
                pass

    def _remove_pid_file(self) -> None:
        p = self._pid_file_path()
        if p and p.exists():
            try:
                pid = int(p.read_text(encoding="utf-8").strip())
                BrowserManager.unregister_pid(pid)
            except Exception:
                pass
            try:
                p.unlink()
            except Exception:
                pass

    async def _force_kill_browser_process(self):
        """强制终止与当前 user_data_dir 相关的浏览器进程。
        优先读取 chrome.pid 精准 kill，仅在 PID 文件不存在或 kill 失败时 fallback 到全机扫描。
        """
        if not self.user_data_dir:
            return

        # --- 阶段 1：PID 文件精准 kill ---
        pid_file = self._pid_file_path()
        had_pid_file = bool(pid_file and pid_file.exists())
        if pid_file and pid_file.exists():
            try:
                old_pid = int(pid_file.read_text(encoding="utf-8").strip())
                def _kill_by_pid(pid: int) -> bool:
                    try:
                        import psutil
                        proc = psutil.Process(pid)
                        name = proc.name().lower()
                        if any(x in name for x in ['chrome', 'msedge', 'chromium']):
                            logger.warning("[BrowserManager] PID 文件精准清理: PID=%d (%s)", pid, name)
                            proc.kill()
                            return True
                    except Exception:
                        pass
                    return False

                killed = await asyncio.to_thread(_kill_by_pid, old_pid)
                self._remove_pid_file()
                if killed:
                    await asyncio.sleep(1.0)
                    logger.info("[BrowserManager] 已通过 PID 文件精准清理残留进程，跳过全机扫描")
                    return
            except Exception:
                pass

        # --- 阶段 2：Fallback 全机进程扫描 ---
        target_path = str(self.user_data_dir).lower().replace("\\", "/")
        path_parts = target_path.split("/")
        feature_token = None
        try:
            if "browser" in path_parts:
                idx = path_parts.index("browser")
                if idx > 0:
                    feature_token = path_parts[idx-1]
        except (ValueError, IndexError):
            pass
            
        search_target = feature_token or target_path
        if had_pid_file:
            logger.info(f"[BrowserManager] PID 文件未能清理目标进程，fallback 扫描残留进程... 目标特征: {search_target}")
        else:
            logger.debug(f"[BrowserManager] 未发现上次 PID 文件，按 profile 特征扫描残留进程... 目标特征: {search_target}")
        
        def _do_kill_sync(target: str) -> int:
            try:
                import psutil
            except ImportError:
                return 0
            terminated = 0
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    proc_name = proc.info.get('name', '').lower()
                    if not any(x in proc_name for x in ['chrome', 'msedge', 'browser', 'chromium']):
                        continue
                    cmdline = " ".join(proc.cmdline() or []).lower().replace("\\", "/")
                    if target in cmdline:
                        logger.warning(f"[BrowserManager] 发现目标残留进程 PID={proc.info['pid']}, 正在强杀以释放文件锁...")
                        proc.kill()
                        terminated += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return terminated

        try:
            terminated_count = await asyncio.to_thread(_do_kill_sync, search_target)
            if terminated_count > 0:
                logger.info(f"[BrowserManager] 成功清理 {terminated_count} 个残留进程，目标: {search_target}")
                wait_sec = 2.0 if terminated_count >= 3 else 1.0
                await asyncio.sleep(wait_sec)
            else:
                logger.debug(f"[BrowserManager] 未发现匹配 {search_target} 的活跃进程")
                
        except Exception as e:
            logger.error(f"[BrowserManager] 强制清理进程异常: {e}")
    
    def get_browser_version(self) -> Optional[str]:
        """获取浏览器版本"""
        return self._browser_version
    
    def has_valid_credentials(self) -> bool:
        """检查账号是否有有效凭证（cookies.json 或持久化 profile 内已有 Cookie 库）。"""
        return self.profile_manager.has_valid_credentials()
