from __future__ import annotations

import json

from browser_diagnostic_tool.desktop.project_probe import build_desktop_launch_context, read_app_config


def test_read_app_config_prefers_project_config(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "app_config.json").write_text(
        json.dumps({"chrome_executable_path": "C:/Chrome/chrome.exe", "browser_scheme": "playwright"}),
        encoding="utf-8",
    )

    assert read_app_config(tmp_path)["chrome_executable_path"] == "C:/Chrome/chrome.exe"


def test_build_desktop_launch_context_shape(tmp_path) -> None:
    ctx = build_desktop_launch_context(
        project_root=tmp_path,
        platform="xiaohongshu",
        mode="wmb_auto",
        account_hash="abc",
        user_data_dir="C:/Users/demo/AppData/Local/WeMediaBaby/data/xhs/user_data",
        controlled_by_playwright=True,
        publish_automation_enabled=True,
    )

    assert ctx["collector"] == "desktop_diagnostic"
    assert ctx["browser_factory_class"] == "BrowserFactory"
    assert ctx["browser_manager_class"] == "UndetectedBrowserManager"
    assert ctx["controlled_by_playwright"] is True

