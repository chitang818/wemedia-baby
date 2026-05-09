"""
将局部补丁深度合并进 app_config 并持久化，避免覆盖整份配置。
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

APP_CONFIG_FILENAME = "app_config.json"


def get_app_config_for_read() -> Dict[str, Any]:
    """优先使用已注册 ConfigCenter 内存中的 app_config；无注册时读磁盘 JSON。

    返回的 dict 在「有注册实例」时与 ``get_app_config()`` 为同一引用，调用方勿随意原地篡改；
    若需修改请通过 ``merge_app_config`` / ``update``。
    """
    from src.infrastructure.common.config.config_center import get_registered_config_center

    cc = get_registered_config_center()
    if cc is not None:
        return cc.get_app_config()
    return read_app_config_from_disk_sync()


def _deep_merge_inplace(out: Dict[str, Any], patch: Dict[str, Any]) -> None:
    for k, v in patch.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            _deep_merge_inplace(out[k], v)
        else:
            out[k] = copy.deepcopy(v)


def read_app_config_from_disk_sync() -> Dict[str, Any]:
    """同步读取用户目录下的 app_config.json（ConfigCenter 尚未初始化时使用）。"""
    from src.infrastructure.common.path_manager import PathManager

    p = Path(PathManager.get_config_dir()) / APP_CONFIG_FILENAME
    if not p.is_file():
        return {}
    try:
        raw = p.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("read_app_config_from_disk_sync 失败: %s", e)
        return {}


async def merge_app_config(cc: Optional[Any], patch: Dict[str, Any]) -> bool:
    """将 patch 深度合并进 app_config 并写盘。patch 顶层键为 app_config 中的键。

    Returns:
        是否已执行写入（ConfigCenter 不可用时返回 False）。
    """
    if cc is None:
        logger.warning("merge_app_config: ConfigCenter 不可用，跳过写入")
        return False
    if not patch:
        return True

    await cc.initialize()
    merged = copy.deepcopy(cc.get_app_config())
    _deep_merge_inplace(merged, patch)
    await cc.update("app_config", merged)
    return True


def merge_app_config_top_level_to_disk_sync(patch: Dict[str, Any]) -> bool:
    """将顶层键合并进用户目录 ``app_config.json``（同步）。

    用于退出路径、关闭到托盘等无法可靠跑 asyncio 的场景；并尽量同步已注册
    ``ConfigCenter`` 内存中的 ``app_config``，避免同进程内读到旧值。
    """
    from src.infrastructure.common.path_manager import PathManager

    if not patch:
        return True
    merged = copy.deepcopy(read_app_config_from_disk_sync())
    _deep_merge_inplace(merged, patch)
    p = Path(PathManager.get_config_dir()) / APP_CONFIG_FILENAME
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("已同步写入 app_config.json（顶层补丁）")
    except OSError as e:
        logger.warning("merge_app_config_top_level_to_disk_sync 写盘失败: %s", e)
        return False
    try:
        from src.infrastructure.common.config.config_center import get_registered_config_center

        cc = get_registered_config_center()
        if cc is not None:
            _deep_merge_inplace(cc.get_app_config(), patch)
    except Exception as e:
        logger.debug("同步 ConfigCenter 内存 app_config 失败: %s", e)
    return True


def merge_single_publish_partial_to_disk_sync(partial: Dict[str, Any]) -> bool:
    """将 ``single_publish`` 局部键合并进用户目录 ``app_config.json``（同步）。

    用于 ConfigCenter 尚未注册等场景，避免用户勾选后配置丢失。
    """
    from src.infrastructure.common.config.app_config_keys import KEY_SINGLE_PUBLISH
    from src.infrastructure.common.path_manager import PathManager

    if not partial:
        return True
    merged = copy.deepcopy(read_app_config_from_disk_sync())
    raw_sp = merged.get(KEY_SINGLE_PUBLISH)
    sp: Dict[str, Any] = copy.deepcopy(raw_sp) if isinstance(raw_sp, dict) else {}
    sp.update(partial)
    merged[KEY_SINGLE_PUBLISH] = sp
    p = Path(PathManager.get_config_dir()) / APP_CONFIG_FILENAME
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.debug("已同步写入 app_config.json（single_publish 局部键）")
        return True
    except OSError as e:
        logger.warning("merge_single_publish_partial_to_disk_sync 写盘失败: %s", e)
        return False


async def persist_single_publish_partial_async(partial: Dict[str, Any]) -> bool:
    """将 ``single_publish`` 下若干键写入配置中心并落盘；无 ConfigCenter 时回退为仅磁盘合并。

    与单视频页两个 SwitchButton、「声明原创」等偏好共用。
    """
    from src.infrastructure.common.config.app_config_keys import KEY_SINGLE_PUBLISH
    from src.infrastructure.common.config.config_center import get_registered_config_center

    if not partial:
        return True
    root = get_app_config_for_read()
    base = root.get(KEY_SINGLE_PUBLISH)
    sp: Dict[str, Any] = copy.deepcopy(base) if isinstance(base, dict) else {}
    sp.update(partial)

    cc = get_registered_config_center()
    if cc is not None:
        ok = await merge_app_config(cc, {KEY_SINGLE_PUBLISH: sp})
        if ok:
            return True
    if merge_single_publish_partial_to_disk_sync(partial):
        return True
    logger.warning("persist_single_publish_partial_async: ConfigCenter 与磁盘写入均未成功")
    return False
