# -*- coding: utf-8 -*-
"""
表格「整行多选」统一配置（非插件）

与业务发布插件（抖音/快手等）无关：仅为 Fluent/QTable 视图设置一致的选择与拖拽标志。
需要 **Excel 式橡皮筋框选** 时，请使用 RubberBandRowSelectTable（见 rubber_band_row_table.py），
本模块不替代该类。

注意：当前项目中所有表格已改用 RubberBandRowSelectTable（内部包含等价配置），
本函数暂无调用方。保留此模块供未来普通 TableWidget 场景复用。

典型用法::

    from src.ui.components.table_row_multiselect import apply_row_multiselect_standard
    self.table = TableWidget(parent)
    apply_row_multiselect_standard(self.table)
"""
from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView


def apply_row_multiselect_standard(
    view: QAbstractItemView,
    *,
    no_edit: bool = True,
) -> None:
    """为只读列表表设置：整行选择、扩展多选（Ctrl/Shift）、关闭行内拖拽干扰。

    Args:
        view: TableWidget / QTableWidget 等 QAbstractItemView 子类。
        no_edit: 为 True 时禁止单元格编辑（预览/媒体库/记录列表等常见场景）。
    """
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    view.setDragEnabled(False)
    view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
    if no_edit:
        view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
