"""
最近活动组件
文件路径：src/ui/components/recent_activity_widget.py
功能：工作台「发布统计」卡片，展示全部账号的已发布最晚时间与到期提醒
"""

from __future__ import annotations

import time
from enum import Enum
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from PySide6.QtGui import QCursor

from qfluentwidgets import (
    CardWidget, BodyLabel, CaptionLabel, SubtitleLabel,
    FluentIcon, TransparentToolButton, isDarkTheme
)

from src.ui.components.workspace_scroll_area import (
    create_workspace_scroll_area,
    set_workspace_scroll_content,
)
from src.ui.components.skeleton import SkeletonItem
from src.ui.utils.fluent_tooltips import ToolTipPosition, install_fluent_tool_tip
from src.ui.workspace_chart_animation_prefs import STATS_SKELETON_MIN_MS

_REMINDER_SKELETON_ROW_COUNT = 5
_REMINDER_ROW_HEIGHT = 32

_OVERDUE_LIGHT = "#E81123"
_OVERDUE_DARK = "#FF6B6B"
_STATUS_DOT_ONLINE_LIGHT = "#107C10"
_STATUS_DOT_ONLINE_DARK = "#6CCB5F"
_STATUS_DOT_OFFLINE = "#E81123"
_COMPACT_NAME_MAX_LEN = 9
# 卡片宽度低于此值时缩短账号名；三列（含已发布最晚时间）始终展示
_COMPACT_LAYOUT_MIN_WIDTH = 300


def _mask_account_name(name: str) -> str:
    """隐私模式下将账号名显示为等长星号。"""
    n = (name or "").strip() or "未命名"
    return "*" * len(n)


def _set_fluent_tooltip(widget: QWidget, text: str) -> None:
    """使用 Fluent 自绘提示，避免原生 QToolTip 黑底。"""
    tip = (text or "").strip()
    widget.setToolTip(tip)
    if tip:
        install_fluent_tool_tip(widget, position=ToolTipPosition.BOTTOM)


def _make_login_status_dot(is_online: bool, parent: QWidget) -> QFrame:
    """账号名前的在线/离线圆点（绿/红），不单独占列。"""
    dark = isDarkTheme()
    if is_online:
        color = _STATUS_DOT_ONLINE_DARK if dark else _STATUS_DOT_ONLINE_LIGHT
    else:
        color = _STATUS_DOT_OFFLINE
    dot = QFrame(parent)
    dot.setFixedSize(8, 8)
    dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
    return dot


def _truncate_account_name(name: str, max_len: int = _COMPACT_NAME_MAX_LEN) -> str:
    """还原窗口下账号昵称最多显示 max_len 个字，超出用省略号。"""
    n = (name or "").strip() or "未命名"
    if len(n) <= max_len:
        return n
    return n[:max_len] + "…"


class _ReminderHeaderRow(QWidget):
    """表头行"""

    def __init__(self, parent=None):
        super().__init__(parent)
        dark = isDarkTheme()
        color = "#888888" if dark else "#666666"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self._time_label: Optional[CaptionLabel] = None
        for text, stretch in (("账号", 4), ("已发布最晚时间", 5), ("到期提醒", 3)):
            lbl = CaptionLabel(text, self)
            lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
            if text == "账号":
                lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            else:
                lbl.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            if text == "已发布最晚时间":
                self._time_label = lbl
            layout.addWidget(lbl, stretch)

    def set_time_column_visible(self, visible: bool) -> None:
        if self._time_label is not None:
            self._time_label.setVisible(visible)


class AccountPublishReminderRow(QWidget):
    """单条账号发布提醒（账号名前绿/红圆点表示在线/离线）"""

    clicked = Signal(int)

    def __init__(self, row: Dict[str, Any], parent=None):
        super().__init__(parent)
        self._account_id = int(row.get("account_id", 0))
        self._is_online = bool(row.get("is_online", row.get("login_status") == "online"))
        self.setCursor(QCursor(Qt.PointingHandCursor))

        dark = isDarkTheme()
        hover_bg = "rgba(255,255,255,0.05)" if dark else "rgba(0,0,0,0.03)"
        self.setStyleSheet(
            f"AccountPublishReminderRow {{ border-radius: 6px; }}"
            f"AccountPublishReminderRow:hover {{ background: {hover_bg}; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        name_color = "#FFFFFF" if dark else "#1A1A1A"
        mid_color = "#AAAAAA" if dark else "#666666"
        if not self._is_online:
            name_color = "#888888" if dark else "#999999"

        self._real_name = (row.get("account_name") or "未命名").strip() or "未命名"
        self._name_hidden = False
        self._name_compact = False

        name_cell = QWidget(self)
        name_layout = QHBoxLayout(name_cell)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(6)
        name_layout.addWidget(_make_login_status_dot(self._is_online, name_cell))
        self._name_label = BodyLabel(self._real_name, name_cell)
        self._name_label.setStyleSheet(f"color: {name_color}; font-size: 13px;")
        self._name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._name_label.setWordWrap(False)
        name_layout.addWidget(self._name_label, 1)
        self._refresh_name_display()
        layout.addWidget(name_cell, 4)

        latest = str(row.get("latest_publish_time") or "-")
        self._time_label = CaptionLabel(latest, self)
        self._time_label.setStyleSheet(f"color: {mid_color}; font-size: 12px;")
        self._time_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        layout.addWidget(self._time_label, 5)

        reminder = str(row.get("reminder_text") or "")
        is_overdue = bool(row.get("is_overdue"))
        self._reminder_label = CaptionLabel(reminder, self)
        if is_overdue:
            overdue_color = _OVERDUE_DARK if dark else _OVERDUE_LIGHT
            self._reminder_label.setStyleSheet(
                f"color: {overdue_color}; font-size: 12px; font-weight: 600;"
            )
        else:
            self._reminder_label.setStyleSheet(f"color: {mid_color}; font-size: 12px;")
        self._reminder_label.setAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        layout.addWidget(self._reminder_label, 3)

    def set_time_column_visible(self, visible: bool) -> None:
        if self._time_label is not None:
            self._time_label.setVisible(visible)

    def set_name_hidden(self, hidden: bool) -> None:
        self._name_hidden = bool(hidden)
        self._refresh_name_display()

    def set_name_compact(self, compact: bool) -> None:
        self._name_compact = bool(compact)
        self._refresh_name_display()

    def _refresh_name_display(self) -> None:
        if self._name_hidden:
            self._name_label.setText(_mask_account_name(self._real_name))
            _set_fluent_tooltip(self._name_label, "")
            return
        if self._name_compact:
            shown = _truncate_account_name(self._real_name)
            self._name_label.setText(shown)
            tip = self._real_name if shown != self._real_name else ""
            _set_fluent_tooltip(self._name_label, tip)
            return
        self._name_label.setText(self._real_name)
        _set_fluent_tooltip(self._name_label, self._real_name)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._account_id:
            self.clicked.emit(self._account_id)


class ReminderLoadState(Enum):
    LOADING = "loading"
    READY = "ready"


class RecentActivityWidget(CardWidget):
    """全部账号发布提醒列表"""

    account_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._load_state = ReminderLoadState.LOADING
        self._loading_shown_at = 0.0
        self._reveal_timer: Optional[QTimer] = None
        self._skeleton_rows: List[SkeletonItem] = []
        self._names_hidden = False
        self._force_name_compact = False
        self._name_compact: Optional[bool] = None
        self._reminder_rows: List[AccountPublishReminderRow] = []
        self._header_row: Optional[_ReminderHeaderRow] = None
        self._win_filter_installed = False
        self._compact_layout_timer = QTimer(self)
        self._compact_layout_timer.setSingleShot(True)
        self._compact_layout_timer.timeout.connect(self._sync_compact_layout)
        self._init_ui()
        self._apply_card_theme()
        
        from qfluentwidgets import qconfig
        qconfig.themeChanged.connect(self._apply_card_theme)
        
        self.show_loading()

    @property
    def is_loading(self) -> bool:
        return self._load_state == ReminderLoadState.LOADING

    def show_loading(self) -> None:
        """进入骨架加载态，避免首启先闪「暂无账号」。"""
        self.cancel_pending_reveal()
        self._load_state = ReminderLoadState.LOADING
        self._loading_shown_at = time.monotonic()
        self._clear_items()
        self._show_skeleton_rows()

    def reveal_reminders(self, rows: List[Dict[str, Any]], *, animate: bool = False) -> None:
        """数据就绪后展示提醒列表（与 KPI 卡 reveal 对齐）。"""
        self.cancel_pending_reveal()
        data = list(rows or [])
        if self._load_state == ReminderLoadState.LOADING and animate:
            elapsed_ms = (time.monotonic() - self._loading_shown_at) * 1000.0
            delay = max(0, int(STATS_SKELETON_MIN_MS - elapsed_ms))

            def _commit() -> None:
                self._finish_reveal(data)

            self._reveal_timer = QTimer(self)
            self._reveal_timer.setSingleShot(True)
            self._reveal_timer.timeout.connect(_commit)
            self._reveal_timer.start(delay)
            return
        self._finish_reveal(data)

    def cancel_pending_reveal(self) -> None:
        if self._reveal_timer is None:
            return
        try:
            self._reveal_timer.stop()
            self._reveal_timer.deleteLater()
        except Exception:
            pass
        self._reveal_timer = None

    def _show_skeleton_rows(self) -> None:
        self._hide_skeleton_rows()
        for _ in range(_REMINDER_SKELETON_ROW_COUNT):
            sk = SkeletonItem(self.list_container, radius=4)
            sk.setFixedHeight(_REMINDER_ROW_HEIGHT)
            sk.start_breathing()
            self.list_layout.addWidget(sk)
            self._skeleton_rows.append(sk)
        self.list_layout.addStretch()

    def _hide_skeleton_rows(self) -> None:
        for sk in self._skeleton_rows:
            try:
                sk.stop_breathing()
                self.list_layout.removeWidget(sk)
                sk.deleteLater()
            except Exception:
                pass
        self._skeleton_rows = []

    def _finish_reveal(self, rows: List[Dict[str, Any]]) -> None:
        self._reveal_timer = None
        self._hide_skeleton_rows()
        self._load_state = ReminderLoadState.READY
        self._populate_reminder_rows(rows)

    def _apply_card_theme(self) -> None:
        """与账号统计卡一致的 CardWidget 底色，避免内嵌滚动区透出灰底。"""
        dark = isDarkTheme()
        if dark:
            card_bg = "rgba(255, 255, 255, 0.04)"
            border = "rgba(255, 255, 255, 0.08)"
        else:
            card_bg = "#FFFFFF"
            border = "#EBEEF2"
        self.setStyleSheet(
            "CardWidget {"
            f"background: {card_bg};"
            f"border: 1px solid {border};"
            "border-radius: 8px;"
            "}"
        )
        transparent = "background: transparent;"
        for widget in (
            getattr(self, "_header_slot", None),
            getattr(self, "list_container", None),
        ):
            if widget is not None:
                widget.setStyleSheet(transparent)
        scroll = getattr(self, "scroll_area", None)
        if scroll is not None:
            scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
            try:
                scroll.viewport().setStyleSheet(transparent)
            except Exception:
                pass

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)

        header = QHBoxLayout()
        self.title_label = SubtitleLabel("发布统计", self)
        dark = isDarkTheme()
        title_color = "#FFFFFF" if dark else "#1A1A1A"
        self.title_label.setStyleSheet(f"font-weight: 600; font-size: 15px; color: {title_color};")
        _set_fluent_tooltip(
            self.title_label,
            "展示全部账号的已发布最晚时间与到期提醒；账号名前绿点为在线、红点为离线，按紧急程度排序",
        )
        header.addWidget(self.title_label)
        header.addStretch()

        self._privacy_btn = TransparentToolButton(FluentIcon.HIDE, self)
        self._privacy_btn.setFixedSize(28, 28)
        _set_fluent_tooltip(self._privacy_btn, "隐藏账号名称")
        self._privacy_btn.clicked.connect(self._toggle_name_privacy)
        header.addWidget(self._privacy_btn)

        layout.addLayout(header)

        # 表头固定在滚动区外，滚动时仅数据行移动
        self._header_slot = QWidget(self)
        self._header_slot_layout = QVBoxLayout(self._header_slot)
        self._header_slot_layout.setContentsMargins(0, 0, 0, 0)
        self._header_slot_layout.setSpacing(0)
        self._header_slot.hide()
        layout.addWidget(self._header_slot)

        self.scroll_area = create_workspace_scroll_area(self)

        self.list_container = QWidget(self)
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        set_workspace_scroll_content(self.scroll_area, self.list_container)

        layout.addWidget(self.scroll_area, 1)

    def _is_main_window_maximized(self) -> bool:
        """FluentWindow 自定义最大化时 isMaximized() 可能为 False，需多重判断。"""
        win = self.window()
        if win is None:
            return False
        try:
            if win.windowState() & Qt.WindowState.WindowMaximized:
                return True
        except Exception:
            pass
        if win.isMaximized():
            return True
        screen = win.screen()
        if screen is not None:
            avail = screen.availableGeometry()
            if win.width() >= avail.width() - 80 and win.height() >= avail.height() - 80:
                return True
        return False

    def set_narrow_column(self, narrow: bool) -> None:
        """工作台半宽并列布局：缩短账号名显示，「已发布最晚时间」列始终保留。"""
        self._force_name_compact = bool(narrow)
        self._name_compact = None
        self._sync_compact_layout()

    def _should_use_name_compact(self) -> bool:
        """半宽或卡片较窄时缩短账号名；最大化主窗口下显示完整昵称。"""
        if self._is_main_window_maximized():
            return False
        if self._force_name_compact:
            return True
        if self.width() >= _COMPACT_LAYOUT_MIN_WIDTH:
            return False
        return True

    def _ensure_window_state_filter(self) -> None:
        win = self.window()
        if win is None or self._win_filter_installed:
            return
        win.installEventFilter(self)
        self._win_filter_installed = True

    def eventFilter(self, obj, event) -> bool:
        if obj is self.window() and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
        ):
            self._compact_layout_timer.start(0)
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self._compact_layout_timer.stop()
        super().closeEvent(event)

    def _sync_compact_layout(self) -> None:
        name_compact = self._should_use_name_compact()
        if name_compact == self._name_compact:
            return
        self._name_compact = name_compact
        if self._header_row is not None:
            self._header_row.set_time_column_visible(True)
        for row in self._reminder_rows:
            row.set_time_column_visible(True)
            row.set_name_compact(name_compact)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_compact_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_window_state_filter()
        self._sync_compact_layout()

    def _show_empty(self, message: str = "暂无账号"):
        self._clear_items()
        dark = isDarkTheme()
        empty_color = "#888888" if dark else "#AAAAAA"
        empty_label = CaptionLabel(message, self.list_container)
        empty_label.setStyleSheet(f"color: {empty_color}; font-size: 13px; padding: 20px 0;")
        empty_label.setAlignment(Qt.AlignCenter)
        self.list_layout.addWidget(empty_label)
        self.list_layout.addStretch()

    def _clear_column_header(self) -> None:
        self._header_row = None
        while self._header_slot_layout.count():
            child = self._header_slot_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _clear_items(self):
        self._reminder_rows = []
        self._clear_column_header()
        self._header_slot.hide()
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _toggle_name_privacy(self) -> None:
        self._names_hidden = not self._names_hidden
        self._update_privacy_button()
        for row in self._reminder_rows:
            row.set_name_hidden(self._names_hidden)

    def _update_privacy_button(self) -> None:
        if self._names_hidden:
            self._privacy_btn.setIcon(FluentIcon.VIEW.icon())
            _set_fluent_tooltip(self._privacy_btn, "显示账号名称")
        else:
            self._privacy_btn.setIcon(FluentIcon.HIDE.icon())
            _set_fluent_tooltip(self._privacy_btn, "隐藏账号名称")

    def set_account_reminders(self, rows: List[Dict[str, Any]]) -> None:
        """兼容旧调用：直接 reveal，无骨架最短时长。"""
        self.reveal_reminders(rows, animate=False)

    def _populate_reminder_rows(self, rows: List[Dict[str, Any]]) -> None:
        self._clear_items()
        if not rows:
            self._show_empty()
            return

        self._header_row = _ReminderHeaderRow(self._header_slot)
        self._header_slot_layout.addWidget(self._header_row)
        self._header_slot.show()

        for row in rows:
            item = AccountPublishReminderRow(row, self.list_container)
            item.set_name_hidden(self._names_hidden)
            item.clicked.connect(self.account_clicked.emit)
            self._reminder_rows.append(item)
            self.list_layout.addWidget(item)

        self.list_layout.addStretch()
        self._name_compact = None
        self._sync_compact_layout()
