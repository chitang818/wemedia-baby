"""Browser launch policy for publishing and account browser sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from src.infrastructure.common.config.app_config_keys import (
    BROWSER_TRUST_MODE_REAL,
)
from src.infrastructure.common.config.app_config_merge import get_app_config_for_read


@dataclass(frozen=True)
class BrowserLaunchPolicy:
    trust_mode: str = BROWSER_TRUST_MODE_REAL
    force_visible_publish: bool = True
    respect_platform_interval: bool = True
    stop_on_risk_prompt: bool = True

    @property
    def use_compat_stealth(self) -> bool:
        return False

    @property
    def use_real_browser(self) -> bool:
        return not self.use_compat_stealth


def _read_app_config() -> Dict[str, Any]:
    try:
        cfg = get_app_config_for_read()
        return cfg if isinstance(cfg, dict) else {}
    except Exception:
        return {}


def get_browser_launch_policy() -> BrowserLaunchPolicy:
    # Legacy browser safety keys remain readable during migration, but no longer
    # alter runtime behavior. Publishing always uses visible, standard Chrome.
    _read_app_config()
    return BrowserLaunchPolicy(
        trust_mode=BROWSER_TRUST_MODE_REAL,
        force_visible_publish=True,
        respect_platform_interval=False,
        stop_on_risk_prompt=True,
    )


def should_force_visible_publish_browser() -> bool:
    return get_browser_launch_policy().force_visible_publish


def should_respect_platform_publish_interval() -> bool:
    # 应用户要求，不再使用平台兜底限制，统一只参考界面的发布设置
    return False


def should_stop_on_risk_prompt() -> bool:
    return get_browser_launch_policy().stop_on_risk_prompt
