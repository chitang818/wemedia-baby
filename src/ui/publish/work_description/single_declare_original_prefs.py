# -*- coding: utf-8 -*-
"""单条发布页「声明原创」勾选持久化（视频号）。"""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.infrastructure.common.config.app_config_keys import (
    KEY_SINGLE_PUBLISH,
    SINGLE_DECLARE_ORIGINAL,
)
from src.infrastructure.common.config.app_config_merge import (
    persist_single_publish_partial_async,
    read_app_config_from_disk_sync,
)
from src.ui.utils.async_helper import run_async_from_ui

logger = logging.getLogger(__name__)


def _single_publish_root() -> Dict[str, Any]:
    root = read_app_config_from_disk_sync()
    sp = root.get(KEY_SINGLE_PUBLISH)
    return sp if isinstance(sp, dict) else {}


def load_persisted_single_declare_original() -> bool:
    """读取单条任务页「声明原创」；无记录时默认 False。"""
    sp = _single_publish_root()
    if SINGLE_DECLARE_ORIGINAL not in sp:
        return False
    try:
        v = sp.get(SINGLE_DECLARE_ORIGINAL)
        return bool(v) and str(v).lower() not in ("0", "false", "")
    except Exception:
        logger.debug("读取单个发布声明原创失败", exc_info=True)
        return False


def save_persisted_single_declare_original(checked: bool) -> None:
    """保存单条任务页「声明原创」勾选。"""

    async def _save() -> None:
        try:
            await persist_single_publish_partial_async(
                {SINGLE_DECLARE_ORIGINAL: bool(checked)}
            )
        except Exception as e:
            logger.warning("写入 single_publish 配置失败: %s", e, exc_info=True)

    try:
        run_async_from_ui(_save)
    except Exception as e:
        logger.warning("调度 single_publish 配置写入失败: %s", e)
