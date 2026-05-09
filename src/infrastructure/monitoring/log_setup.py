"""
日志初始化模块
文件路径：src/infrastructure/monitoring/log_setup.py
功能：初始化应用程序日志配置
"""

import atexit
import os
import sys
import logging
import io
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path


def _ensure_utf8_stdio() -> None:
    """确保 stdout/stderr 可输出任意 Unicode（含 emoji），避免 Windows 默认 GBK 导致 UnicodeEncodeError。"""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        # Python 3.7+ 支持 reconfigure；在 Windows 上可强制 utf-8 并容错输出
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
                continue
            except Exception:
                pass
        # 兜底：若是文本流但无 reconfigure，则用其底层 buffer 重新包一层
        buf = getattr(stream, "buffer", None)
        if buf is not None:
            try:
                wrapped = io.TextIOWrapper(buf, encoding="utf-8", errors="backslashreplace", write_through=True)
                setattr(sys, name, wrapped)
            except Exception:
                pass


class _TeeTextStream:
    """同时写入原流与镜像文件（用于可选的终端镜像，避免 print 类输出只在控制台）。"""

    def __init__(self, primary, mirror_file):
        self._primary = primary
        self._mirror = mirror_file

    def write(self, data):
        try:
            self._primary.write(data)
        finally:
            try:
                self._mirror.write(data)
                self._mirror.flush()
            except Exception:
                pass

    def flush(self):
        try:
            self._primary.flush()
        except Exception:
            pass
        try:
            self._mirror.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._primary, name)


def _mirror_console_enabled() -> bool:
    v = os.environ.get("WEMEDIA_MIRROR_CONSOLE", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _maybe_install_console_mirror(log_dir: str, root_logger: logging.Logger) -> None:
    """源码运行时可选：把 stdout/stderr 镜像到 console_mirror.log（需设置环境变量 WEMEDIA_MIRROR_CONSOLE=1）。"""
    if getattr(sys, "frozen", False):
        return
    if not _mirror_console_enabled():
        return
    path = Path(log_dir) / "console_mirror.log"
    mirror_f = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    try:
        mirror_f.write(f"\n{'=' * 60}\n[{datetime.now().isoformat(timespec='seconds')}] 终端镜像会话开始\n")
        mirror_f.flush()
    except Exception:
        pass

    def _close_mirror():
        try:
            mirror_f.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] 终端镜像会话结束\n")
            mirror_f.flush()
        except Exception:
            pass
        try:
            mirror_f.close()
        except Exception:
            pass

    atexit.register(_close_mirror)

    orig_out = sys.stdout
    orig_err = sys.stderr
    sys.stdout = _TeeTextStream(orig_out, mirror_f)
    sys.stderr = _TeeTextStream(orig_err, mirror_f)
    for h in root_logger.handlers:
        if isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is orig_out:
            h.setStream(sys.stdout)


def init_log_manager(
    log_dir: str = "logs", 
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    app_name: str = "qasync_app"
) -> logging.Logger:
    """初始化日志管理器
    
    Args:
        log_dir: 日志目录
        console_level: 控制台日志级别
        file_level: 文件日志级别
        app_name: 应用名称
        
    Returns:
        Root Logger
    """
    # 确保日志目录存在
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # 确保控制台输出编码为 UTF-8（避免 emoji/特殊字符触发 UnicodeEncodeError）
    _ensure_utf8_stdio()
    
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 根记录器捕获所有，由Handler过滤
    
    # 清除现有 Handler（避免重复注册导致日志输出多份）
    # 过滤掉非 basicConfig 留下的 StreamHandler，仅保留完整的自定义 Handler 列表
    root_logger.handlers.clear()
    
    # 定义日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 1. 控制台 Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 2. 文件 Handler (按大小轮转) - app.log
    # 单文件刻意保持较小，便于人工与 AI 分块阅读；靠多份备份保留足够历史
    max_bytes = 2 * 1024 * 1024  # 2MB/文件
    backup_count = 30
    file_path = os.path.join(log_dir, f"{app_name}.log")
    file_handler = RotatingFileHandler(
        file_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # 3. 错误日志 Handler (按天轮转) - error.log
    error_path = os.path.join(log_dir, "error.log")
    error_handler = TimedRotatingFileHandler(
        error_path,
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # 抑制部分嘈杂库的日志
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("tortoise").setLevel(logging.WARNING)
    
    # 记录启动信息
    logging.info(f"日志系统初始化完成: console={logging.getLevelName(console_level)}, file={logging.getLevelName(file_level)}")
    logging.info(
        "主日志文件轮转: 单文件约 %sMB，最多保留 %s 个备份（qasync_app.log, .1, .2 …）",
        max_bytes // (1024 * 1024),
        backup_count,
    )

    _maybe_install_console_mirror(log_dir, root_logger)

    return root_logger
