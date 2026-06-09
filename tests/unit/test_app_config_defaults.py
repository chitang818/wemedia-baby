"""app_config 默认骨架与 ConfigCenter 加载时补齐。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.infrastructure.common.config.app_config_defaults import (
    apply_app_config_defaults_inplace,
    default_app_config_skeleton,
)
from src.infrastructure.common.config.app_config_keys import (
    BROWSER_TRUST_MODE,
    BROWSER_TRUST_MODE_REAL,
    KEY_BATCH_PUBLISH,
    BATCH_PUBLISH_DESCRIPTION,
    BATCH_LOCATION,
    BATCH_LOCATION_POI_INFO,
    BATCH_LOCATION_WX_OPEN_PICKER,
    KEY_SINGLE_PUBLISH,
    SINGLE_COPYWRITING_MATCH_MODE,
    SINGLE_COPYWRITING_RANDOM_CATEGORY,
    START_IN_TRAY_NEXT_LAUNCH,
    MAIN_WINDOW_CLOSE_BEHAVIOR,
    PUBLISH_FORCE_VISIBLE_BROWSER,
    PUBLISH_RESPECT_PLATFORM_INTERVAL,
    PUBLISH_STOP_ON_RISK_PROMPT,
    XIAOHONGSHU_AUTO_CLICK_SUBMIT_HIGH_RISK,
    XIAOHONGSHU_LOGIN_BROWSER_MODE,
    XIAOHONGSHU_LOGIN_BROWSER_MODE_DETACHED_CHROME,
    XIAOHONGSHU_SYNC_AFTER_DETACHED_CLOSE,
)
from src.infrastructure.common.config.config_center import ConfigCenter

pytestmark = pytest.mark.unit


def test_apply_defaults_fills_only_missing_keys():
    cfg = {"material_library_root": "D:\\", "minimize_to_tray": True}
    assert apply_app_config_defaults_inplace(cfg) is True
    assert cfg["material_library_root"] == "D:\\"
    assert cfg["minimize_to_tray"] is True
    assert cfg.get("chrome_executable_path") == ""
    assert cfg[BROWSER_TRUST_MODE] == BROWSER_TRUST_MODE_REAL
    assert cfg[PUBLISH_FORCE_VISIBLE_BROWSER] is True
    assert cfg[PUBLISH_RESPECT_PLATFORM_INTERVAL] is True
    assert cfg[PUBLISH_STOP_ON_RISK_PROMPT] is True
    assert cfg[XIAOHONGSHU_LOGIN_BROWSER_MODE] == XIAOHONGSHU_LOGIN_BROWSER_MODE_DETACHED_CHROME
    assert cfg[XIAOHONGSHU_SYNC_AFTER_DETACHED_CLOSE] is True
    assert cfg[XIAOHONGSHU_AUTO_CLICK_SUBMIT_HIGH_RISK] is True
    assert KEY_BATCH_PUBLISH in cfg
    assert cfg[KEY_BATCH_PUBLISH][BATCH_LOCATION] == {
        BATCH_LOCATION_POI_INFO: "",
        BATCH_LOCATION_WX_OPEN_PICKER: False,
    }
    assert BATCH_PUBLISH_DESCRIPTION in cfg[KEY_BATCH_PUBLISH]
    assert cfg[KEY_SINGLE_PUBLISH][SINGLE_COPYWRITING_MATCH_MODE] == "standard"
    assert cfg[KEY_SINGLE_PUBLISH][SINGLE_COPYWRITING_RANDOM_CATEGORY] is None
    assert apply_app_config_defaults_inplace(cfg) is False


def test_apply_defaults_idempotent_on_full_skeleton():
    cfg = default_app_config_skeleton()
    assert apply_app_config_defaults_inplace(cfg) is False


def test_default_skeleton_has_expected_top_level_keys():
    sk = default_app_config_skeleton()
    assert set(sk.keys()) >= {
        "enabled_platform_plugins",
        "material_library_root",
        "chrome_executable_path",
        "browser_scheme",
        BROWSER_TRUST_MODE,
        PUBLISH_FORCE_VISIBLE_BROWSER,
        PUBLISH_RESPECT_PLATFORM_INTERVAL,
        PUBLISH_STOP_ON_RISK_PROMPT,
        XIAOHONGSHU_LOGIN_BROWSER_MODE,
        XIAOHONGSHU_SYNC_AFTER_DETACHED_CLOSE,
        XIAOHONGSHU_AUTO_CLICK_SUBMIT_HIGH_RISK,
        "minimize_to_tray",
        START_IN_TRAY_NEXT_LAUNCH,
        MAIN_WINDOW_CLOSE_BEHAVIOR,
        "auto_start",
        KEY_BATCH_PUBLISH,
        "single_publish",
        "publish_list",
        "ui",
    }
    assert sk[MAIN_WINDOW_CLOSE_BEHAVIOR] == "ask"


@pytest.mark.asyncio
async def test_config_center_partial_file_fills_memory_and_disk(tmp_path: Path):
    (tmp_path / "app_config.json").write_text(
        json.dumps({"material_library_root": "D:\\"}, ensure_ascii=False),
        encoding="utf-8",
    )
    cc = ConfigCenter(config_dir=str(tmp_path))
    try:
        await cc.initialize()
        app = cc.get_app_config()
        assert app["material_library_root"] == "D:\\"
        assert "chrome_executable_path" in app
        assert app["chrome_executable_path"] == ""
        assert "minimize_to_tray" in app
        assert app["minimize_to_tray"] is True
        on_disk = json.loads(
            (tmp_path / "app_config.json").read_text(encoding="utf-8")
        )
        assert "chrome_executable_path" in on_disk
        assert on_disk["material_library_root"] == "D:\\"
    finally:
        cc.close()


@pytest.mark.asyncio
async def test_config_center_preserves_user_values(tmp_path: Path):
    (tmp_path / "app_config.json").write_text(
        json.dumps(
            {"material_library_root": "", "minimize_to_tray": True},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cc = ConfigCenter(config_dir=str(tmp_path))
    try:
        await cc.initialize()
        assert cc.get_app_config()["minimize_to_tray"] is True
    finally:
        cc.close()


@pytest.mark.asyncio
async def test_config_center_missing_file_persists_skeleton(tmp_path: Path):
    cc = ConfigCenter(config_dir=str(tmp_path))
    try:
        await cc.initialize()
        p = tmp_path / "app_config.json"
        assert p.is_file()
        loaded = json.loads(p.read_text(encoding="utf-8"))
        assert "enabled_platform_plugins" in loaded
        assert KEY_BATCH_PUBLISH in loaded
        assert loaded[KEY_BATCH_PUBLISH][BATCH_LOCATION] == {
            BATCH_LOCATION_POI_INFO: "",
            BATCH_LOCATION_WX_OPEN_PICKER: False,
        }
        assert BATCH_PUBLISH_DESCRIPTION in loaded[KEY_BATCH_PUBLISH]
        assert loaded[KEY_SINGLE_PUBLISH][SINGLE_COPYWRITING_MATCH_MODE] == "standard"
        assert loaded[KEY_SINGLE_PUBLISH][SINGLE_COPYWRITING_RANDOM_CATEGORY] is None
        assert loaded.get("browser_scheme") == "patchright"
    finally:
        cc.close()
