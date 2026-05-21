# -*- coding: utf-8 -*-
"""
批量视频页 — 任务预览表格右键菜单（打开文件 / 打开所在文件夹 / 删除选中任务）
文件路径：src/pro_features/batch/menus/batch_preview_context_menu.py
"""

from PySide6.QtCore import QObject, QPoint
from PySide6.QtWidgets import QWidget, QMenu

try:
    from qfluentwidgets import RoundMenu, Action, FluentIcon

    _FLUENT = True
except ImportError:
    _FLUENT = False

from src.ui.components.fluent_context_menu import (
    install_round_menu_close_on_app_inactive,
    is_round_menu_alive,
    round_menu_parent,
)


class BatchPreviewContextMenu(QObject):
    """复用 RoundMenu + Action，与《右键菜单标准化规范》一致。"""

    def __init__(self, page: QWidget):
        super().__init__(page)
        self._page = page
        self._menu = None
        self._act_open_file = None
        self._act_open_folder = None
        self._act_delete = None

    def _open_action_flags(self) -> tuple:
        fn = getattr(self._page, "_batch_preview_ctx_open_flags", None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                return False, False
        return False, False

    def _ensure_fluent(self) -> bool:
        if not _FLUENT:
            return False
        if self._menu is not None and is_round_menu_alive(self._menu):
            return True
        parent = round_menu_parent(self._page)
        if parent is None:
            return False
        self._menu = RoundMenu(parent=parent)
        self._act_open_file = Action(FluentIcon.DOCUMENT, "打开文件", parent)
        self._act_open_file.setToolTip(
            "使用系统默认程序打开；视频用默认播放器播放"
        )
        self._act_open_file.triggered.connect(self._trigger_open_file)
        self._act_open_folder = Action(FluentIcon.FOLDER, "打开所在文件夹", parent)
        self._act_open_folder.triggered.connect(self._trigger_open_folder)
        self._menu.addAction(self._act_open_file)
        self._menu.addAction(self._act_open_folder)
        self._menu.addSeparator()
        self._act_delete = Action(FluentIcon.DELETE, "删除选中任务", parent)
        self._act_delete.triggered.connect(self._trigger_delete)
        self._menu.addAction(self._act_delete)
        install_round_menu_close_on_app_inactive(self._menu)
        return True

    def _trigger_open_file(self) -> None:
        fn = getattr(self._page, "_on_preview_open_file", None)
        if not callable(fn):
            fn = getattr(self._page, "_on_preview_open_video_file", None)
        if callable(fn):
            fn()

    def _trigger_open_folder(self) -> None:
        fn = getattr(self._page, "_on_preview_open_video_folder", None)
        if callable(fn):
            fn()

    def _trigger_delete(self) -> None:
        fn = getattr(self._page, "_on_preview_delete_selected", None)
        if callable(fn):
            fn()

    def exec_at(self, global_pos: QPoint, fallback_parent: QWidget) -> None:
        folder_ok, file_ok = self._open_action_flags()
        if self._ensure_fluent():
            if self._act_open_file is not None:
                self._act_open_file.setEnabled(file_ok)
            if self._act_open_folder is not None:
                self._act_open_folder.setEnabled(folder_ok)
            self._menu.exec(global_pos)
            return
        menu = QMenu(fallback_parent)
        act_file = menu.addAction("打开文件", self._trigger_open_file)
        act_file.setEnabled(file_ok)
        act_folder = menu.addAction("打开所在文件夹", self._trigger_open_folder)
        act_folder.setEnabled(folder_ok)
        menu.addSeparator()
        menu.addAction("删除选中任务", self._trigger_delete)
        menu.exec(global_pos)
