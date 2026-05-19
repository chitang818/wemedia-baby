"""
最近活动组件
文件路径：src/ui/components/recent_activity_widget.py
功能：工作台「最近发布」卡片，展示在线账号的已发布最晚时间与发布提醒
"""

from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QEvent, QTimer
from PySide6.QtGui import QCursor

from qfluentwidgets import (
    CardWidget, BodyLabel, CaptionLabel, SubtitleLabel,
    FluentIcon, TransparentToolButton, isDarkTheme
)

from src.ui.utils.fluent_tooltips import ToolTipPosition, install_fluent_tool_tip

_OVERDUE_LIGHT = "#E81123"
_OVERDUE_DARK = "#FF6B6B"
_COMPACT_NAME_MAX_LEN = 9
# 卡片宽度低于此值时使用紧凑两列；最大化主窗口时始终展开三列
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
        for text, stretch in (("账号", 4), ("已发布最晚时间", 5), ("发布提醒", 3)):
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
    """单条在线账号发布提醒"""

    clicked = Signal(int)

    def __init__(self, row: Dict[str, Any], parent=None):
        super().__init__(parent)
        self._account_id = int(row.get("account_id", 0))
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

        self._real_name = (row.get("account_name") or "未命名").strip() or "未命名"
        self._name_hidden = False
        self._name_compact = False
        self._name_label = BodyLabel(self._real_name, self)
        self._name_label.setStyleSheet(f"color: {name_color}; font-size: 13px;")
        self._name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._name_label.setWordWrap(False)
        self._refresh_name_display()
        layout.addWidget(self._name_label, 4)

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


class RecentActivityWidget(CardWidget):
    """在线账号发布提醒列表"""

    account_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._names_hidden = False
        self._hide_time_column: Optional[bool] = None
        self._name_compact: Optional[bool] = None
        self._reminder_rows: List[AccountPublishReminderRow] = []
        self._header_row: Optional[_ReminderHeaderRow] = None
        self._win_filter_installed = False
        self._init_ui()
        self._show_empty()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(0)

        header = QHBoxLayout()
        self.title_label = SubtitleLabel("最近发布", self)
        dark = isDarkTheme()
        title_color = "#FFFFFF" if dark else "#1A1A1A"
        self.title_label.setStyleSheet(f"font-weight: 600; font-size: 16px; color: {title_color};")
        _set_fluent_tooltip(
            self.title_label,
            "展示已登录账号的最近成功发布时间与发布提醒，按紧急程度排序",
        )
        header.addWidget(self.title_label)
        header.addStretch()

        self._privacy_btn = TransparentToolButton(FluentIcon.HIDE, self)
        self._privacy_btn.setFixedSize(28, 28)
        _set_fluent_tooltip(self._privacy_btn, "隐藏账号名称")
        self._privacy_btn.clicked.connect(self._toggle_name_privacy)
        header.addWidget(self._privacy_btn)

        layout.addLayout(header)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.list_container = QWidget(self)
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 4, 0, 0)
        self.list_layout.setSpacing(2)
        self.scroll_area.setWidget(self.list_container)

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

    def _should_use_compact_layout(self) -> bool:
        """还原且卡片较窄时用紧凑布局；最大化主窗口时始终三列+完整昵称。"""
        if self._is_main_window_maximized():
            return False
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
            QTimer.singleShot(0, self._sync_compact_layout)
        return super().eventFilter(obj, event)

    def _sync_compact_layout(self) -> None:
        compact = self._should_use_compact_layout()
        if compact == self._hide_time_column and compact == self._name_compact:
            return
        self._hide_time_column = compact
        self._name_compact = compact
        show_time = not compact
        if self._header_row is not None:
            self._header_row.set_time_column_visible(show_time)
        for row in self._reminder_rows:
            row.set_time_column_visible(show_time)
            row.set_name_compact(compact)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_compact_layout()

    def showEvent(self, event):
        super().showEvent(event)
        self._ensure_window_state_filter()
        self._sync_compact_layout()

    def _show_empty(self, message: str = "暂无在线账号"):
        self._clear_items()
        dark = isDarkTheme()
        empty_color = "#888888" if dark else "#AAAAAA"
        empty_label = CaptionLabel(message, self.list_container)
        empty_label.setStyleSheet(f"color: {empty_color}; font-size: 13px; padding: 20px 0;")
        empty_label.setAlignment(Qt.AlignCenter)
        self.list_layout.addWidget(empty_label)
        self.list_layout.addStretch()

    def _clear_items(self):
        self._reminder_rows = []
        self._header_row = None
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

    def set_account_reminders(self, rows: List[Dict[str, Any]]):
        """设置在线账号发布提醒列表"""
        self._clear_items()

        if not rows:
            self._show_empty()
            return

        self._header_row = _ReminderHeaderRow(self.list_container)
        self.list_layout.addWidget(self._header_row)

        for row in rows:
            item = AccountPublishReminderRow(row, self.list_container)
            item.set_name_hidden(self._names_hidden)
            item.clicked.connect(self.account_clicked.emit)
            self._reminder_rows.append(item)
            self.list_layout.addWidget(item)

        self.list_layout.addStretch()
        self._hide_time_column = None
        self._name_compact = None
        self._sync_compact_layout()
