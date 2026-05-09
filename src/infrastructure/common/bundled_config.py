"""
内置资源 JSON 读取（随安装包分发的 config/ 等）。

通过 PathManager.get_resource_path 解析路径，兼容开发 / PyInstaller / Nuitka；
与用户数据目录 PathManager.get_config_dir() 无关。
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict

from src.infrastructure.common.path_manager import PathManager

logger = logging.getLogger(__name__)

# abs path str -> (mtime, parsed dict)
_json_cache: Dict[str, tuple[float, Dict[str, Any]]] = {}


def clear_bundled_json_cache() -> None:
    """清空进程内 JSON 缓存（供测试或热重载工具使用）。"""
    _json_cache.clear()


def bundled_file_path(relative_path: str) -> Path:
    """内置文件绝对路径。relative_path 为相对项目根，如 config/platforms/douyin.json。"""
    return PathManager.get_resource_path(relative_path)


def read_bundled_json(relative_path: str) -> Dict[str, Any]:
    """读取内置 JSON 对象；文件不存在或解析失败时返回 {}。

    使用 mtime 做进程内缓存，文件变更后自动失效；返回深拷贝避免调用方污染缓存。
    """
    path = bundled_file_path(relative_path)
    if not path.is_file():
        return {}
    try:
        mtime = path.stat().st_mtime
        key = str(path.resolve())
        hit = _json_cache.get(key)
        if hit is not None and hit[0] == mtime:
            return copy.deepcopy(hit[1])
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            data = {}
        _json_cache[key] = (mtime, data)
        return copy.deepcopy(data)
    except Exception as e:
        logger.debug("read_bundled_json 失败 %s: %s", relative_path, e)
        return {}


def load_platform_bundle(platform_id: str) -> Dict[str, Any]:
    """读取 config/platforms/{platform_id}.json。"""
    pid = (platform_id or "").strip()
    if not pid:
        return {}
    return read_bundled_json(f"config/platforms/{pid}.json")
