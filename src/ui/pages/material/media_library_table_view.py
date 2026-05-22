# -*- coding: utf-8 -*-
"""QTableView wrapper for media library pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QAbstractItemView, QHeaderView
from qfluentwidgets import TableView
from qfluentwidgets.components.widgets.table_view import TableItemDelegate

from src.ui.pages.material.media_library_table_model import MediaLibraryTableModel


@dataclass
class _MediaLibraryItemAdapter:
    table: "MediaLibraryTableView"
    _row: int
    _column: int

    def text(self) -> str:
        idx = self.table.model().index(self._row, self._column)
        return str(self.table.model().data(idx, Qt.ItemDataRole.DisplayRole) or "")

    def data(self, role: int) -> Any:
        idx = self.table.model().index(self._row, self._column)
        if role == Qt.ItemDataRole.UserRole:
            return self.table.model().data(idx, MediaLibraryTableModel.RawItemRole)
        return self.table.model().data(idx, role)

    def setText(self, text: str) -> None:
        return None

    def setData(self, role: int, value: Any) -> None:
        return None

    def row(self) -> int:
        return self._row

    def column(self) -> int:
        return self._column


class MediaLibraryTableView(TableView):
    cellClicked = Signal(int, int)
    cellDoubleClicked = Signal(int, int)
    itemSelectionChanged = Signal()

    def __init__(self, parent=None, *, kind: str = MediaLibraryTableModel.KIND_VIDEO) -> None:
        super().__init__(parent)
        self._model = MediaLibraryTableModel(kind, self)
        self._kind = kind
        self.setModel(self._model)
        self.setItemDelegate(TableItemDelegate(self))
        self._apply_visual_defaults()
        self.clicked.connect(lambda idx: self.cellClicked.emit(idx.row(), idx.column()))
        self.doubleClicked.connect(lambda idx: self.cellDoubleClicked.emit(idx.row(), idx.column()))
        if self.selectionModel() is not None:
            self.selectionModel().selectionChanged.connect(lambda *_args: self.itemSelectionChanged.emit())

    def _apply_visual_defaults(self) -> None:
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(42)

        header = self.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(48)
        for col, width in self._column_widths().items():
            self.setColumnWidth(col, width)

    def _column_widths(self) -> Dict[int, int]:
        if self._kind == MediaLibraryTableModel.KIND_IMAGE_FOLDER:
            return {
                MediaLibraryTableModel.COL_NO: 50,
                MediaLibraryTableModel.COL_IMAGE_COUNT: 78,
                MediaLibraryTableModel.COL_IMAGE_SIZE: 90,
                MediaLibraryTableModel.COL_IMAGE_OWNER: 132,
                MediaLibraryTableModel.COL_IMAGE_USAGE: 76,
            }
        return {
            MediaLibraryTableModel.COL_NO: 50,
            MediaLibraryTableModel.COL_VIDEO_SIZE: 88,
            MediaLibraryTableModel.COL_VIDEO_DURATION: 76,
            MediaLibraryTableModel.COL_VIDEO_RESOLUTION: 96,
            MediaLibraryTableModel.COL_VIDEO_ORIENTATION: 60,
            MediaLibraryTableModel.COL_VIDEO_OWNER: 118,
            MediaLibraryTableModel.COL_VIDEO_USAGE: 76,
        }

    def source_model(self) -> MediaLibraryTableModel:
        return self._model

    def set_items(self, items: List[Any]) -> None:
        self._model.set_items(items or [])

    def notify_item_changed(self, item_or_path: Any, columns: Optional[List[int]] = None) -> bool:
        return self._model.notify_item_changed(item_or_path, columns)

    def notify_columns_changed(self, columns: List[int]) -> None:
        self._model.notify_columns_changed(columns)

    def rowCount(self) -> int:
        return self._model.rowCount()

    def setColumnCount(self, count: int) -> None:
        return None

    def setHorizontalHeaderLabels(self, labels) -> None:
        return None

    def setRowCount(self, count: int) -> None:
        if count == 0:
            self._model.set_items([])

    def setItem(self, row: int, column: int, item) -> None:
        return None

    def item(self, row: int, column: int) -> Optional[_MediaLibraryItemAdapter]:
        if row < 0 or row >= self._model.rowCount() or column < 0 or column >= self._model.columnCount():
            return None
        return _MediaLibraryItemAdapter(self, row, column)

    def itemAt(self, pos) -> Optional[_MediaLibraryItemAdapter]:  # type: ignore[override]
        idx = self.indexAt(pos)
        if not idx.isValid():
            return None
        return self.item(idx.row(), idx.column())

    def selectedItems(self) -> List[_MediaLibraryItemAdapter]:
        sm = self.selectionModel()
        if sm is None:
            return []
        return [
            _MediaLibraryItemAdapter(self, idx.row(), 0)
            for idx in sm.selectedRows()
        ]

    def removeRow(self, row: int) -> None:
        self._model.remove_row(row)

    def record_at(self, row: int) -> Optional[Any]:
        return self._model.item_at(row)
