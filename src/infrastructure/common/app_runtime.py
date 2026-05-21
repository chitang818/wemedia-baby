from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from src.infrastructure.common.shutdown import cleanup_application_resources
from src.infrastructure.common.single_instance import connect_activation_handler


def _mark(name: str) -> None:
    try:
        from src.utils.startup_profiler import mark

        mark(name)
    except Exception:
        pass


def inject_52pojie_local_user() -> None:
    """Populate the offline local user only for the 52POJIE distribution."""

    try:
        from config.feature_flags import FeatureFlags

        if not FeatureFlags.is_52pojie():
            return

        from src.services.auth import CurrentUserService

        current_user = CurrentUserService()
        if current_user.is_logged_in():
            return

        current_user.set_user(
            user_id=520052,
            username="52pojie",
            level="vip1",
            is_expired=False,
        )
        logging.info("52POJIE mode: injected local offline vip1 account.")
    except Exception as e:
        logging.warning("52POJIE local account injection failed: %s", e)


def create_and_show_main_window():
    _mark("create_window_start")
    from src.ui.main_window import MainWindow

    window = MainWindow()
    _mark("create_window_done")

    _mark("window_show")
    window.show()
    window.apply_startup_tray_behavior()

    if window.isVisible():
        from PySide6.QtCore import QTimer

        window.bring_to_foreground()
        QTimer.singleShot(0, window.bring_to_foreground)

    return window


async def _auto_login_and_maybe_log() -> None:
    try:
        from src.services.auth.auth_remember import try_auto_login_async

        if await try_auto_login_async():
            logging.info("Auto login succeeded with remembered credentials.")
    except Exception as e:
        logging.warning("Auto login failed: %s", e)
    finally:
        _mark("autologin_done")


def schedule_auto_login(task_registry: Any) -> None:
    from config.feature_flags import FeatureFlags

    _mark("autologin_start")
    if FeatureFlags.is_52pojie():
        _mark("autologin_done")
        return

    task_registry.create_task(
        _auto_login_and_maybe_log(),
        name="startup.auto_login",
        group="startup",
    )


def _memory_usage_suffix() -> str:
    try:
        import psutil

        process = psutil.Process(os.getpid())
        mem_mb = process.memory_info().rss / 1024 / 1024
        return f"  memory: {mem_mb:.1f} MB"
    except Exception:
        return ""


async def heartbeat_task() -> None:
    heartbeat_logger = logging.getLogger("heartbeat")
    while True:
        try:
            await asyncio.sleep(60)
            heartbeat_logger.info(
                "[heartbeat] application is alive%s",
                _memory_usage_suffix(),
            )
        except asyncio.CancelledError:
            break
        except Exception:
            pass


def schedule_heartbeat(task_registry: Any) -> None:
    task_registry.create_task(
        heartbeat_task(),
        name="monitoring.heartbeat",
        group="monitoring",
    )


def connect_main_window_activation(local_server: Any, window: Any) -> None:
    def activate_main_window() -> None:
        if not window.isVisible():
            window._persist_start_in_tray_next_launch(False)
            window.showNormal()

        window.bring_to_foreground()

    connect_activation_handler(local_server, activate_main_window)


def is_startup_browser_warmup_enabled() -> bool:
    return os.environ.get("ENABLE_BROWSER_WARMUP_ON_START", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


async def load_plugins() -> None:
    try:
        from src.infrastructure.common.di.service_locator import Scope, ServiceLocator
        from src.plugins.core.plugin_manager import PluginManager

        _mark("plugin_start")
        PluginManager.initialize()
        ServiceLocator().register(PluginManager, PluginManager(), scope=Scope.SINGLETON)
        _mark("plugin_done")
        logging.info("Plugin loading finished.")
    except Exception as e:
        logging.warning("Background plugin loading failed: %s", e)


def schedule_plugin_loading(task_registry: Any) -> None:
    task_registry.create_task(
        load_plugins(),
        name="startup.plugin_loading",
        group="startup",
    )


async def warmup_browser_environment() -> None:
    try:
        from src.infrastructure.browser.browser_manager import UndetectedBrowserManager

        _mark("warmup_start")
        await UndetectedBrowserManager.ensure_warmup()
        _mark("warmup_done")
        logging.info("Browser environment warmup finished.")
    except Exception as e:
        logging.warning("Background browser warmup failed: %s", e)


def schedule_optional_browser_warmup(task_registry: Any) -> None:
    if not is_startup_browser_warmup_enabled():
        return

    task_registry.create_task(
        warmup_browser_environment(),
        name="startup.browser_warmup",
        group="startup",
    )


async def wait_for_application_quit(app: Any) -> None:
    quit_event = asyncio.Event()

    def on_about_to_quit() -> None:
        logging.info("Received application quit signal.")
        quit_event.set()

    app.aboutToQuit.connect(on_about_to_quit)

    try:
        await quit_event.wait()
    except asyncio.CancelledError:
        pass


async def run_desktop_runtime(
    *,
    app: Any,
    local_server: Any,
    loop: asyncio.AbstractEventLoop,
    task_registry: Any,
) -> int:
    """Run the main window and startup background tasks until QApplication exits."""

    try:
        inject_52pojie_local_user()
        window = create_and_show_main_window()
        schedule_auto_login(task_registry)
        schedule_heartbeat(task_registry)
        connect_main_window_activation(local_server, window)
        logging.info("Main window is visible; qasync event loop is running.")
        schedule_plugin_loading(task_registry)
        schedule_optional_browser_warmup(task_registry)
        await wait_for_application_quit(app)
        return 0
    except asyncio.CancelledError:
        logging.info("Main runtime task cancelled.")
        return 0
    except Exception as e:
        logging.error("Failed to start main window: %s", e, exc_info=True)
        return 1
    finally:
        await cleanup_application_resources(
            task_registry=task_registry,
            loop=loop,
        )
