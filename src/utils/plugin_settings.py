from __future__ import annotations

from typing import List, Optional, Sequence

from src.infrastructure.common.config.config_center import ConfigCenter
from src.plugins.core.plugin_manager import PluginManager


APP_CONFIG_KEY_ENABLED_PLUGINS = "enabled_platform_plugins"


def get_all_platform_ids() -> List[str]:
    """All platform ids known to PluginManager (no plugin import)."""
    return PluginManager.get_available_platforms()


def get_default_enabled_platform_ids() -> List[str]:
    """Default enabled platforms on first install.

    须与 app_config_defaults._DEFAULT_ENABLED_PLATFORM_PLUGINS 保持一致。
    """
    return ["douyin", "kuaishou", "wechat_video", "xiaohongshu"]


def _enabled_ids_from_app_dict(app: dict) -> List[str]:
    value = app.get(APP_CONFIG_KEY_ENABLED_PLUGINS)
    if not isinstance(value, list):
        return get_default_enabled_platform_ids()
    ids = [str(x) for x in value if isinstance(x, str) and x.strip()]
    if not ids:
        return get_default_enabled_platform_ids()
    return ids


def get_enabled_platform_ids(config_center: Optional[ConfigCenter] = None) -> List[str]:
    """读取已启用平台列表。

    ``config_center`` 为 None 时使用 ``get_app_config_for_read()``（注册单例或磁盘），
    避免新建未初始化的 ``ConfigCenter()`` 导致读到空配置。
    """
    if config_center is not None:
        app = config_center.get_app_config()
    else:
        from src.infrastructure.common.config.app_config_merge import get_app_config_for_read

        app = get_app_config_for_read()
    return _enabled_ids_from_app_dict(app)


async def set_enabled_platform_ids(config_center: ConfigCenter, ids: Sequence[str]) -> None:
    # 必须先加载磁盘上的完整 app_config，否则会写出「仅含插件列表」的 JSON，覆盖掉 material_library_root 等字段
    await config_center.initialize()
    app = {**config_center.get_app_config()}
    app[APP_CONFIG_KEY_ENABLED_PLUGINS] = sorted({str(x).strip() for x in ids if str(x).strip()})
    await config_center.update("app_config", app)


def is_platform_enabled(platform_id: str, *, config_center: Optional[ConfigCenter] = None) -> bool:
    """判断平台是否启用。未传 ``config_center`` 时与 ``get_enabled_platform_ids()`` 同源读取。"""
    enabled = set(get_enabled_platform_ids(config_center))
    return platform_id in enabled


def filter_enabled_platform_ids(all_ids: Sequence[str], enabled_ids: Sequence[str]) -> List[str]:
    enabled_set = set(enabled_ids)
    return [pid for pid in all_ids if pid in enabled_set]
