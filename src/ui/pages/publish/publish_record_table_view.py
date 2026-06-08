# -*- coding: utf-8 -*-
"""QTableView compatibility wrapper for publish record tables."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from PySide6.QtCore import QModelIndex, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
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
from src.utils.platform_names import PLATFORM_ID_TO_NAME

logger = logging.getLogger(__name__)


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
    def __init__(self, parent: QTableView):
        super().__init__(parent)
        self.table = parent

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        if index.column() == PublishRecordTableModel.COL_ACTION:
            base = QStyleOptionViewItem(option)
            base.text = ""  # type: ignore
            
            # 修复 QFluentWidgets 背景断层 bug: 
            # FluentWidgets 根据逻辑列索引(index.column())判断是否为末列并绘制圆角，
            # 当 COL_ACTION (逻辑末列) 在视觉上被移至中间时，会误画圆角导致与右侧列之间产生白边。
            # 这里通过视觉索引重新计算它应具备的逻辑“位置”，欺骗它画出正确的连通背景。
            header = self.table.horizontalHeader()
            v_idx = header.visualIndex(index.column())
            is_first = (v_idx == 0)
            is_last = (v_idx == header.count() - 1)
            fake_col = 0 if is_first else (header.count() - 1 if is_last else 1)
            fake_index = index.sibling(index.row(), fake_col)
            
            super().paint(painter, base, fake_index)
            self._paint_action(painter, option, str(index.data(Qt.ItemDataRole.DisplayRole) or "编辑"))
            return
        super().paint(painter, option, index)

    def _paint_action(self, painter: QPainter, option: QStyleOptionViewItem, text: str) -> None:
        btn = QStyleOptionButton()
        btn.rect = option.rect.adjusted(10, 6, -10, -6)  # type: ignore
        btn.text = text  # type: ignore
        btn.state = QStyle.StateFlag.State_Enabled  # type: ignore
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
        pending_column_order: bool = False,
    ) -> None:
        super().__init__(parent)
        self._model = PublishRecordTableModel(self)
        self._recycle_page = recycle_page
        self._pending_column_order = pending_column_order
        self._model.set_recycle_page(recycle_page)
        self._model.set_success_page(success_page)
        self._model.set_action_text(action_text)
        self.setModel(self._model)
        self.setItemDelegate(PublishRecordTableDelegate(self))
        self._apply_legacy_table_visual_defaults()
        header = self.horizontalHeader()
        if not getattr(self, "_column_width_clamp_connected", False):
            header.sectionResized.connect(self._on_column_section_resized)
            self._column_width_clamp_connected = True
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
        # 操作列含按钮，保持固定宽度；其余列均可拖拽调整
        header.setSectionResizeMode(PublishRecordTableModel.COL_ACTION, QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(48)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        widths = self._recycle_widths() if self._recycle_page else self._publish_widths()
        for col, width in widths.items():
            self.setColumnWidth(col, width)
        self._ensure_minimum_column_widths()
        self._apply_column_visual_order()
        self.verticalHeader().setDefaultSectionSize(42)

    def _apply_column_visual_order(self) -> None:
        header = self.horizontalHeader()
        order = (
            self._primary_action_visual_order()
            if self._use_pending_visual_order()
            else self._default_visual_order()
        )
        for visual_index, logical_index in enumerate(order):
            current_visual = header.visualIndex(logical_index)
            if current_visual != visual_index:
                header.moveSection(current_visual, visual_index)

    def _use_pending_visual_order(self) -> bool:
        return self._pending_column_order

    @staticmethod
    def _default_visual_order() -> list[int]:
        return list(range(PublishRecordTableModel.COL_ACTION + 1))

    def _primary_action_visual_order(self) -> list[int]:
        return (
            self._recycle_primary_action_visual_order()
            if self._recycle_page
            else self._publish_primary_action_visual_order()
        )

    @staticmethod
    def _publish_primary_action_visual_order() -> list[int]:
        m = PublishRecordTableModel
        return [
            m.COL_CREATE_TIME,
            m.COL_STATUS,
            m.COL_ACTION,
            m.COL_TYPE,
            m.COL_PLATFORM,
            m.COL_ACCOUNT_GROUP,
            m.COL_TASK_SOURCE,
            m.COL_ACCOUNT_NAME,
            m.COL_FILE,
            m.COL_COVER,
            m.COL_TITLE,
            m.COL_DESCRIPTION,
            m.COL_SCHEDULED_TIME,
            m.COL_ORIGINAL,
            m.COL_MUSIC,
            m.COL_CART,
            m.COL_GROUP_BUY,
            m.COL_LOCATION,
            m.COL_FILE_LOCATION,
        ]

    @staticmethod
    def _recycle_primary_action_visual_order() -> list[int]:
        m = PublishRecordTableModel
        return [
            m.COL_CREATE_TIME,
            m.COL_LOCATION,
            m.COL_ACTION,
            m.COL_TYPE,
            m.COL_PLATFORM,
            m.COL_ACCOUNT_GROUP,
            m.COL_TASK_SOURCE,
            m.COL_ACCOUNT_NAME,
            m.COL_FILE,
            m.COL_COVER,
            m.COL_TITLE,
            m.COL_DESCRIPTION,
            m.COL_SCHEDULED_TIME,
            m.COL_ORIGINAL,
            m.COL_MUSIC,
            m.COL_CART,
            m.COL_GROUP_BUY,
            m.COL_STATUS,
            m.COL_FILE_LOCATION,
        ]

    @staticmethod
    def _table_font_metrics() -> QFontMetrics:
        try:
            from qfluentwidgets.common.font import getFont

            return QFontMetrics(getFont(13))
        except Exception:
            return QFontMetrics(QApplication.font())

    @staticmethod
    def _text_column_width(sample: str, *, extra: int = 40) -> int:
        return PublishRecordTableView._table_font_metrics().horizontalAdvance(sample) + extra

    @staticmethod
    def _platform_column_width() -> int:
        """平台列宽：按最长中文平台名（含兼容名「微信视频号」）完整显示。"""
        longest = max((*PLATFORM_ID_TO_NAME.values(), "微信视频号"), key=len)
        return PublishRecordTableView._text_column_width(longest)

    @staticmethod
    def _cover_column_width() -> int:
        """封面列宽：按 Fluent TableItemDelegate 的 13pt 字体测算「本地封面」完整显示。"""
        return PublishRecordTableView._text_column_width("本地封面")

    @staticmethod
    def _status_column_width() -> int:
        """状态列宽：含 emoji 的「⏳ 待发布」等需更宽。"""
        return PublishRecordTableView._text_column_width("\u23f3 \u5f85\u53d1\u5e03")

    @staticmethod
    def _original_column_width() -> int:
        """作品声明列宽：常见抖音文案「内容含营销推广信息」完整显示。"""
        return PublishRecordTableView._text_column_width("\u5185\u5bb9\u542b\u8425\u9500\u63a8\u5e7f\u4fe1\u606f")

    @staticmethod
    def _column_min_widths() -> Dict[int, int]:
        """拖拽列宽时的下限，避免关键列被拖得过窄只剩「…」。"""
        m = PublishRecordTableModel
        return {
            m.COL_CREATE_TIME: 158,
            m.COL_TYPE: 68,
            m.COL_PLATFORM: PublishRecordTableView._platform_column_width(),
            m.COL_COVER: PublishRecordTableView._cover_column_width(),
            m.COL_SCHEDULED_TIME: 158,
            m.COL_ORIGINAL: PublishRecordTableView._original_column_width(),
            m.COL_STATUS: PublishRecordTableView._status_column_width(),
        }

    def _ensure_minimum_column_widths(self) -> None:
        """刷新默认列宽后，把关键列拉回可读下限（含用户曾拖窄的情况）。"""
        for col, min_w in self._column_min_widths().items():
            if self.columnWidth(col) < min_w:
                self.setColumnWidth(col, min_w)

    def _on_column_section_resized(self, logical_index: int, _old_size: int, new_size: int) -> None:
        if logical_index == PublishRecordTableModel.COL_ACTION:
            return
        min_w = self._column_min_widths().get(logical_index)
        if min_w is not None and new_size < min_w:
            self.setColumnWidth(logical_index, min_w)

    @staticmethod
    def _publish_widths() -> Dict[int, int]:
        return {
            PublishRecordTableModel.COL_CREATE_TIME: 158,
            PublishRecordTableModel.COL_TYPE: 68,
            PublishRecordTableModel.COL_PLATFORM: PublishRecordTableView._platform_column_width(),
            PublishRecordTableModel.COL_ACCOUNT_GROUP: 88,
            PublishRecordTableModel.COL_TASK_SOURCE: 72,
            PublishRecordTableModel.COL_ACCOUNT_NAME: 168,
            PublishRecordTableModel.COL_FILE: 128,
            PublishRecordTableModel.COL_COVER: PublishRecordTableView._cover_column_width(),
            PublishRecordTableModel.COL_TITLE: 116,
            PublishRecordTableModel.COL_DESCRIPTION: 132,
            PublishRecordTableModel.COL_SCHEDULED_TIME: 158,
            PublishRecordTableModel.COL_ORIGINAL: PublishRecordTableView._original_column_width(),
            PublishRecordTableModel.COL_MUSIC: 82,
            PublishRecordTableModel.COL_CART: 86,
            PublishRecordTableModel.COL_GROUP_BUY: 54,
            PublishRecordTableModel.COL_LOCATION: 78,
            PublishRecordTableModel.COL_STATUS: PublishRecordTableView._status_column_width(),
            PublishRecordTableModel.COL_FILE_LOCATION: 170,
            PublishRecordTableModel.COL_ACTION: 76,
        }

    @staticmethod
    def _recycle_widths() -> Dict[int, int]:
        return {
            PublishRecordTableModel.COL_CREATE_TIME: 158,
            PublishRecordTableModel.COL_TYPE: 68,
            PublishRecordTableModel.COL_PLATFORM: PublishRecordTableView._platform_column_width(),
            PublishRecordTableModel.COL_ACCOUNT_GROUP: 88,
            PublishRecordTableModel.COL_TASK_SOURCE: 72,
            PublishRecordTableModel.COL_ACCOUNT_NAME: 168,
            PublishRecordTableModel.COL_FILE: 128,
            PublishRecordTableModel.COL_COVER: PublishRecordTableView._cover_column_width(),
            PublishRecordTableModel.COL_TITLE: 112,
            PublishRecordTableModel.COL_DESCRIPTION: 128,
            PublishRecordTableModel.COL_SCHEDULED_TIME: 158,
            PublishRecordTableModel.COL_ORIGINAL: PublishRecordTableView._original_column_width(),
            PublishRecordTableModel.COL_MUSIC: 88,
            PublishRecordTableModel.COL_CART: 54,
            PublishRecordTableModel.COL_GROUP_BUY: 82,
            PublishRecordTableModel.COL_LOCATION: 120,
            PublishRecordTableModel.COL_STATUS: 170,
            PublishRecordTableModel.COL_FILE_LOCATION: 64,
            PublishRecordTableModel.COL_ACTION: 76,
        }

    def set_records(
        self,
        records,
        *,
        success_page: Optional[bool] = None,
        action_text: Optional[str] = None,
        recycle_page: Optional[bool] = None,
    ) -> None:
        start = time.perf_counter()
        if recycle_page is not None:
            self._recycle_page = recycle_page
        self._model.set_records(
            records or [],
            success_page=success_page,
            action_text=action_text,
            recycle_page=recycle_page,
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms >= 80:
            logger.warning(
                "PublishRecordTableView.set_records rendered %s rows in %.1f ms",
                len(records or []),
                elapsed_ms,
            )
        else:
            logger.debug(
                "PublishRecordTableView.set_records rendered %s rows in %.1f ms",
                len(records or []),
                elapsed_ms,
            )
        self._ensure_minimum_column_widths()

    def source_model(self) -> PublishRecordTableModel:
        return self._model

    def set_success_page(self, enabled: bool) -> None:
        self._model.set_success_page(enabled)

    def set_action_text(self, text: str) -> None:
        self._model.set_action_text(text)

    def set_recycle_page(self, enabled: bool) -> None:
        if self._recycle_page == enabled:
            return
        self._recycle_page = enabled
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
        self.set_cell_text(row, column, str(text))

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
