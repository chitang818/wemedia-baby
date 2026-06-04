"""
app_config.json 默认骨架与「仅补缺失键」合并。

新增任何会持久化到 app_config 顶层的键时，须同步更新 ``default_app_config_skeleton()``，
否则升级后 JSON 仍可能缺少新键（参见 app_config_keys 模块说明）。
"""

from __future__ import annotations

import copy
from typing import Any, Dict

from src.domain.publish.work_declaration import (
    DEFAULT_DOUYIN_VALUE,
    DEFAULT_KUAISHOU_VALUE,
    DEFAULT_XHS_CONTENT_ATTR,
    KEY_DOUYIN,
    KEY_DOUYIN_AUTO,
    KEY_KUAISHOU,
    KEY_KUAISHOU_AUTO,
    KEY_XHS_CONTENT_ATTR,
    KEY_XHS_CONTENT_ATTR_AUTO,
    KEY_XHS_ORIGINAL,
)
from src.infrastructure.common.config.app_config_keys import (
    BATCH_PUBLISH_DESCRIPTION,
    BROWSER_TRUST_MODE,
    BROWSER_TRUST_MODE_REAL,
    BATCH_LOCATION,
    BATCH_LOCATION_POI_INFO,
    BATCH_LOCATION_WX_OPEN_PICKER,
    BATCH_WORK_DECLARATION,
    KEY_BATCH_PUBLISH,
    KEY_PUBLISH_DIAGNOSTICS,
    KEY_PUBLISH_LIST,
    KEY_SINGLE_PUBLISH,
    KEY_UI,
    PUBLISH_LIST_POST_PUBLISH_FILE_ACTION,
    PUBLISH_LIST_SHOW_BROWSER,
    PUBLISH_DIAGNOSTICS_CAPTURE_DOM_SUMMARY,
    PUBLISH_DIAGNOSTICS_CAPTURE_HTML,
    PUBLISH_DIAGNOSTICS_ENABLED,
    PUBLISH_DIAGNOSTICS_MAX_HTML_BYTES,
    PUBLISH_DIAGNOSTICS_RETENTION_DAYS,
    MAIN_WINDOW_CLOSE_BEHAVIOR,
    MAIN_WINDOW_CLOSE_REMIND,
    MAIN_WINDOW_CLOSE_REMEMBER_CHOICE,
    MAIN_WINDOW_CLOSE_ACTION,
    PUBLISH_FORCE_VISIBLE_BROWSER,
    PUBLISH_RESPECT_PLATFORM_INTERVAL,
    PUBLISH_STOP_ON_RISK_PROMPT,
    SINGLE_AUTO_MATCH_COPYWRITING,
    SINGLE_AUTO_MATCH_VIDEO_LIBRARY,
    SINGLE_COPYWRITING_MATCH_MODE,
    SINGLE_COPYWRITING_RANDOM_CATEGORY,
    SINGLE_DECLARE_ORIGINAL,
    START_IN_TRAY_NEXT_LAUNCH,
    UI_PAGE_ANIMATION_REDUCED,
    UI_STARTUP_PRELOADS,
    XIAOHONGSHU_AUTO_CLICK_SUBMIT_HIGH_RISK,
    XIAOHONGSHU_LOGIN_BROWSER_MODE,
    XIAOHONGSHU_LOGIN_BROWSER_MODE_DETACHED_CHROME,
    XIAOHONGSHU_SYNC_AFTER_DETACHED_CLOSE,
)

# 须与 src.utils.plugin_settings.get_default_enabled_platform_ids 默认返回值保持一致
_DEFAULT_ENABLED_PLATFORM_PLUGINS = ["douyin", "kuaishou", "wechat_video", "xiaohongshu"]


def default_app_config_skeleton() -> Dict[str, Any]:
    """权威顶层结构：标量/列表用空或安全默认值，业务分组用空对象占位。"""
    return {
        "enabled_platform_plugins": list(_DEFAULT_ENABLED_PLATFORM_PLUGINS),
        KEY_PUBLISH_DIAGNOSTICS: {
            PUBLISH_DIAGNOSTICS_ENABLED: True,
            PUBLISH_DIAGNOSTICS_CAPTURE_HTML: True,
            PUBLISH_DIAGNOSTICS_CAPTURE_DOM_SUMMARY: True,
            PUBLISH_DIAGNOSTICS_MAX_HTML_BYTES: 5_000_000,
            PUBLISH_DIAGNOSTICS_RETENTION_DAYS: 14,
        },
        "material_library_root": "",
        "chrome_executable_path": "",
        "browser_scheme": "playwright",
        BROWSER_TRUST_MODE: BROWSER_TRUST_MODE_REAL,
        PUBLISH_FORCE_VISIBLE_BROWSER: True,
        PUBLISH_RESPECT_PLATFORM_INTERVAL: True,
        PUBLISH_STOP_ON_RISK_PROMPT: True,
        XIAOHONGSHU_LOGIN_BROWSER_MODE: XIAOHONGSHU_LOGIN_BROWSER_MODE_DETACHED_CHROME,
        XIAOHONGSHU_SYNC_AFTER_DETACHED_CLOSE: True,
        XIAOHONGSHU_AUTO_CLICK_SUBMIT_HIGH_RISK: True,
        "minimize_to_tray": True,
        START_IN_TRAY_NEXT_LAUNCH: False,
        # 新版主窗口关闭行为默认：每次询问
        MAIN_WINDOW_CLOSE_BEHAVIOR: "ask",
        MAIN_WINDOW_CLOSE_REMIND: True,
        MAIN_WINDOW_CLOSE_REMEMBER_CHOICE: False,
        MAIN_WINDOW_CLOSE_ACTION: "minimize_to_tray",
        "auto_start": False,
        "show_environment_info_tab": False,
        KEY_BATCH_PUBLISH: {
            BATCH_LOCATION: {
                BATCH_LOCATION_POI_INFO: "",
                BATCH_LOCATION_WX_OPEN_PICKER: False,
            },
            BATCH_PUBLISH_DESCRIPTION: {
                "title": "",
                "desc": "",
                "apply_to_all_tasks": True,
                "use_library_title": False,
                "use_library_desc": False,
                "auto_match_enabled": False,
                "match_mode": "standard",
                "random_category_id": None,
                "copywriting_assign_strategy": "round_robin",
            },
            BATCH_WORK_DECLARATION: {
                KEY_DOUYIN: DEFAULT_DOUYIN_VALUE,
                KEY_KUAISHOU: DEFAULT_KUAISHOU_VALUE,
                KEY_DOUYIN_AUTO: False,
                KEY_KUAISHOU_AUTO: False,
                KEY_XHS_ORIGINAL: False,
                KEY_XHS_CONTENT_ATTR: DEFAULT_XHS_CONTENT_ATTR,
                KEY_XHS_CONTENT_ATTR_AUTO: False,
            },
        },
        KEY_SINGLE_PUBLISH: {
            SINGLE_DECLARE_ORIGINAL: False,
            SINGLE_AUTO_MATCH_VIDEO_LIBRARY: False,
            SINGLE_AUTO_MATCH_COPYWRITING: False,
            SINGLE_COPYWRITING_MATCH_MODE: "standard",
            SINGLE_COPYWRITING_RANDOM_CATEGORY: None,
        },
        KEY_PUBLISH_LIST: {
            PUBLISH_LIST_POST_PUBLISH_FILE_ACTION: "move",
            PUBLISH_LIST_SHOW_BROWSER: True,
        },
        KEY_UI: {
            UI_PAGE_ANIMATION_REDUCED: False,
            UI_STARTUP_PRELOADS: "off",
        },
    }


def apply_app_config_defaults_inplace(cfg: Dict[str, Any]) -> bool:
    """将骨架中缺失的键（含嵌套 dict 内缺失键）写入 cfg，不覆盖已有键值。

    Returns:
        是否曾写入任何缺失键（用于启动后将补全结果持久化到 app_config.json）。
    """
    if not isinstance(cfg, dict):
        return False
    return _fill_missing_from_skeleton_inplace(
        default_app_config_skeleton(), cfg
    )


def _fill_missing_from_skeleton_inplace(
    skeleton: Dict[str, Any], target: Dict[str, Any]
) -> bool:
    changed = False
    for k, skel_v in skeleton.items():
        if k not in target:
            target[k] = copy.deepcopy(skel_v)
            changed = True
            continue
        cur = target[k]
        if isinstance(skel_v, dict) and isinstance(cur, dict):
            if _fill_missing_from_skeleton_inplace(skel_v, cur):
                changed = True
    return changed
