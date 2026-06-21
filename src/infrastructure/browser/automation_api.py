"""Unified Patchright browser automation API.

Production browser automation must import from this module instead of
``playwright.async_api`` so Patchright is the only runtime engine.
"""

from __future__ import annotations

import os
import sys


def _ensure_patchright_node_path() -> None:
    """打包环境下修正 Patchright node.exe 路径。

    Patchright 通过 inspect.getfile(patchright) 定位 driver/node.exe，
    但 Nuitka 编译后该路径可能失效。此函数在打包环境中自动检测并设置
    PLAYWRIGHT_NODEJS_PATH 环境变量，使 patchright 能正确找到 node.exe。
    """
    # 仅在未手动设置且处于打包环境时执行
    if os.environ.get("PLAYWRIGHT_NODEJS_PATH"):
        return
    is_frozen = getattr(sys, "frozen", False) or "__compiled__" in dir()
    if not is_frozen:
        return

    # 打包后 exe 所在目录即为应用根目录
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidate = os.path.join(app_dir, "patchright", "driver", "node.exe")
    if os.path.isfile(candidate):
        os.environ["PLAYWRIGHT_NODEJS_PATH"] = candidate


_ensure_patchright_node_path()

try:
    from patchright.async_api import (
        Browser,
        BrowserContext,
        Locator,
        Page,
        Playwright,
        TimeoutError,
        async_playwright,
        expect,
    )
except ImportError as exc:  # pragma: no cover - depends on installation state
    raise RuntimeError(
        "Patchright is required for WeMediaBaby browser automation. "
        "Install dependencies with `pip install -r requirements.txt`."
    ) from exc

ENGINE_NAME = "patchright"
_START_PATCHRIGHT = async_playwright


async def start_patchright() -> Playwright:
    """Start the required Patchright runtime."""
    return await _START_PATCHRIGHT().start()

__all__ = [
    "Browser",
    "BrowserContext",
    "ENGINE_NAME",
    "Locator",
    "Page",
    "Playwright",
    "TimeoutError",
    "async_playwright",
    "expect",
    "start_patchright",
]
