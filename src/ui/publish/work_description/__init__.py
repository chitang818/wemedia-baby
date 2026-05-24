# -*- coding: utf-8 -*-
"""作品描述 UI：轻量编辑器控制器 + 按需加载的配置弹窗。"""

from .work_description_edit_controller import WorkDescriptionEditController
from .work_declaration_prefs import (
    load_persisted_work_declaration,
    save_persisted_work_declaration,
)

_DIALOG_EXPORTS = {
    "LibraryFetchCoordinator",
    "PublishDescriptionDialog",
    "PublishDescriptionState",
    "clear_publish_description_dialog_session",
    "load_persisted_declare_original",
    "load_persisted_publish_description_prefs",
    "reset_persisted_publish_description_prefs",
    "save_persisted_declare_original",
    "save_persisted_publish_description_prefs",
}


def __getattr__(name: str):
    if name in _DIALOG_EXPORTS:
        from . import publish_description_dialog as dialog

        value = getattr(dialog, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "WorkDescriptionEditController",
    "PublishDescriptionDialog",
    "LibraryFetchCoordinator",
    "PublishDescriptionState",
    "load_persisted_declare_original",
    "save_persisted_declare_original",
    "load_persisted_work_declaration",
    "save_persisted_work_declaration",
    "load_persisted_publish_description_prefs",
    "save_persisted_publish_description_prefs",
    "clear_publish_description_dialog_session",
    "reset_persisted_publish_description_prefs",
]
