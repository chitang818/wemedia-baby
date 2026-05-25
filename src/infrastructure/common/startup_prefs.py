"""启动期偏好：预加载模式等（环境变量优先，其次 app_config）。"""

from __future__ import annotations

import os
from typing import Any, Optional

# app_config.ui.startup_preloads: off | minimal | full
KEY_UI = "ui"
STARTUP_PRELOADS = "startup_preloads"

_VALID_MODES = frozenset({"off", "minimal", "full"})


def normalize_startup_preload_mode(mode: str | None) -> str:
    mode = (mode or "off").strip().lower()
    if mode in {"0", "false", "no", "off", "none", "disabled"}:
        return "off"
    if mode in {"1", "true", "yes", "full", "all"}:
        return "full"
    if mode == "minimal":
        return "minimal"
    return "off"


def _mode_from_app_config() -> Optional[str]:
    try:
        from src.infrastructure.common.config.app_config_merge import get_app_config_for_read

        ui = get_app_config_for_read().get(KEY_UI) or {}
        if not isinstance(ui, dict):
            return None
        raw = ui.get(STARTUP_PRELOADS)
        if raw is None:
            return None
        return normalize_startup_preload_mode(str(raw))
    except Exception:
        return None


def resolve_startup_preload_mode(*, explicit: str | None = None) -> str:
    """解析启动预加载模式：explicit > 环境变量 > app_config > 默认 off。"""
    if explicit is not None:
        return normalize_startup_preload_mode(explicit)
    env_raw = os.environ.get("WEMEDIABABY_STARTUP_PRELOADS")
    if env_raw is not None and str(env_raw).strip() != "":
        return normalize_startup_preload_mode(env_raw)
    from_config = _mode_from_app_config()
    if from_config is not None:
        return from_config
    return "off"


def startup_preload_timing() -> tuple[int, int]:
    """返回 (base_ms, step_ms)。"""
    def _env_int(name: str, default: int) -> int:
        raw = os.environ.get(name)
        if raw is None:
            return default
        try:
            return max(0, int(str(raw).strip()))
        except (TypeError, ValueError):
            return default

    return (
        _env_int("WEMEDIABABY_STARTUP_PRELOAD_BASE_MS", 8000),
        _env_int("WEMEDIABABY_STARTUP_PRELOAD_STEP_MS", 500),
    )


def startup_scheduler_delays_ms() -> dict[str, int]:
    """showEvent 后各启动检查/预热的默认延迟（毫秒）。"""
    return {
        "material_library_check": _env_int("WEMEDIABABY_STARTUP_MATERIAL_CHECK_MS", 1200),
        "chrome_check": _env_int("WEMEDIABABY_STARTUP_CHROME_CHECK_MS", 2000),
        "account_list_prewarm": _env_int("WEMEDIABABY_STARTUP_ACCOUNT_PREWARM_MS", 6000),
        "update_check": _env_int("WEMEDIABABY_STARTUP_UPDATE_CHECK_MS", 5000),
        "auto_login_delay": _env_int("WEMEDIABABY_STARTUP_AUTO_LOGIN_DELAY_MS", 400),
    }


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return max(0, int(str(raw).strip()))
    except (TypeError, ValueError):
        return default
