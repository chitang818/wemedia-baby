# -*- coding: utf-8 -*-
"""
位置功能模块 — UI 子件：视频号在未填 POI 时，是否保留发布页默认城市定位。

与批量页「不需要输入位置」下两项一致：
- 勾选（默认）：wechat_empty_location_open_picker=False → 发布插件步骤6不操作、直接完成。
- 不勾选：wechat_empty_location_open_picker=True → 在发布页选「不显示位置」。

与 `src.ui.publish.location` 内其它控件共同服务于位置标准字段落库。
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QWidget

try:
    from qfluentwidgets import CheckBox
except ImportError:
    from PySide6.QtWidgets import QCheckBox as CheckBox  # type: ignore

from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip


class WechatVideoLocationOption:
    """默认勾选「默认城市定位」；有地理位置文案时禁用并取消勾选（与落库无关）。"""

    def __init__(self, parent=None) -> None:
        self._cb = CheckBox("默认城市定位", parent)
        self._row = QWidget(parent)
        _h = QHBoxLayout(self._row)
        _h.setContentsMargins(0, 0, 0, 0)
        _h.setSpacing(4)
        _h.addWidget(self._cb)
        apply_instructional_tooltip(
            "仅对视频号有效，勾选后则定位默认当前城市，不勾选则显示不展示位置",
            self._cb,
            position=ToolTipPosition.BOTTOM,
        )
        self._cb.setChecked(True)

    def widget(self) -> QWidget:
        return self._row

    def attach_line_edit(self, line_edit: QLineEdit) -> None:
        line_edit.textChanged.connect(self._on_text_changed)
        self._on_text_changed(line_edit.text())

    def _on_text_changed(self, text: str) -> None:
        if (text or "").strip():
            self._cb.blockSignals(True)
            self._cb.setChecked(False)
            self._cb.setEnabled(False)
            self._cb.blockSignals(False)
        else:
            self._cb.setEnabled(True)
            self._cb.setChecked(True)

    def set_row_visible(self, visible: bool) -> None:
        self._row.setVisible(visible)
        if not visible:
            self._cb.blockSignals(True)
            self._cb.setChecked(True)
            self._cb.blockSignals(False)

    def value_for_persist(
        self,
        *,
        tag_is_location: bool,
        effective_location_empty: bool,
    ) -> Optional[bool]:
        """空 POI 且控件可用时：勾选「默认城市定位」→ False；不勾选 → True。否则 None。"""
        if not tag_is_location or not effective_location_empty:
            return None
        if not self._cb.isVisible() or not self._cb.isEnabled():
            return None
        # DB: False=保留发布页位置；True=去页面选「不显示位置」
        return not bool(self._cb.isChecked())

    def apply_from_db(self, raw: Optional[bool]) -> None:
        self._cb.blockSignals(True)
        if raw is False:
            self._cb.setChecked(True)
        else:
            # True 或未写(NULL)：历史上多为「要在页面选不显示」→ 新控件上为不勾选
            self._cb.setChecked(False)
        self._cb.blockSignals(False)

    def refresh_from_line_text(self, text: str) -> None:
        self._on_text_changed(text)
