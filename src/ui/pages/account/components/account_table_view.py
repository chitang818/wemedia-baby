# -*- coding: utf-8 -*-
"""QTableView based account table widget.

This module keeps the public API of the old AccountTableWidget while moving
the row storage/rendering path to QAbstractTableModel + QTableView.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from PySide6.QtCore import QEvent, QSettings, QSortFilterProxyModel, Qt, Signal, QModelIndex, QRect, QTimer
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import QApplication, QAbstractItemView, QHeaderView, QStyleOptionViewItem, QTableView, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, TableView, isDarkTheme
from qfluentwidgets.components.widgets.table_view import TableItemDelegate

from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.services.material.media_library_stats_cache import get_media_library_stats_cache
from src.services.material.media_library_stats_service import get_media_library_stats_service
from src.ui.pages.account.components.account_table_model import AccountTableModel

_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_LATEST_PUBLISH_TIME_FMT = "%Y-%m-%d %H:%M"
_LATEST_PUBLISH_PAST_RED = QColor("#E81123")
_TABLE_BORDER_LIGHT = QColor("#E5E7EB")
_TABLE_BORDER_DARK = QColor("#3A3A3A")
_SETTINGS_ORG = "WeMediaBaby"
_SETTINGS_APP = "媒小宝"
_COLUMN_WIDTHS_KEY = "account_table/column_widths_v3"


class AccountFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._keyword = ""
        self._platform = "all"

    def set_filter(self, keyword: str = "", platform: str = "all") -> None:
        self._keyword = (keyword or "").strip().lower()
        self._platform = platform or "all"
        self.invalidateFilter()

    def is_filter_active(self) -> bool:
        return bool(self._keyword) or self._platform != "all"

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex | QPersistentModelIndex) -> bool:
  # type: ignore
  # type: ignore
        model = self.sourceModel()
        if model is None:
            return True
  # type: ignore
        record = model.record_at(source_row)
  # type: ignore
        if not record:
            return False
        if self._platform != "all" and record.get("platform") != self._platform:
            return False
        if self._keyword:
            username = str(record.get("platform_username") or record.get("account_name") or "")
            if self._keyword not in username.lower():
                return False
        return True


@dataclass
class _ModelItemAdapter:
    table: "AccountTableView"
    _row: int
    _column: int

    def text(self) -> str:
        return str(self.table.model().data(self.table.model().index(self._row, self._column), Qt.ItemDataRole.DisplayRole) or "")

    def data(self, role: int) -> Any:
        idx = self.table.model().index(self._row, self._column)
        if role == Qt.ItemDataRole.UserRole:
            if self._column == AccountTableModel.COL_PLATFORM:
                return self.table.model().data(idx, AccountTableModel.PlatformIdRole)
            return self.table.model().data(idx, AccountTableModel.AccountIdRole)
        if role == Qt.ItemDataRole.UserRole + 1:
            rec = self.table.record_at_view_row(self._row) or {}
            return rec.get("platform_username") or rec.get("account_name")
        if role == Qt.ItemDataRole.UserRole + 2:
            rec = self.table.record_at_view_row(self._row) or {}
            return rec.get("profile_folder_name")
        return self.table.model().data(idx, role)

    def row(self) -> int:  # type: ignore[override]
        return self._row

    def column(self) -> int:  # type: ignore[override]
        return self._column


class AccountTableView(TableView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHorizontalHeader(_RightBorderHeader(Qt.Orientation.Horizontal, self))
        self._right_border_color = _TABLE_BORDER_DARK if isDarkTheme() else _TABLE_BORDER_LIGHT

    def viewportEvent(self, event) -> bool:  # type: ignore[override]
        handled = super().viewportEvent(event)
        if event.type() == QEvent.Type.Paint:
            self._paint_viewport_right_border()
        return handled

    def _paint_viewport_right_border(self) -> None:
        viewport = self.viewport()
        if viewport is None:
            return
        painter = QPainter(viewport)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(QPen(self._right_border_color, 1))
            x = viewport.width() - 1
            painter.drawLine(x, 0, x, viewport.height())
        finally:
            painter.end()

    def rowCount(self) -> int:
        model = self.model()
        return model.rowCount() if model is not None else 0

    def item(self, row: int, column: int) -> Optional[_ModelItemAdapter]:
        model = self.model()
        if model is None or row < 0 or row >= model.rowCount() or column < 0 or column >= model.columnCount():
            return None
        return _ModelItemAdapter(self, row, column)

    def itemAt(self, pos) -> Optional[_ModelItemAdapter]:  # type: ignore[override]
        idx = self.indexAt(pos)
        if not idx.isValid():
            return None
        return self.item(idx.row(), idx.column())

    def record_at_view_row(self, row: int) -> Optional[Dict[str, Any]]:
        proxy = self.model()
        if proxy is None:
            return None
        src = proxy.sourceModel() if hasattr(proxy, "sourceModel") else proxy
        idx = proxy.index(row, 0)
        if hasattr(proxy, "mapToSource"):
            idx = proxy.mapToSource(idx)
        if not idx.isValid() or not hasattr(src, "record_at"):
            return None
        return src.record_at(idx.row())


class _RightBorderHeader(QHeaderView):
    def __init__(self, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(orientation, parent)
        self._right_border_color = _TABLE_BORDER_DARK if isDarkTheme() else _TABLE_BORDER_LIGHT

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            painter.setPen(QPen(self._right_border_color, 1))
            x = self.viewport().width() - 1
            painter.drawLine(x, 0, x, self.viewport().height())
        finally:
            painter.end()


class AccountTableDelegate(TableItemDelegate):
  # type: ignore
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
  # type: ignore
        self._is_dark = isDarkTheme()
        self._normal_text_color = QColor("#EEEEEE") if self._is_dark else QColor("#333333")
        self._platform_icons = {
            "douyin": FluentIcon.VIDEO.icon(),
            "kuaishou": FluentIcon.MOVIE.icon(),
            "wechat_video": FluentIcon.CHAT.icon(),
            "xiaohongshu": FluentIcon.PHOTO.icon(),
            "default": FluentIcon.GLOBE.icon(),
        }
        self._action_icon = FluentIcon.GLOBE.icon()
        self._online_color = QColor("#107C10")
        self._offline_color = QColor("#E81123")
        self._placeholder_color = QColor("#CCCCCC")
        self._tag_bg = QColor("#E1F5FE")
        self._tag_fg = QColor("#01579B")
        self._tag_border = QColor("#B3E5FC")

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        col = index.column()
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        if col in (
            AccountTableModel.COL_PLATFORM,
            AccountTableModel.COL_LOGIN_STATUS,
            AccountTableModel.COL_GROUP,
            AccountTableModel.COL_TAGS,
            AccountTableModel.COL_LATEST_PUBLISH,
            AccountTableModel.COL_ACTION,
        ):
            self._paint_fluent_background(painter, option, index)
            record = index.data(AccountTableModel.RawRecordRole) or {}
            if col == AccountTableModel.COL_PLATFORM:
                self._paint_platform(painter, option, record, text)
            elif col == AccountTableModel.COL_LOGIN_STATUS:
                self._paint_status_badge(painter, option, record, text)
            elif col == AccountTableModel.COL_GROUP:
                self._paint_group(painter, option, text)
            elif col == AccountTableModel.COL_TAGS:
                self._paint_tags(painter, option, record)
            elif col == AccountTableModel.COL_LATEST_PUBLISH:
                self._paint_latest_publish(painter, option, text)
            elif col == AccountTableModel.COL_ACTION:
                self._paint_action_icon(painter, option)
            return
        super().paint(painter, option, index)

    def _paint_fluent_background(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        """Draw qfluentwidgets row background without drawing DisplayRole text."""
        opt = QStyleOptionViewItem(option)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
  # type: ignore
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
  # type: ignore
        painter.setClipping(True)
        painter.setClipRect(opt.rect)
  # type: ignore
        opt.rect.adjust(0, self.margin, 0, -self.margin)
  # type: ignore
  # type: ignore

        is_hover = self.hoverRow == index.row()
        is_pressed = self.pressedRow == index.row()
        is_alternate = index.row() % 2 == 0 and self.parent().alternatingRowColors()
  # type: ignore
        c = 255 if self._is_dark else 0
        alpha = 0

        if index.row() not in self.selectedRows:
            if is_pressed:
                alpha = 9 if self._is_dark else 6
            elif is_hover:
                alpha = 12
            elif is_alternate:
                alpha = 5
        else:
            if is_pressed:
                alpha = 15 if self._is_dark else 9
            elif is_hover:
                alpha = 25
            else:
                alpha = 17

        background = index.data(Qt.ItemDataRole.BackgroundRole)
        painter.setBrush(background if background else QColor(c, c, c, alpha))
  # type: ignore
        self._drawBackground(painter, opt, index)

        if (
            index.row() in self.selectedRows
            and index.column() == 0
            and self.parent().horizontalScrollBar().value() == 0
  # type: ignore
        ):
  # type: ignore
            self._drawIndicator(painter, opt, index)

  # type: ignore
        painter.restore()

    def _paint_platform(self, painter: QPainter, option: QStyleOptionViewItem, record: Dict[str, Any], text: str) -> None:
        painter.save()
        rect = option.rect.adjusted(12, 0, -8, 0)
  # type: ignore
        icon_rect = QRect(0, 0, 24, 24)
        text_width = option.fontMetrics.horizontalAdvance(text)
  # type: ignore
        total_width = min(rect.width(), 24 + 8 + text_width)
        left = rect.left() + max(0, (rect.width() - total_width) // 2)
  # type: ignore
        icon_rect.moveLeft(left)
        icon_rect.moveTop(rect.top() + (rect.height() - 24) // 2)
        self._platform_icon(str(record.get("platform") or "")).paint(
            painter,
            icon_rect,
            Qt.AlignmentFlag.AlignCenter,
  # type: ignore
        )

        font = QFont(option.font)
  # type: ignore
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.setPen(self._normal_text_color)
        text_rect = QRect(icon_rect.right() + 8, rect.top(), max(0, rect.right() - icon_rect.right() - 8), rect.height())
        text_to_draw = option.fontMetrics.elidedText(text, Qt.TextElideMode.ElideRight, text_rect.width())
  # type: ignore
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text_to_draw)
        painter.restore()
  # type: ignore

  # type: ignore
    def _paint_status_badge(self, painter: QPainter, option: QStyleOptionViewItem, record: Dict[str, Any], text: str) -> None:
        status = str(record.get("login_status") or "").lower()
        online = status == "online" or text == "在线"
        color = self._online_color if online else self._offline_color
        self._paint_solid_badge(painter, option, "在线" if online else "离线", color)

    def _paint_group(self, painter: QPainter, option: QStyleOptionViewItem, text: str) -> None:
        display = text.strip() or "-"
        painter.save()
        painter.setPen(self._placeholder_color if display == "-" else option.palette.color(QPalette.ColorRole.Text))
  # type: ignore
        painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, display)
  # type: ignore
        painter.restore()

    def _paint_tags(self, painter: QPainter, option: QStyleOptionViewItem, record: Dict[str, Any]) -> None:
        tags = record.get("tags") or []
        if not isinstance(tags, (list, tuple)):
            raw = str(tags or "").strip()
  # type: ignore
            tags = [raw] if raw and raw != "-" else []

        cleaned = [str(tag).strip() for tag in tags if str(tag).strip()]
        if not cleaned:
            painter.save()
            painter.setPen(self._placeholder_color)
            painter.drawText(option.rect, Qt.AlignmentFlag.AlignCenter, "-")
  # type: ignore
            painter.restore()
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont(option.font)
  # type: ignore
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)

        metrics = painter.fontMetrics()
        chip_h = 22
        spacing = 6
        available = max(0, option.rect.width() - 8)
  # type: ignore
        chips: list[tuple[str, int]] = []
        used = 0
        for tag in cleaned:
            chip_w = metrics.horizontalAdvance(tag) + 18
            next_used = used + (spacing if chips else 0) + chip_w
            if chips and next_used > available:
                break
            if not chips and chip_w > available:
  # type: ignore
                tag = metrics.elidedText(tag, Qt.TextElideMode.ElideRight, max(20, available - 18))
  # type: ignore
                chip_w = min(available, metrics.horizontalAdvance(tag) + 18)
                next_used = chip_w
  # type: ignore
            chips.append((tag, chip_w))
            used = next_used

        if len(chips) < len(cleaned) and chips:
            more = f"+{len(cleaned) - len(chips)}"
            more_w = metrics.horizontalAdvance(more) + 18
            if len(chips) > 1 and used + spacing + more_w > available:
                removed = chips.pop()
                used -= removed[1] + spacing
            chips.append((more, more_w))

  # type: ignore
        total = sum(width for _, width in chips) + spacing * max(0, len(chips) - 1)
  # type: ignore
        x = option.rect.left() + max(4, (option.rect.width() - total) // 2)
  # type: ignore
  # type: ignore
        y = option.rect.top() + (option.rect.height() - chip_h) // 2
  # type: ignore
        for tag, chip_w in chips:
            chip_rect = QRect(int(x), int(y), int(chip_w), chip_h)
  # type: ignore
  # type: ignore
            painter.setPen(QPen(self._tag_border, 1))
            painter.setBrush(QBrush(self._tag_bg))
  # type: ignore
            painter.drawRoundedRect(chip_rect, 4, 4)
            painter.setPen(self._tag_fg)
            painter.drawText(chip_rect.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignCenter, tag)
            x += chip_w + spacing
        painter.restore()

    def _paint_latest_publish(self, painter: QPainter, option: QStyleOptionViewItem, text: str) -> None:
        painter.save()
        painter.setPen(_LATEST_PUBLISH_PAST_RED if self._latest_publish_cell_should_be_red(text) else option.palette.color(QPalette.ColorRole.Text))
  # type: ignore
        display = option.fontMetrics.elidedText(text or "-", Qt.TextElideMode.ElideRight, max(0, option.rect.width() - 8))
  # type: ignore
        painter.drawText(option.rect.adjusted(4, 0, -4, 0), Qt.AlignmentFlag.AlignCenter, display)
  # type: ignore
        painter.restore()

    def _paint_solid_badge(self, painter: QPainter, option: QStyleOptionViewItem, text: str, color: QColor) -> None:
        painter.save()
        badge_w = max(44, option.fontMetrics.horizontalAdvance(text) + 22)
  # type: ignore
        badge_h = 24
        rect = QRect(0, 0, badge_w, badge_h)
        rect.moveCenter(option.rect.center())
  # type: ignore
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def _paint_action_icon(self, painter: QPainter, option: QStyleOptionViewItem) -> None:
        painter.save()
        icon_rect = QRect(0, 0, 16, 16)
        icon_rect.moveCenter(option.rect.center())
  # type: ignore
        self._action_icon.paint(painter, icon_rect, Qt.AlignmentFlag.AlignCenter)
        painter.restore()

    def _platform_icon(self, platform: str):
        return self._platform_icons.get(platform, self._platform_icons["default"])

    @staticmethod
    def _latest_publish_cell_should_be_red(display_text: str) -> bool:
        s = (display_text or "").strip()
        if not s or s in ("-", "—") or len(s) < 16:
            return False
        try:
            naive = datetime.strptime(s[:16], _LATEST_PUBLISH_TIME_FMT)
        except ValueError:
            return False
        return naive.replace(tzinfo=_SHANGHAI_TZ) < datetime.now(_SHANGHAI_TZ)


class AccountTableViewWidget(QWidget):
    account_double_clicked = Signal(int)
    account_selected = Signal(list)
    switch_account_requested = Signal(int)
    context_menu_requested = Signal(dict, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stats_cache = get_media_library_stats_cache()
        self._model = AccountTableModel(self)
        self._proxy = AccountFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self.table = AccountTableView(self)
        self.table.setModel(self._proxy)
        self.table.setItemDelegate(AccountTableDelegate(self.table))
        self._applying_column_layout = False
        self._user_column_widths = self._load_column_widths()
        self._fit_columns_timer = QTimer(self)
        self._fit_columns_timer.setSingleShot(True)
        self._fit_columns_timer.setInterval(0)
        self._fit_columns_timer.timeout.connect(self._apply_column_layout)
        self._save_column_widths_timer = QTimer(self)
        self._save_column_widths_timer.setSingleShot(True)
        self._save_column_widths_timer.setInterval(250)
        self._save_column_widths_timer.timeout.connect(self._save_current_column_widths)
        self._latest_publish_style_timer = QTimer(self)
        self._latest_publish_style_timer.setInterval(60_000)
        self._latest_publish_style_timer.timeout.connect(self.table.viewport().update)
        self._setup_ui()
        try:
            self._stats_cache.statsUpdated.connect(self._on_media_stats_updated)
        except Exception:
            pass
        app = QApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.connect(self._flush_pending_column_widths)
            except Exception:
                pass

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.table.setObjectName("AccountTable")
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.verticalScrollBar().setSingleStep(24)
        self.table.horizontalScrollBar().setSingleStep(24)
        # Candidate view must keep the old table's initial row order; header sorting
        # can be re-enabled after its visual/interaction parity is reviewed.
        self.table.setSortingEnabled(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.verticalHeader().setMinimumSectionSize(52)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(AccountTableModel.COL_PLATFORM, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(AccountTableModel.COL_USERNAME, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(AccountTableModel.COL_LOGIN_STATUS, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(AccountTableModel.COL_GROUP, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(AccountTableModel.COL_TAGS, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(AccountTableModel.COL_VIDEO_STATS, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(AccountTableModel.COL_IMAGE_STATS, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(AccountTableModel.COL_LATEST_PUBLISH, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(AccountTableModel.COL_ACTION, QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(52)
        header.sectionResized.connect(self._on_header_section_resized)
        palette = self.table.palette()
        palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 120, 212, 15))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("black"))
        self.table.setPalette(palette)
        self._apply_column_layout()
        self.table.clicked.connect(self._on_clicked)
        self.table.doubleClicked.connect(self._on_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        if self.table.selectionModel() is not None:
            self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        try:
            self._fit_columns_timer.start()
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._flush_pending_column_widths()
        try:
            self._latest_publish_style_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def _flush_pending_column_widths(self) -> None:
        if self._save_column_widths_timer.isActive():
            self._save_column_widths_timer.stop()
            self._save_current_column_widths()

    def _load_column_widths(self) -> Dict[int, int]:
        raw = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_COLUMN_WIDTHS_KEY, "")
  # type: ignore
        if not raw:
            return {}
        try:
            data = json.loads(str(raw))
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        widths: Dict[int, int] = {}
        for key, value in data.items():
            try:
                col = int(key)
                width = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= col < len(AccountTableModel.HEADERS):
                widths[col] = max(52, min(width, 420))
        return widths

    def _save_current_column_widths(self) -> None:
        if self._applying_column_layout:
            return
        try:
  # type: ignore
            count = self._model.columnCount()
            widths = {str(col): int(self.table.columnWidth(col)) for col in range(count)}
  # type: ignore
            settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
            settings.setValue(
                _COLUMN_WIDTHS_KEY,
                json.dumps(widths, ensure_ascii=False),
            )
            settings.sync()
            self._user_column_widths = {int(col): width for col, width in widths.items()}
        except Exception:
            return

    def _on_header_section_resized(self, logical_index: int, old_size: int, new_size: int) -> None:
        if self._applying_column_layout or old_size == new_size:
            return
        if logical_index == AccountTableModel.COL_ACTION:
            return
        self._save_column_widths_timer.start()

    def _apply_saved_column_widths(self, available: int, expand_saved_widths: bool) -> bool:
        if not self._user_column_widths:
            return False
        count = self._model.columnCount()
        widths = {
            col: int(self._user_column_widths.get(col, self.table.columnWidth(col)))
  # type: ignore
            for col in range(count)
        }
        if len(widths) != count or any(width <= 0 for width in widths.values()):
            return False
        # 操作列不允许被保存值压缩到无法点击的宽度，强制最小 68px
        widths[AccountTableModel.COL_ACTION] = max(
            widths.get(AccountTableModel.COL_ACTION, 68), 68
        )

        stretch_weights = {
            AccountTableModel.COL_USERNAME: 5,
            AccountTableModel.COL_TAGS: 4,
            AccountTableModel.COL_LATEST_PUBLISH: 3,
            AccountTableModel.COL_GROUP: 2,
            AccountTableModel.COL_PLATFORM: 1,
        }
        slack = 0
        slack = 0
        total = sum(widths.values())
        if total > available:
            overflow = total - available
            shrink_columns = [
                AccountTableModel.COL_TAGS,
                AccountTableModel.COL_LATEST_PUBLISH,
                AccountTableModel.COL_GROUP,
                AccountTableModel.COL_VIDEO_STATS,
                AccountTableModel.COL_IMAGE_STATS,
                AccountTableModel.COL_PLATFORM,
                AccountTableModel.COL_LOGIN_STATUS,
                AccountTableModel.COL_USERNAME,
            ]
            for col in shrink_columns:
                if overflow <= 0:
                    break
                min_width = 52 if col != AccountTableModel.COL_USERNAME else 96
                shrink = min(overflow, max(0, widths[col] - min_width))
                widths[col] -= shrink
  # type: ignore
                overflow -= shrink
            if overflow > 0:
                return False
        else:
            slack = available - total
            if slack <= 24:
                slack = 0

        if expand_saved_widths and total <= available and slack > 0:
            weight_sum = sum(stretch_weights.values())
            used = 0
            for col, weight in stretch_weights.items():
                extra = int(slack * weight / weight_sum)
                widths[col] = widths.get(col, self.table.columnWidth(col)) + extra
                used += extra
            widths[AccountTableModel.COL_USERNAME] += slack - used

        self._applying_column_layout = True
        try:
            for col, width in widths.items():
                self.table.setColumnWidth(col, width)
        finally:
            self._applying_column_layout = False
        return True

    def _apply_column_layout(self) -> None:
        try:
            viewport_w = int(self.table.viewport().width())
  # type: ignore
        except Exception:
            return
        if viewport_w <= 0:
            viewport_w = 920

        compact = viewport_w < 1120
        if compact:
            fixed = {
                AccountTableModel.COL_PLATFORM: 96,
                AccountTableModel.COL_LOGIN_STATUS: 78,
                AccountTableModel.COL_VIDEO_STATS: 82,
                AccountTableModel.COL_IMAGE_STATS: 82,
                AccountTableModel.COL_ACTION: 68,
            }
            flex_min = {
                AccountTableModel.COL_USERNAME: 110,
                AccountTableModel.COL_GROUP: 70,
                AccountTableModel.COL_TAGS: 96,
                AccountTableModel.COL_LATEST_PUBLISH: 112,
            }
            flex_pref = {
                AccountTableModel.COL_USERNAME: 150,
                AccountTableModel.COL_GROUP: 74,
                AccountTableModel.COL_TAGS: 126,
                AccountTableModel.COL_LATEST_PUBLISH: 124,
            }
        else:
            fixed = {
                AccountTableModel.COL_PLATFORM: 112,
                AccountTableModel.COL_LOGIN_STATUS: 86,
                AccountTableModel.COL_VIDEO_STATS: 104,
                AccountTableModel.COL_IMAGE_STATS: 104,
                AccountTableModel.COL_ACTION: 92,
            }
            flex_min = {
                AccountTableModel.COL_USERNAME: 120,
  # type: ignore
                AccountTableModel.COL_GROUP: 90,
                AccountTableModel.COL_TAGS: 120,
                AccountTableModel.COL_LATEST_PUBLISH: 168,
            }
            flex_pref = {
  # type: ignore
                AccountTableModel.COL_USERNAME: 160,
                AccountTableModel.COL_GROUP: 100,
                AccountTableModel.COL_TAGS: 160,
                AccountTableModel.COL_LATEST_PUBLISH: 184,
            }
  # type: ignore

        # 操作列最小宽度（随 compact 状态而定）
        min_action_width = 68 if compact else 92

        available = max(0, viewport_w - 4)
        if self._apply_saved_column_widths(available, viewport_w >= 1120):
  # type: ignore
            # 兜底：确保操作列在任何保存列宽下都不会被压缩到无法显示
            if self.table.columnWidth(AccountTableModel.COL_ACTION) < min_action_width:
                self._applying_column_layout = True
  # type: ignore
                try:
                    self.table.setColumnWidth(AccountTableModel.COL_ACTION, min_action_width)
                finally:
                    self._applying_column_layout = False
            return

        self._applying_column_layout = True
        try:
            for col, width in fixed.items():
                self.table.setColumnWidth(col, int(width))
  # type: ignore

            remaining = available - sum(fixed.values())
            if remaining < sum(flex_min.values()):
                for col, width in flex_min.items():
                    self.table.setColumnWidth(col, int(width))
  # type: ignore
                return

            pref_sum = max(1, sum(flex_pref.values()))
            widths = {
                col: max(int(flex_min[col]), int(remaining * (pref / pref_sum)))
  # type: ignore
                for col, pref in flex_pref.items()
            }
            diff = remaining - sum(widths.values())
            widths[AccountTableModel.COL_USERNAME] = max(
                widths[AccountTableModel.COL_USERNAME] + diff,
                int(flex_min[AccountTableModel.COL_USERNAME]),
  # type: ignore
            )
            for col, width in widths.items():
                self.table.setColumnWidth(col, int(width))
  # type: ignore
        finally:
            self._applying_column_layout = False

    def load_accounts(self, accounts: List[Dict]) -> None:
        self._model.set_records(accounts or [])
        self._proxy.invalidate()
        self._refresh_media_stats_from_cache()
        self._refresh_media_stats_async()
        if accounts:
            self._latest_publish_style_timer.start()
        else:
            self._latest_publish_style_timer.stop()

    def filter_accounts(self, keyword: str = "", platform: str = "all") -> None:
        self._proxy.set_filter(keyword, platform)

    def is_filter_active(self) -> bool:
        return self._proxy.is_filter_active()

    def get_visible_records(self) -> List[Dict[str, Any]]:
        """返回当前筛选条件下表格可见行的账号记录。"""
        records: List[Dict[str, Any]] = []
        proxy = self._proxy
        for row in range(proxy.rowCount()):
            rec = self.table.record_at_view_row(row)
            if rec:
                records.append(dict(rec))
        return records

    def update_account_status(self, account_id: int, new_status: str, error_msg: str = "") -> None:
        updates: Dict[str, Any] = {"login_status": new_status}
        if error_msg:
            updates["_login_error_msg"] = error_msg
        self._model.update_record(account_id, updates)

    def update_account_fields(self, account_id: Any, updates: Dict[str, Any]) -> None:
        if updates:
            self._model.update_record(account_id, updates)

    def update_accounts_fields(self, updates_by_account_id: Dict[Any, Dict[str, Any]]) -> None:
        if not updates_by_account_id:
            return
        self.table.setUpdatesEnabled(False)
        try:
            for account_id, updates in updates_by_account_id.items():
                if updates:
                    self._model.update_record(account_id, updates)
        finally:
            self.table.setUpdatesEnabled(True)
            self.table.viewport().update()

    def get_selected_account_ids(self) -> List[int]:
        sm = self.table.selectionModel()
        if sm is None:
            return []
        ids: List[int] = []
        seen = set()
        for idx in sm.selectedRows(AccountTableModel.COL_USERNAME):
            account_id = idx.data(AccountTableModel.AccountIdRole)
            try:
                account_id = int(account_id)
            except (TypeError, ValueError):
                continue
            if account_id not in seen:
                ids.append(account_id)
  # type: ignore
                seen.add(account_id)
        return ids

    def _on_selection_changed(self) -> None:
        self.account_selected.emit(self.get_selected_account_ids())

    def _on_clicked(self, index: QModelIndex) -> None:
        if index.column() != AccountTableModel.COL_ACTION:
            return
        account_id = index.data(AccountTableModel.AccountIdRole)
        if account_id:
            self.switch_account_requested.emit(int(account_id))

    def _on_double_clicked(self, index: QModelIndex) -> None:
        if index.column() != AccountTableModel.COL_USERNAME:
            return
        account_id = index.data(AccountTableModel.AccountIdRole)
        if account_id:
            self.account_double_clicked.emit(int(account_id))

    def _on_context_menu(self, pos) -> None:
        idx = self.table.indexAt(pos)
        if not idx.isValid():
            return
        self.table.selectRow(idx.row())
        rec = self.table.record_at_view_row(idx.row())
        if not rec:
            return
        self.context_menu_requested.emit(dict(rec), self.table.viewport().mapToGlobal(pos))

    @staticmethod
    def _fmt_counts(total: int, used: int, unused: int) -> str:
        try:
            return f"{int(total)}/{int(used)}/{int(unused)}"
  # type: ignore
        except Exception:
            return "-"

    def _refresh_media_stats_from_cache(self) -> None:
        try:
            stats = self._stats_cache.get()
        except Exception:
            stats = None
        if stats is not None:
            self._on_media_stats_updated(stats)

    def _refresh_media_stats_async(self) -> None:
        coro = None
        try:
            coro = get_media_library_stats_service().refresh()
            get_async_task_registry().create_task(
                coro,
                name="ui.account_table_view.media_stats_refresh",
                group="ui",
            )
        except Exception:
            if coro is not None:
                try:
                    coro.close()
                except Exception:
                    pass
            pass

    def _on_media_stats_updated(self, stats: object) -> None:
        if stats is None:
            return
        video_by_account = getattr(getattr(stats, "video", None), "by_account_id", {}) or {}
        image_by_account = getattr(getattr(stats, "image", None), "by_account_id", {}) or {}
        for aid in set(video_by_account) | set(image_by_account):
            updates: Dict[str, Any] = {}
            vc = video_by_account.get(aid)
            ic = image_by_account.get(aid)
            if vc is not None:
                updates["_video_stats_text"] = self._fmt_counts(vc.total, vc.used, vc.unused)
            if ic is not None:
                updates["_image_stats_text"] = self._fmt_counts(ic.total, ic.used, ic.unused)
            if updates:
                self._model.update_record(aid, updates)


AccountTableWidget = AccountTableViewWidget
