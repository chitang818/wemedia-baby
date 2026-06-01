# -*- coding: utf-8 -*-
"""Model for video and image-folder media library tables."""

from __future__ import annotations

import typing
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QPersistentModelIndex


class MediaLibraryTableModel(QAbstractTableModel):
    KIND_VIDEO = "video"
    KIND_IMAGE_FOLDER = "image_folder"

    COL_NO = 0
    COL_NAME = 1
    COL_VIDEO_SIZE = 2
    COL_VIDEO_DURATION = 3
    COL_VIDEO_RESOLUTION = 4
    COL_VIDEO_ORIENTATION = 5
    COL_VIDEO_OWNER = 6
    COL_VIDEO_USAGE = 7

    COL_IMAGE_COUNT = 2
    COL_IMAGE_SIZE = 3
    COL_IMAGE_OWNER = 4
    COL_IMAGE_USAGE = 5

    RawItemRole = Qt.ItemDataRole.UserRole + 1

    VIDEO_HEADERS = ["序号", "文件名称", "文件大小", "时长", "分辨率", "方向", "视频归属", "使用统计"]
    IMAGE_HEADERS = ["序号", "文件夹名称", "图片数量", "总大小", "图片归属", "使用统计"]

    def __init__(self, kind: str = KIND_VIDEO, parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._items: List[Any] = []

    def set_kind(self, kind: str) -> None:
        if kind not in (self.KIND_VIDEO, self.KIND_IMAGE_FOLDER):
            raise ValueError(f"Unsupported media library kind: {kind}")
        if self._kind == kind:
            return
        self.beginResetModel()
        self._kind = kind
        self._items = []
        self.endResetModel()

    def set_items(self, items: List[Any]) -> None:
        self.beginResetModel()
        self._items = list(items or [])
        self.endResetModel()

    def items(self) -> List[Any]:
        return list(self._items)

    def item_at(self, row: int) -> Optional[Any]:
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]

    def row_for_path(self, path: Any) -> int:
        target = self._norm_path(path)
        if not target:
            return -1
        for row, item in enumerate(self._items):
            if self._norm_path(getattr(item, "path", None)) == target:
                return row
        return -1

    def notify_item_changed(self, item_or_path: Any, columns: Optional[List[int]] = None) -> bool:
        row = self.row_for_path(getattr(item_or_path, "path", item_or_path))
        if row < 0:
            return False
        if columns:
            left_col = max(0, min(columns))
            right_col = min(self.columnCount() - 1, max(columns))
        else:
            left_col = 0
            right_col = self.columnCount() - 1
        self.dataChanged.emit(
            self.index(row, left_col),
            self.index(row, right_col),
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole],
        )
        return True

    def notify_columns_changed(self, columns: List[int]) -> None:
        if not self._items or not columns:
            return
        left_col = max(0, min(columns))
        right_col = min(self.columnCount() - 1, max(columns))
        self.dataChanged.emit(
            self.index(0, left_col),
            self.index(len(self._items) - 1, right_col),
            [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole],
        )

    def remove_row(self, row: int) -> bool:
        if row < 0 or row >= len(self._items):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        self._items.pop(row)
        self.endRemoveRows()
        if row < len(self._items):
            self.dataChanged.emit(
                self.index(row, self.COL_NO),
                self.index(len(self._items) - 1, self.COL_NO),
                [Qt.ItemDataRole.DisplayRole],
            )
        return True

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self.VIDEO_HEADERS if self._kind == self.KIND_VIDEO else self.IMAGE_HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Vertical:
            return section + 1
        headers = self.VIDEO_HEADERS if self._kind == self.KIND_VIDEO else self.IMAGE_HEADERS
        return headers[section] if 0 <= section < len(headers) else None

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> typing.Any:
        if not index.isValid():
            return None
        item = self.item_at(index.row())
        if item is None:
            return None
        if role == self.RawItemRole:
            return item
        if role == Qt.ItemDataRole.UserRole:
            return item
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip_value(item, index.column())
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return self._display_value(item, index.row(), index.column())

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if column == self.COL_NO:
            return
        if not self._items:
            return
        reverse = order == Qt.SortOrder.DescendingOrder

        def key(pair: tuple[int, Any]):
            original_row, item = pair
            value = self._display_value(item, original_row, column)
            try:
                return (0, float(value.split()[0]) if isinstance(value, str) else float(str(value).split()[0]))
            except Exception:
                return (1, value) if isinstance(value, str) else (1, str(value))

        self.layoutAboutToBeChanged.emit()
        decorated = list(enumerate(self._items))
        decorated.sort(key=key, reverse=reverse)
        self._items = [item for _row, item in decorated]
        self.layoutChanged.emit()

    def _display_value(self, item: Any, row: int, col: int) -> str:
        if col == self.COL_NO:
            return str(row + 1)
        if col == self.COL_NAME:
            return str(getattr(item, "name", "") or "")
        if self._kind == self.KIND_VIDEO:
            return self._video_display_value(item, col)
        return self._image_display_value(item, col)

    def _video_display_value(self, item: Any, col: int) -> str:
        if col == self.COL_VIDEO_SIZE:
            size = float(getattr(item, "size_mb", 0.0) or 0.0)
            return f"{size:.2f} MB" if size > 0 else "-"
        if col == self.COL_VIDEO_DURATION:
            return str(getattr(item, "duration", "") or "-")
        if col == self.COL_VIDEO_RESOLUTION:
            return str(getattr(item, "resolution", "") or "-")
        if col == self.COL_VIDEO_ORIENTATION:
            return str(getattr(item, "orientation", "") or "-")
        if col == self.COL_VIDEO_OWNER:
            return str(getattr(item, "owner", "") or "")
        if col == self.COL_VIDEO_USAGE:
            return "已占用" if bool(getattr(item, "in_use", False)) else ""
        return ""

    def _image_display_value(self, item: Any, col: int) -> str:
        if col == self.COL_IMAGE_COUNT:
            count = int(getattr(item, "image_count", 0) or 0)
            return str(count) if count > 0 else "-"
        if col == self.COL_IMAGE_SIZE:
            size = float(getattr(item, "size_mb", 0.0) or 0.0)
            return f"{size:.2f} MB" if size > 0 else "-"
        if col == self.COL_IMAGE_OWNER:
            return str(getattr(item, "owner", "") or "")
        if col == self.COL_IMAGE_USAGE:
            return "已占用" if bool(getattr(item, "in_use", False)) else ""
        return ""

    def _tooltip_value(self, item: Any, col: int) -> str:
        if col == self.COL_NAME:
            path = getattr(item, "path", None)
            return str(path) if path else str(getattr(item, "name", "") or "")
        return ""

    @staticmethod
    def _norm_path(path: Any) -> str:
        if path is None:
            return ""
        try:
            return str(Path(path)).lower()
        except Exception:
            return str(path).lower()
