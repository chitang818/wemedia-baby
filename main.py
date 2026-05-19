"""
主程序入口
文件路径：main.py
功能：应用程序入口，初始化所有服务并启动主窗口
"""

import sys
import os
import logging
import ctypes

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _fatal_crash_log_file():
    """应急崩溃日志路径，与 PathManager 一致（与 qasync_app.log、error.log 同目录）。"""
    from pathlib import Path
    from src.infrastructure.common.path_manager import PathManager

    return PathManager.get_log_dir() / "fatal_crash.log"


# 打包后从快捷方式/桌面双击启动时，工作目录可能不是 exe 所在目录，导致 Qt 等找不到插件而静默退出
if getattr(sys, "frozen", False):
    try:
        app_dir = os.path.dirname(os.path.abspath(sys.executable))
        if app_dir and os.path.isdir(app_dir):
            os.chdir(app_dir)
    except Exception:
        pass

# 抑制 WebEngine 相关的系统级警告
# DirectComposition 错误是 Chromium 在 Windows 上的已知问题，不影响功能
os.environ.setdefault('QT_LOGGING_RULES', 'qt.webenginecontext.info=false;qt.webenginecontext.debug=false')
# 抑制 Chromium 的 DirectComposition 相关错误输出
os.environ.setdefault('QT_QPA_PLATFORM_PLUGIN_PATH', '')
# 禁用 Chromium 的日志输出
os.environ.setdefault('QTWEBENGINE_DISABLE_SANDBOX', '0')
# 设置 Chromium 日志级别为 FATAL（只显示致命错误）
os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-logging --log-level=3')

# 退出守护：若正常 sys.exit 未在此时限内完成，则强制 os._exit（秒）
EXIT_WATCHDOG_SECONDS = 3

# ============================================================================
# 防止 console=False 打包模式下因为 print 或向 sys.stdout 输出导致的闪退
# ============================================================================
class DummyStream:
    def write(self, data): pass
    def flush(self): pass
    def fileno(self):
        import io
        raise io.UnsupportedOperation("fileno")
    @property
    def closed(self):
        return False

if sys.stdout is None:
    sys.stdout = DummyStream()
if sys.stderr is None:
    sys.stderr = DummyStream()

# ============================================================================
# 全局异常钩子：静默处理 qfluentwidgets 的已知问题
# ============================================================================
# qfluentwidgets 的 FlowLayout 在窗口关闭时会触发 RuntimeError，
# 这是因为其 eventFilter 尝试访问已被 C++ 层删除的 QWidgetItem 对象。
# 这是库的已知问题，不影响应用功能，使用全局钩子静默处理。
_original_excepthook = sys.excepthook

def _custom_excepthook(exc_type, exc_value, exc_tb):
    """自定义异常钩子，静默处理 qfluentwidgets / asyncio 退出时的已知无害异常"""
    # asyncio 退出时常见：取消、事件循环已关闭等
    if exc_type is RuntimeError:
        msg = str(exc_value)
        if any(p in msg for p in (
            'Event loop is closed',
            'Event loop stopped',
            'no running event loop',
        )):
            return
    if exc_type is RuntimeError:
        error_msg = str(exc_value)
        if any(pattern in error_msg for pattern in [
            'QWidgetItem',
            'already deleted',
            'eventFilter',
            'Python override of QObject::eventFilter',
            'Python override of QLayout::eventFilter',
            'wrapped C/C++ object',  # PySide6 对象已删除（原 exception_hook 处理的场景）
        ]):
            return
    if getattr(exc_type, '__name__', '') == 'CancelledError':
        return

    # 针对未被屏蔽的严重错误，记录到独立日志并尝试弹窗
    try:
        import traceback
        import datetime

        crash_file = _fatal_crash_log_file()
        time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        with open(crash_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{time_str}] FATAL CRASH:\n{err_msg}\n")
            
        # 尝试弹框警告用户（如果 QApplication 已初始化）；优先 Fluent，失败再 QMessageBox 兜底
        from PySide6.QtWidgets import QApplication, QMessageBox
        app_inst = QApplication.instance()
        if app_inst:
            dlg_parent = app_inst.activeModalWidget() or app_inst.focusWidget()
            body = (
                f"发生未捕获的严重异常，程序可能不稳定或即将退出。\n\n"
                f"详情已记录到:\n{crash_file}\n\n错误信息:\n{str(exc_value)}"
            )
            try:
                from src.ui.utils.fluent_dialogs import show_error
                show_error(dlg_parent, "应用发生严重错误", body)
            except Exception:
                QMessageBox.critical(
                    dlg_parent,
                    "应用发生严重错误",
                    body,
                )
    except Exception as e:
        logging.getLogger("main").exception("写入崩溃日志或弹窗时发生异常: %s", e)

    _original_excepthook(exc_type, exc_value, exc_tb)

sys.excepthook = _custom_excepthook


# ============================================================================
# Windows 结构化异常（SEH）捕获：捕获 Qt/Chromium 导致的底层崩溃（段错误等）
# 这类崩溃不经过 Python 异常机制，普通 excepthook 无法捕获
# ============================================================================
def _install_windows_crash_handler():
    """安装 Windows 未处理异常过滤器，记录底层崩溃（如跨线程 Qt 调用、内存错误等）"""
    try:
        import ctypes
        import datetime
        import threading

        EXCEPTION_EXECUTE_HANDLER = 1

        # SetUnhandledExceptionFilter 原型
        SetUnhandledExceptionFilter = ctypes.windll.kernel32.SetUnhandledExceptionFilter
        SetUnhandledExceptionFilter.restype = ctypes.c_void_p

        # ExceptionRecord 中的 ExceptionCode 偏移为 0（第一个字段）
        EXCEPTION_CODES = {
            0xC0000005: "ACCESS_VIOLATION（非法内存访问，常见于跨线程 Qt UI 操作）",
            0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
            0xC00000FD: "STACK_OVERFLOW",
            0xC0000017: "NO_MEMORY",
            0x80000003: "BREAKPOINT",
            0xC0000409: "STACK_BUFFER_OVERRUN",
        }

        @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
        def _seh_handler(exception_pointers):
            try:
                # 读取异常码（ExceptionPointers->ExceptionRecord->ExceptionCode）
                exc_record_ptr = ctypes.cast(exception_pointers, ctypes.POINTER(ctypes.c_void_p))[0]
                exc_code = ctypes.cast(exc_record_ptr, ctypes.POINTER(ctypes.c_uint32))[0]
                code_desc = EXCEPTION_CODES.get(exc_code, f"未知异常码 0x{exc_code:08X}")

                crash_file = _fatal_crash_log_file()
                time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                thread_name = threading.current_thread().name

                mem_info = ""
                try:
                    import psutil, os
                    proc = psutil.Process(os.getpid())
                    mem_mb = proc.memory_info().rss / 1024 / 1024
                    mem_info = f"  内存使用: {mem_mb:.1f} MB\n"
                except Exception:
                    pass

                msg = (
                    f"\n[{time_str}] WINDOWS SEH CRASH:\n"
                    f"  异常码: 0x{exc_code:08X} - {code_desc}\n"
                    f"  当前线程: {thread_name}\n"
                    f"{mem_info}"
                    f"  提示: 此类崩溃通常由在非UI线程直接操作Qt控件引起\n"
                )
                with open(crash_file, "a", encoding="utf-8") as f:
                    f.write(msg)
            except Exception:
                pass
            # 返回 0 表示继续默认处理（让进程崩溃，不吞掉崩溃）
            return 0

        # 保存引用防止被 GC
        _install_windows_crash_handler._handler_ref = _seh_handler
        SetUnhandledExceptionFilter(_seh_handler)
    except Exception:
        pass


def _patch_qframelesswindow():
    """修复 qframelesswindow 在显示器句柄无效时调用 GetMonitorInfo 导致的底层崩溃"""
    try:
        import pywintypes
        import qframelesswindow.utils.win32_utils as win32_utils

        original_isFullScreen = win32_utils.isFullScreen

        def safe_isFullScreen(hWnd):
            try:
                return original_isFullScreen(hWnd)
            except pywintypes.error:
                # 捕获 (1461, 'GetMonitorInfo', '无效监视器句柄。')
                return False

        win32_utils.isFullScreen = safe_isFullScreen
    except Exception:
        pass


if sys.platform == "win32":
    _install_windows_crash_handler()
    _patch_qframelesswindow()


class StderrFilter:
    """stderr 过滤器，过滤掉已知的无害错误信息（Qt/qfluentwidgets 关闭、asyncio 退出等）"""
    
    # 一旦出现这些行，则开始过滤后续多行（直到空行或明显非错误行）
    _block_start_patterns = (
        'Exception ignored in atexit callback',
        'Task was destroyed but it is pending',
        'Task exception was never retrieved',
        'Future exception was never retrieved',
        'coroutine was never awaited',
        'RuntimeWarning: coroutine ',
        'Event loop stopped before Future completed',
        'Event loop is closed',
    )

    def __init__(self, original_stderr):
        self.original_stderr = original_stderr
        self.filtered_patterns = [
            # DirectComposition 相关错误
            'direct_composition_support.cc',
            'QueryInterface to IDCompositionDevice4 failed',
            '涓嶆敮鎸佹鎺ュ彛',  # 乱码版本的错误信息
            'ERROR:direct_composition',
            # qfluentwidgets 在 atexit 回调期间的已知问题
            'Exception ignored in atexit callback',
            '__moduleShutdown',
            'QWidgetItem',
            'already deleted',
            'eventFilter',
            'flow_layout.py',
            'style_sheet.py',
            'scroll_bar.py',
            'tool_tip.py',
            'Python override of QObject::eventFilter',
            'Python override of QLayout::eventFilter',
            'Python override of QWidget::eventFilter',
            'Internal C++ object',
            # Traceback lines frequent in qfluentwidgets exit errors
            'if e.type() != QEvent.DynamicPropertyChange:',
            'if e.type() != QEvent.Type.Paint',
            'dirty-qss',
            'if obj is self.parent():',
            'if obj in [w.widget() for w in self._items]',
            'wrapped C/C++ object has been deleted',
            'RuntimeError: wrapped C/C++ object has been deleted',
            'if e.type() == QEvent.ToolTip:',
            'if e.type() == QEvent.Type.Wheel:',
            'if obj is not self.parent():',
            # asyncio/qasync 退出时的无害报错
            'Task was destroyed but it is pending',
            'Task exception was never retrieved',
            'Future exception was never retrieved',
            'coroutine was never awaited',
            'Event loop stopped before Future completed',
            'Event loop is closed',
            'asyncio.exceptions.CancelledError',
            'qasync',
            # Qt 退出时线程存储清理
            'QThreadStorage:',
            'destroyed before end of thread',
            'Enable tracemalloc to get the object allocation traceback',
        ]
        self._filtering_block = False

    def write(self, text):
        """过滤掉包含特定模式的行，并对多行错误块整体过滤"""
        if not text or not self.original_stderr:
            return
        # 检测多行错误块的开始（整块后续都过滤）
        if any(p in text for p in self._block_start_patterns):
            self._filtering_block = True
            return
        # 正在过滤块：Traceback/File/空行/缩进行 视为同一块继续过滤
        if self._filtering_block:
            is_traceback_line = (
                text.startswith(' ') or text.startswith('\t') or
                text.startswith('File ') or text.startswith('Traceback ') or
                text.strip().startswith('File ') or
                'Traceback (most recent' in text or '  File "' in text
            )
            if text.strip() == '' and not is_traceback_line:
                self._filtering_block = False
            elif is_traceback_line or any(p in text for p in self.filtered_patterns):
                return
            else:
                self._filtering_block = False
        should_filter = any(pattern in text for pattern in self.filtered_patterns)
        if not should_filter:
            try:
                self.original_stderr.write(text)
            except Exception:
                pass
    
    def flush(self):
        if self.original_stderr:
            try:
                self.original_stderr.flush()
            except Exception:
                pass
    
    def __getattr__(self, name):
        # 转发其他属性到原始 stderr
        return getattr(self.original_stderr, name)

# ============================================================================
# 安装 stderr 过滤器（必须在所有其他导入之前）
# ============================================================================
sys.stderr = StderrFilter(sys.stderr)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

# 仅保留启动最早需要的轻量模块，其余在 initialize_services_async 内按需导入以加快首屏
from src.infrastructure.common.path_manager import PathManager
from src.infrastructure.monitoring.log_setup import init_log_manager


async def initialize_services_async() -> bool:
    """初始化所有服务（异步版本，新架构）
    
    Returns:
        如果初始化成功返回True，否则返回False
    """
    try:
        from src.utils.startup_profiler import mark
        mark("init_start")
        # 按需导入重型模块，避免启动时一次性加载
        from src.infrastructure.common.di.service_locator import ServiceLocator, Scope
        from src.infrastructure.common.event.event_bus import EventBus
        from src.infrastructure.common.cache.cache_manager import CacheManager
        from src.infrastructure.common.config.config_center import ConfigCenter
        from src.infrastructure.common.security.rbac import RBAC
        from src.infrastructure.common.security.encryption import EncryptionManager
        from src.infrastructure.storage.file_storage import AsyncFileStorage
        from src.infrastructure.network.http_client import AsyncHttpClient
        from src.services.publish.publish_service import PublishService
        from src.services.account.account_service import AccountService
        from src.services.subscription.subscription_service import SubscriptionService
        from src.infrastructure.common.pipeline.publish_pipeline import PublishPipeline
        from src.infrastructure.monitoring.metrics import MetricsCollector
        from src.infrastructure.monitoring.logger import StructuredLogger
        from src.infrastructure.monitoring.alerting import AlertManager
        from src.services.browser.playwright_service import PlaywrightBrowserService
        from src.infrastructure.storage.tortoise_manager import init_tortoise
        from src.domain.repositories import (
            AccountRepositoryAsync,
            UserRepositoryAsync,
            SubscriptionRepositoryAsync,
            PublishRecordRepositoryAsync,
            BatchTaskRepositoryAsync,
        )
        from src.infrastructure.common.pipeline.filters.execution_filter import PublishExecutionFilter
        from src.services.account.account_manager_async import AccountManagerAsync
        from src.services.subscription.permission_controller_async import PermissionControllerAsync as PermissionController
        from src.services.publish.pipeline.filters.permission_check_filter_async import PermissionCheckFilterAsync

        # 0. 数据迁移 (已移除)
        
        # 初始化日志管理器 (使用 AppData 下的 logs 目录)
        log_dir = str(PathManager.get_log_dir())
        log_manager = init_log_manager(log_dir=log_dir)
        mark("log_init_done")
        # 使用标准logging模块获取logger
        logger = logging.getLogger("main")
        logger.info("=" * 60)
        logger.info("🚀 媒小宝启动中...")
        logger.info("=" * 60)
        logger.info(f"📁 应用数据目录: {PathManager.get_app_data_dir()}")
        logger.info(f"📝 日志目录: {log_dir}")
        logger.info("")
        # 源码运行时提醒：完整技术日志在文件里，终端滚动不会丢记录
        if not getattr(sys, "frozen", False):
            try:
                from pathlib import Path as _Path

                _main_log = _Path(log_dir) / "qasync_app.log"
                _mirror_hint = ""
                import os as _os

                if _os.environ.get("WEMEDIA_MIRROR_CONSOLE", "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                ):
                    _mirror_hint = f"\n  终端镜像: {_Path(log_dir) / 'console_mirror.log'}"
                print(
                    f"\n[媒小宝] 完整日志已写入文件（与终端是否滚屏无关）:\n"
                    f"  {_main_log.resolve()}{_mirror_hint}\n",
                    file=sys.stderr,
                )
            except Exception:
                pass

        def _cleanup_debug_screenshots_bg() -> None:
            try:
                from src.utils.debug_screenshots_cleanup import cleanup_debug_screenshots_older_than
                n = cleanup_debug_screenshots_older_than(days=7)
                if n:
                    logging.getLogger("main").info("已清理超过 7 天的诊断截图: %s 个文件", n)
            except Exception as e:
                logging.getLogger("main").debug("诊断截图后台清理跳过: %s", e)

        import threading
        threading.Thread(target=_cleanup_debug_screenshots_bg, daemon=True).start()
        
        # 拆分初始化任务
        logger.info("⚡开始并发加载组件与配置...")
        # 提取环境目录供各服务初始化使用
        db_path = str(PathManager.get_db_path())
        file_storage_path = str(PathManager.get_app_data_dir() / "data")
        cache_dir = str(PathManager.get_cache_dir())
        config_dir = str(PathManager.get_config_dir())
        
        service_locator = ServiceLocator()
        service_locator.register(type(log_manager), log_manager, scope=Scope.SINGLETON)
        
        # ----------------------------------------------------
        # 同步轻量级组件：Repository、基础内存模块、DI 组装等
        # ----------------------------------------------------
        
        account_repo = AccountRepositoryAsync()
        service_locator.register(AccountRepositoryAsync, account_repo, scope=Scope.SINGLETON)
        user_repo = UserRepositoryAsync()
        service_locator.register(UserRepositoryAsync, user_repo, scope=Scope.SINGLETON)
        subscription_repo = SubscriptionRepositoryAsync()
        service_locator.register(SubscriptionRepositoryAsync, subscription_repo, scope=Scope.SINGLETON)
        publish_record_repo = PublishRecordRepositoryAsync()
        service_locator.register(PublishRecordRepositoryAsync, publish_record_repo, scope=Scope.SINGLETON)
        batch_task_repo = BatchTaskRepositoryAsync()
        service_locator.register(BatchTaskRepositoryAsync, batch_task_repo, scope=Scope.SINGLETON)
        
        async_file_storage = AsyncFileStorage(file_storage_path)
        service_locator.register(AsyncFileStorage, async_file_storage, scope=Scope.SINGLETON)
        
        http_client = AsyncHttpClient()
        service_locator.register(AsyncHttpClient, http_client, scope=Scope.SINGLETON)
        
        event_bus = EventBus()
        service_locator.register(EventBus, event_bus, scope=Scope.SINGLETON)
        
        cache_manager = CacheManager(l2_cache_dir=cache_dir)
        service_locator.register(CacheManager, cache_manager, scope=Scope.SINGLETON)
        
        rbac = RBAC()
        service_locator.register(RBAC, rbac, scope=Scope.SINGLETON)
        
        encryption_manager = EncryptionManager()
        service_locator.register(EncryptionManager, encryption_manager, scope=Scope.SINGLETON)
        
        # 管道并发上限与执行器层 PublishExecutor 的 max_concurrent=3 对齐，
        # 避免管道槽(5)多于执行器槽(3)导致批量场景下槽位空占浪费
        publish_pipeline = PublishPipeline(max_concurrent=3)
        permission_controller = PermissionController(
            user_repo=service_locator.get(UserRepositoryAsync),
            sub_repo=service_locator.get(SubscriptionRepositoryAsync),
        )
        publish_pipeline.add_filter(PermissionCheckFilterAsync(permission_controller))
        publish_pipeline.add_filter(PublishExecutionFilter())
        service_locator.register(PublishPipeline, publish_pipeline, scope=Scope.SINGLETON)
        
        publish_service = PublishService()
        service_locator.register(PublishService, publish_service, scope=Scope.SINGLETON)
        
        account_service = AccountService()
        service_locator.register(AccountService, account_service, scope=Scope.SINGLETON)
        
        subscription_service = SubscriptionService()
        service_locator.register(SubscriptionService, subscription_service, scope=Scope.SINGLETON)
        
        browser_account_manager = AccountManagerAsync(user_id=1, event_bus=event_bus)
        playwright_browser_service = PlaywrightBrowserService(browser_account_manager)
        service_locator.register(PlaywrightBrowserService, playwright_browser_service, scope=Scope.SINGLETON)
        
        metrics_collector = MetricsCollector()
        service_locator.register(MetricsCollector, metrics_collector, scope=Scope.SINGLETON)
        
        structured_logger = StructuredLogger()
        service_locator.register(StructuredLogger, structured_logger, scope=Scope.SINGLETON)
        
        alert_manager = AlertManager()
        service_locator.register(AlertManager, alert_manager, scope=Scope.SINGLETON)
        
        mark("di_light_done")
        logger.info("✅ 1/2 轻量组件注入完毕")
        
        # ----------------------------------------------------
        # 并发执行耗时任务 (IO 或密集型等)
        # ----------------------------------------------------
        config_center = ConfigCenter(config_dir=config_dir)
        service_locator.register(ConfigCenter, config_center, scope=Scope.SINGLETON)
        
        import asyncio
        async def wrapped_tortoise():
            mark("orm_start")
            await init_tortoise(db_path)
            mark("orm_done")
        async def wrapped_config():
            mark("config_start")
            await config_center.initialize()
            mark("config_done")
        mark("gather_start")
        init_tasks = [
            wrapped_tortoise(),
            wrapped_config(),
        ]
        await asyncio.gather(*init_tasks)
        mark("gather_done")
        logger.info("✅ 2/2 模块配置、ORM 初始化完成（插件与浏览器延后至主窗口显示后加载）")

        async def _background_material_library_sync():
            try:
                from src.infrastructure.common.material_library_manager import MaterialLibraryManager

                await MaterialLibraryManager.sync_platform_account_tree()
            except Exception as e:
                logger.debug("启动后同步媒体库目录树跳过或失败（可忽略）: %s", e)

        asyncio.create_task(_background_material_library_sync())
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ 所有服务初始化成功! Application ready!")
        logger.info("=" * 60)
        return True
        
    except Exception as e:
        logging.error(f"服务初始化失败: {e}", exc_info=True)
        return False


def main():
    """主函数
    
    使用 qasync 统一 Qt 和 asyncio 事件循环，解决以下问题：
    1. 避免 UI 假死（在主线程直接 await 会卡死界面）
    2. 避免任务不执行（未启动 asyncio loop 导致异步任务挂起）
    3. 统一事件循环管理，简化异步代码
    """
    import asyncio
    import qasync
    
    # 这样可以捕获 Chromium 输出的 DirectComposition 错误
    original_stderr = sys.stderr
    stderr_filter = StderrFilter(original_stderr)
    sys.stderr = stderr_filter
    
    # 设置 AppUserModelID，确保任务栏图标正确显示（独立于 Python 图标）
    # 修改 ID 以强制刷新 Windows 图标缓存
    try:
        myappid = 'wemedia_baby.client.1.0.1.force_refresh' 
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass
    
    try:
        # [高DPI屏幕适配]
        # Qt6 默认已开启 High-DPI scaling 和 High-DPI pixmaps
        # 这里配置缩放策略，确保 2K/4K 屏幕（125%, 150% 缩放）下显示清晰不模糊
        if hasattr(QApplication, 'setHighDpiScaleFactorRoundingPolicy'):
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

        # 创建应用程序
        app = QApplication(sys.argv)
        from config.feature_flags import FeatureFlags
        app.setApplicationName("媒小宝-吾爱破解论坛特别版" if FeatureFlags.is_52pojie() else "媒小宝")
        # 日期/时间选择器弹窗：确定在右、取消在左
        try:
            from src.ui.patches.picker_confirm_right import apply_picker_confirm_right
            apply_picker_confirm_right()
            from src.ui.patches.picker_item_mask_align import apply_picker_item_mask_align
            apply_picker_item_mask_align()
            from src.ui.patches.picker_item_mask_drawtext import (
                apply_picker_item_mask_drawtext_safe,
            )
            apply_picker_item_mask_drawtext_safe()
        except Exception as e:
            logging.debug("picker confirm-right / item-mask patch skip: %s", e)
        from src.version import __version__
        app.setApplicationVersion(__version__)

        # [异常过滤] 模块级 _custom_excepthook 已注册（见文件顶部），包含了所有过滤规则，此处无需重复设置

        # --- 初始化主题管理器 ---
        try:
            from src.ui.styles.theme_manager import get_theme_manager
            # 获取实例会自动应用主题和QSS
            theme_manager = get_theme_manager() 
            logging.info("主题管理器初始化完成")
        except Exception as e:
            logging.error(f"主题管理器初始化失败: {e}")
            # 仍尽量应用 Fluent 默认主题，避免主窗口不再调用 setTheme 时界面完全无样式
            try:
                from qfluentwidgets import setTheme, Theme
                setTheme(Theme.AUTO)
            except Exception:
                pass

        # --- 单实例应用检查 ---
        from PySide6.QtNetwork import QLocalSocket, QLocalServer
        
        # 定义唯一的服务名称（通常使用 AppUserModelID 或类似的唯一标识）
        # 注意: 在 Windows 上，LocalServer 名称如果是全局的，可能受权限影响，但在用户 Session 下通常没问题
        INSTANCE_SERVICE_NAME = "wemedia_baby_single_instance_v1"
        
        # 1. 尝试连接已存在的实例
        check_socket = QLocalSocket()
        check_socket.connectToServer(INSTANCE_SERVICE_NAME)
        if check_socket.waitForConnected(500):
            logging.info("检测到已有实例在运行，尝试唤醒并退出当前进程...")
            # 终端启动时默认只看控制台：写 stderr 便于用户理解「为何立刻退出」
            try:
                print(
                    "\n媒小宝已在运行：本进程将退出，并尝试把已有窗口调到前台。"
                    " 若未见窗口，请检查任务栏或其它终端里是否还有 python main.py。\n",
                    file=sys.stderr,
                )
            except Exception:
                pass
            # 连接成功，说明已有实例。
            # 这里可以发送参数给旧实例（例如要打开的文件），暂不需要
            check_socket.disconnectFromServer()
            return 0
        
        # 2. 如果连接失败，说明是第一个实例，启动服务器
        local_server = QLocalServer()
        # 清理可能残留的死链接 (例如上次崩溃导致未正常关闭)
        local_server.removeServer(INSTANCE_SERVICE_NAME)
        
        if not local_server.listen(INSTANCE_SERVICE_NAME):
            logging.warning(f"启动单实例监听服务失败: {local_server.errorString()}")
        else:
            logging.info(f"单实例监听服务已启动: {INSTANCE_SERVICE_NAME}")
        
        # --- 检查结束 ---
        
        # 设置全局应用图标 (使用 PathManager 统一路径，兼容打包环境)
        from src.infrastructure.common.path_manager import PathManager
        project_root = str(PathManager.get_resource_dir())
        icon_path_ico = os.path.join(project_root, "resources", "icons", "app.ico")
        icon_path_png = os.path.join(project_root, "resources", "logo.png")
        
        # 优先使用 PNG (Qt对PNG支持很好)，其次使用 ICO
        icon_to_use = None
        if os.path.exists(icon_path_png):
            icon_to_use = icon_path_png
            logging.info(f"发现 PNG 图标: {icon_path_png}")
        elif os.path.exists(icon_path_ico):
             icon_to_use = icon_path_ico
             logging.info(f"发现 ICO 图标: {icon_path_ico}")
        
        if icon_to_use:
            app_icon = QIcon(icon_to_use)
            if not app_icon.isNull():
                app.setWindowIcon(app_icon)
                logging.info(f"成功设置应用图标: {icon_to_use}")
            else:
                logging.error(f"加载图标失败 (QIcon isNull): {icon_to_use}")
        else:
            logging.warning(f"未找到任何应用图标文件")



        
        # 使用 qasync 统一事件循环
        # 这样 Qt 事件和 asyncio 协程共用同一个事件循环
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        
        # 捕获异步事件循环中未处理的异常
        def custom_exception_handler(loop, context):
            exc = context.get("exception")
            msg = exc if exc is not None else context.get("message", "")
            text = str(msg)
            low = text.lower()
            
            # 忽略 aiohttp 的 Unclosed client session (长连接 ClientSession 析构时的安全警告)
            if "unclosed client session" in low:
                return
                
            # 浏览器已关闭后仍有协程访问 Playwright 时的典型错误，降级为 debug，不写 fatal_crash
            if exc is not None:
                benign_closed = ("target page" in low and "closed" in low) or (
                    "context or browser has been closed" in low
                )
                if benign_closed:
                    logging.getLogger("asyncio").debug("[Asyncio 预期内] 浏览器/页面已关闭: %s", text)
                    return

            logging.error(f"[Asyncio 未处理异常]: {msg}")

            # 记录到崩溃日志（与主日志目录一致）
            try:
                import datetime
                with open(_fatal_crash_log_file(), "a", encoding="utf-8") as f:
                    time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"\n[{time_str}] ASYNC ERROR:\n{context}\n")
            except Exception:
                pass

        loop.set_exception_handler(custom_exception_handler)
        
        async def run_app():
            """异步运行应用程序"""
            # 异步初始化服务
            if not await initialize_services_async():
                logging.error("服务初始化失败，程序退出")
                return 1

            # 52POJIE 特别版：启动即注入本地 VIP 用户态（无云端、免登录）
            try:
                from config.feature_flags import FeatureFlags
                if FeatureFlags.is_52pojie():
                    from src.services.auth import CurrentUserService
                    curr = CurrentUserService()
                    if not curr.is_logged_in():
                        curr.set_user(
                            user_id=520052,
                            username="52pojie",
                            level="vip1",
                            is_expired=False,
                        )
                        logging.info("52POJIE 模式：已注入本地离线账号（vip1）")
            except Exception as e:
                logging.warning("52POJIE 本地账号注入失败：%s", e)
            
                # 创建主窗口（延后导入以加快进入 run_app）
            try:
                from src.utils.startup_profiler import mark
                mark("create_window_start")
                from src.ui.main_window import MainWindow
                window = MainWindow()
                mark("create_window_done")

                # 先显示主窗口，避免因自动登录网络请求（可能数秒）导致界面卡顿
                mark("window_show")
                window.show()
                # 仅当上次为「关闭到托盘」且仍启用该选项时，冷启动后再藏到托盘；真正退出后的下次启动显示主界面
                window.apply_startup_tray_behavior()
                # 主界面显示时抢到前台（Windows 上否则常只剩任务栏图标高亮）
                if window.isVisible():
                    from PySide6.QtCore import QTimer

                    window.bring_to_foreground()
                    QTimer.singleShot(0, window.bring_to_foreground)

                # 自动登录放到后台执行，完成后 UI 会通过 CurrentUserService 等更新用户名
                # 52POJIE 特别版不接入云端账号体系，跳过自动登录
                from config.feature_flags import FeatureFlags

                mark("autologin_start")
                if FeatureFlags.is_52pojie():
                    mark("autologin_done")
                else:
                    async def _auto_login_and_maybe_log():
                        try:
                            from src.services.auth.auth_remember import try_auto_login_async
                            if await try_auto_login_async():
                                logging.info("已使用记住的账号自动登录")
                        except Exception as e:
                            logging.warning("自动登录失败: %s", e)
                        mark("autologin_done")
                    asyncio.create_task(_auto_login_and_maybe_log())

                # 启动心跳任务：每60秒写一次存活记录（含内存用量）
                # 用于在下次崩溃后通过日志时间线推断崩溃发生在哪个任务附近
                async def _heartbeat_task():
                    import datetime
                    _hb_logger = logging.getLogger("heartbeat")
                    while True:
                        try:
                            await asyncio.sleep(60)
                            mem_info = ""
                            try:
                                import psutil
                                proc = psutil.Process(os.getpid())
                                mem_mb = proc.memory_info().rss / 1024 / 1024
                                mem_info = f"  内存: {mem_mb:.1f} MB"
                            except Exception:
                                pass
                            _hb_logger.info("[心跳] 程序运行正常%s", mem_info)
                        except asyncio.CancelledError:
                            break
                        except Exception:
                            pass

                asyncio.create_task(_heartbeat_task())

                # 配置单实例唤醒逻辑
                def handle_activation():
                    """处理来自新实例的唤醒请求"""
                    logging.info("收到新实例的唤醒请求，正在激活主窗口...")

                    # 必须处理 pending connection 否则信号会不断触发
                    while local_server.hasPendingConnections():
                        conn = local_server.nextPendingConnection()
                        conn.close()

                    # 若窗口处于隐藏状态（缩到托盘 = hide()，非最小化），
                    # 需先调用 showNormal() 使其可见，再置前激活。
                    # 与托盘图标双击的 _tray_show_window() 逻辑保持一致。
                    if not window.isVisible():
                        window._persist_start_in_tray_next_launch(False)
                        window.showNormal()

                    window.bring_to_foreground()

                if local_server.isListening():
                    local_server.newConnection.connect(handle_activation)
                
                logging.info("主窗口已显示（qasync 统一事件循环）")

                # 主窗口显示后再加载插件与浏览器功能（不阻塞首屏）
                async def load_plugins_and_browser():
                    try:
                        from src.utils.startup_profiler import mark
                        from src.plugins.core.plugin_manager import PluginManager
                        from src.infrastructure.common.di.service_locator import ServiceLocator, Scope
                        from src.infrastructure.browser.browser_manager import UndetectedBrowserManager
                        mark("plugin_start")
                        PluginManager.initialize()
                        sl = ServiceLocator()
                        sl.register(PluginManager, PluginManager(), scope=Scope.SINGLETON)
                        mark("plugin_done")
                        logging.info("插件加载完成")
                        mark("warmup_start")
                        await UndetectedBrowserManager.ensure_warmup()
                        mark("warmup_done")
                        logging.info("浏览器环境预热完成")
                    except Exception as e:
                        logging.warning("后台加载插件/浏览器失败: %s", e)
                asyncio.create_task(load_plugins_and_browser())
                
                # 使用 asyncio.Event 等待应用退出
                # 这比轮询 isVisible() 更可靠
                quit_event = asyncio.Event()
                
                def on_about_to_quit():
                    """QApplication 即将退出时触发"""
                    logging.info("收到应用退出信号")
                    quit_event.set()
                
                app.aboutToQuit.connect(on_about_to_quit)
                
                # 等待退出事件
                try:
                    await quit_event.wait()
                except asyncio.CancelledError:
                    pass
                finally:
                    # --- 增强的资源清理逻辑（任一步骤异常也不阻塞退出，确保最终 os._exit 被执行）---
                    # 注意：必须先做依赖事件循环的异步清理（浏览器关闭），再做会可能影响事件循环的步骤（配置/HTTP 等）

                    # [看门狗] 线程级兜底：清理阶段 + 后续 loop.close() 如果整体超时则强制退出
                    import threading as _th
                    def _cleanup_timeout_exit():
                        try:
                            logging.warning("!!! 资源清理总超时 (10s)，强制终止进程 !!!")
                        except Exception:
                            pass
                        os._exit(0)
                    _cleanup_dog = _th.Timer(10.0, _cleanup_timeout_exit)
                    _cleanup_dog.daemon = True
                    _cleanup_dog.start()

                    try:
                        logging.info("开始清理应用资源...")
                        sl = None
                        try:
                            from src.infrastructure.common.di.service_locator import ServiceLocator
                            sl = ServiceLocator()
                        except Exception as e:
                            logging.warning(f"获取 ServiceLocator 失败: {e}")

                        # 1. 关闭所有 Playwright 浏览器
                        #    qasync 退出后 asyncio.get_running_loop() 会报错，但 await 仍能正常工作
                        #    （已验证：await client.close() 在同一环境下成功执行），因此直接尝试 await。
                        try:
                            from src.services.browser.playwright_service import PlaywrightBrowserService
                            if sl and sl.is_registered(PlaywrightBrowserService):
                                pw_service = sl.get(PlaywrightBrowserService)
                                if hasattr(pw_service, "shutdown"):
                                    logging.info("正在关闭所有浏览器实例...")
                                    try:
                                        await pw_service.shutdown()
                                        logging.info("所有浏览器实例已关闭")
                                    except Exception as e:
                                        _e = str(e).lower()
                                        if "no running event loop" in _e or "event loop is closed" in _e:
                                            logging.info("浏览器优雅关闭部分完成，剩余由 Process Guardian 清理")
                                        else:
                                            logging.warning("浏览器优雅关闭异常: %s，将由 Process Guardian 清理", e)
                        except Exception as e:
                            logging.warning(f"关闭浏览器服务失败: {e}，将依赖 Process Guardian 清理")

                        # 2. Process Guardian（同步，一轮扫描即可；退出前 main 末尾会再扫一次）
                        try:
                            from src.infrastructure.browser.browser_manager import UndetectedBrowserManager
                            UndetectedBrowserManager.cleanup_all_processes()
                        except Exception as e:
                            if "no running event loop" not in str(e):
                                logging.warning(f"浏览器进程清理失败: {e}")

                        if not sl:
                            try:
                                from src.infrastructure.common.di.service_locator import ServiceLocator
                                sl = ServiceLocator()
                            except Exception:
                                sl = None

                        # 3. 停止批量任务执行器
                        try:
                            if sl:
                                from src.pro_features.batch.services.batch_task_manager_async import BatchTaskManagerAsync
                                if sl.is_registered(BatchTaskManagerAsync):
                                    batch_manager = sl.get(BatchTaskManagerAsync)
                                    if hasattr(batch_manager, 'shutdown'):
                                        logging.info("正在停止批量任务管理器...")
                                        batch_manager.shutdown()
                        except Exception as e:
                            logging.warning(f"清理批量任务资源失败 (若模块未加载可忽略): {e}")

                        # 4. 停止配置中心
                        try:
                            # 提前导入，防止下面判定 sl.is_registered 时因未导入抛出进而导致 except 块中也找不到名字
                            from src.infrastructure.common.config.config_center import ConfigCenter
                            if sl and sl.is_registered(ConfigCenter):
                                config_center_instance = sl.get(ConfigCenter)
                                config_center_instance.close()
                                logging.info("配置中心监听已停止")
                        except ImportError as e:
                            logging.debug(f"ConfigCenter 未导入，跳过清理: {e}")
                        except Exception as e:
                            logging.warning(f"停止配置中心失败: {e}")

                        # 6. 关闭 HTTP 客户端
                        try:
                            from src.infrastructure.network.http_client import AsyncHttpClient
                            if sl and sl.is_registered(AsyncHttpClient):
                                client = sl.get(AsyncHttpClient)
                                await client.close()
                                logging.info("HTTP 客户端已关闭")
                        except RuntimeError as e:
                            if "no running event loop" in str(e):
                                pass
                            else:
                                logging.warning(f"关闭 HTTP 客户端失败: {e}")
                        except Exception as e:
                            logging.warning(f"关闭 HTTP 客户端失败: {e}")

                        # 6b. 关闭更新检查共享 aiohttp 会话
                        logging.info("正在关闭更新检查 HTTP 会话...")
                        try:
                            from src.services.update_check_service import close_update_check_session
                            await close_update_check_session()
                        except Exception as e:
                            logging.warning("关闭更新检查会话失败: %s", e)
                        logging.info("更新检查 HTTP 会话已关闭")
                        try:
                            for _h in logging.root.handlers:
                                fl = getattr(_h, "flush", None)
                                if callable(fl):
                                    fl()
                        except Exception:
                            pass

                        # 7. 关闭 Tortoise ORM 连接
                        try:
                            from src.infrastructure.storage.tortoise_manager import close_tortoise
                            await close_tortoise()
                            logging.info("Tortoise ORM 连接已安全关闭")
                        except asyncio.CancelledError:
                            logging.debug("关闭 Tortoise 被取消（应用退出中，可忽略）")
                        except Exception:
                            pass

                    except Exception as e:
                        logging.error(f"资源清理过程发生错误: {e}")
                    finally:
                        # 取消未完成的 asyncio 任务
                        #   qasync 退出后 asyncio.get_running_loop() 会失败，
                        #   改用外层闭包的 loop 对象（qasync.QEventLoop 实例）。
                        try:
                            if not loop.is_closed():
                                try:
                                    _cur_task = asyncio.current_task()
                                except RuntimeError:
                                    _cur_task = None
                                pending = []
                                try:
                                    for t in asyncio.all_tasks(loop):
                                        if t is not _cur_task:
                                            pending.append(t)
                                except RuntimeError:
                                    pending = []
                                if pending:
                                    logging.info("发现 %d 个未完成的后台任务，正在取消...", len(pending))
                                    for task in pending:
                                        task.cancel()
                            logging.info("资源清理流程结束，准备退出进程")
                        except Exception as e:
                            logging.error(f"退出清理过程异常: {e}，仍将强制退出进程")
                        finally:
                            _cleanup_dog.cancel()

                        # 资源清理已完成，安排快速强制退出以防 loop.close() 死锁
                        def _post_cleanup_exit():
                            try:
                                logging.debug("loop.close() 超时，强制退出")
                            except Exception:
                                pass
                            os._exit(0)
                        _post_dog = _th.Timer(0.5, _post_cleanup_exit)
                        _post_dog.daemon = True
                        _post_dog.start()

                    return 0
            
            except asyncio.CancelledError:
                # 正常捕获取消异常
                logging.info("主运行任务被取消")
                return 0
            except Exception as e:
                logging.error(f"启动主窗口失败: {e}", exc_info=True)
                return 1
        
        # 使用 qasync 运行应用程序
        # 不使用 `with loop:` 上下文管理器，因为其 __exit__ 调用 loop.close()
        # 在 Qt 事件循环已停止的情况下可能死锁。改为手动管理生命周期。
        try:
            return loop.run_until_complete(run_app())
        except asyncio.CancelledError:
            # qasync 在 Qt 退出路径上可能在此处抛出 CancelledError（run_until_complete 层），
            # 与协程内已处理的取消不同；若不捕获会被 PyInstaller 视为未处理脚本异常。
            logging.debug("应用程序正常退出（qasync 事件循环取消）")
            return 0
        except RuntimeError as e:
            # qasync 在窗口关闭时会抛出此错误，属于正常行为
            if "Event loop stopped before Future completed" in str(e):
                logging.debug("应用程序正常退出")
                return 0
            raise
        finally:
            try:
                if not loop.is_closed():
                    loop.close()
            except Exception:
                pass
    
    except Exception as e:
        logging.error(f"应用程序启动失败: {e}", exc_info=True)
        return 1
    finally:
        # 恢复原始 stderr
        sys.stderr = original_stderr


def _run_smoke_test() -> int:
    """打包后冒烟测试：验证关键模块可导入、核心资源文件存在，打印结果并退出。
    用法：WeMediaBaby.exe --smoke-test
    """
    import importlib
    from pathlib import Path

    print("=" * 60)
    print("  媒小宝 冒烟测试 (--smoke-test)")
    print("=" * 60)

    # 发行模式（PRO/OSS）探测：用于定位“安装后仍显示 OSS”的问题
    try:
        from config.feature_flags import FeatureFlags
        info = FeatureFlags.debug_dist_mode() if hasattr(FeatureFlags, "debug_dist_mode") else {"dist_mode": FeatureFlags.get_dist_mode(), "source": ""}
        print(f"  [INFO] dist_mode = {info.get('dist_mode')}  source = {info.get('source')}")
    except Exception as e:
        print(f"  [WARN] dist_mode 探测失败: {e}")

    modules = [
        # 页面工厂中的动态导入
        "src.ui.pages.workspace_page",
        "src.ui.pages.account",
        "src.ui.pages.account_group",
        "src.ui.pages.publish.publish_list_page",
        "src.ui.pages.publish",
        "src.ui.pages.publish.image_single_task_creation_page",
        "src.ui.pages.settings_page",
        "src.ui.pages.material.video_library_page",
        "src.ui.pages.material.image_library_page",
        "src.ui.pages.material.copywriting_library_page",
        "src.ui.pages.material.yellow_cart_promotion_page",
        "src.ui.pages.material.group_buy_promotion_page",
        # 插件
        "src.plugins.community.douyin.login_plugin",
        "src.plugins.community.douyin.publish_plugin",
        "src.plugins.community.kuaishou.login_plugin",
        "src.plugins.community.kuaishou.publish_plugin",
        # 核心基础设施
        "src.infrastructure.storage.tortoise_manager",
        "src.infrastructure.common.pipeline.publish_pipeline",
        "src.services.account.account_service",
        "src.services.publish.publish_service",
        # 发布域（作品描述 / 位置等，打包后动态页若漏收集可在此暴露）
        "src.domain.publish.work_description",
        "src.ui.publish.work_description",
        # 三方关键依赖
        "PySide6.QtWidgets",
        "qasync",
        "qfluentwidgets",
        "tortoise",
        "aiosqlite",
        "playwright",
        "cryptography",
        "pydantic",
        "aiohttp",
    ]

    failed = []
    for mod in modules:
        try:
            importlib.import_module(mod)
            print(f"  [OK] {mod}")
        except Exception as e:
            failed.append((mod, str(e)))
            print(f"  [FAIL] {mod}  ->  {e}")

    print()

    # 检查关键资源（目录用 exe 旁路径；单文件与 data_dirs 一致）
    # PyInstaller(one-dir) 的资源通常位于 _internal；Nuitka 位于 exe 同级；开发环境位于仓库根目录
    try:
        from src.infrastructure.common.path_manager import PathManager as _PM
        _PM._resource_dir = None
        base = _PM.get_resource_dir()
    except Exception:
        base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

    resources = ["config", "resources"]
    missing_res = []
    for r in resources:
        p = base / r
        if not p.exists():
            missing_res.append(str(p))
            print(f"  [MISSING] 资源目录: {p}")
        else:
            print(f"  [OK] 资源目录: {p}")

    try:
        from src.infrastructure.common.path_manager import PathManager as _PM
        _PM._resource_dir = None
        _stealth = _PM.get_resource_path("src/resources/scripts/stealth/stealth.js")
    except Exception:
        _stealth = base / "src" / "resources" / "scripts" / "stealth" / "stealth.js"
    if not _stealth.exists():
        missing_res.append(str(_stealth))
        print(f"  [MISSING] 抗检测脚本 stealth.js: {_stealth}")
    else:
        print(f"  [OK] 抗检测脚本: {_stealth}")

    print()
    print("=" * 60)
    total_issues = len(failed) + len(missing_res)
    if total_issues == 0:
        print("  冒烟测试通过! 所有模块可导入，资源完整。")
        print("=" * 60)
        return 0
    else:
        print(f"  冒烟测试发现 {total_issues} 个问题！")
        for mod, err in failed:
            print(f"    模块: {mod} -> {err}")
        for r in missing_res:
            print(f"    缺失: {r}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        sys.exit(_run_smoke_test())
    if "--print-dist-mode" in sys.argv:
        try:
            from config.feature_flags import FeatureFlags
            print(FeatureFlags.get_dist_mode())
            sys.exit(0)
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    import threading

    # [全局看门狗] 在 main() 调用之前启动，确保无论 main() 是否能正常返回，
    # 进程最终都会在超时后被强制终止。避免 qasync loop.close() 死锁导致进程永远挂起。
    _GLOBAL_EXIT_TIMEOUT = 15  # 秒（给清理流程充足时间）
    _global_watchdog_active = False

    def _global_hard_kill():
        if _global_watchdog_active:
            try:
                logging.warning("!!! 全局看门狗超时 (%ds)，强制终止进程 !!!", _GLOBAL_EXIT_TIMEOUT)
            except Exception:
                pass
            os._exit(0)

    _global_dog = threading.Timer(_GLOBAL_EXIT_TIMEOUT, _global_hard_kill)
    _global_dog.daemon = True

    try:
        ret_code = main()

        # main() 正常返回，激活全局看门狗（防止后续 sys.exit 被非守护线程阻塞）
        _global_watchdog_active = True
        _global_dog.start()

        # [加固] 退出前执行最后一次强力进程清理 (Process Guardian)
        try:
            from src.infrastructure.browser.browser_manager import UndetectedBrowserManager
            UndetectedBrowserManager.cleanup_all_processes()
        except Exception:
            pass

        logging.info("主程序正常退出，返回码: %d", ret_code)
        sys.exit(ret_code)
    except KeyboardInterrupt:
        os._exit(0)
    except SystemExit:
        os._exit(0)
    except Exception:
        try:
            from src.infrastructure.browser.browser_manager import UndetectedBrowserManager
            UndetectedBrowserManager.cleanup_all_processes()
        except Exception:
            pass
        os._exit(1)
