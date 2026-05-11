# -*- coding: utf-8 -*-
"""作品描述 UI：单条页编辑器控制器 + 批量「配置描述」弹窗（与 ``domain.publish.work_description`` 配套）。"""

from .work_description_edit_controller import WorkDescriptionEditController
from .publish_description_dialog import (
    LibraryFetchCoordinator,
    PublishDescriptionDialog,
    PublishDescriptionState,
    clear_publish_description_dialog_session,
    load_persisted_declare_original,
    load_persisted_publish_description_prefs,
    load_persisted_work_declaration,
    reset_persisted_publish_description_prefs,
    save_persisted_declare_original,
    save_persisted_publish_description_prefs,
    save_persisted_work_declaration,
)

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
