"""Cleanup helpers for publish debug screenshots and diagnostic bundles."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def cleanup_debug_artifacts_older_than(days: int = 7) -> int:
    """Delete old debug screenshots and diagnostic bundle files.

    Returns the number of files deleted. Empty diagnostic directories are
    removed as housekeeping but are not counted.
    """
    from src.infrastructure.common.path_manager import PathManager

    cutoff = time.time() - max(1, int(days)) * 86400
    debug_root = PathManager.get_app_data_dir() / "debug"
    removed = 0

    screenshots_root = debug_root / "screenshots"
    if screenshots_root.is_dir():
        for path in screenshots_root.rglob("*.png"):
            if not path.is_file():
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError as exc:
                logger.debug("Skip deleting debug screenshot %s: %s", path, exc)

    diagnostics_root = debug_root / "diagnostics"
    if diagnostics_root.is_dir():
        for path in sorted(diagnostics_root.rglob("*"), reverse=True):
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
            except OSError as exc:
                logger.debug("Skip deleting diagnostic artifact %s: %s", path, exc)

    return removed


def cleanup_debug_screenshots_older_than(days: int = 7) -> int:
    """Backward-compatible wrapper for existing callers."""
    return cleanup_debug_artifacts_older_than(days=days)
