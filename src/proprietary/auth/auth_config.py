"""
认证配置模块（闭源实现）
原路径：src/services/auth/auth_config.py
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_AUTH_CONFIG_CACHE = None


def _load_auth_config() -> dict:
    """从 config/auth_config.json 读取认证配置，带缓存。"""
    global _AUTH_CONFIG_CACHE
    if _AUTH_CONFIG_CACHE is not None:
        return _AUTH_CONFIG_CACHE
    candidates = [
        Path(__file__).resolve().parents[3] / "config" / "auth_config.json",
        Path.cwd() / "config" / "auth_config.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                _AUTH_CONFIG_CACHE = json.loads(p.read_text(encoding="utf-8"))
                return _AUTH_CONFIG_CACHE
            except Exception as e:
                logger.warning("读取 auth_config.json 失败: %s", e)
    _AUTH_CONFIG_CACHE = {}
    return _AUTH_CONFIG_CACHE


def get_auth_api_base() -> str:
    """
    获取认证接口 base URL。
    优先级：环境变量 AUTH_API_BASE > config/auth_config.json > 空字符串。
    环境变量显式设为空字符串时，表示禁用云端认证（用于测试或离线场景）。
    """
    if "AUTH_API_BASE" in os.environ:
        return os.environ.get("AUTH_API_BASE", "").strip().rstrip("/")
    cfg = _load_auth_config()
    return (cfg.get("auth_api_base") or "").strip().rstrip("/")


def is_cloud_auth_enabled() -> bool:
    """
    是否启用云端认证（即是否配置了有效的 AUTH_API_BASE）。
    若为 True，则 login/register 优先走云端；否则回退本地。
    """
    try:
        from config.feature_flags import FeatureFlags
        if FeatureFlags.is_52pojie():
            return False
    except Exception:
        pass

    base = get_auth_api_base()
    return bool(base and base.startswith("http"))

