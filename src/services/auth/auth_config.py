"""
认证配置模块（开源包装层）

说明：
- 若存在闭源目录 `src/proprietary/`，则优先加载闭源实现；
- 若不存在（开源仓库/社区版），则默认禁用云端认证，避免因缺失闭源模块导致崩溃。
"""

from __future__ import annotations

import os
from typing import Callable


def _load_impl() -> tuple[Callable[[], str], Callable[[], bool]]:
    try:
        from src.proprietary.auth.auth_config import get_auth_api_base, is_cloud_auth_enabled
        return get_auth_api_base, is_cloud_auth_enabled
    except Exception:
        # 开源版默认：不启用云端认证（由闭源版提供）
        def _base() -> str:
            if "AUTH_API_BASE" in os.environ:
                return os.environ.get("AUTH_API_BASE", "").strip().rstrip("/")
            return ""

        def _enabled() -> bool:
            return False

        return _base, _enabled


get_auth_api_base, is_cloud_auth_enabled = _load_impl()

