"""
主程序入口
文件路径：main.py
功能：应用程序入口，初始化所有服务并启动主窗口
"""

import sys
import os
import logging

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.infrastructure.common.runtime_guards import (
    StderrFilter,
    configure_frozen_working_directory,
    configure_qt_environment,
    install_crash_handlers,
    install_asyncio_exception_handler,
    install_null_stdio,
    install_stderr_filter,
)
from src.infrastructure.common.app_bootstrap import (
    apply_picker_patches,
    configure_windows_app_user_model_id,
    create_application,
    initialize_theme_manager,
    set_application_icon,
)
from src.infrastructure.common.single_instance import (
    another_instance_is_running,
    connect_activation_handler,
    create_single_instance_server,
)

configure_frozen_working_directory()
configure_qt_environment()

install_null_stdio()
install_crash_handlers()
install_stderr_filter()

# 仅保留启动最早需要的轻量模块，其余在 initialize_services_async 内按需导入以加快首屏
from src.infrastructure.common.service_bootstrap import initialize_services_async
from src.infrastructure.common.shutdown import cleanup_application_resources, run_with_global_exit_watchdog


def main():
    """Run the Qt/qasync desktop application."""
    import asyncio
    import qasync

    original_stderr = sys.stderr
    stderr_filter = StderrFilter(original_stderr)
    sys.stderr = stderr_filter

    configure_windows_app_user_model_id()

    try:
        app = create_application()
        apply_picker_patches()
        initialize_theme_manager()

        if another_instance_is_running():
            return 0
        local_server = create_single_instance_server()
        set_application_icon(app)

        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)
        install_asyncio_exception_handler(loop)

        async def run_app():
            """异步运行应用程序"""
            # 异步初始化服务
            if not await initialize_services_async():
                logging.error("服务初始化失败，程序退出")
                return 1

            from src.infrastructure.common.async_task_registry import get_async_task_registry
            task_registry = get_async_task_registry()

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
                    task_registry.create_task(
                        _auto_login_and_maybe_log(),
                        name="startup.auto_login",
                        group="startup",
                    )

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

                task_registry.create_task(
                    _heartbeat_task(),
                    name="monitoring.heartbeat",
                    group="monitoring",
                )

                def activate_main_window():
                    if not window.isVisible():
                        window._persist_start_in_tray_next_launch(False)
                        window.showNormal()

                    window.bring_to_foreground()

                connect_activation_handler(local_server, activate_main_window)
                
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
                task_registry.create_task(
                    load_plugins_and_browser(),
                    name="startup.plugins_browser_warmup",
                    group="startup",
                )
                
                # 使用 asyncio.Event 等待应用退出
                # 这比轮询 isVisible() 更可靠
                quit_event = asyncio.Event()
                
                def on_about_to_quit():
                    """QApplication 即将退出时触发"""
                    logging.info("收到应用退出信号")
                    quit_event.set()
                
                app.aboutToQuit.connect(on_about_to_quit)
                
                try:
                    await quit_event.wait()
                except asyncio.CancelledError:
                    pass
                finally:
                    await cleanup_application_resources(
                        task_registry=task_registry,
                        loop=loop,
                    )

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


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        from src.infrastructure.common.smoke_test import run_smoke_test

        sys.exit(run_smoke_test())
    if "--print-dist-mode" in sys.argv:
        try:
            from config.feature_flags import FeatureFlags
            print(FeatureFlags.get_dist_mode())
            sys.exit(0)
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    run_with_global_exit_watchdog(main)
