"""
发布失败诊断截图清理：删除用户数据目录下 debug/screenshots 中超过指定天数的 .png 文件。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_debug_screenshots_older_than(days: int = 7) -> int:
    """删除 {AppData}/debug/screenshots 下修改时间早于 cutoff 的 png。

    Returns:
        成功删除的文件数量
    """
    from src.infrastructure.common.path_manager import PathManager

    root = PathManager.get_app_data_dir() / "debug" / "screenshots"
    if not root.is_dir():
        return 0

    cutoff = time.time() - max(1, int(days)) * 86400
    removed = 0
    for path in root.rglob("*.png"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError as e:
            logger.debug("跳过删除诊断截图 %s: %s", path, e)

    return removed
