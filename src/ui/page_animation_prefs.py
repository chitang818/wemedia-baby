"""
主界面页面切换动画偏好（堆栈位移动画 + BasePage 淡入）。

持久化：app_config.ui.page_animation_reduced
覆盖：环境变量 UI_PAGE_ANIMATION_REDUCED=1 / 0
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

# 与 MainWindow 默认一致；减弱模式用更短或关闭动画以减轻卡顿感
FULL_STACK_TRANSITION_MS = 180
REDUCED_STACK_TRANSITION_MS = 48

FULL_PAGE_FADE_MS = 220
REDUCED_PAGE_FADE_MS = 0


def _env_override_reduced() -> bool | None:
    raw = os.environ.get("UI_PAGE_ANIMATION_REDUCED", "").strip().lower()
    if raw in ("1", "true", "yes"):
        return True
    if raw in ("0", "false", "no"):
        return False
    return None


def is_page_animation_reduced() -> bool:
    env = _env_override_reduced()
    if env is not None:
        return env
    try:
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.infrastructure.common.config.config_center import ConfigCenter
        from src.infrastructure.common.config.app_config_keys import KEY_UI, UI_PAGE_ANIMATION_REDUCED

        cc = ServiceLocator().get(ConfigCenter)
        root = cc.get_app_config()
        ui = root.get(KEY_UI) or {}
        return bool(ui.get(UI_PAGE_ANIMATION_REDUCED, False))
    except Exception as e:
        logger.debug("读取页面动画偏好失败，使用默认: %s", e)
        return False


def get_stack_transition_duration_ms() -> int:
    return REDUCED_STACK_TRANSITION_MS if is_page_animation_reduced() else FULL_STACK_TRANSITION_MS


def get_page_fade_duration_ms() -> int:
    return REDUCED_PAGE_FADE_MS if is_page_animation_reduced() else FULL_PAGE_FADE_MS
