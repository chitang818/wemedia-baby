# -*- coding: utf-8 -*-
"""Lightweight persisted work-declaration preferences."""

from __future__ import annotations

import logging

from src.infrastructure.common.config.config_center import get_registered_config_center
from src.infrastructure.common.config.app_config_keys import (
    KEY_BATCH_PUBLISH,
    BATCH_WORK_DECLARATION,
)
from src.infrastructure.common.config.app_config_merge import (
    merge_app_config,
    read_app_config_from_disk_sync,
)

logger = logging.getLogger(__name__)


def _batch_publish_root() -> dict:
    cc = get_registered_config_center()
    if cc is not None:
        bp = cc.get_app_config().get(KEY_BATCH_PUBLISH)
        if isinstance(bp, dict):
            return bp
        return {}
    root = read_app_config_from_disk_sync()
    bp = root.get(KEY_BATCH_PUBLISH)
    return bp if isinstance(bp, dict) else {}


def _batch_publish_root_for_write() -> dict:
    return dict(_batch_publish_root())


def _read_pref_bool(raw: object, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return raw != 0
    if isinstance(raw, str):
        t = raw.strip().lower()
        if t in ("1", "true", "yes", "on"):
            return True
        if t in ("0", "false", "no", "off", ""):
            return False
    try:
        return bool(raw)
    except Exception:
        return default


def load_persisted_work_declaration() -> dict:
    """Read declaration options shared by single and batch publish pages."""
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
        normalize_douyin_value,
        normalize_kuaishou_value,
        normalize_xhs_content_attr,
    )

    bp = _batch_publish_root()
    wd = bp.get(BATCH_WORK_DECLARATION)
    if not isinstance(wd, dict):
        return {
            KEY_DOUYIN: DEFAULT_DOUYIN_VALUE,
            KEY_KUAISHOU: DEFAULT_KUAISHOU_VALUE,
            KEY_DOUYIN_AUTO: False,
            KEY_KUAISHOU_AUTO: False,
            KEY_XHS_ORIGINAL: False,
            KEY_XHS_CONTENT_ATTR: DEFAULT_XHS_CONTENT_ATTR,
            KEY_XHS_CONTENT_ATTR_AUTO: False,
        }
    return {
        KEY_DOUYIN: normalize_douyin_value(str(wd.get(KEY_DOUYIN) or "") or None),
        KEY_KUAISHOU: normalize_kuaishou_value(str(wd.get(KEY_KUAISHOU) or "") or None),
        KEY_DOUYIN_AUTO: _read_pref_bool(wd.get(KEY_DOUYIN_AUTO), False),
        KEY_KUAISHOU_AUTO: _read_pref_bool(wd.get(KEY_KUAISHOU_AUTO), False),
        KEY_XHS_ORIGINAL: _read_pref_bool(wd.get(KEY_XHS_ORIGINAL), False),
        KEY_XHS_CONTENT_ATTR: normalize_xhs_content_attr(
            str(wd.get(KEY_XHS_CONTENT_ATTR) or "") or None
        ),
        KEY_XHS_CONTENT_ATTR_AUTO: _read_pref_bool(wd.get(KEY_XHS_CONTENT_ATTR_AUTO), False),
    }


def save_persisted_work_declaration(d: dict) -> None:
    """Persist declaration options without importing the publish-description dialog."""
    from src.domain.publish.work_declaration import (
        KEY_DOUYIN,
        KEY_DOUYIN_AUTO,
        KEY_KUAISHOU,
        KEY_KUAISHOU_AUTO,
        KEY_XHS_CONTENT_ATTR,
        KEY_XHS_CONTENT_ATTR_AUTO,
        KEY_XHS_ORIGINAL,
    )
    from src.ui.utils.async_helper import run_async_from_ui

    async def _save() -> None:
        bp = _batch_publish_root_for_write()
        cur = bp.get(BATCH_WORK_DECLARATION)
        merged = dict(cur) if isinstance(cur, dict) else {}
        if isinstance(d, dict):
            if KEY_DOUYIN in d:
                merged[KEY_DOUYIN] = d[KEY_DOUYIN]
            if KEY_KUAISHOU in d:
                merged[KEY_KUAISHOU] = d[KEY_KUAISHOU]
            if KEY_DOUYIN_AUTO in d:
                merged[KEY_DOUYIN_AUTO] = bool(d[KEY_DOUYIN_AUTO])
            if KEY_KUAISHOU_AUTO in d:
                merged[KEY_KUAISHOU_AUTO] = bool(d[KEY_KUAISHOU_AUTO])
            if KEY_XHS_ORIGINAL in d:
                merged[KEY_XHS_ORIGINAL] = bool(d[KEY_XHS_ORIGINAL])
            if KEY_XHS_CONTENT_ATTR in d:
                merged[KEY_XHS_CONTENT_ATTR] = str(d[KEY_XHS_CONTENT_ATTR] or "")
            if KEY_XHS_CONTENT_ATTR_AUTO in d:
                merged[KEY_XHS_CONTENT_ATTR_AUTO] = bool(d[KEY_XHS_CONTENT_ATTR_AUTO])
        bp[BATCH_WORK_DECLARATION] = merged
        ok = await merge_app_config(get_registered_config_center(), {KEY_BATCH_PUBLISH: bp})
        if not ok:
            logger.warning("保存作品申明失败: ConfigCenter 不可用")

    try:
        run_async_from_ui(_save)
    except Exception as e:
        logger.warning("保存作品申明失败: %s", e)
