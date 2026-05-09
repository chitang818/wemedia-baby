# -*- coding: utf-8 -*-
"""
批量视频发布页 —「位置设置」偏好读写。

持久化在 app_config.batch_publish.location，经 ConfigCenter 合并写入（与自动匹配等批量偏好一致）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from src.infrastructure.common.config.config_center import get_registered_config_center
from src.infrastructure.common.config.app_config_keys import (
    BATCH_LOCATION,
    BATCH_LOCATION_POI_INFO,
    BATCH_LOCATION_WX_OPEN_PICKER,
    KEY_BATCH_PUBLISH,
)
from src.infrastructure.common.config.app_config_merge import merge_app_config, read_app_config_from_disk_sync

logger = logging.getLogger(__name__)


def _location_dict() -> Dict[str, Any]:
    cc = get_registered_config_center()
    if cc is not None:
        bp = cc.get_app_config().get(KEY_BATCH_PUBLISH)
        if isinstance(bp, dict):
            loc = bp.get(BATCH_LOCATION)
            if isinstance(loc, dict):
                return loc
        return {}
    root = read_app_config_from_disk_sync()
    bp = root.get(KEY_BATCH_PUBLISH)
    if not isinstance(bp, dict):
        return {}
    loc = bp.get(BATCH_LOCATION)
    return loc if isinstance(loc, dict) else {}


def load_batch_location_prefs() -> Tuple[str, bool]:
    """返回 (poi_info 存储串, 视频号空位是否点选「不显示位置」)。"""
    loc = _location_dict()
    poi = loc.get(BATCH_LOCATION_POI_INFO)
    wx = loc.get(BATCH_LOCATION_WX_OPEN_PICKER)
    poi_s = (poi if isinstance(poi, str) else "") or ""
    try:
        wx_b = bool(wx) if wx is not None else False
    except Exception:
        wx_b = False
    return poi_s, wx_b


def save_batch_location_prefs(poi_info: str, wechat_empty_location_open_picker: bool) -> None:
    """写入配置中心并落盘。"""
    from src.ui.utils.async_helper import run_async_from_ui

    poi_clean = poi_info if isinstance(poi_info, str) else (str(poi_info) if poi_info is not None else "")
    wx_b = bool(wechat_empty_location_open_picker)

    async def _save() -> None:
        cc = get_registered_config_center()
        bp_existing: Dict[str, Any] = {}
        if cc is not None:
            raw = cc.get_app_config().get(KEY_BATCH_PUBLISH)
            if isinstance(raw, dict):
                bp_existing = dict(raw)
        loc = dict(bp_existing.get(BATCH_LOCATION) or {})
        loc[BATCH_LOCATION_POI_INFO] = poi_clean
        loc[BATCH_LOCATION_WX_OPEN_PICKER] = wx_b
        bp_existing[BATCH_LOCATION] = loc
        await merge_app_config(cc, {KEY_BATCH_PUBLISH: bp_existing})

    try:
        run_async_from_ui(_save)
    except Exception as e:
        logger.warning("保存批量位置偏好失败: %s", e)
