"""Application entry point for WeMediaBaby."""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.infrastructure.common.app_bootstrap import (
    apply_picker_patches,
    configure_windows_app_user_model_id,
    create_application,
    initialize_theme_manager,
    set_application_icon,
)
from src.infrastructure.common.app_runtime import run_desktop_runtime
from src.infrastructure.common.runtime_guards import (
    StderrFilter,
    configure_frozen_working_directory,
    configure_qt_environment,
    install_asyncio_exception_handler,
    install_crash_handlers,
    install_null_stdio,
    install_stderr_filter,
)
from src.infrastructure.common.service_bootstrap import initialize_services_async
from src.infrastructure.common.shutdown import run_with_global_exit_watchdog
from src.infrastructure.common.single_instance import (
    another_instance_is_running,
    create_single_instance_server,
)


configure_frozen_working_directory()
configure_qt_environment()
install_null_stdio()
install_crash_handlers()
install_stderr_filter()


def main() -> int:
    """Run the Qt/qasync desktop application."""

    import asyncio

    import qasync

    original_stderr = sys.stderr
    sys.stderr = StderrFilter(original_stderr)

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

        async def run_app() -> int:
            if not await initialize_services_async():
                logging.error("Service initialization failed; exiting.")
                return 1

            from src.infrastructure.common.async_task_registry import (
                get_async_task_registry,
            )

            return await run_desktop_runtime(
                app=app,
                local_server=local_server,
                loop=loop,
                task_registry=get_async_task_registry(),
            )

        try:
            return loop.run_until_complete(run_app())
        except asyncio.CancelledError:
            logging.debug("Application exited normally after qasync cancellation.")
            return 0
        except RuntimeError as e:
            if "Event loop stopped before Future completed" in str(e):
                logging.debug("Application exited normally after event loop stop.")
                return 0
            raise
        finally:
            try:
                if not loop.is_closed():
                    loop.close()
            except Exception:
                pass
    except Exception as e:
        logging.error("Application startup failed: %s", e, exc_info=True)
        return 1
    finally:
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
