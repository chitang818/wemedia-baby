"""
主窗口模块
文件路径：src/ui/main_window.py
功能：主窗口实现，使用 PySide6-Fluent-Widgets 的 FluentWindow 和 NavigationInterface
"""

from typing import Optional
import asyncio
import ctypes
import datetime
import os
import sys
import qasync
from PySide6.QtWidgets import (
    QWidget,
    QMainWindow,
    QStatusBar,
    QApplication,
    QSystemTrayIcon,
    QMenu,
    QSizePolicy,
)
from PySide6.QtGui import QIcon, QDesktopServices, QAction
from PySide6.QtCore import QTimer, QUrl, Qt
from qasync import asyncSlot
from PySide6.QtCore import Slot

import logging

# 导入 PySide6-Fluent-Widgets
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
    isDarkTheme, InfoBar, InfoBarPosition, StateToolTip, NavigationDisplayMode,
    BodyLabel, CheckBox,
)
FLUENT_WIDGETS_AVAILABLE = True

from src.ui.navigation_config import NavigationConfig
from src.ui.utils.async_helper import run_async_from_ui
from src.infrastructure.common.di.service_locator import ServiceLocator
from src.infrastructure.common.config.config_center import ConfigCenter
from src.ui.page_factory import PageFactory
from config.feature_flags import FeatureFlags

# 功能开关：用 find_spec 检测模块是否存在，避免启动时导入重型可选模块
import importlib.util

def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False

BATCH_FEATURE_AVAILABLE = _module_available("src.pro_features.batch.pages.batch_task_creation_page") and FeatureFlags.is_feature_enabled("batch_publish")
DATA_CENTER_AVAILABLE = _module_available("src.pro_features.data_center.pages.data_center_page") and FeatureFlags.is_feature_enabled("data_center")
INTERACTION_FEATURE_AVAILABLE = _module_available("src.pro_features.interaction.pages.comment_page") and FeatureFlags.is_feature_enabled("interaction")
SUBSCRIPTION_PAGE_AVAILABLE = _module_available("src.ui.pages.subscription_page") and FeatureFlags.is_feature_enabled("subscription")

MATERIAL_LIBRARY_AVAILABLE = _module_available("src.ui.pages.material.video_library_page") and FeatureFlags.is_feature_enabled("material_library")
COMMERCE_PROMOTION_AVAILABLE = _module_available("src.ui.pages.material.cart_promotion_page") and FeatureFlags.is_feature_enabled("commerce_promotion")

logger = logging.getLogger(__name__)


# 根据可用性选择基类
if FLUENT_WIDGETS_AVAILABLE:
    _BaseWindow = FluentWindow
else:
    _BaseWindow = QMainWindow


class MainWindow(FluentWindow):
    """主窗口 - 继承 FluentWindow 实现现代化 Fluent Design 风格"""
    
    def __init__(self):
        """初始化主窗口"""
        super().__init__()
        
        # 初始化页面工厂
        self.page_factory = PageFactory()

        # 设置窗口图标 (使用 PathManager 统一路径，兼容打包环境)
        from src.infrastructure.common.path_manager import PathManager
        project_root = str(PathManager.get_resource_dir())
        
        icon_png = os.path.join(project_root, "resources", "logo.png")
        icon_ico = os.path.join(project_root, "resources", "icons", "app.ico")
        
        if os.path.exists(icon_png):
            self.setWindowIcon(QIcon(icon_png))
            logger.debug(f"MainWindow 设置图标 (PNG): {icon_png}")
        elif os.path.exists(icon_ico):
            self.setWindowIcon(QIcon(icon_ico))
            logger.debug(f"MainWindow 设置图标 (ICO): {icon_ico}")
        else:
            logger.warning(f"MainWindow 未找到图标: {icon_png}")

        self._setup_ui()
        self._setup_navigation()
        self._setup_status_bar()
        self._setup_tray_icon()
        self._init_services()
        logger.debug("主窗口初始化完成 (Lazy Loading Mode)")

    def _get_or_create_page(self, page_name: str):
        """按需获取或创建页面实例 (Factory Pattern + Lazy Loading)"""
        # 1. 检查是否已存在
        if hasattr(self, page_name):
            return getattr(self, page_name)

        import time
        from src.utils.startup_profiler import is_page_load_profiler_enabled, log_page_create_timing

        t0 = time.perf_counter() if is_page_load_profiler_enabled() else 0.0

        # 2. 使用工厂创建
        try:
            logger.debug(f"正在惰性加载页面: {page_name} ...")
            page_instance = self.page_factory.create_page(page_name, self)

            if not page_instance:
                logger.error(f"页面创建失败: {page_name}")
                return None

            # 3. 挂载到 self
            setattr(self, page_name, page_instance)

            # 4. 添加到 StackedWidget (如果尚未添加)
            if hasattr(self, "stackedWidget"):
                if self.stackedWidget.indexOf(page_instance) == -1:
                    self.stackedWidget.addWidget(page_instance)

            if is_page_load_profiler_enabled():
                log_page_create_timing(page_name, time.perf_counter() - t0)

            logger.debug(f"页面加载完成: {page_name}")
            return page_instance
        except Exception as e:
            logger.error(f"加载页面异常 {page_name}: {e}", exc_info=True)
            return None
    
    def _init_services(self):
        """初始化服务和事件监听"""
        self._event_handlers = []
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.infrastructure.common.event.event_bus import EventBus
            from src.infrastructure.common.event.events import PublishStartedEvent, TaskFailedEvent, PublishCompletedEvent
            
            service_locator = ServiceLocator()
            if service_locator.is_registered(EventBus):
                self.event_bus = service_locator.get(EventBus)
                self.event_bus.subscribe("PublishStartedEvent", self._on_publish_started)
                self.event_bus.subscribe("TaskFailedEvent", self._on_task_failed)
                self.event_bus.subscribe("PublishCompletedEvent", self._on_publish_completed)
                self.event_bus.subscribe("SessionEvictedEvent", self._on_session_evicted)
                self._event_handlers.extend([
                    ("PublishStartedEvent", self._on_publish_started),
                    ("TaskFailedEvent", self._on_task_failed),
                    ("PublishCompletedEvent", self._on_publish_completed),
                    ("SessionEvictedEvent", self._on_session_evicted),
                ])
                logger.debug("主窗口事件监听已注册")
            self._init_event_subscriptions()
        except Exception as e:
            logger.error(f"初始化主窗口服务失败: {e}")

    def _on_publish_started(self, event):
        """发布开始事件回调"""
        msg = f"正在发布: {getattr(event, 'account_name', '未知账号')}"
        self.show_status_message(msg)

    def _on_publish_completed(self, event):
        """发布完成事件回调"""
        msg = f"发布完成: {getattr(event, 'account_name', '未知账号')}"
        self.show_status_message(msg, 5000)

    def _on_task_failed(self, event):
        """任务失败事件回调"""
        msg = f"任务失败: {getattr(event, 'error', '未知错误')}"
        self.show_status_message(msg, 5000, is_error=True)

    def _on_session_evicted(self, event):
        """账号在其他设备登录，当前会话被顶下线"""
        reason = getattr(event, "reason", "您的账号已在其他设备登录，请重新登录。")
        # 此回调可能从非 UI 线程触发（qasync 工作线程），必须切换到 UI 线程操作 Qt 控件
        from PySide6.QtCore import QMetaObject, Q_ARG, Qt
        QMetaObject.invokeMethod(self, "_show_session_evicted_bar", Qt.QueuedConnection,
                                 Q_ARG(str, reason))

    @Slot(str)
    def _show_session_evicted_bar(self, reason: str):
        """在 UI 主线程中显示顶下线提示（线程安全）"""
        if FLUENT_WIDGETS_AVAILABLE:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(
                title="账号已在其他设备登录",
                content=f"{reason}\n请重新登录媒小宝账号后再继续发布。",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=-1,
            )

    def show_status_message(self, message: str, duration: int = 3000, is_error: bool = False):
        """显示状态信息 (线程安全)"""
        from PySide6.QtCore import QMetaObject, Q_ARG, Qt
        QMetaObject.invokeMethod(self, "_update_status_bar_impl", Qt.QueuedConnection,
                                 Q_ARG(str, message), Q_ARG(int, duration))
        
        if is_error and FLUENT_WIDGETS_AVAILABLE:
             QMetaObject.invokeMethod(self, "_show_error_bar", Qt.QueuedConnection,
                                      Q_ARG(str, message))

    # 定义为 Slot 供 invokeMethod 调用
    @Slot(str, int)
    def _update_status_bar_impl(self, message: str, duration: int):
        if hasattr(self, 'statusBar') and callable(self.statusBar) and self.statusBar():
            self.statusBar().showMessage(message, duration)
        
        # 用户要求移除顶部的蓝色消息状态弹窗功能
        # if self.window():
        #      StateToolTip(
        #          title="",
        #          content=message,
        #          parent=self.window()
        #      ).show()

    @Slot(str)
    def _show_error_bar(self, message: str):
        InfoBar.error(
            title='错误',
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        try:
            from src.utils.startup_profiler import mark, log_summary
            mark("showEvent")
        except Exception:
            pass
        # 窗口显示后，设置为最大化（只在首次显示时）
        if not hasattr(self, '_maximized_set'):
            self._maximized_set = True
            logger.debug("窗口显示完成")
        # 浏览器页已从导航移除，不再延迟初始化
        # 强制展开导航栏 (解决默认收起问题)
        QTimer.singleShot(50, lambda: self._force_nav_expand())
        # 浏览器预热：默认按需触发；ENABLE_BROWSER_WARMUP_ON_START=1 时恢复启动后 3 秒预热
        if os.environ.get("ENABLE_BROWSER_WARMUP_ON_START", "").strip().lower() in ("1", "true", "yes"):
            QTimer.singleShot(3000, self._warmup_browser_service)
        # 强制更新：打开软件立即检测，有新版本则弹窗并退出，旧版本不可用
        # 52POJIE 特别版不检测软件更新
        if not FeatureFlags.is_52pojie() and not getattr(self, "_update_check_startup_done", False):
            self._update_check_startup_done = True
            QTimer.singleShot(5000, self._run_startup_update_check)
        # Chrome 检测：启动后约 2 秒检测一次，未安装时提示前往设置安装（仅提示一次）
        if not getattr(self, "_chrome_check_done", False):
            QTimer.singleShot(2000, self._run_chrome_check)
        # 媒体库：未配置根路径时弹窗引导前往设置（已配置则静默，仅检测一次）
        if not getattr(self, "_material_library_check_scheduled", False):
            self._material_library_check_scheduled = True
            QTimer.singleShot(1200, self._run_material_library_startup_check)
        # 空闲预加载高频页面：错开时间片，避免同一时刻多页 import/__init__ 抢满 UI 线程
        if not getattr(self, "_preload_scheduled", False):
            self._preload_scheduled = True
            preload_pages = [
                "publish_list_page",
                "publish_records_page",
                "single_task_creation_page",
                "account_page",
                "settings_page",
            ]
            if BATCH_FEATURE_AVAILABLE:
                preload_pages.append("batch_task_creation_page")
            _preload_base_ms = 800
            _preload_step_ms = 260
            for i, name in enumerate(preload_pages):
                delay = _preload_base_ms + i * _preload_step_ms
                QTimer.singleShot(delay, lambda n=name: self._get_or_create_page(n))
        try:
            from src.utils.startup_profiler import log_summary
            log_summary()
        except Exception:
            pass
    
    def _run_material_library_startup_check(self):
        """启动后检测是否已配置媒体库根路径；未配置则弹窗引导至设置（每个进程仅执行一次）。"""
        if getattr(self, "_material_library_startup_check_done", False):
            return
        self._material_library_startup_check_done = True
        try:
            from src.infrastructure.common.material_library_manager import MaterialLibraryManager

            if MaterialLibraryManager.get_root_base_dir() is not None:
                return
            from src.ui.utils.fluent_dialogs import show_confirm

            content = (
                "尚未配置媒体库存储位置。视频库、图片库及批量发布中的「从媒体库选择」等功能需要指定本地文件夹。\n\n"
                "是否前往「设置」→「数据管理」中的「媒体库存储位置」完成设置？"
            )
            if show_confirm(self, "未配置媒体库", content):
                self.navigate_to("settings_page")
        except Exception as e:
            logger.warning("启动时媒体库路径检测失败: %s", e)

    def _run_chrome_check(self):
        """启动后延迟检测 Chrome 是否安装；未安装时提示前往 设置 → 工具依赖 安装（仅执行一次）"""
        if getattr(self, "_chrome_check_done", False):
            return
        import sys
        if sys.platform != "win32":
            self._chrome_check_done = True
            return
        self._chrome_check_done = True
        try:
            from src.ui.utils.async_helper import AsyncWorker
            def check():
                from src.utils.chrome_installer import detect_chrome
                return detect_chrome()
            worker = AsyncWorker(check)
            worker.setParent(self)
            worker.finished.connect(self._on_chrome_check_done)
            worker.error.connect(lambda e: None)
            worker.start()
        except Exception as e:
            logger.debug("启动时 Chrome 检测调度失败: %s", e)

    def _on_chrome_check_done(self, result):
        """Chrome 检测完成：未安装时显示 InfoBar 引导用户前往设置安装"""
        if result is None:
            return
        installed = result[0] if isinstance(result, (tuple, list)) and len(result) >= 1 else True
        if installed:
            return
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.warning(
                title="未检测到 Chrome",
                content="未检测到 Google Chrome，浏览器相关功能（账号管理、发布等）将不可用。请前往 设置 → 工具依赖 下载安装。",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=7000,
            )
        except Exception as e:
            logger.debug("Chrome 未安装提示显示失败: %s", e)

    def _run_startup_update_check(self):
        """启动时立即执行一次更新检查；有新版本则弹窗后退出应用"""
        try:
            config_center = ServiceLocator().get(ConfigCenter)
            run_async_from_ui(lambda: self._startup_update_check_async(config_center))
        except Exception as e:
            logger.warning("启动更新检查失败: %s", e)
    
    async def _startup_update_check_async(self, config_center: ConfigCenter):
        """异步检查更新；有新版本则在主线程弹窗，关闭对话框后退出应用（强制更新）"""
        try:
            from src.services.update_check_service import check_for_updates
            result = await check_for_updates(force_refresh=False)
            if not result.has_update or not result.remote_version or not result.download_url:
                return
            QTimer.singleShot(0, lambda: self._show_force_update_dialog(result))
        except Exception as e:
            logger.warning("启动更新检查异常: %s", e)

    def _show_force_update_dialog(self, result):
        """强制更新：弹窗提示当前版本已不可用，关闭后退出应用"""
        try:
            from src.ui.utils.fluent_dialogs import show_force_update_confirm

            if show_force_update_confirm(
                self,
                result.current_version,
                result.remote_version or "",
                result.notes or "",
            ):
                QDesktopServices.openUrl(QUrl(result.download_url))
            QApplication.quit()
        except Exception as e:
            logger.warning("显示强制更新对话框失败: %s", e)
            QApplication.quit()
    
    def _force_nav_expand(self):
        """强制展开导航栏 (安全调用)"""
        try:
            if not hasattr(self, 'navigationInterface'):
                return
                
            nav = self.navigationInterface
            
            # 方法1: 使用 expand() (推荐)
            if hasattr(nav, 'expand'):
                # useAni=False 禁用动画，立即展开
                nav.expand(useAni=False)
                logger.debug("已通过 expand() 强制展开导航栏")
                return
            
            # 方法2: 使用 setDisplayMode
            if hasattr(nav, 'setDisplayMode'):
                from qfluentwidgets import NavigationDisplayMode
                nav.setDisplayMode(NavigationDisplayMode.EXPAND)
                logger.debug("已通过 setDisplayMode() 强制展开导航栏")
                
        except Exception as e:
            logger.warning(f"强制展开导航栏失败: {e}")

    def _setup_tray_icon(self):
        """创建系统托盘图标和右键菜单"""
        self._tray_icon = QSystemTrayIcon(self)
        self._tray_icon.setIcon(self.windowIcon())
        self._tray_icon.setToolTip("媒小宝")

        tray_menu = QMenu(self)
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self._tray_show_window)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._tray_quit_app)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        # 托盘图标显示策略：
        # - 关闭行为=tray：始终显示托盘图标（便于随时恢复）
        # - 关闭行为!=tray 但上次选择了“关闭到托盘”（start_in_tray_next_launch=True）：显示托盘图标
        try:
            close_behavior = self._get_window_close_behavior()
        except Exception:
            close_behavior = "ask"

        start_in_tray = self._is_start_in_tray_next_launch_enabled()
        if QSystemTrayIcon.isSystemTrayAvailable() and (
            close_behavior == "tray" or start_in_tray
        ):
            self._tray_icon.show()
        else:
            self._tray_icon.hide()

    def _map_old_close_config_to_new_behavior(self, app_cfg: dict) -> str:
        """把旧配置（minimize_to_tray/close_remind 等）映射到新枚举行为。"""
        # 旧逻辑：
        # - remind 关闭：直接按 minimize_to_tray 决定最小化/退出
        # - remind 开启：
        #   - remember_choice 开启：按 main_window_close_action 直接执行
        #   - remember_choice 关闭：每次都询问
        minimize_to_tray = bool(app_cfg.get("minimize_to_tray", True))
        remind_enabled = bool(app_cfg.get("main_window_close_remind", True))
        if not remind_enabled:
            return "tray" if minimize_to_tray else "exit"

        remember_choice = bool(app_cfg.get("main_window_close_remember_choice", False))
        action = str(app_cfg.get("main_window_close_action", "minimize_to_tray") or "minimize_to_tray")
        if remember_choice:
            return "tray" if action == "minimize_to_tray" else "exit"
        return "ask"

    def _get_window_close_behavior(self) -> str:
        """读取/迁移主窗口关闭行为（三选一：ask/tray/exit）。"""
        from src.infrastructure.common.config.app_config_keys import (
            MAIN_WINDOW_CLOSE_BEHAVIOR,
        )
        from src.infrastructure.common.config.app_config_merge import (
            merge_app_config_top_level_to_disk_sync,
        )

        default_behavior = "ask"
        try:
            config_center = ServiceLocator().get(ConfigCenter)
            app_cfg = config_center.get_app_config()
            if not isinstance(app_cfg, dict):
                return default_behavior

            cur = app_cfg.get(MAIN_WINDOW_CLOSE_BEHAVIOR)
            if cur in {"ask", "tray", "exit"}:
                return str(cur)

            # 仅当缺失新键时做一次性迁移写回（避免反复覆盖用户配置）
            if MAIN_WINDOW_CLOSE_BEHAVIOR not in app_cfg:
                mapped = self._map_old_close_config_to_new_behavior(app_cfg)
                merge_app_config_top_level_to_disk_sync(
                    {MAIN_WINDOW_CLOSE_BEHAVIOR: mapped}
                )
                return mapped

            # 新键存在但非法：降级为 ask（不强行覆盖磁盘）
            logger.warning(
                "main_window_close_behavior 非法值：%r，降级为 ask", cur
            )
            return default_behavior
        except Exception as e:
            logger.warning("读取主窗口关闭行为失败：%s，默认 ask", e)
            return default_behavior

    def set_tray_visible(self, visible: bool):
        """外部调用：切换托盘图标显示状态"""
        if hasattr(self, '_tray_icon'):
            if visible:
                self._tray_icon.show()
            else:
                self._tray_icon.hide()

    def _persist_start_in_tray_next_launch(self, value: bool) -> None:
        """记录「下次冷启动是否直接进托盘」：仅在上次点关闭缩到托盘时为 True；真正退出后应为 False。"""
        try:
            from src.infrastructure.common.config.app_config_keys import START_IN_TRAY_NEXT_LAUNCH
            from src.infrastructure.common.config.app_config_merge import (
                merge_app_config_top_level_to_disk_sync,
            )

            merge_app_config_top_level_to_disk_sync({START_IN_TRAY_NEXT_LAUNCH: bool(value)})
        except Exception as e:
            logger.debug("持久化 start_in_tray_next_launch 失败: %s", e)

    def _is_start_in_tray_next_launch_enabled(self) -> bool:
        """上次会话是否以「关闭到托盘」结束（下次冷启动才隐藏主窗口）。"""
        try:
            from src.infrastructure.common.config.app_config_keys import START_IN_TRAY_NEXT_LAUNCH

            app_cfg = ServiceLocator().get(ConfigCenter).get_app_config()
            return bool(app_cfg.get(START_IN_TRAY_NEXT_LAUNCH, False))
        except Exception:
            return False

    def apply_startup_tray_behavior(self):
        """启动时是否隐藏主窗口（仅当上次为“关闭到托盘”且当前关闭行为仍为 tray）。"""
        try:
            close_behavior = self._get_window_close_behavior()
        except Exception:
            close_behavior = "ask"

        if close_behavior != "tray":
            return

        if not self._is_start_in_tray_next_launch_enabled():
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("当前环境无系统托盘，跳过启动时隐藏主窗口")
            return
        self.hide()

    def bring_to_foreground(self):
        """将主窗口置于桌面最前并聚焦（Windows 上避免仅任务栏高亮、窗口留在其它窗口后面）。"""
        current_state = self.windowState()
        if current_state & Qt.WindowMinimized:
            self.setWindowState(current_state & ~Qt.WindowMinimized | Qt.WindowActive)
        else:
            self.setWindowState(current_state | Qt.WindowActive)
        self.raise_()
        self.activateWindow()
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                if hwnd:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

    def _on_tray_activated(self, reason):
        """托盘图标被激活（双击 = 显示窗口）"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_show_window()

    def _tray_show_window(self):
        """从托盘恢复主窗口"""
        self._persist_start_in_tray_next_launch(False)
        self.showNormal()
        self.bring_to_foreground()

    def _tray_quit_app(self):
        """托盘菜单 → 退出：标记为真正退出，然后 close"""
        self._force_quit = True
        self.close()
        # 冷启动后若主窗口一直处于 hide（仅托盘），关闭时可能不满足「最后一个可见顶层窗口关闭」，
        # Qt 不会走默认的 quit → aboutToQuit，qasync 里 await 退出事件会一直挂起，最终被 5s 守护 os._exit。
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)

    def _read_close_behavior_pref(self) -> tuple[bool, str]:
        """读取主窗口关闭行为偏好：是否记住、动作(close|minimize_to_tray)。"""
        try:
            cfg = ServiceLocator().get(ConfigCenter).get_app_config()
            if not isinstance(cfg, dict):
                logger.debug("_read_close_behavior_pref: cfg is not dict, returning defaults")
                return False, "minimize_to_tray"
            remembered = bool(cfg.get("main_window_close_remember_choice", False))
            action = str(cfg.get("main_window_close_action", "minimize_to_tray") or "minimize_to_tray")
            if action not in {"close", "minimize_to_tray"}:
                action = "minimize_to_tray"
            logger.debug("_read_close_behavior_pref: remembered=%s, action=%s", remembered, action)
            return remembered, action
        except Exception as e:
            logger.warning("_read_close_behavior_pref 异常: %s", e)
            return False, "minimize_to_tray"

    def _save_close_behavior_pref(self, remember: bool, action: str) -> None:
        try:
            from src.infrastructure.common.config.app_config_merge import (
                merge_app_config_top_level_to_disk_sync,
            )
            merge_app_config_top_level_to_disk_sync({
                "main_window_close_remember_choice": bool(remember),
                "main_window_close_action": str(action or "minimize_to_tray"),
            })
        except Exception as e:
            logger.debug("保存主窗口关闭行为偏好失败: %s", e)

    def _ask_close_behavior(self) -> tuple[str | None, bool]:
        """询问用户关闭行为（ask 模式）

        返回:
            (action, remembered)
            - action: "tray" / "exit" / None（None 表示仅关闭弹窗，不做主程序任何操作）
            - remembered: 是否勾选了“记住我的选择”
        """
        from src.ui.components.base_dialog import AppMessageBoxBase
        from src.infrastructure.common.config.app_config_keys import (
            MAIN_WINDOW_CLOSE_BEHAVIOR,
        )

        chosen_action: str | None = None
        remembered: bool = False
        dlg = AppMessageBoxBase(self, header_title="关闭主程序")
        desc = BodyLabel("请选择关闭主程序或最小化到托盘。", dlg)
        # 关闭弹窗正文：禁止自动换行，宽度不够时用省略号
        desc.setWordWrap(False)
        try:
            desc.setTextElideMode(Qt.ElideRight)
        except Exception:
            pass
        desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        dlg.viewLayout.addWidget(desc)

        remember_check = CheckBox("记住我的选择", dlg)
        dlg.viewLayout.addWidget(remember_check)

        dlg.yesButton.setText("最小化到托盘")
        dlg.cancelButton.setText("退出应用")

        def _choose_tray() -> None:
            nonlocal chosen_action, remembered
            chosen_action = "tray"
            remembered = bool(remember_check.isChecked())
            if remembered:
                from src.infrastructure.common.config.app_config_merge import (
                    merge_app_config_top_level_to_disk_sync,
                )

                merge_app_config_top_level_to_disk_sync(
                    {MAIN_WINDOW_CLOSE_BEHAVIOR: "tray"}
                )
            dlg.accept()  # 选择按钮不应被当作“X/取消关闭”

        def _choose_exit() -> None:
            nonlocal chosen_action, remembered
            chosen_action = "exit"
            remembered = bool(remember_check.isChecked())
            if remembered:
                from src.infrastructure.common.config.app_config_merge import (
                    merge_app_config_top_level_to_disk_sync,
                )

                merge_app_config_top_level_to_disk_sync(
                    {MAIN_WINDOW_CLOSE_BEHAVIOR: "exit"}
                )
            dlg.accept()  # 选择按钮不应被当作“X/取消关闭”

        try:
            dlg.yesButton.clicked.connect(_choose_tray)
        except Exception:
            pass
        try:
            dlg.cancelButton.clicked.connect(_choose_exit)
        except Exception:
            pass

        dlg.exec()
        # X/ESC/关闭弹窗会触发 reject，此时 chosen_action 仍为 None
        return chosen_action, remembered

    def _confirm_tray_unavailable_then_exit(self) -> bool:
        """托盘不可用时的兜底提示：点“确定”后退出；否则保持不退出。"""
        from src.ui.components.base_dialog import AppMessageBoxBase

        allow_exit = False
        dlg = AppMessageBoxBase(self, header_title="托盘不可用")
        desc = BodyLabel("当前系统托盘不可用，点击“确定”后将退出应用。", dlg)
        # 关闭弹窗正文：禁止自动换行，宽度不够时用省略号
        desc.setWordWrap(False)
        try:
            desc.setTextElideMode(Qt.ElideRight)
        except Exception:
            pass
        desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        dlg.viewLayout.addWidget(desc)

        dlg.yesButton.setText("确定")
        cancel_btn = getattr(dlg, "cancelButton", None)
        if cancel_btn is not None:
            cancel_btn.setVisible(False)
            cancel_btn.setEnabled(False)

        def _choose_exit() -> None:
            nonlocal allow_exit
            allow_exit = True
            dlg.accept()

        try:
            dlg.yesButton.clicked.connect(_choose_exit)
        except Exception:
            pass

        dlg.exec()
        return allow_exit

    def closeEvent(self, event):
        """主窗口关闭事件"""
        force_quit = getattr(self, "_force_quit", False)

        # 主窗口“关闭事件”分两类：
        # - tray：hide + event.ignore + 记录 start_in_tray_next_launch=True
        # - exit：走原本的清理逻辑，并确保 _force_quit=True 让 Qt/qasync 正常退出
        close_behavior = "exit" if force_quit else self._get_window_close_behavior()
        remembered = False
        if close_behavior == "ask":
            chosen_action, remembered = self._ask_close_behavior()
            if chosen_action is None:
                # 仅关闭弹窗，不做任何主程序操作
                event.ignore()
                return
        elif close_behavior == "tray":
            chosen_action = "tray"
            remembered = True
        else:
            chosen_action = "exit"
            remembered = False

        logger.debug(
            "closeEvent 决策: close_behavior=%s, chosen_action=%s",
            close_behavior,
            chosen_action,
        )

        # chosen_action == "tray"：托盘分支（若托盘不可用则提示后退出）
        if chosen_action == "tray":
            if not QSystemTrayIcon.isSystemTrayAvailable():
                # 按你的要求：选择最小化但托盘不可用 -> 提示并点“确定”后退出
                allow_exit = self._confirm_tray_unavailable_then_exit()
                if not allow_exit:
                    event.ignore()
                    return
                # allow_exit=True：继续走 exit 分支清理并退出
            else:
                try:
                    self.set_tray_visible(True)
                except Exception:
                    pass

                event.ignore()
                # 只有当“托盘行为已记住”或当前设置就是 tray 时，才让下次启动也藏到托盘
                self._persist_start_in_tray_next_launch(remembered)
                self.hide()
                if hasattr(self, "_tray_icon"):
                    self._tray_icon.showMessage(
                        "媒小宝",
                        "程序已最小化到系统托盘，双击图标可恢复窗口。",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )
                return

        # chosen_action == "exit"：真正退出
        self._force_quit = True
        # 下次冷启动显示主界面
        self._persist_start_in_tray_next_launch(False)

        logger.info("主窗口关闭事件触发，开始清理...")

        if hasattr(self, '_tray_icon'):
            self._tray_icon.hide()

        # 0. 取消 EventBus 订阅
        if hasattr(self, 'event_bus') and self.event_bus:
            for event_name, handler in getattr(self, '_event_handlers', []):
                try:
                    self.event_bus.unsubscribe(event_name, handler)
                except Exception as e:
                    logger.debug("取消事件订阅失败 %s: %s", event_name, e)
            self._event_handlers.clear()

        # 1. 清理子页面资源
        if hasattr(self, 'page_factory'):
            for page_name in self.page_factory.get_all_page_names():
                if hasattr(self, page_name):
                    page = getattr(self, page_name)
                    if hasattr(page, 'shutdown'):
                        try:
                            logger.info(f"正在关闭页面资源: {page_name}")
                            page.shutdown()
                        except Exception as e:
                            logger.error(f"关闭页面 {page_name} 失败: {e}")
                            
        # 2. 显式清理 NavigationInterface
        if hasattr(self, 'navigationInterface'):
            try:
                self.navigationInterface.disconnect()
                if hasattr(self, '_cleanup_flow_layouts'):
                    self._cleanup_flow_layouts(self.navigationInterface)
                self.navigationInterface.setParent(None)
                self.navigationInterface.deleteLater()
            except Exception as e:
                logger.debug("关闭导航界面时异常: %s", e)
                
        # 3. 全局清理 FlowLayout (包括主窗口自身)
        if hasattr(self, '_cleanup_flow_layouts'):
            self._cleanup_flow_layouts(self)
        
        # 4. 调用父类关闭事件
        try:
            super().closeEvent(event)
        except (RuntimeError, AttributeError):
            event.accept()
        except Exception as e:
            logger.debug("closeEvent 父类调用异常: %s", e)
            event.accept()

        # 5. [加固] 线程级强制退出守护（使用 threading.Timer 而非 QTimer）
        #    QTimer 依赖 Qt 事件循环，但此时 Qt 事件循环即将停止，QTimer 回调永远不会触发。
        #    threading.Timer 运行在独立线程，不受 Qt/asyncio 事件循环状态影响。
        import threading
        _exit_guard_sec = 5.0
        logger.info("已启动退出守护计时器 (%.1fs)...", _exit_guard_sec)
        def _force_exit_guard():
            try:
                logger.warning("!!! 优雅退出超时 (%.1fs)，执行强制终止 !!!", _exit_guard_sec)
            except Exception:
                pass
            os._exit(0)
        _guard = threading.Timer(_exit_guard_sec, _force_exit_guard)
        _guard.daemon = True
        _guard.start()
    
    def _setup_status_bar(self):
        """设置状态栏"""
        if hasattr(self, 'statusBar') and callable(self.statusBar) and self.statusBar():
            try:
                from .components.status_bar import CustomStatusBar
                self.custom_status_bar = CustomStatusBar(self)
                # 手动定位
                self.custom_status_bar.resize(self.width(), 32)
                self.custom_status_bar.move(0, self.height() - 32)
                self.custom_status_bar.show()
                self.custom_status_bar.raise_()
            except Exception as e:
                logger.error(f"自定义状态栏加载失败: {e}", exc_info=True)
                self.statusBar().showMessage("系统就绪")
        elif FLUENT_WIDGETS_AVAILABLE:
            pass
        else:
            logger.info("当前窗口不支持状态栏，跳过设置")
    
    def _setup_ui(self) -> None:
        """设置UI"""
        self.setWindowTitle("媒小宝-吾爱破解论坛特别版" if FeatureFlags.is_52pojie() else "媒小宝")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 768)
        
        # 将窗口居中显示
        from PySide6.QtGui import QScreen
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            window_geometry = self.frameGeometry()
            center_point = screen_geometry.center()
            window_geometry.moveCenter(center_point)
            self.move(window_geometry.topLeft())

        # 全局浅色/深色由 main.py 中 ThemeManager（get_theme_manager）统一 setTheme，此处勿再覆盖，否则会忽略用户持久化的主题模式。
        # 页面切换动画优化见 _optimize_page_transitions()。

    def _jump_to_feature(self, target_page_name: str):
        """抢占式跳转：点击父级菜单时，直接更新导航栏选中态并切换页面"""
        try:
            # 1. 立即切换页面 (视觉响应优先)
            self.navigate_to(target_page_name)
            
            # 2. 异步展开对应的父级菜单 (避免卡顿)
            # 查找该页面所属的父级容器
            child_to_parent = NavigationConfig.get_child_to_parent_mapping()
            parent_key = child_to_parent.get(target_page_name)
            
            if parent_key:
                QTimer.singleShot(50, lambda: self._expand_nav_item(parent_key))
                
        except Exception as e:
            logger.error(f"跳转失败: {e}")

    def _expand_nav_item(self, object_name: str):
        """展开指定的导航项"""
        item = self._nav_items.get(object_name)
        if item and hasattr(item, 'setExpanded'):
             # 仅当未展开时才展开
            is_expanded = item.isExpanded
            if callable(is_expanded):
                is_expanded = is_expanded()
            
            if not is_expanded:
                item.setExpanded(True, ani=True)

    def _setup_navigation(self) -> None:
        """设置导航栏"""
        # 关闭亚克力效果，可能会导致背景色差
        if hasattr(self.navigationInterface, 'setAcrylicEnabled'):
            self.navigationInterface.setAcrylicEnabled(False)
            logger.debug("已关闭导航栏亚克力效果以修复背景问题")
        
        # 启用手风琴模式 (Accordion)
        if hasattr(self.navigationInterface, 'setCollapsible'):
            self.navigationInterface.setCollapsible(True)
            logger.debug("已启用导航栏可折叠模式")
        
        # 启用返回顶部 (如果支持)
        if hasattr(self.navigationInterface, 'setReturnToStartPos'):
            self.navigationInterface.setReturnToStartPos(True)
            
        # 彻底移除蓝色选中指示器 - 三层攻击
        self._remove_indicators()

        # ---------------------------------------------------------------------
        # 1. 核心页面 (立即加载)
        # ---------------------------------------------------------------------
        self.workspace_page = self.page_factory.create_page("workspace_page", self)
        if not self.workspace_page:
            # 打包环境下若动态导入的页面未被包含，会导致 workspace_page 为 None；
            # 这里给出明确错误并中止启动，避免双击“无反应”。
            err = "工作台页面加载失败：无法导入 src.ui.pages.workspace_page.WorkspacePage"
            logger.critical(err)
            try:
                from src.ui.utils.fluent_dialogs import show_error
                show_error(self, "启动失败", err)
            except Exception:
                pass
            raise SystemExit(1)
        self.workspace_page.setObjectName("workspace_page")
        
        # ---------------------------------------------------------------------
        # 2. 构建导航菜单 (Dynamic Navigation Construction)
        # ---------------------------------------------------------------------
        
        # 存储导航项以便后续控制
        self._nav_items = {}
        
        # 52POJIE 特别版不含云端账号体系，隐藏个人中心
        subscription_visible = SUBSCRIPTION_PAGE_AVAILABLE and not FeatureFlags.is_52pojie()

        nav_items_config = NavigationConfig.get_items(
            batch_feature=BATCH_FEATURE_AVAILABLE,
            data_center=DATA_CENTER_AVAILABLE,
            interaction=INTERACTION_FEATURE_AVAILABLE,
            subscription=subscription_visible,
            material_library=MATERIAL_LIBRARY_AVAILABLE,
            commerce_promotion=COMMERCE_PROMOTION_AVAILABLE,
        )
        
        # 递归添加导航项
        for item_conf in nav_items_config:
            self._add_nav_item(item_conf)

        self._setup_nav_width()
        self._setup_accordion_behavior()  # 设置手风琴效果
        self._disable_all_indicators()  # 确保所有导航项指示器被禁用
        self._optimize_page_transitions()  # 优化页面切换动画
        logger.debug("导航栏设置完成 (Config Driven)")

    def _remove_indicators(self):
        """移除导航栏指示器"""
        try:
            panel = getattr(self.navigationInterface, 'panel', None)
            if panel:
                # 1. 直接隐藏指示器 QWidget
                if hasattr(panel, 'indicator') and panel.indicator:
                    panel.indicator.hide()
                    panel.indicator.setMaximumSize(0, 0)
                
                # 2. 禁用指示器动画功能
                if hasattr(panel, 'setIndicatorAnimationEnabled'):
                    panel.setIndicatorAnimationEnabled(False)
                
                # 3. 遍历所有导航项，设置指示器颜色为透明
                from PySide6.QtWidgets import QWidget
                from PySide6.QtGui import QColor
                for item in panel.findChildren(QWidget):
                    if hasattr(item, 'setIndicatorColor'):
                        item.setIndicatorColor(QColor(0, 0, 0, 0), QColor(0, 0, 0, 0))
        except Exception as e:
            logger.warning(f"移除指示器失败: {e}")

    def _add_nav_item(self, conf: dict, parent_key: str = None):
        """递归添加导航项"""
        route_key = conf.get("route_key")
        text = conf.get("text")
        icon = conf.get("icon")
        if not route_key or not text or icon is None:
            logger.warning("导航项配置缺少必填项 route_key/text/icon，已跳过: %s", conf)
            return
        position = conf.get("position", NavigationItemPosition.TOP)
        selectable = conf.get("selectable", True)
        
        # 决定 onClick
        on_click = None
        if selectable and "children" not in conf: 
             on_click = lambda: self.navigate_to(route_key)
        elif "onClick" in conf:
             on_click = conf["onClick"]
        # [Fix] 即使不可选中，如果是父级容器，也需要响应点击以支持手风琴
        elif not selectable and "children" in conf:
            # 这里先给一个空 lambda，后续在 _setup_accordion_behavior 中会覆盖
            # 但 Fluent 可能会因为 selectable=False 而忽略点击，所以我们尝试强制允许点击但不选中
            pass

        # 添加 Item
        item_widget = None
        
        # 注意 workspace 是 addSubInterface，比较特殊
        if route_key == "workspace_page":
             # workspace_page 已经在前面实例化了
             item_widget = self.addSubInterface(
                 self.workspace_page, icon, text, position
             )
        else:
             item_widget = self.navigationInterface.addItem(
                 routeKey=route_key,
                 icon=icon,
                 text=text,
                 onClick=on_click,
                 selectable=selectable,
                 parentRouteKey=parent_key,
                 position=position
             )
        
        if item_widget:
            self._nav_items[route_key] = item_widget
            
            # 设置默认展开
            if conf.get("expanded", False) and hasattr(item_widget, 'setExpanded'):
                item_widget.setExpanded(True)

        # 处理子级
        if "children" in conf:
            for child in conf["children"]:
                self._add_nav_item(child, parent_key=route_key)
    
    def _setup_accordion_behavior(self):
        """手风琴导航：接管 itemWidget.itemClicked，即时展开/收起 + 子项 opacity 渐入。"""
        from qfluentwidgets.components.navigation import NavigationTreeWidget

        self._parent_containers = NavigationConfig.get_accordion_mapping()

        for container_key, first_child_key in self._parent_containers.items():
            container = self._nav_items.get(container_key)
            if not (container and isinstance(container, NavigationTreeWidget)):
                continue

            try:
                container.itemWidget.itemClicked.disconnect(container._onClicked)
            except Exception:
                pass

            container.itemWidget.itemClicked.connect(
                lambda tv, ca, ck=container_key, fk=first_child_key, c=container:
                    self._on_item_clicked(c, ck, fk, tv, ca)
            )

        logger.debug("手风琴导航行为已设置")

    def _on_item_clicked(self, container, container_key: str, first_child_key: str,
                         triggerByUser: bool, clickArrow: bool):
        """手风琴核心处理器。

        布局操作全部即时完成（setExpanded(ani=False)），零动画零延迟零冲突。
        展开后对子项做 opacity 渐入（不影响布局），提供优雅的视觉反馈。
        """
        from qfluentwidgets.components.navigation import NavigationTreeWidget

        try:
            if container.isCompacted:
                container.clicked.emit(triggerByUser)
                return

            if not container.isExpanded:
                # 1. 即时收起所有其他展开的容器
                for key in self._parent_containers:
                    if key != container_key:
                        other = self._nav_items.get(key)
                        if (other and isinstance(other, NavigationTreeWidget)
                                and other.isExpanded):
                            other.expandAni.stop()
                            other.setExpanded(False, ani=False)

                # 2. 即时展开目标容器
                container.expandAni.stop()
                container.setExpanded(True, ani=False)

                # 3. 子项 opacity 渐入（纯视觉，不影响布局）
                self._fade_in_children(container)

                # 4. 切页
                self._smooth_navigate(first_child_key)

            else:
                self._smooth_navigate(first_child_key)

            # clicked.emit 可能把选中态设到父容器（publish_container 是 selectable=True）
            container.clicked.emit(triggerByUser)
            # 在 emit 之后强制把选中态设到第一个子项，覆盖父级选中
            self.navigationInterface.setCurrentItem(first_child_key)

        except Exception as e:
            logger.warning(f"手风琴点击处理失败: {e}")

    def _fade_in_children(self, container):
        """子菜单项逐项依次渐入（stagger fade-in），不影响布局。"""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        from PySide6.QtCore import QPropertyAnimation, QEasingCurve

        DURATION = 200
        STAGGER = 45

        for i, child in enumerate(container.treeChildren):
            old_ani = getattr(child, '_fade_ani', None)
            if old_ani is not None:
                old_ani.stop()
                child.setGraphicsEffect(None)

            effect = QGraphicsOpacityEffect(child)
            effect.setOpacity(0.0)
            child.setGraphicsEffect(effect)

            ani = QPropertyAnimation(effect, b"opacity", child)
            ani.setDuration(DURATION)
            ani.setStartValue(0.0)
            ani.setEndValue(1.0)
            ani.setEasingCurve(QEasingCurve.OutQuad)
            ani.finished.connect(lambda c=child: c.setGraphicsEffect(None))
            child._fade_ani = ani

            if i == 0:
                ani.start()
            else:
                QTimer.singleShot(i * STAGGER, ani.start)
    
    def _refresh_publish_records_after_navigate(self, page_name: str, page) -> None:
        """进入「待发布 / 已发布 / 任务回收站」页后立即拉库。

        懒加载页首次 showEvent 时表格可能尚未创建，仅靠 showEvent 可能无法拉库；
        switchTo 后补一次加载，避免首屏为空。
        """
        if page is None:
            return
        if page_name in ("publish_records_page", "publish_list_page"):
            loader = getattr(page, "_load_publish_records", None)
            if callable(loader):
                loader()
        elif page_name == "publish_recycle_bin_page":
            loader = getattr(page, "_load_deleted_records", None)
            if callable(loader):
                loader()

    def _deferred_publish_records_load(self, interface) -> None:
        """切页后再拉发布相关表格，避免与堆栈切换同一帧抢 UI 线程。"""
        if interface is None:
            return
        self._refresh_publish_records_after_navigate(interface.objectName() or "", interface)

    def _smooth_navigate(self, page_name: str):
        """导航到页面；轻量位移动画切页，兼顾响应速度与过渡连贯感。"""
        try:
            from src.ui.page_animation_prefs import get_stack_transition_duration_ms

            page = self._get_or_create_page(page_name)
            if page:
                if hasattr(self, 'stackedWidget') and hasattr(self.stackedWidget, 'view'):
                    from PySide6.QtCore import QEasingCurve
                    self.stackedWidget.view.setCurrentWidget(
                        page,
                        False,
                        True,
                        get_stack_transition_duration_ms(),
                        QEasingCurve.OutCubic,
                    )
                else:
                    self.switchTo(page)
                # 高亮由 FluentWindowBase._onCurrentInterfaceChanged 统一处理

                QTimer.singleShot(
                    0, lambda p=page_name, pg=page: self._refresh_publish_records_after_navigate(p, pg)
                )

                logger.debug(f"平滑导航到: {page_name}")
        except Exception as e:
            logger.warning(f"平滑导航失败: {e}")
    
    def _setup_nav_width(self):
        """设置导航栏宽度"""
        try:
            if hasattr(self, 'navigationInterface'):
                nav = self.navigationInterface
                # 设置展开宽度
                if hasattr(nav, 'setExpandWidth'):
                    nav.setExpandWidth(200)
                    logger.debug("导航栏展开宽度已设置为 200px")
                # 设置默认展开模式
                if hasattr(nav, 'displayMode'):
                    nav.setDisplayMode(NavigationDisplayMode.EXPAND)
                    logger.debug("导航栏已设置为默认展开模式")
                
                # 连接显示模式变更信号
                if hasattr(nav, 'displayModeChanged'):
                    nav.displayModeChanged.connect(self._on_display_mode_changed)
                    logger.debug("已连接导航栏模式变更信号")
                    
        except Exception as e:
            logger.warning(f"设置导航栏宽度及模式失败: {e}")

    def _on_display_mode_changed(self, mode):
        """处理导航栏显示模式变更：收起时折叠所有手风琴菜单。"""
        from qfluentwidgets import NavigationDisplayMode
        from qfluentwidgets.components.navigation import NavigationTreeWidget

        try:
            if mode in (NavigationDisplayMode.MINIMAL, NavigationDisplayMode.COMPACT):
                if hasattr(self, '_parent_containers'):
                    for container_key in self._parent_containers:
                        container = self._nav_items.get(container_key)
                        if (container and isinstance(container, NavigationTreeWidget)
                                and container.isExpanded):
                            container.setExpanded(False, ani=False)
                    logger.debug("导航栏收起，已折叠所有手风琴菜单")

            if hasattr(self, 'navigationInterface'):
                self.navigationInterface.update()
                panel = getattr(self.navigationInterface, 'panel', None)
                if panel:
                    panel.update()

            logger.debug(f"导航栏显示模式已变更: {mode}")
        except Exception as e:
            logger.warning(f"处理导航栏模式变更失败: {e}")
    
    _PAGE_TRANSITION_DY = 24

    def _optimize_page_transitions(self):
        """主内容区切换：轻量位移 + 淡入动画，兼顾响应速度与过渡连贯感。"""
        try:
            if not hasattr(self, "stackedWidget"):
                return
            sw = self.stackedWidget
            if not hasattr(sw, "view"):
                return
            view = sw.view
            view.setAnimationEnabled(True)
            if hasattr(view, "aniInfos"):
                for info in view.aniInfos:
                    info.deltaY = self._PAGE_TRANSITION_DY
                    info.deltaX = 0
            from src.ui.page_animation_prefs import get_stack_transition_duration_ms

            _ms = get_stack_transition_duration_ms()
            logger.debug(
                "已启用页面过渡动画（%dms / deltaY=%dpx）",
                _ms,
                self._PAGE_TRANSITION_DY,
            )
        except Exception as e:
            logger.warning(f"优化页面切换动画失败: {e}")

    def switchTo(self, interface, popOut=False):
        """切换堆栈页面；拉库延后一帧先完成切页绘制。"""
        from PySide6.QtWidgets import QAbstractScrollArea
        from src.ui.page_animation_prefs import get_stack_transition_duration_ms

        if hasattr(self, 'stackedWidget'):
            if isinstance(interface, QAbstractScrollArea):
                interface.verticalScrollBar().setValue(0)

            if hasattr(self.stackedWidget, 'view'):
                from PySide6.QtCore import QEasingCurve
                self.stackedWidget.view.setCurrentWidget(
                    interface,
                    popOut,
                    True,
                    get_stack_transition_duration_ms(),
                    QEasingCurve.OutCubic,
                )
            else:
                self.stackedWidget.setCurrentWidget(interface, popOut)
        else:
            super().switchTo(interface, popOut)

        if interface is not None:
            QTimer.singleShot(0, lambda w=interface: self._deferred_publish_records_load(w))

    def _disable_all_indicators(self):
        """禁用所有导航项的蓝色选中指示器。

        不再在 paintEvent 外包一层 QPainter 画选中底纹：子菜单渐入等场景会给导航项挂
        QGraphicsOpacityEffect，与「先自绘再调原始 paintEvent」易触发同一控件上嵌套
        QPainter / QWidgetEffectSourcePrivate::pixmap 冲突（终端里 recursive repaint）。
        选中态仍由 qfluentwidgets 自带圆角底纹 + 指示器透明体现。
        """
        try:
            from PySide6.QtWidgets import QWidget
            from PySide6.QtGui import QColor

            panel = getattr(self.navigationInterface, 'panel', None)
            if not panel:
                logger.warning("未找到 navigationInterface.panel")
                return

            if hasattr(panel, 'indicator') and panel.indicator:
                panel.indicator.hide()
                panel.indicator.setMaximumSize(0, 0)

            transparent = QColor(0, 0, 0, 0)

            for item in panel.findChildren(QWidget):
                if hasattr(item, 'setIndicatorColor'):
                    item.setIndicatorColor(transparent, transparent)

                if hasattr(item, 'itemWidget') and hasattr(item.itemWidget, 'setIndicatorColor'):
                    item.itemWidget.setIndicatorColor(transparent, transparent)

            logger.debug("所有导航项指示器已禁用（导航设置完成后）")
        except Exception as e:
            logger.warning(f"禁用导航指示器失败: {e}")

    def navigate_to(self, page_name: str):
        """导航到指定页面 (支持 Lazy Loading)
        
        Args:
            page_name: 页面名称 (routeKey)
        """
        try:
            # 1. 尝试获取或创建页面
            page = self._get_or_create_page(page_name)
            
            if page:
                self.switchTo(page)
                # 导航高亮由 FluentWindowBase._onCurrentInterfaceChanged 统一处理
                logger.debug(f"已导航到页面: {page_name}")
            else:
                logger.warning(f"无法导航，页面不存在: {page_name}")
        except Exception as e:
            logger.error(f"导航到页面失败 {page_name}: {e}", exc_info=True)

    def _init_event_subscriptions(self):
        """初始化全局事件订阅（只执行一次）"""
        if getattr(self, '_event_subscriptions_initialized', False):
            return
        self._event_subscriptions_initialized = True
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.infrastructure.common.event.event_bus import EventBus
            from src.infrastructure.common.event.events import GlobalToastEvent
            
            service_locator = ServiceLocator()
            if service_locator.is_registered(EventBus):
                event_bus = service_locator.get(EventBus)
                
                event_bus.subscribe(
                    GlobalToastEvent.__name__, 
                    self._on_global_toast,
                    priority=0
                )
                self._event_handlers.append(
                    (GlobalToastEvent.__name__, self._on_global_toast)
                )
                logger.debug("全局事件订阅成功")
        except Exception as e:
            logger.error(f"初始化事件订阅失败: {e}")

    def _on_global_toast(self, event):
        """处理全局 Toast 通知"""
        # 确保在主线程执行 UI 操作
        # 如果是异步回调，qasync 会自动处理，但 InfoBar 最好在主线程
        from qfluentwidgets import InfoBar, InfoBarPosition
        
        title = getattr(event, 'title', '通知')
        content = getattr(event, 'content', '')
        toast_type = getattr(event, 'toast_type', 'info')
        
        if toast_type == 'success':
            InfoBar.success(title=title, content=content, parent=self, position=InfoBarPosition.TOP, duration=3000)
        elif toast_type == 'warning':
            InfoBar.warning(title=title, content=content, parent=self, position=InfoBarPosition.TOP, duration=3000)
        elif toast_type == 'error':
            InfoBar.error(title=title, content=content, parent=self, position=InfoBarPosition.TOP, duration=5000)
        else:
            InfoBar.info(title=title, content=content, parent=self, position=InfoBarPosition.TOP, duration=3000)

    @qasync.asyncSlot()
    async def _warmup_browser_service(self):
        """浏览器服务预热（仅当 ENABLE_BROWSER_WARMUP_ON_START=1 时在启动后 3 秒调用；内部走 ensure_warmup 仅执行一次）"""
        try:
            from src.utils.startup_profiler import mark, log_summary
            mark("warmup_start")
        except Exception:
            pass
        try:
            from src.infrastructure.browser.browser_manager import UndetectedBrowserManager
            await UndetectedBrowserManager.ensure_warmup()
            try:
                from src.utils.startup_profiler import mark, log_summary
                mark("warmup_done")
                log_summary()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Browser warmup failed: {e}")


    
    def _cleanup_flow_layouts(self, widget):
        """递归清理 widget 中的 FlowLayout 事件过滤器"""
        try:
            from qfluentwidgets.components.layout import FlowLayout
            from PySide6.QtWidgets import QWidget
            
            # 检查 widget 的 layout
            layout = widget.layout()
            if layout is not None:
                if isinstance(layout, FlowLayout):
                    # 清除 FlowLayout 的 items 列表以避免访问已删除对象
                    try:
                        if hasattr(layout, '_items'):
                            for item in layout._items:
                                try:
                                    if item and item.widget():
                                        item.widget().removeEventFilter(layout)
                                except RuntimeError:
                                    pass
                            layout._items.clear()
                    except (RuntimeError, AttributeError):
                        pass
            
            # 递归处理子组件
            for child in widget.findChildren(QWidget):
                try:
                    child_layout = child.layout()
                    if child_layout is not None:
                        if isinstance(child_layout, FlowLayout) and hasattr(child_layout, '_items'):
                            child_layout._items.clear()
                except RuntimeError:
                    pass
                    
        except Exception as e:
            logger.debug("_cleanup_flow_layouts 异常: %s", e)

    def resizeEvent(self, event):
        """窗口大小改变事件"""
        super().resizeEvent(event)
        if hasattr(self, 'custom_status_bar') and self.custom_status_bar:
            self.custom_status_bar.resize(self.width(), 32)
            self.custom_status_bar.move(0, self.height() - 32)
            self.custom_status_bar.raise_()
