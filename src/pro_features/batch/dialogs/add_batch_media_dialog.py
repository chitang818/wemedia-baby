"""
批量发布 - 添加媒体文件弹窗（视频与图文通用）
文件路径：src/pro_features/batch/dialogs/add_batch_media_dialog.py

提供两个对外弹窗：
- AddBatchMediaChoiceDialog：选择「添加单文件 / 添加文件夹 / 从媒体库选择」
- LibraryMediaSelectDialog：从媒体库多选文件

两个弹窗均通过构造参数接收媒体类型相关的配置，批量视频页传入视频相关参数，
批量图文页传入图文参数，无需修改弹窗自身代码。
"""

from __future__ import annotations

import os
from typing import Any, Callable, List, Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QWidget

from qfluentwidgets import BodyLabel, CheckBox, ComboBox, FluentIcon, PrimaryPushButton, PushButton

from src.ui.components.base_dialog import AppMessageBoxBase
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.infrastructure.common.media_assign_strategy import (
    AssignStrategy,
    STRATEGY_DISPLAY_NAMES,
    strategy_from_display_name,
    load_assign_strategy,
    save_assign_strategy,
)


class AddBatchMediaChoiceDialog(AppMessageBoxBase):
    """选择添加媒体方式的弹窗。

    Args:
        parent:            父组件。
        batch_page:        宿主批量页，用于在开关变化时触发自动匹配。
        media_label:       媒体类型的中文名，用于按钮文案，例如 "视频" 或 "图片"。
        auto_match_label:  自动匹配 checkbox 文案，例如 "自动从视频库添加视频"。
        load_pref:         读取自动匹配偏好的回调 ``() -> bool``。
        save_pref:         保存自动匹配偏好的回调 ``(bool) -> None``。
    """

    def __init__(
        self,
        parent=None,
        *,
        batch_page: Any = None,
        media_label: str = "视频",
        auto_match_label: str = "自动从视频库添加视频",
        load_pref: Callable[[], bool] = lambda: False,
        save_pref: Callable[[bool], None] = lambda _: None,
    ):
        super().__init__(parent, header_title=f"添加{media_label}")  # type: ignore
        self._choice: Optional[str] = None  # 'files' | 'folder' | 'library' | None
        self._batch_page = batch_page
        self._save_pref = save_pref

        hint = BodyLabel("请选择添加方式", self)
        self.viewLayout.addWidget(hint)

        row = QHBoxLayout()
        row.setSpacing(10)

        btn_files = PrimaryPushButton(FluentIcon.ADD, f"添加{media_label}", self)
        btn_folder = PushButton(FluentIcon.FOLDER, f"添加{media_label}文件夹", self)
        btn_library = PushButton(FluentIcon.LIBRARY, "从媒体库选择", self)
        btn_files.setFixedHeight(32)
        btn_folder.setFixedHeight(32)
        btn_library.setFixedHeight(32)

        row.addWidget(btn_files, 1)
        row.addWidget(btn_folder, 1)
        row.addWidget(btn_library, 1)
        self.viewLayout.addLayout(row)

        # 添加视频分配策略（对所有添加方式生效）
        strategy_row = QHBoxLayout()
        strategy_row.setSpacing(8)
        strategy_label = BodyLabel("添加视频分配策略", self)
        self._strategy_combo = ComboBox(self)
        self._strategy_combo.addItems(STRATEGY_DISPLAY_NAMES)
        self._strategy_combo.setCurrentText(load_assign_strategy("batch").display_name())
        self._strategy_combo.setFixedHeight(28)
        self._strategy_combo.setMinimumWidth(130)
        _st_tip = "添加视频时，视频分配给多账号的算法"
        apply_instructional_tooltip(
            _st_tip,
            strategy_label,
            self._strategy_combo,
            position=ToolTipPosition.TOP,
        )
        self._strategy_combo.currentTextChanged.connect(self._on_strategy_changed)
        strategy_row.addWidget(strategy_label)
        strategy_row.addWidget(self._strategy_combo)
        strategy_row.addStretch()
        self.viewLayout.addLayout(strategy_row)

        self._auto_match_check = CheckBox(auto_match_label, self)
        self._auto_match_check.blockSignals(True)
        self._auto_match_check.setChecked(load_pref())
        self._auto_match_check.blockSignals(False)
        self._auto_match_check.stateChanged.connect(self._on_auto_match_changed)
        self.viewLayout.addWidget(self._auto_match_check)

        self.yesButton.setVisible(False)
        self.cancelButton.setVisible(False)

        self.widget.setMinimumWidth(420)

        self._btn_files = btn_files
        self._btn_folder = btn_folder
        self._btn_library = btn_library
        btn_files.clicked.connect(self._choose_files)
        btn_folder.clicked.connect(self._choose_folder)
        btn_library.clicked.connect(self._choose_library)

        self._sync_button_state()

    def _on_auto_match_changed(self, *_args) -> None:
        checked = self._auto_match_check.isChecked()
        self._save_pref(checked)
        self._sync_button_state()
        if self._batch_page is not None:
            # 与「批量发布设置」里「视频配置」下拉立即联动（不依赖异步偏好读回）
            self._batch_page._sync_batch_publish_settings_ui(video_auto_match=checked)
        if self._batch_page is not None and checked:
            # 偏好异步落盘，必须用 force_run，否则 load_auto_match_pref 仍为 False 会跳过匹配
            self._batch_page._schedule_auto_match_if_enabled(force_run=True)

    def _on_strategy_changed(self, text: str) -> None:
        save_assign_strategy(strategy_from_display_name(text), "batch")

    def _sync_button_state(self) -> None:
        """自动匹配开启时禁用手动添加按钮。"""
        enabled = not self._auto_match_check.isChecked()
        self._btn_files.setEnabled(enabled)
        self._btn_folder.setEnabled(enabled)
        self._btn_library.setEnabled(enabled)

    def _choose_files(self) -> None:
        self._choice = "files"
        self.accept()

    def _choose_folder(self) -> None:
        self._choice = "folder"
        self.accept()

    def _choose_library(self) -> None:
        self._choice = "library"
        self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    @property
    def choice(self) -> Optional[str]:
        return self._choice

    @property
    def auto_match_enabled(self) -> bool:
        return self._auto_match_check.isChecked()

    @property
    def selected_strategy(self) -> AssignStrategy:
        """返回用户在弹窗中选择的分配策略。"""
        return strategy_from_display_name(self._strategy_combo.currentText())


class LibraryMediaSelectDialog(AppMessageBoxBase):
    """从媒体库多选文件弹窗（视频与图文通用）。

    Args:
        library_files: 媒体库文件列表，每条含 file_path / file_name / file_size / owner_label。
        parent:        父组件。
        media_label:   媒体类型中文名，用于计数提示，例如 "视频" 或 "图片"。
        header_title:  弹窗标题，默认 "从媒体库选择<media_label>"。
    """

    def __init__(
        self,
        library_files: List[dict],
        parent=None,
        *,
        media_label: str = "视频",
        header_title: Optional[str] = None,
    ):
        title = header_title or f"从媒体库选择{media_label}"
        super().__init__(parent, header_title=title)  # type: ignore
        self._library_files = library_files or []
        self._selected_files: List[dict] = []
        self._media_label = media_label

        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(
            self.list_widget.SelectionMode.NoSelection  # type: ignore
        )
        self.list_widget.setSpacing(2)
        self.list_widget.setStyleSheet(
            "QListWidget{border:1px solid rgba(0,0,0,0.08); border-radius:6px;"
            " background: rgba(255,255,255,0.5);} QListWidget::item{height:44px;}"
        )
        self.viewLayout.addWidget(self.list_widget)

        hint = BodyLabel("", self)
        hint.setStyleSheet("color:#666; font-size:12px;")
        self._hint_label = hint
        self.viewLayout.addWidget(self._hint_label)

        self.widget.setMinimumWidth(680)
        self.widget.setMinimumHeight(480)

        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self.yesButton.setEnabled(False)
        self._reorder_buttons()

        self._render()

    def _reorder_buttons(self) -> None:
        button_layout = getattr(self, "buttonLayout", None)
        if button_layout is None:
            button_layout = self.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(self.yesButton)
            button_layout.removeWidget(self.cancelButton)
            button_layout.addWidget(self.cancelButton)
            button_layout.addWidget(self.yesButton)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _render(self) -> None:
        self.list_widget.clear()
        self.list_widget.setUpdatesEnabled(False)
        for f in self._library_files:
            fp = f.get("file_path", "")
            name = (
                f.get("original_name")
                or f.get("file_name")
                or (os.path.basename(fp) if fp else "未命名")
            )
            size = f.get("file_size", 0) or 0
            owner = (f.get("owner_label") or "").strip()
            display_name = f"{name}  [{owner}]" if owner else name

            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(QSize(0, 48))
            item.setData(Qt.UserRole, f)

            w = QWidget(self.list_widget)
            row = QHBoxLayout(w)
            row.setContentsMargins(12, 6, 12, 6)
            row.setSpacing(10)

            cb = CheckBox("")
            cb.setFixedSize(20, 20)
            w._file_checkbox = cb  # type: ignore[attr-defined]

            name_label = BodyLabel(display_name, w)
            size_label = QLabel(f"{size / (1024 * 1024):.1f}M" if size else "")
            size_label.setStyleSheet("color:#666; font-size:12px;")

            row.addWidget(cb)
            row.addWidget(name_label, 1)
            row.addWidget(size_label)

            cb.stateChanged.connect(lambda *_: self._update_selection())
            self.list_widget.setItemWidget(item, w)

        self.list_widget.setUpdatesEnabled(True)
        self.list_widget.itemClicked.connect(self._toggle_item_checkbox)
        self._update_selection()

    def _toggle_item_checkbox(self, item: QListWidgetItem) -> None:
        w = self.list_widget.itemWidget(item)
        if w and getattr(w, "_file_checkbox", None):
            w._file_checkbox.setChecked(not w._file_checkbox.isChecked())

    def _update_selection(self) -> None:
        selected: List[dict] = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            w = self.list_widget.itemWidget(item)
            if w and getattr(w, "_file_checkbox", None) and w._file_checkbox.isChecked():
                data = item.data(Qt.UserRole)
                if data:
                    selected.append(data)
        self._selected_files = selected
        n = len(selected)
        self._hint_label.setText(f"已选 {n} 个{self._media_label}" if n else "")
        self._hint_label.setVisible(n > 0)
        self.yesButton.setEnabled(n > 0)

    @property
    def selected_files(self) -> List[dict]:
        return self._selected_files
