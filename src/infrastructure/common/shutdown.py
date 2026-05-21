from __future__ import annotations

import asyncio
import logging
import os
import threading
import sys
from typing import Any


async def cleanup_application_resources(
    *,
    task_registry: Any,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Best-effort shutdown for services that depend on the qasync loop."""

    def _cleanup_timeout_exit() -> None:
        try:
            logging.warning("Application cleanup timed out; forcing process exit.")
        except Exception:
            pass
        os._exit(0)

    cleanup_watchdog = threading.Timer(10.0, _cleanup_timeout_exit)
    cleanup_watchdog.daemon = True
    cleanup_watchdog.start()

    try:
        logging.info("Starting application resource cleanup...")
        service_locator = _get_service_locator()

        await _shutdown_playwright_service(service_locator)
        _cleanup_browser_processes()

        if service_locator is None:
            service_locator = _get_service_locator()

        _shutdown_batch_manager(service_locator)
        _close_config_center(service_locator)
        await _close_http_client(service_locator)
        await _close_update_check_session()
        _flush_logging_handlers()
        await _close_tortoise()
    except Exception as e:
        logging.error("Application cleanup failed: %s", e)
    finally:
        await _cancel_registered_tasks(task_registry)
        _cancel_pending_loop_tasks(loop)
        cleanup_watchdog.cancel()
        _schedule_post_cleanup_exit()


def _get_service_locator():
    try:
        from src.infrastructure.common.di.service_locator import ServiceLocator

        return ServiceLocator()
    except Exception as e:
        logging.warning("Failed to get ServiceLocator during shutdown: %s", e)
        return None


async def _shutdown_playwright_service(service_locator) -> None:
    try:
        if service_locator and service_locator.is_registered("PlaywrightBrowserService"):
            playwright_service = service_locator.get("PlaywrightBrowserService")
            if hasattr(playwright_service, "shutdown"):
                logging.info("Closing browser instances...")
                try:
                    await playwright_service.shutdown()
                    logging.info("Browser instances closed.")
                except Exception as e:
                    text = str(e).lower()
                    if "no running event loop" in text or "event loop is closed" in text:
                        logging.info("Browser graceful shutdown partially completed.")
                    else:
                        logging.warning("Browser graceful shutdown failed: %s", e)
    except Exception as e:
        logging.warning("Browser service shutdown failed: %s", e)


def _cleanup_browser_processes() -> None:
    try:
        from src.infrastructure.browser.browser_manager import UndetectedBrowserManager

        UndetectedBrowserManager.cleanup_all_processes()
    except Exception as e:
        if "no running event loop" not in str(e):
            logging.warning("Browser process cleanup failed: %s", e)


def _shutdown_batch_manager(service_locator) -> None:
    try:
        if not service_locator:
            return
        from src.pro_features.batch.services.batch_task_manager_async import BatchTaskManagerAsync

        if service_locator.is_registered(BatchTaskManagerAsync):
            batch_manager = service_locator.get(BatchTaskManagerAsync)
            if hasattr(batch_manager, "shutdown"):
                logging.info("Stopping batch task manager...")
                batch_manager.shutdown()
    except Exception as e:
        logging.warning("Batch task cleanup failed: %s", e)


def _close_config_center(service_locator) -> None:
    try:
        from src.infrastructure.common.config.config_center import ConfigCenter

        if service_locator and service_locator.is_registered(ConfigCenter):
            config_center = service_locator.get(ConfigCenter)
            config_center.close()
            logging.info("ConfigCenter stopped.")
    except ImportError as e:
        logging.debug("ConfigCenter not imported; skipping: %s", e)
    except Exception as e:
        logging.warning("ConfigCenter cleanup failed: %s", e)


async def _close_http_client(service_locator) -> None:
    try:
        from src.infrastructure.network.http_client import AsyncHttpClient

        if service_locator and service_locator.is_registered(AsyncHttpClient):
            client = service_locator.get(AsyncHttpClient)
            await client.close()
            logging.info("HTTP client closed.")
    except RuntimeError as e:
        if "no running event loop" not in str(e):
            logging.warning("HTTP client cleanup failed: %s", e)
    except Exception as e:
        logging.warning("HTTP client cleanup failed: %s", e)


async def _close_update_check_session() -> None:
    logging.info("Closing update-check HTTP session...")
    try:
        from src.services.update_check_service import close_update_check_session

        await close_update_check_session()
    except Exception as e:
        logging.warning("Update-check session cleanup failed: %s", e)
    logging.info("Update-check HTTP session closed.")


def _flush_logging_handlers() -> None:
    try:
        for handler in logging.root.handlers:
            flush = getattr(handler, "flush", None)
            if callable(flush):
                flush()
    except Exception:
        pass


async def _close_tortoise() -> None:
    try:
        from src.infrastructure.storage.tortoise_manager import close_tortoise

        await close_tortoise()
        logging.info("Tortoise ORM closed.")
    except asyncio.CancelledError:
        logging.debug("Tortoise shutdown cancelled during app exit.")
    except Exception:
        pass


async def _cancel_registered_tasks(task_registry: Any) -> None:
    try:
        await task_registry.cancel_all(timeout=2.0, exclude_current=True)
    except Exception as e:
        logging.warning("Registered background task cancellation failed: %s", e)


def _cancel_pending_loop_tasks(loop: asyncio.AbstractEventLoop) -> None:
    try:
        if loop.is_closed():
            return
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        try:
            pending = [task for task in asyncio.all_tasks(loop) if task is not current_task]
        except RuntimeError:
            pending = []
        if pending:
            logging.info("Cancelling %d pending background task(s)...", len(pending))
            for task in pending:
                task.cancel()
        logging.info("Application resource cleanup finished.")
    except Exception as e:
        logging.error("Exit cleanup encountered an error: %s", e)


def _schedule_post_cleanup_exit() -> None:
    def _post_cleanup_exit() -> None:
        try:
            logging.debug("loop.close() timeout; forcing process exit.")
        except Exception:
            pass
        os._exit(0)

    post_watchdog = threading.Timer(0.5, _post_cleanup_exit)
    post_watchdog.daemon = True
    post_watchdog.start()


def run_with_global_exit_watchdog(main_func, *, timeout_seconds: int = 15) -> None:
    """Run main(), then force process exit if non-daemon cleanup blocks sys.exit."""

    watchdog_active = False

    def _global_hard_kill() -> None:
        if watchdog_active:
            try:
                logging.warning(
                    "Global exit watchdog timed out (%ds); forcing process exit.",
                    timeout_seconds,
                )
            except Exception:
                pass
            os._exit(0)

    global_watchdog = threading.Timer(timeout_seconds, _global_hard_kill)
    global_watchdog.daemon = True

    try:
        ret_code = main_func()
        watchdog_active = True
        global_watchdog.start()
        _cleanup_browser_processes()
        logging.info("Main process exited normally, return code: %d", ret_code)
        sys.exit(ret_code)
    except KeyboardInterrupt:
        os._exit(0)
    except SystemExit:
        os._exit(0)
    except Exception:
        _cleanup_browser_processes()
        os._exit(1)
