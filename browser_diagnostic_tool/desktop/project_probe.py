"""Read-only project probes used by the standalone diagnostic tool."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_app_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "WeMediaBaby"
    return Path.home() / "AppData" / "Local" / "WeMediaBaby"


def browser_diagnostics_dir(platform: str, date_part: str, test_run_id: str) -> Path:
    return default_app_data_dir() / "debug" / "browser_diagnostics" / platform / date_part / test_run_id


def read_app_config(project_root: str | Path) -> dict[str, Any]:
    """Best-effort read of app config defaults without importing the main app."""

    root = Path(project_root)
    candidates = [
        root / "config" / "app_config.json",
        default_app_data_dir() / "config" / "app_config.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                return raw if isinstance(raw, dict) else {}
            except Exception:
                continue
    return {}


def build_desktop_launch_context(
    *,
    project_root: str | Path,
    platform: str,
    mode: str,
    account_hash: str = "",
    user_data_dir: str = "",
    controlled_by_playwright: bool | None = None,
    publish_automation_enabled: bool | None = None,
) -> dict[str, Any]:
    """Build a sanitized launch context using explicit values and read-only config."""

    cfg = read_app_config(project_root)
    chrome_executable = cfg.get("chrome_executable_path") if isinstance(cfg, dict) else ""
    return {
        "collector": "desktop_diagnostic",
        "platform": platform,
        "mode": mode,
        "account_hash": account_hash,
        "browser_factory_class": "BrowserFactory",
        "browser_manager_class": "UndetectedBrowserManager",
        "chrome_executable": chrome_executable or "",
        "user_data_dir": user_data_dir,
        "controlled_by_playwright": controlled_by_playwright,
        "publish_automation_enabled": publish_automation_enabled,
        "browser_scheme": cfg.get("browser_scheme", "playwright") if isinstance(cfg, dict) else "playwright",
    }

