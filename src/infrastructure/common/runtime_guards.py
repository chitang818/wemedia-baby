from __future__ import annotations

import ctypes
import logging
import os
import sys


def _fatal_crash_log_file():
    from src.infrastructure.common.path_manager import PathManager

    return PathManager.get_log_dir() / "fatal_crash.log"


class DummyStream:
    def write(self, data):
        pass

    def flush(self):
        pass

    def fileno(self):
        import io

        raise io.UnsupportedOperation("fileno")

    @property
    def closed(self):
        return False


class StderrFilter:
    """Filter known harmless Qt/qasync shutdown noise from stderr."""

    _block_start_patterns = (
        "Exception ignored in atexit callback",
        "Task was destroyed but it is pending",
        "Task exception was never retrieved",
        "Future exception was never retrieved",
        "coroutine was never awaited",
        "RuntimeWarning: coroutine ",
        "Event loop stopped before Future completed",
        "Event loop is closed",
    )

    def __init__(self, original_stderr):
        self.original_stderr = original_stderr
        self.filtered_patterns = [
            "direct_composition_support.cc",
            "QueryInterface to IDCompositionDevice4 failed",
            "ERROR:direct_composition",
            "Exception ignored in atexit callback",
            "__moduleShutdown",
            "QWidgetItem",
            "already deleted",
            "eventFilter",
            "flow_layout.py",
            "style_sheet.py",
            "scroll_bar.py",
            "tool_tip.py",
            "Python override of QObject::eventFilter",
            "Python override of QLayout::eventFilter",
            "Python override of QWidget::eventFilter",
            "Internal C++ object",
            "if e.type() != QEvent.DynamicPropertyChange:",
            "if e.type() != QEvent.Type.Paint",
            "dirty-qss",
            "if obj is self.parent():",
            "if obj in [w.widget() for w in self._items]",
            "wrapped C/C++ object has been deleted",
            "RuntimeError: wrapped C/C++ object has been deleted",
            "if e.type() == QEvent.ToolTip:",
            "if e.type() == QEvent.Type.Wheel:",
            "if obj is not self.parent():",
            "Task was destroyed but it is pending",
            "Task exception was never retrieved",
            "Future exception was never retrieved",
            "coroutine was never awaited",
            "Event loop stopped before Future completed",
            "Event loop is closed",
            "asyncio.exceptions.CancelledError",
            "qasync",
            "QThreadStorage:",
            "destroyed before end of thread",
            "Enable tracemalloc to get the object allocation traceback",
        ]
        self._filtering_block = False

    def write(self, text):
        if not text or not self.original_stderr:
            return
        if any(p in text for p in self._block_start_patterns):
            self._filtering_block = True
            return
        if self._filtering_block:
            is_traceback_line = (
                text.startswith(" ")
                or text.startswith("\t")
                or text.startswith("File ")
                or text.startswith("Traceback ")
                or text.strip().startswith("File ")
                or "Traceback (most recent" in text
                or '  File "' in text
            )
            if text.strip() == "" and not is_traceback_line:
                self._filtering_block = False
            elif is_traceback_line or any(p in text for p in self.filtered_patterns):
                return
            else:
                self._filtering_block = False
        if not any(pattern in text for pattern in self.filtered_patterns):
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
        return getattr(self.original_stderr, name)


def configure_frozen_working_directory() -> None:
    if not getattr(sys, "frozen", False):
        return
    try:
        app_dir = os.path.dirname(os.path.abspath(sys.executable))
        if app_dir and os.path.isdir(app_dir):
            os.chdir(app_dir)
    except Exception:
        pass


def configure_qt_environment() -> None:
    os.environ.setdefault(
        "QT_LOGGING_RULES",
        "qt.webenginecontext.info=false;qt.webenginecontext.debug=false",
    )
    os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", "")
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "0")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-logging --log-level=3")
    # 禁用 Qt Multimedia FFmpeg 后端的硬件解码，防止加载特殊视频（如 HDR、高帧率等）时引发 C++ 段错误
    os.environ.setdefault("QT_FFMPEG_USE_HARDWARE_DECODING", "0")


def install_null_stdio() -> None:
    if sys.stdout is None:
        sys.stdout = DummyStream()
    if sys.stderr is None:
        sys.stderr = DummyStream()


def install_stderr_filter() -> None:
    sys.stderr = StderrFilter(sys.stderr)


def install_exception_hook() -> None:
    original_excepthook = sys.excepthook

    def _custom_excepthook(exc_type, exc_value, exc_tb):
        if exc_type is RuntimeError:
            msg = str(exc_value)
            if any(
                p in msg
                for p in (
                    "Event loop is closed",
                    "Event loop stopped",
                    "no running event loop",
                )
            ):
                return
            if any(
                pattern in msg
                for pattern in [
                    "QWidgetItem",
                    "already deleted",
                    "eventFilter",
                    "Python override of QObject::eventFilter",
                    "Python override of QLayout::eventFilter",
                    "wrapped C/C++ object",
                ]
            ):
                return
        if getattr(exc_type, "__name__", "") == "CancelledError":
            return

        try:
            import datetime
            import traceback

            crash_file = _fatal_crash_log_file()
            time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            with open(crash_file, "a", encoding="utf-8") as f:
                f.write(f"\n[{time_str}] FATAL CRASH:\n{err_msg}\n")

            from PySide6.QtWidgets import QApplication, QMessageBox

            app_inst = QApplication.instance()
            if app_inst:
                dlg_parent = app_inst.activeModalWidget() or app_inst.focusWidget()
  # type: ignore
  # type: ignore
                body = (
                    "应用发生未捕获的严重异常，程序可能不稳定或即将退出。\n\n"
                    f"详情已记录到:\n{crash_file}\n\n错误信息:\n{exc_value}"
                )
                try:
                    from src.ui.utils.fluent_dialogs import show_error

                    show_error(dlg_parent, "应用发生严重错误", body)
                except Exception:
                    QMessageBox.critical(dlg_parent, "应用发生严重错误", body)
        except Exception as e:
            logging.getLogger("main").exception(
                "写入崩溃日志或弹窗时发生异常: %s",
                e,
            )

        original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _custom_excepthook


def install_windows_crash_handler() -> None:
    try:
        import datetime
        import threading

        set_unhandled_exception_filter = ctypes.windll.kernel32.SetUnhandledExceptionFilter
        set_unhandled_exception_filter.restype = ctypes.c_void_p

        exception_codes = {
            0xC0000005: "ACCESS_VIOLATION",
            0xC0000094: "INTEGER_DIVIDE_BY_ZERO",
            0xC00000FD: "STACK_OVERFLOW",
            0xC0000017: "NO_MEMORY",
            0x80000003: "BREAKPOINT",
            0xC0000409: "STACK_BUFFER_OVERRUN",
        }

        @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
        def _seh_handler(exception_pointers):
            try:
                exc_record_ptr = ctypes.cast(exception_pointers, ctypes.POINTER(ctypes.c_void_p))[0]
                exc_code = ctypes.cast(exc_record_ptr, ctypes.POINTER(ctypes.c_uint32))[0]
                code_desc = exception_codes.get(exc_code, f"UNKNOWN 0x{exc_code:08X}")

                crash_file = _fatal_crash_log_file()
                time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                thread_name = threading.current_thread().name

                mem_info = ""
                try:
                    import psutil

                    proc = psutil.Process(os.getpid())
                    mem_mb = proc.memory_info().rss / 1024 / 1024
                    mem_info = f"  memory: {mem_mb:.1f} MB\n"
                except Exception:
                    pass

                with open(crash_file, "a", encoding="utf-8") as f:
                    f.write(
                        f"\n[{time_str}] WINDOWS SEH CRASH:\n"
                        f"  exception: 0x{exc_code:08X} - {code_desc}\n"
                        f"  thread: {thread_name}\n"
                        f"{mem_info}"
                    )
            except Exception:
                pass
            return 0

  # type: ignore
        install_windows_crash_handler._handler_ref = _seh_handler
  # type: ignore
        set_unhandled_exception_filter(_seh_handler)
    except Exception:
        pass


def patch_qframelesswindow() -> None:
    try:
        import pywintypes
        import qframelesswindow.utils.win32_utils as win32_utils

        original_is_full_screen = win32_utils.isFullScreen

        def safe_is_full_screen(hwnd):
            try:
                return original_is_full_screen(hwnd)
            except pywintypes.error:
                return False
  # type: ignore

        win32_utils.isFullScreen = safe_is_full_screen
  # type: ignore
    except Exception:
        pass


def install_crash_handlers() -> None:
    install_exception_hook()
    if sys.platform == "win32":
        install_windows_crash_handler()
        patch_qframelesswindow()


def install_asyncio_exception_handler(loop) -> None:
    def custom_exception_handler(_loop, context):
        exc = context.get("exception")
        msg = exc if exc is not None else context.get("message", "")
        text = str(msg)
        low = text.lower()

        if "unclosed client session" in low:
            return

        if exc is not None:
            benign_closed = ("target page" in low and "closed" in low) or (
                "context or browser has been closed" in low
            )
            if benign_closed:
                logging.getLogger("asyncio").debug(
                    "[Asyncio expected] browser/page already closed: %s",
                    text,
                )
                return

        logging.error("[Asyncio unhandled exception]: %s", msg)

        try:
            import datetime

            with open(_fatal_crash_log_file(), "a", encoding="utf-8") as f:
                time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n[{time_str}] ASYNC ERROR:\n{context}\n")
        except Exception:
            pass

    loop.set_exception_handler(custom_exception_handler)
