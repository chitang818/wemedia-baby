"""
app_config.json 默认骨架与「仅补缺失键」合并。

新增任何会持久化到 app_config 顶层的键时，须同步更新 ``default_app_config_skeleton()``，
否则升级后 JSON 仍可能缺少新键（参见 app_config_keys 模块说明）。
"""

from __future__ import annotations

import copy
from typing import Any, Dict

from src.infrastructure.common.config.app_config_keys import (
    BATCH_PUBLISH_DESCRIPTION,
    BATCH_LOCATION,
    BATCH_LOCATION_POI_INFO,
    BATCH_LOCATION_WX_OPEN_PICKER,
    KEY_BATCH_PUBLISH,
    KEY_PUBLISH_LIST,
    KEY_SINGLE_PUBLISH,
    KEY_UI,
    PUBLISH_LIST_POST_PUBLISH_FILE_ACTION,
    PUBLISH_LIST_SHOW_BROWSER,
    MAIN_WINDOW_CLOSE_BEHAVIOR,
    MAIN_WINDOW_CLOSE_REMIND,
    MAIN_WINDOW_CLOSE_REMEMBER_CHOICE,
    MAIN_WINDOW_CLOSE_ACTION,
    SINGLE_AUTO_MATCH_COPYWRITING,
    SINGLE_AUTO_MATCH_VIDEO_LIBRARY,
    SINGLE_COPYWRITING_MATCH_MODE,
    SINGLE_COPYWRITING_RANDOM_CATEGORY,
    SINGLE_DECLARE_ORIGINAL,
    START_IN_TRAY_NEXT_LAUNCH,
    UI_PAGE_ANIMATION_REDUCED,
)

# 须与 src.utils.plugin_settings.get_default_enabled_platform_ids 默认返回值保持一致
_DEFAULT_ENABLED_PLATFORM_PLUGINS = ["douyin", "kuaishou", "wechat_video"]


def default_app_config_skeleton() -> Dict[str, Any]:
    """权威顶层结构：标量/列表用空或安全默认值，业务分组用空对象占位。"""
    return {
        "enabled_platform_plugins": list(_DEFAULT_ENABLED_PLATFORM_PLUGINS),
        "material_library_root": "",
        "chrome_executable_path": "",
        "browser_scheme": "playwright",
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
