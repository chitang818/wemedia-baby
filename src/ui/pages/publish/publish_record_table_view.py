# -*- coding: utf-8 -*-
"""QTableView compatibility wrapper for publish record tables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QHeaderView,
    QStyle,
    QStyleOptionButton,
    QStyleOptionViewItem,
    QTableView,
)
from qfluentwidgets import TableView
from qfluentwidgets.components.widgets.table_view import TableItemDelegate

from src.ui.pages.publish.publish_record_table_model import PublishRecordTableModel


@dataclass
class _ModelItemAdapter:
    table: "PublishRecordTableView"
    _row: int
    _column: int

    def text(self) -> str:
        idx = self.table.model().index(self._row, self._column)
        return str(self.table.model().data(idx, Qt.ItemDataRole.DisplayRole) or "")

    def data(self, role: int) -> Any:
        idx = self.table.model().index(self._row, self._column)
        if role == Qt.ItemDataRole.UserRole:
            return self.table.model().data(idx, PublishRecordTableModel.RecordIdRole)
        return self.table.model().data(idx, role)

    def setData(self, role: int, value: Any) -> None:
        if role == Qt.ItemDataRole.DisplayRole:
            self.table.set_cell_text(self._row, self._column, str(value))

    def row(self) -> int:
        return self._row

    def column(self) -> int:
        return self._column


class PublishRecordTableDelegate(TableItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index.column() == PublishRecordTableModel.COL_ACTION:
            base = QStyleOptionViewItem(option)
            base.text = ""
            super().paint(painter, base, index)
            self._paint_action(painter, option, str(index.data(Qt.ItemDataRole.DisplayRole) or "编辑"))
            return
        super().paint(painter, option, index)

    def _paint_action(self, painter: QPainter, option: QStyleOptionViewItem, text: str) -> None:
        btn = QStyleOptionButton()
        btn.rect = option.rect.adjusted(10, 6, -10, -6)
        btn.text = text
        btn.state = QStyle.StateFlag.State_Enabled
        QApplication.style().drawControl(QStyle.ControlElement.CE_PushButton, btn, painter)


class PublishRecordTableView(TableView):
    cellClicked = Signal(int, int)
    cellDoubleClicked = Signal(int, int)
    itemSelectionChanged = Signal()

    def __init__(
        self,
        parent=None,
        *,
        success_page: bool = False,
        action_text: str = "编辑",
        recycle_page: bool = False,
    ) -> None:
        super().__init__(parent)
        self._model = PublishRecordTableModel(self)
        self._recycle_page = bool(recycle_page)
        self._model.set_recycle_page(recycle_page)
        self._model.set_success_page(success_page)
        self._model.set_action_text(action_text)
        self.setModel(self._model)
        self.setItemDelegate(PublishRecordTableDelegate(self))
        self._apply_legacy_table_visual_defaults()
        self.clicked.connect(lambda idx: self.cellClicked.emit(idx.row(), idx.column()))
        self.doubleClicked.connect(lambda idx: self.cellDoubleClicked.emit(idx.row(), idx.column()))
        if self.selectionModel() is not None:
            self.selectionModel().selectionChanged.connect(lambda *_args: self.itemSelectionChanged.emit())

    def _apply_legacy_table_visual_defaults(self) -> None:
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.horizontalHeader()
        for col in range(PublishRecordTableModel.COL_ACTION + 1):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(PublishRecordTableModel.COL_ACTION, QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(52)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        widths = self._recycle_widths() if self._recycle_page else self._publish_widths()
        for col, width in widths.items():
            self.setColumnWidth(col, width)
        self.verticalHeader().setDefaultSectionSize(42)

    @staticmethod
    def _publish_widths() -> Dict[int, int]:
        return {
            PublishRecordTableModel.COL_CREATE_TIME: 132,
            PublishRecordTableModel.COL_TYPE: 52,
            PublishRecordTableModel.COL_PLATFORM: 68,
            PublishRecordTableModel.COL_ACCOUNT_GROUP: 78,
            PublishRecordTableModel.COL_TASK_SOURCE: 64,
            PublishRecordTableModel.COL_ACCOUNT_NAME: 108,
            PublishRecordTableModel.COL_FILE: 128,
            PublishRecordTableModel.COL_COVER: 62,
            PublishRecordTableModel.COL_TITLE: 116,
            PublishRecordTableModel.COL_DESCRIPTION: 132,
            PublishRecordTableModel.COL_SCHEDULED_TIME: 116,
            PublishRecordTableModel.COL_ORIGINAL: 104,
            PublishRecordTableModel.COL_MUSIC: 82,
            PublishRecordTableModel.COL_CART: 86,
            PublishRecordTableModel.COL_GROUP_BUY: 54,
            PublishRecordTableModel.COL_LOCATION: 78,
            PublishRecordTableModel.COL_STATUS: 82,
            PublishRecordTableModel.COL_FILE_LOCATION: 170,
            PublishRecordTableModel.COL_ACTION: 76,
        }

    @staticmethod
    def _recycle_widths() -> Dict[int, int]:
        return {
            PublishRecordTableModel.COL_CREATE_TIME: 132,
            PublishRecordTableModel.COL_TYPE: 52,
            PublishRecordTableModel.COL_PLATFORM: 68,
            PublishRecordTableModel.COL_ACCOUNT_GROUP: 78,
            PublishRecordTableModel.COL_TASK_SOURCE: 64,
            PublishRecordTableModel.COL_ACCOUNT_NAME: 108,
            PublishRecordTableModel.COL_FILE: 128,
            PublishRecordTableModel.COL_COVER: 62,
            PublishRecordTableModel.COL_TITLE: 112,
            PublishRecordTableModel.COL_DESCRIPTION: 128,
            PublishRecordTableModel.COL_SCHEDULED_TIME: 116,
            PublishRecordTableModel.COL_ORIGINAL: 104,
            PublishRecordTableModel.COL_MUSIC: 88,
            PublishRecordTableModel.COL_CART: 54,
            PublishRecordTableModel.COL_GROUP_BUY: 82,
            PublishRecordTableModel.COL_LOCATION: 120,
            PublishRecordTableModel.COL_STATUS: 170,
            PublishRecordTableModel.COL_FILE_LOCATION: 64,
            PublishRecordTableModel.COL_ACTION: 76,
        }

    def set_records(self, records) -> None:
        self._model.set_records(records or [])

    def source_model(self) -> PublishRecordTableModel:
        return self._model

    def set_success_page(self, enabled: bool) -> None:
        self._model.set_success_page(enabled)

    def set_action_text(self, text: str) -> None:
        self._model.set_action_text(text)

    def set_recycle_page(self, enabled: bool) -> None:
        self._recycle_page = bool(enabled)
        self._model.set_recycle_page(enabled)
        self._apply_legacy_table_visual_defaults()

    def rowCount(self) -> int:
        return self._model.rowCount()

    def setColumnCount(self, count: int) -> None:
        return None

    def setHorizontalHeaderLabels(self, labels) -> None:
        return None

    def setRowCount(self, count: int) -> None:
        if count == 0:
            self._model.set_records([])

    def item(self, row: int, column: int) -> Optional[_ModelItemAdapter]:
        if row < 0 or row >= self._model.rowCount() or column < 0 or column >= self._model.columnCount():
            return None
        return _ModelItemAdapter(self, row, column)

    def itemAt(self, pos) -> Optional[_ModelItemAdapter]:  # type: ignore[override]
        idx = self.indexAt(pos)
        if not idx.isValid():
            return None
        return self.item(idx.row(), idx.column())

    def setItem(self, row: int, column: int, item) -> None:
        text_getter = getattr(item, "text", None)
        text = text_getter() if callable(text_getter) else str(item)
        self.set_cell_text(row, column, text)

    def set_cell_text(self, row: int, column: int, text: str) -> None:
        rec = self.record_at(row)
        if not rec:
            return
        self._model.set_cell_text(rec.get("id"), column, text)

    def removeRow(self, row: int) -> None:
        self._model.remove_record_at(row)

    def cellWidget(self, row: int, column: int):
        return None

    def removeCellWidget(self, row: int, column: int) -> None:
        return None

    def record_at(self, row: int) -> Optional[Dict[str, Any]]:
        return self._model.record_at(row)
