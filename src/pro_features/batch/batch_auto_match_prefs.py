"""
批量发布 - 自动从媒体库匹配素材的偏好读写
文件路径：src/pro_features/batch/batch_auto_match_prefs.py

持久化在 app_config.batch_publish.auto_match，通过 ConfigCenter 合并写入。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.infrastructure.common.config.config_center import get_registered_config_center
from src.infrastructure.common.config.app_config_keys import (
    KEY_BATCH_PUBLISH,
    BATCH_AUTO_MATCH,
    AUTO_MATCH_VIDEO_LIBRARY,
    AUTO_MATCH_IMAGE_LIBRARY,
)
from src.infrastructure.common.config.app_config_merge import merge_app_config, read_app_config_from_disk_sync

logger = logging.getLogger(__name__)


def _auto_match_dict() -> Dict[str, Any]:
    cc = get_registered_config_center()
    if cc is not None:
        bp = cc.get_app_config().get(KEY_BATCH_PUBLISH)
        if isinstance(bp, dict):
            am = bp.get(BATCH_AUTO_MATCH)
            if isinstance(am, dict):
                return am
        return {}
    root = read_app_config_from_disk_sync()
    bp = root.get(KEY_BATCH_PUBLISH)
    if not isinstance(bp, dict):
        return {}
    am = bp.get(BATCH_AUTO_MATCH)
    return am if isinstance(am, dict) else {}


def load_auto_match_pref(media_type: str = "video") -> bool:
    """读取指定媒体类型「自动从媒体库匹配素材」开关。

    Args:
        media_type: "video"（默认）或 "image"。
    """
    am = _auto_match_dict()
    key = AUTO_MATCH_VIDEO_LIBRARY if media_type == "video" else AUTO_MATCH_IMAGE_LIBRARY
    try:
        return bool(am.get(key, False))
    except Exception:
        return False


def save_auto_match_pref(checked: bool, media_type: str = "video") -> None:
    """保存指定媒体类型「自动从媒体库匹配素材」开关。"""
    from src.ui.utils.async_helper import run_async_from_ui

    key = AUTO_MATCH_VIDEO_LIBRARY if media_type == "video" else AUTO_MATCH_IMAGE_LIBRARY

    async def _save() -> None:
        cc = get_registered_config_center()
        bp_existing: Dict[str, Any] = {}
        if cc is not None:
            raw = cc.get_app_config().get(KEY_BATCH_PUBLISH)
            if isinstance(raw, dict):
                bp_existing = dict(raw)
        am = dict(bp_existing.get(BATCH_AUTO_MATCH) or {})
        am[key] = bool(checked)
        bp_existing[BATCH_AUTO_MATCH] = am
        await merge_app_config(cc, {KEY_BATCH_PUBLISH: bp_existing})

    try:
        run_async_from_ui(_save)
    except Exception as e:
        logger.warning("保存自动匹配开关失败 (media_type=%s): %s", media_type, e)
