"""
发布时间设置弹窗
文件路径：src/pro_features/batch/dialogs/publish_time_dialog.py
功能：批量视频任务页使用，支持定时排期与「立即发布」槽位混合（单次手动添加中 None 表示立即发布）。
布局：左侧排期设置（顶部分段切换批量/单次；批量 Tab 内①日期与②时间池水平并排）、右侧③排期结果、底部统计。
"""
import random
import re
from collections import Counter
from datetime import date as py_date, datetime as py_datetime
from typing import Any, Dict, List, Optional, Tuple

from src.domain.publish.schedule.batch_slots import compute_batch_schedule_slots
from src.domain.publish.schedule.templates import (
    generate_daily_templates_random_minute_axis,
    generate_daily_templates_whole_hour_axis,
)

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QFormLayout, QHeaderView, QAbstractItemView,
    QTableWidgetItem, QStackedWidget, QWidget, QFrame, QLabel, QSizePolicy,
    QButtonGroup, QScrollArea, QTableWidget, QApplication, QStyleOptionViewItem,
)
from PySide6.QtCore import Qt, QDate, QDateTime, QTime, QSize, Signal, QModelIndex
from PySide6.QtGui import (
    QGuiApplication, QKeySequence, QShortcut, QColor, QPalette,
)

from qfluentwidgets import (
    PushButton,
    PrimaryPushButton,
    TableWidget, TimePicker, InfoBar, InfoBarPosition,
    SegmentedWidget, ComboBox, EditableComboBox, BodyLabel, CaptionLabel,
    RadioButton, IconWidget, FluentIcon, LineEdit, StrongBodyLabel, themeColor,
    isDarkTheme,
)
from qfluentwidgets.components.widgets.table_view import TableItemDelegate

from src.ui.components.base_dialog import AppMessageBoxBase
from src.ui.components.fast_calendar_picker import create_fast_calendar_picker
from src.ui.utils.fluent_tooltips import apply_instructional_tooltip
from src.ui.utils.table_cell_center_host import _TableCellCenterHost

# QFluentWidgets TimePicker：无秒时库默认每列 120px；项目与单任务页一致用 80px 即可完整显示时/分。
# 批量 Tab 标题栏内曾用 42px 导致弹层分钟列变为「…」，与官方组件表现不符。
_TIME_PICKER_COLUMN_WIDTH = 80


def _normalize_time_str(s: str) -> Optional[str]:
    """将输入转为 HH:mm，无效返回 None。"""
    s = (s or "").strip()
    if not s:
        return None
    t = QTime.fromString(s, "HH:mm")
    if not t.isValid():
        t = QTime.fromString(s, "H:m")
    if not t.isValid():
        return None
    return t.toString("HH:mm")


# 等分锚点算法允许的最大每日档位数（与单元测试一致）
QUICK_SCHEDULE_TIMES_PER_DAY_MIN = 1
QUICK_SCHEDULE_TIMES_PER_DAY_MAX = 288
# 弹窗「每日次数」：手输允许 1～99；下拉仅提供 1～6 快捷项（等分算法上限仍为 QUICK_SCHEDULE_TIMES_PER_DAY_MAX）
QUICK_UI_TIMES_PER_DAY_MIN = 1
QUICK_UI_TIMES_PER_DAY_MAX = 99
QUICK_UI_PRESET_TIMES_PER_DAY_MAX = 6


def _parse_times_per_day_from_quick_ui(text: str) -> Optional[int]:
    """从「快捷每日排期」输入/选项中解析次数；合法则返回整数，否则 None。"""
    s = (text or "").strip()
    if not s:
        return None
    m = re.search(r"(\d+)", s)
    if not m:
        return None
    v = int(m.group(1))
    if QUICK_UI_TIMES_PER_DAY_MIN <= v <= QUICK_UI_TIMES_PER_DAY_MAX:
        return v
    return None


def _qdate_to_py(d: QDate) -> py_date:
    return py_date(d.year(), d.month(), d.day())


def _qdatetime_to_py(dt: QDateTime) -> py_datetime:
    if hasattr(dt, "toPython"):
        v = dt.toPython()
        if isinstance(v, py_datetime):
            return v
    qd = dt.date()
    qt = dt.time()
    return py_datetime(qd.year(), qd.month(), qd.day(), qt.hour(), qt.minute())


def compute_batch_schedule_slots_core(
    daily_time_templates: List[str],
    days: int,
    base_date: QDate,
    random_minutes: bool,
    min_dt: QDateTime,
    max_dt: QDateTime,
    rng: Optional[random.Random] = None,
    custom_flags: Optional[List[bool]] = None,
) -> Tuple[List[str], Dict[str, Any]]:
    """由每日时间模板与天数生成排期字符串列表（委托 `domain.publish.schedule`）。

    custom_flags 与 templates 等长；True 表示②标题栏自定义行，不在随机分钟模式下做小时内二次随机。
    """
    if not base_date.isValid() or days < 1:
        return [], {
            "per_day_counts": {},
            "shortfall_total": 0,
            "per_date_shortfall": {},
            "configured_templates_per_day": 0,
        }
    n = len(daily_time_templates)
    flags = list(custom_flags) if custom_flags is not None else [False] * n
    if len(flags) < n:
        flags.extend([False] * (n - len(flags)))
    else:
        flags = flags[:n]
    return compute_batch_schedule_slots(
        daily_time_templates,
        flags,
        days,
        _qdate_to_py(base_date),
        random_minutes_mode=random_minutes,
        min_dt=_qdatetime_to_py(min_dt),
        max_dt=_qdatetime_to_py(max_dt),
        rng=rng,
    )


def _normalize_random_mode_pool_input(s: str) -> Optional[str]:
    """随机分钟模式下编辑时间格：规范为 HH:mm（仅存小时语义，分为 00）。"""
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,2})\s*:\s*随机\s*$", s)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return f"{h:02d}:00"
        return None
    m2 = re.match(r"^(\d{1,2})$", s)
    if m2:
        h = int(m2.group(1))
        if 0 <= h <= 23:
            return f"{h:02d}:00"
        return None
    return _normalize_time_str(s)


class DailyPoolRandomHourDelegate(TableItemDelegate):
    """随机分钟模式下，时间列编辑框仅显示两位小时（如 08），不显示「:随机」。"""

    def __init__(self, dialog: "PublishTimeDialog", parent: QTableWidget):
        super().__init__(parent)
        self._dialog = dialog

    def _is_random_minute_time_col(self, index: QModelIndex) -> bool:
        """随机分钟模式下非「自定义」行用仅小时编辑；自定义行走默认编辑器以编辑完整 HH:mm。"""
        if not (
            index.isValid()
            and index.column() == 1
            and self._dialog.radio_batch_time_random.isChecked()
        ):
            return False
        table = self.parent()
        if not isinstance(table, QTableWidget):
            return False
        item = table.item(index.row(), 1)
        if item is None:
            return False
        canon = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(canon, str) and self._dialog._is_template_custom(canon):
            return False
        return True

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ):
        if self._is_random_minute_time_col(index):
            line_edit = LineEdit(parent)
            line_edit.setProperty("transparent", False)
            line_edit.setStyle(QApplication.style())
            line_edit.setClearButtonEnabled(False)
            return line_edit
        return super().createEditor(parent, option, index)

    def setEditorData(self, editor: QWidget, index: QModelIndex) -> None:
        if self._is_random_minute_time_col(index):
            table = self.parent()
            if not isinstance(table, QTableWidget):
                return
            item = table.item(index.row(), 1)
            if item is None:
                return
            canon = item.data(Qt.ItemDataRole.UserRole)
            base_t = QTime.fromString(canon, "HH:mm") if canon else QTime()
            h = base_t.hour() if base_t.isValid() else 0
            editor.setText(f"{h:02d}")
            return
        super().setEditorData(editor, index)

    def setModelData(self, editor: QWidget, model, index: QModelIndex) -> None:
        if self._is_random_minute_time_col(index):
            table = self.parent()
            if not isinstance(table, QTableWidget) or not isinstance(editor, LineEdit):
                return
            item = table.item(index.row(), 1)
            if item is None:
                return
            raw = editor.text().strip()
            new_norm = _normalize_random_mode_pool_input(raw)
            if new_norm is None:
                try:
                    h = int(raw)
                    if 0 <= h <= 23:
                        new_norm = f"{h:02d}:00"
                except ValueError:
                    new_norm = None
            if not new_norm:
                self._dialog._revert_daily_pool_cell(item)
                self._dialog._show_infobar_throttled(
                    "格式不正确",
                    "请输入 0–23 的小时，例如 8 或 08",
                    duration=2000,
                )
                return
            old = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(old, str):
                old = _normalize_time_str(item.text()) or ""
            self._dialog._apply_daily_pool_time_change(item, old, new_norm)
            return
        super().setModelData(editor, model, index)


class DailyPoolTimePicker(TimePicker):
    """时间选择器：在弹出层每次点击对号确认时发出信号。

    库自带 ``timeChanged`` 仅在确认后的时间与确认前不同才触发；
    排期时间池需要在「未改刻度直接确认」时也能加入，故增加本信号。
    """

    timeConfirmed = Signal(QTime)

    def _onConfirmed(self, value: list):
        super()._onConfirmed(value)
        t = self.time
        if t.isValid():
            self.timeConfirmed.emit(t)


class PublishTimeDialog(AppMessageBoxBase):
    """发布时间设置弹窗"""

    def __init__(
        self,
        initial_slots: Optional[List[Optional[str]]] = None,
        owner_count: int = 0,
        parent=None,
    ):
        super().__init__(parent, header_title="设置发布时间排期")  # type: ignore
        # 排期列表：str 为定时 "yyyy-MM-dd HH:mm"；None 表示该槽位「立即发布」（与任务层 scheduled_publish_time=None 一致）
        self.time_slots: List[Optional[str]] = list(initial_slots) if initial_slots else []
        self._owner_count = int(owner_count) if owner_count is not None else 0
        self._is_validating_time = False
        self._last_infobar_ms = 0
        self._last_infobar = None
        self.daily_time_templates: List[str] = []
        # 与 daily_time_templates 等长：True=②标题栏自定义添加，随机分钟模式下不对该档做小时内二次随机
        self._template_custom_flags: List[bool] = []
        self._pool_table_updating = False
        self._batch_schedule_meta: Dict[str, Any] = {}
        # 表格增量刷新：避免同结构下重复创建数百个 Fluent 按钮 + CellHost
        self._time_slots_render_snapshot: Optional[List[Optional[str]]] = None
        self._pool_render_key: Optional[
            Tuple[bool, Tuple[str, ...], Tuple[bool, ...]]
        ] = None

        self.widget.setMinimumSize(960, 580)
        self._apply_initial_size()
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self._reorder_buttons()

        self.viewLayout.addSpacing(6)

        # ---- 主内容区：左侧排期设置（分段控件 + 堆叠页）| 右侧③；横向约 9:6；底部统计 ----
        body_container = QWidget(self)
        body_outer = QVBoxLayout(body_container)
        body_outer.setContentsMargins(0, 0, 0, 0)
        body_outer.setSpacing(10)

        top_row = QWidget(body_container)
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(12)

        self._schedule_settings_column = QWidget(top_row)
        # Ignored 横向：让宽度仅按 stretch 派分，不被内部 sizeHint 偏移，便于底部统计条对齐。
        self._schedule_settings_column.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        ss_lay = QVBoxLayout(self._schedule_settings_column)
        ss_lay.setContentsMargins(0, 0, 0, 0)
        ss_lay.setSpacing(8)

        self.pivot = SegmentedWidget(self._schedule_settings_column)
        self.pivot.setObjectName("PublishTimePivot")
        ss_lay.addWidget(self.pivot)

        self.stacked_widget = QStackedWidget(self._schedule_settings_column)
        self.stacked_widget.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        ss_lay.addWidget(self.stacked_widget, 1)

        self.pivot.addItem(routeKey="batch", text="批量组合生成",
                           onClick=lambda: self.stacked_widget.setCurrentIndex(0))
        self.pivot.addItem(routeKey="single", text="单次手动添加",
                           onClick=lambda: self.stacked_widget.setCurrentIndex(1))
        self.pivot.setCurrentItem("batch")
        self._apply_pivot_style()
        try:
            self.pivot.currentItemChanged.connect(self._sync_pivot_selection)
        except Exception:
            pass

        self._init_batch_mode_page()
        self._init_single_mode_page()

        # 第一行统计：列结构与上方 top_row 一致——9 : 6（设置区 : 排期结果），
        # 设置区内部再 5 : 4（①排期日期 : ②排期时间），三段间距均 12px，
        # 让三色标签宽度精确对齐对应卡片，在批量 Tab 下视觉一致。
        self._schedule_stats_bar = QFrame(body_container)
        self._schedule_stats_bar.setObjectName("PublishTimeScheduleStatsBar")
        self._schedule_stats_inner = QHBoxLayout(self._schedule_stats_bar)
        _stats_inner = self._schedule_stats_inner
        _stats_inner.setContentsMargins(0, 10, 0, 10)
        _stats_inner.setSpacing(12)

        self._schedule_stat_pill_days = QLabel(self._schedule_stats_bar)
        self._schedule_stat_pill_days.setObjectName("PublishTimeStatPillDays")
        self._schedule_stat_pill_days.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._schedule_stat_pill_days.setText("排期 0 天")
        self._schedule_stat_pill_days.setToolTip("排期天数")
        self._schedule_stat_pill_daily = QLabel(self._schedule_stats_bar)
        self._schedule_stat_pill_daily.setObjectName("PublishTimeStatPillDaily")
        self._schedule_stat_pill_daily.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._schedule_stat_pill_daily.setText("每日 0 篇")
        self._schedule_stat_pill_daily.setToolTip("每日均发")
        self._schedule_stat_pill_total = QLabel(self._schedule_stats_bar)
        self._schedule_stat_pill_total.setObjectName("PublishTimeStatPillTotal")
        self._schedule_stat_pill_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._schedule_stat_pill_total.setText("任务 0 篇")
        self._schedule_stat_pill_total.setToolTip("任务总计")
        for _p in (
            self._schedule_stat_pill_days,
            self._schedule_stat_pill_daily,
            self._schedule_stat_pill_total,
        ):
            _p.setWordWrap(False)
            _p.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            _p.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            # Ignored 横向：宽度仅由 stretch 派分，与上方卡片同步对齐。
            _p.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        _settings_pills_wrap = QWidget(self._schedule_stats_bar)
        _settings_pills_wrap.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        _settings_pills_lay = QHBoxLayout(_settings_pills_wrap)
        _settings_pills_lay.setContentsMargins(0, 0, 0, 0)
        _settings_pills_lay.setSpacing(12)
        _settings_pills_lay.addWidget(self._schedule_stat_pill_days, 6)
        _settings_pills_lay.addWidget(self._schedule_stat_pill_daily, 4)

        _stats_inner.addWidget(_settings_pills_wrap, 10)
        _stats_inner.addWidget(self._schedule_stat_pill_total, 5)

        # ---- 第二行统计：详情条（图标 + 标签 + 数值），含公式与排期窗口，可读性更强 ----
        self._schedule_stats_bar2 = QFrame(body_container)
        self._schedule_stats_bar2.setObjectName("PublishTimeScheduleInfoBar")
        self._schedule_stats2_inner = QHBoxLayout(self._schedule_stats_bar2)
        _stats2_inner = self._schedule_stats2_inner
        _stats2_inner.setContentsMargins(2, 6, 2, 4)
        _stats2_inner.setSpacing(20)

        chip_owner, self._stat_chip_owner_value, _ = self._create_stat_info_chip(
            FluentIcon.PEOPLE, "账号/账号组", "0 个"
        )
        chip_owner.setToolTip("当前批量视频任务页已选账号或账号组数量")
        _stats2_inner.addWidget(chip_owner, 0, Qt.AlignmentFlag.AlignVCenter)

        (
            chip_total,
            self._stat_chip_total_value,
            self._stat_chip_total_hint,
        ) = self._create_stat_info_chip(
            FluentIcon.ACCEPT, "计划总任务", "0 个", "= 0 篇 × 0 个账号"
        )
        chip_total.setToolTip("计划总任务数 = 任务篇数 × 账号/账号组数量")
        _stats2_inner.addWidget(chip_total, 0, Qt.AlignmentFlag.AlignVCenter)

        chip_range, self._stat_chip_range_value, _ = self._create_stat_info_chip(
            FluentIcon.CALENDAR, "排期窗口", "—"
        )
        chip_range.setToolTip("从首个排期日期到末个排期日期；括号内为覆盖天数。")
        _stats2_inner.addWidget(chip_range, 0, Qt.AlignmentFlag.AlignVCenter)

        _stats2_inner.addStretch(1)

        _result_header_tools = QWidget(top_row)
        _rht_lay = QHBoxLayout(_result_header_tools)
        _rht_lay.setContentsMargins(0, 0, 0, 0)
        _rht_lay.setSpacing(8)
        self._btn_clear_daily_templates = PrimaryPushButton(
            FluentIcon.BROOM, "清空", _result_header_tools)
        self._btn_clear_daily_templates.setFixedHeight(30)
        self._btn_clear_daily_templates.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_clear_daily_templates.clicked.connect(self._on_clear_daily_template)
        _rht_lay.addWidget(self._btn_clear_daily_templates, 0, Qt.AlignmentFlag.AlignVCenter)

        self.schedule_result_card, _result_host, result_lay = self._create_module_card(
            top_row, "排期结果", _result_header_tools)
        # Ignored 横向：使排期结果卡片宽度严格按 stretch 派分，便于底部「任务 X 篇」对齐。
        self.schedule_result_card.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)

        self.time_table = TableWidget(_result_host)
        self.time_table.setObjectName("PublishTimeTable")
        self.time_table.setColumnCount(3)
        for col, title in enumerate(("序号", "时间", "操作")):
            header_item = QTableWidgetItem(title)
            header_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.time_table.setHorizontalHeaderItem(col, header_item)
        self.time_table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hh = self.time_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        # 避免末列在默认 stretchLastSection 下与 Stretch 中间列叠加，导致末列 indexWidget 几何异常
        hh.setStretchLastSection(False)
        # 序号列需容纳中文表头与内边距，避免窄屏下被裁切。
        self.time_table.setColumnWidth(0, 56)
        self.time_table.setColumnWidth(2, 88)
        self.time_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.time_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.time_table.verticalHeader().setVisible(False)
        self.time_table.setAlternatingRowColors(True)
        self.time_table.verticalHeader().setDefaultSectionSize(34)
        self.time_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # 避免 Fluent 表格在列宽偏紧时对日期时间字符串中间省略
        self.time_table.setTextElideMode(Qt.TextElideMode.ElideNone)

        self.schedule_result_empty_placeholder = self._create_schedule_result_empty_placeholder(
            _result_host)
        self.schedule_result_stack = QStackedWidget(_result_host)
        self.schedule_result_stack.setObjectName("ScheduleResultStack")
        self.schedule_result_stack.addWidget(self.schedule_result_empty_placeholder)
        self.schedule_result_stack.addWidget(self.time_table)
        result_lay.addWidget(self.schedule_result_stack, 1)

        top_layout.addWidget(self._schedule_settings_column, 10)
        top_layout.addWidget(self.schedule_result_card, 5)

        body_outer.addWidget(top_row, 1)
        body_outer.addWidget(self._schedule_stats_bar, 0)
        body_outer.addWidget(self._schedule_stats_bar2, 0)

        self.viewLayout.addWidget(body_container, 1)

        self.stacked_widget.currentChanged.connect(self._on_stacked_publish_mode_changed)
        self._on_stacked_publish_mode_changed(self.stacked_widget.currentIndex())

        # 须在 time_table、template_stack 等全部就绪后再刷新；无已有排期且已选每日次数时才套用快捷等分（避免覆盖 initial_slots）
        if not self.time_slots:
            n0 = _parse_times_per_day_from_quick_ui(
                self.quick_schedule_combo.currentText())
            if n0 is not None:
                self._apply_quick_templates(n0)
        else:
            self._hydrate_daily_templates_from_existing_slots()
            self._refresh_daily_time_pool_table()
        self._update_statistics_panel()

        self._apply_publish_time_dialog_chrome()

        self._refresh_time_table()

        try:
            self.yesButton.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass
        self.yesButton.clicked.connect(self._on_confirm)

        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.activated.connect(self.reject)

    def is_publish_immediately(self) -> bool:
        """兼容旧调用：当排期全部为立即发布槽（仅含 None）时为 True。"""
        return bool(self.time_slots) and all(s is None for s in self.time_slots)

    def _on_confirm(self) -> None:
        if not self.time_slots:
            InfoBar.warning(
                "提示",
                "请添加至少一个排期（定时时间或立即发布）",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2500,
            )
            return
        self.accept()

    # ------------------------------------------------------------------ UI 辅助
    def _reorder_buttons(self):
        button_layout = getattr(self, "buttonLayout", None)
        if button_layout is None:
            button_layout = self.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(self.yesButton)
            button_layout.removeWidget(self.cancelButton)
            button_layout.addWidget(self.cancelButton)
            button_layout.addWidget(self.yesButton)

    def _apply_pivot_style(self):
        """Tab 栏区分样式"""
        palette = self._palette_publish_dialog()
        bg_hover = palette.get("BG_HOVER", "rgba(0,0,0,0.06)")
        border = palette.get("BORDER_DEFAULT", "#E5E5E5")
        tp = palette.get("TEXT_PRIMARY", "#1A1A1A")
        ts = palette.get("TEXT_SECONDARY", "#666666")
        bg_card = palette.get("BG_CARD", "#FFFFFF")
        self.pivot.setStyleSheet(f"""
            #PublishTimePivot {{
                background-color: {bg_hover}; border: 1px solid {border};
                border-radius: 8px; padding: 4px; min-height: 36px;
            }}
            #PublishTimePivot SegmentedItem {{
                border: none; border-radius: 6px; padding: 6px 20px;
                font-size: 13px; color: {ts}; background: transparent;
            }}
            #PublishTimePivot SegmentedItem:hover {{
                color: {tp}; background: rgba(128,128,128,0.15);
            }}
            #PublishTimePivot SegmentedItem[isSelected="true"],
            #PublishTimePivot SegmentedItem[isSelected="1"] {{
                color: {tp}; font-weight: 600; background-color: {bg_card};
            }}
        """)

    def _palette_publish_dialog(self) -> dict:
        try:
            from src.ui.styles.theme_manager import ThemeManager
            return ThemeManager()._get_current_palette()
        except Exception:
            return {
                "BG_MAIN": "#F3F3F3",
                "BG_HOVER": "rgba(0,0,0,0.06)",
                "BORDER_DEFAULT": "#E5E5E5",
                "TEXT_PRIMARY": "#1A1A1A",
                "TEXT_SECONDARY": "#666666",
                "BG_CARD": "#FFFFFF",
            }

    def _create_stat_info_chip(
        self,
        icon_type,
        label_text: str,
        initial_value: str = "",
        initial_hint: str = "",
    ) -> Tuple[QWidget, QLabel, QLabel]:
        """构造「图标 + 标签 + 数值 + 备注」详情块；返回 (chip, value_label, hint_label)。

        用于第二行统计条；样式由 _apply_publish_time_dialog_chrome 注入，
        各部分通过 objectName 在 QSS 中分别匹配（标签/数值/备注）。
        """
        chip = QWidget(self._schedule_stats_bar2)
        chip.setObjectName("PublishTimeStatChip")
        lay = QHBoxLayout(chip)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        icon_w = IconWidget(icon_type, chip)
        icon_w.setFixedSize(14, 14)
        lay.addWidget(icon_w, 0, Qt.AlignmentFlag.AlignVCenter)

        label_w = QLabel(label_text, chip)
        label_w.setObjectName("PublishTimeStatChipLabel")
        lay.addWidget(label_w, 0, Qt.AlignmentFlag.AlignVCenter)

        value_w = QLabel(initial_value, chip)
        value_w.setObjectName("PublishTimeStatChipValue")
        value_w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(value_w, 0, Qt.AlignmentFlag.AlignVCenter)

        hint_w = QLabel(initial_hint, chip)
        hint_w.setObjectName("PublishTimeStatChipHint")
        hint_w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        if not initial_hint:
            hint_w.setVisible(False)
        lay.addWidget(hint_w, 0, Qt.AlignmentFlag.AlignVCenter)

        return chip, value_w, hint_w

    def _create_module_card(
        self,
        parent: QWidget,
        title: str,
        header_right: Optional[QWidget] = None,
        title_instruction: Optional[str] = None,
    ) -> Tuple[QFrame, QWidget, QVBoxLayout]:
        """统一模块卡：顶栏 + 分隔线 + 内容区（供①②③排期卡片）。"""
        frame = QFrame(parent)
        frame.setObjectName("PublishScheduleModuleCard")
        frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(frame)
        header.setObjectName("PublishScheduleModuleHeader")
        header.setFixedHeight(40)
        header.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 6, 10, 6)
        hl.setSpacing(8)
        title_lbl = BodyLabel(title, frame)
        title_lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        hl.addWidget(title_lbl)
        if title_instruction:
            apply_instructional_tooltip(title_instruction, title_lbl)
        hl.addStretch(1)
        if header_right is not None:
            hl.addWidget(
                header_right, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addWidget(header)

        sep = QWidget(frame)
        sep.setObjectName("PublishScheduleModuleHeaderSep")
        sep.setFixedHeight(1)
        outer.addWidget(sep)

        content_host = QWidget(frame)
        content_lay = QVBoxLayout(content_host)
        content_lay.setContentsMargins(12, 10, 12, 12)
        content_lay.setSpacing(8)
        outer.addWidget(content_host, 1)

        return frame, content_host, content_lay

    def _apply_widget_fill_bg(self, w: Optional[QWidget], bg_hex: str) -> None:
        """将控件填充为与卡片一致的底色（用于滚动区 viewport，避免露出灰底）。"""
        if w is None:
            return
        c = QColor(bg_hex)
        if not c.isValid():
            return
        w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        w.setAutoFillBackground(True)
        pal = w.palette()
        pal.setColor(QPalette.ColorRole.Window, c)
        pal.setColor(QPalette.ColorRole.Base, c)
        w.setPalette(pal)

    def _apply_publish_time_dialog_chrome(self) -> None:
        """三卡模块壳、表头与表格样式（随主题色板）。"""
        p = self._palette_publish_dialog()
        bc = p.get("BG_CARD", "#FFFFFF")
        bm = p.get("BG_MAIN", "#F3F3F3")
        border = p.get("BORDER_DEFAULT", "#E5E5E5")
        tp = p.get("TEXT_PRIMARY", "#1A1A1A")

        module_ss = f"""
            QFrame#PublishScheduleModuleCard {{
                border: 1px solid {border};
                border-radius: 10px;
                background-color: {bc};
            }}
            QFrame#PublishScheduleModuleCard QWidget#PublishScheduleModuleHeader {{
                background-color: {bm};
                border: none;
                border-bottom: 1px solid {border};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
            QFrame#PublishScheduleModuleCard QWidget#PublishScheduleModuleHeaderSep {{
                background-color: {border};
                max-height: 1px;
            }}
        """
        for w in (
            getattr(self, "batch_date_card", None),
            getattr(self, "single_date_card", None),
            getattr(self, "batch_time_card", None),
            getattr(self, "schedule_result_card", None),
        ):
            if w is not None:
                w.setStyleSheet(module_ss)

        # 「②排期时间」内滚动区 / 空状态：与右侧「③排期结果」内容区同为卡片白底
        ds = getattr(self, "_daily_pool_scroll", None)
        if ds is not None:
            self._apply_widget_fill_bg(ds, bc)
            self._apply_widget_fill_bg(ds.viewport(), bc)
        self._apply_widget_fill_bg(getattr(self, "_daily_pool_scroll_inner", None), bc)
        self._apply_widget_fill_bg(getattr(self, "template_stack", None), bc)
        self._apply_widget_fill_bg(getattr(self, "daily_pool_empty_placeholder", None), bc)
        self._apply_widget_fill_bg(getattr(self, "schedule_result_stack", None), bc)
        self._apply_widget_fill_bg(getattr(self, "schedule_result_empty_placeholder", None), bc)

        table_ss = f"""
            TableWidget#DailyTimePoolTable, TableWidget#PublishTimeTable {{
                background-color: {bc};
                border: none;
                outline: none;
            }}
            /* 左侧时间池可编辑：选中/焦点格不显系统蓝底，与右侧一致 */
            TableWidget#DailyTimePoolTable {{
                selection-background-color: transparent;
                selection-color: {tp};
            }}
            TableWidget#DailyTimePoolTable::item:selected,
            TableWidget#DailyTimePoolTable::item:selected:active,
            TableWidget#DailyTimePoolTable::item:selected:!active {{
                background-color: transparent;
                color: {tp};
            }}
            TableWidget#DailyTimePoolTable::item, TableWidget#PublishTimeTable::item {{
                padding: 4px 8px;
            }}
            TableWidget#DailyTimePoolTable QHeaderView::section,
            TableWidget#PublishTimeTable QHeaderView::section {{
                background-color: {bm};
                color: {tp};
                padding: 8px 6px;
                border: none;
                border-bottom: 1px solid {border};
                font-weight: 600;
                font-size: 12px;
            }}
        """
        if getattr(self, "daily_pool_table", None):
            self.daily_pool_table.setStyleSheet(table_ss)
        if getattr(self, "time_table", None):
            self.time_table.setStyleSheet(table_ss)

        stats_bar = getattr(self, "_schedule_stats_bar", None)
        if stats_bar is not None:
            stats_bar.setStyleSheet(f"""
                #PublishTimeScheduleStatsBar {{
                    background-color: transparent;
                    border: none;
                }}
            """)
        stats_bar2 = getattr(self, "_schedule_stats_bar2", None)
        if stats_bar2 is not None:
            ts = p.get("TEXT_SECONDARY", "#666666")
            stats_bar2.setStyleSheet(f"""
                QFrame#PublishTimeScheduleInfoBar {{
                    background-color: transparent;
                    border: none;
                }}
                QFrame#PublishTimeScheduleInfoBar QLabel#PublishTimeStatChipLabel {{
                    color: {ts};
                    font-size: 12px;
                }}
                QFrame#PublishTimeScheduleInfoBar QLabel#PublishTimeStatChipValue {{
                    color: {tp};
                    font-size: 13px;
                    font-weight: 600;
                }}
                QFrame#PublishTimeScheduleInfoBar QLabel#PublishTimeStatChipHint {{
                    color: {ts};
                    font-size: 12px;
                }}
            """)
        self._apply_schedule_stat_pills_theme()

    def _apply_schedule_stat_pills_theme(self) -> None:
        """第一行：三色圆角标签（浅底深字 / 深色主题略加深底）。第二行的详情条样式由 chrome 注入。"""
        if getattr(self, "_schedule_stat_pill_days", None) is None:
            return
        dark = isDarkTheme()
        if dark:
            days_bg, days_fg = "#1B3D5C", "#90CAF9"
            daily_bg, daily_fg = "#1D4E3A", "#A5D6A7"
            total_bg, total_fg = "#4A235A", "#E1BEE7"
        else:
            days_bg, days_fg = "#E3F2FD", "#1565C0"
            daily_bg, daily_fg = "#E8F5E9", "#2E7D32"
            total_bg, total_fg = "#F3E5F5", "#6A1B9A"
        base = (
            "border-radius: 14px; padding: 6px 12px; font-size: 13px; font-weight: 500;"
        )
        self._schedule_stat_pill_days.setStyleSheet(
            f"#PublishTimeStatPillDays {{ background-color: {days_bg}; color: {days_fg}; {base} }}"
        )
        self._schedule_stat_pill_daily.setStyleSheet(
            f"#PublishTimeStatPillDaily {{ background-color: {daily_bg}; color: {daily_fg}; {base} }}"
        )
        self._schedule_stat_pill_total.setStyleSheet(
            f"#PublishTimeStatPillTotal {{ background-color: {total_bg}; color: {total_fg}; {base} }}"
        )

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_pivot_selection()
        self._apply_publish_time_dialog_chrome()

    def _sync_pivot_selection(self):
        try:
            get_current = getattr(self.pivot, "currentRouteKey", None)
            current_key = get_current() if callable(get_current) else "batch"
        except Exception:
            current_key = "batch"
        for child in self.pivot.findChildren(QWidget):
            if type(child).__name__ == "SegmentedItem":
                key = child.property("routeKey") or ""
                child.setProperty("isSelected", key == current_key)
                child.style().unpolish(child)
                child.style().polish(child)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _apply_initial_size(self):
        try:
            screen = QGuiApplication.primaryScreen()
            geo = screen.availableGeometry() if screen else None
            if not geo:
                self.widget.resize(960, 660)
                return
            w = min(max(960, self.widget.minimumWidth()), int(geo.width() * 0.92))
            h = min(max(660, self.widget.minimumHeight()), int(geo.height() * 0.88))
            self.widget.resize(w, h)
        except Exception:
            self.widget.resize(960, 660)

    # ------------------------------------------------------------------ 单次手动添加（侧栏内 QFormLayout 适配）
    def _init_single_mode_page(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(10)

        self.single_date_card, ch, card_lay = self._create_module_card(
            page,
            "①排期日期",
            None,
            title_instruction=(
                "选择日期与时间后点击「添加排期」，或点击「立即发布」加入立即槽位；"
                "条目按添加顺序出现在右侧列表，可与定时混排。"
            ),
        )

        form = QFormLayout()
        form.setSpacing(10)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        now = QDateTime.currentDateTime()
        target = now.addSecs(9000 + 300)

        self.batch_date_picker = create_fast_calendar_picker(
            ch, initial_date=target.date())
        form.addRow(BodyLabel("日期：", ch), self.batch_date_picker)

        self.batch_time_picker = TimePicker(ch)
        self.batch_time_picker.setTime(target.time())
        for _c in (0, 1):
            self.batch_time_picker.setColumnWidth(_c, _TIME_PICKER_COLUMN_WIDTH)
        form.addRow(BodyLabel("时间：", ch), self.batch_time_picker)

        card_lay.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_add_time = PushButton("添加排期", ch)
        btn_add_time.setFixedWidth(120)
        btn_add_time.clicked.connect(self._on_add_time)
        btn_row.addWidget(btn_add_time, 0, Qt.AlignmentFlag.AlignLeft)
        btn_immediate = PushButton("立即发布", ch)
        btn_immediate.setFixedWidth(120)
        btn_immediate.setToolTip("在排期结果中增加一条「立即发布」槽位，可与定时时间混排")
        btn_immediate.clicked.connect(self._on_add_immediate)
        btn_row.addWidget(btn_immediate, 0, Qt.AlignmentFlag.AlignLeft)
        btn_row.addStretch(1)
        card_lay.addLayout(btn_row)

        lay.addWidget(self.single_date_card, 1)

        self.batch_date_picker.dateChanged.connect(self._validate_schedule_time)
        self.batch_time_picker.timeChanged.connect(self._validate_schedule_time)

        self.stacked_widget.addWidget(page)

    def _on_stacked_publish_mode_changed(self, _index: int) -> None:
        """切换批量/单次时③排期结果与底部统计保持显示；仅更新统计文案（配置档 vs 日均）。"""
        self._update_statistics_panel()

    # ------------------------------------------------------------------ 批量组合生成（① 与 ② 水平并排；时间池见 _build_batch_pool_column）
    def _init_batch_mode_page(self):
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 2, 0, 0)
        lay.setSpacing(12)

        self.batch_date_card, ch, card_lay = self._create_module_card(
            page,
            "①排期日期",
            None,
            title_instruction=(
                "设置开始日期、发布天数、每日次数（可输入数字）、开始与结束时间；快捷在「当日」从"
                "开始时间至结束时间之间等分。在「②排期时间」卡片中可再添加或编辑具体时刻。"
            ),
        )

        form = QFormLayout()
        form.setSpacing(10)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.batch_combo_start_date_picker = create_fast_calendar_picker(
            ch,
            initial_date=QDateTime.currentDateTime().date().addDays(1),
        )
        form.addRow(
            BodyLabel("开始日期：", ch),
            self.batch_combo_start_date_picker)

        days_row = QWidget(ch)
        days_row_lay = QHBoxLayout(days_row)
        days_row_lay.setContentsMargins(0, 0, 0, 0)
        days_row_lay.setSpacing(8)
        self.days_combo_box = ComboBox(ch)
        for i in range(1, 15):
            self.days_combo_box.addItem(f"{i} 天", userData=i)
        self.days_combo_box.setCurrentIndex(1)
        self.days_combo_box.setFixedWidth(88)
        days_row_lay.addWidget(self.days_combo_box)
        days_row_lay.addStretch(1)
        form.addRow(BodyLabel("发布天数：", ch), days_row)

        quick_only = QWidget(ch)
        quick_only_lay = QHBoxLayout(quick_only)
        quick_only_lay.setContentsMargins(0, 0, 0, 0)
        quick_only_lay.setSpacing(12)
        # EditableComboBox：下拉预设 1～6；可手输 1～99
        self.quick_schedule_combo = EditableComboBox(ch)
        for _n in range(QUICK_UI_TIMES_PER_DAY_MIN, QUICK_UI_PRESET_TIMES_PER_DAY_MAX + 1):
            self.quick_schedule_combo.addItem(str(_n), None, _n)
        self.quick_schedule_combo.setFixedWidth(76)
        self.quick_schedule_combo.setToolTip(
            f"下拉为 1～{QUICK_UI_PRESET_TIMES_PER_DAY_MAX} 快捷项；"
            f"亦可手动输入 {QUICK_UI_TIMES_PER_DAY_MIN}～{QUICK_UI_TIMES_PER_DAY_MAX} 的整数。"
            f"在下方开始时间～结束时间之间均匀插点。"
        )
        # EditableComboBox 继承 LineEdit，无 lineEdit()；setCurrentIndex(-1) 会清空并恢复占位
        self.quick_schedule_combo.blockSignals(True)
        self.quick_schedule_combo.setCurrentIndex(-1)
        self.quick_schedule_combo.blockSignals(False)
        try:
            self.quick_schedule_combo.returnPressed.disconnect()
        except TypeError:
            pass
        self.quick_schedule_combo.returnPressed.connect(self._on_quick_schedule_return_pressed)
        self.quick_schedule_combo.currentIndexChanged.connect(self._on_quick_schedule_index_changed)
        # 下拉再次点选当前项时 index 不变，currentIndexChanged 不触发；activated 每次点击都会发
        self.quick_schedule_combo.activated.connect(self._on_quick_schedule_index_changed)
        self.quick_schedule_combo.editingFinished.connect(self._on_quick_schedule_editing_finished)
        # 手输多位数时若未失焦/回车不会触发 editingFinished；文本变化即尝试套用合法次数（无防抖延迟）
        self.quick_schedule_combo.currentTextChanged.connect(
            self._on_quick_schedule_text_changed)
        quick_only_lay.addWidget(self.quick_schedule_combo, 0, Qt.AlignmentFlag.AlignVCenter)
        self._quick_schedule_summary_label = StrongBodyLabel("", ch)
        self._quick_schedule_summary_label.setObjectName("QuickScheduleSummaryLabel")
        _accent = themeColor()
        _r, _g, _b = _accent.red(), _accent.green(), _accent.blue()
        self._quick_schedule_summary_label.setStyleSheet(
            f"QLabel#QuickScheduleSummaryLabel {{"
            f"font-size: 15px;"
            f"font-weight: 600;"
            f"color: {_accent.name()};"
            f"background-color: rgba({_r},{_g},{_b},0.14);"
            f"padding: 5px 14px;"
            f"border-radius: 6px;"
            f"}}"
        )
        quick_only_lay.addWidget(self._quick_schedule_summary_label, 0, Qt.AlignmentFlag.AlignVCenter)
        quick_only_lay.addStretch(1)
        self._update_quick_schedule_summary_label()
        form.addRow(BodyLabel("每日次数：", ch), quick_only)

        start_row = QWidget(ch)
        start_row_lay = QHBoxLayout(start_row)
        start_row_lay.setContentsMargins(0, 0, 0, 0)
        start_row_lay.setSpacing(8)
        self.batch_schedule_start_time_picker = DailyPoolTimePicker(start_row)
        self.batch_schedule_start_time_picker.setTime(QTime(6, 0))
        for _c in (0, 1):
            self.batch_schedule_start_time_picker.setColumnWidth(_c, _TIME_PICKER_COLUMN_WIDTH)
        self.batch_schedule_start_time_picker.setFixedHeight(30)
        self.batch_schedule_start_time_picker.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        start_row_lay.addWidget(
            self.batch_schedule_start_time_picker, 0, Qt.AlignmentFlag.AlignVCenter)
        start_row_lay.addStretch(1)
        form.addRow(BodyLabel("开始时间：", ch), start_row)

        end_row = QWidget(ch)
        end_row_lay = QHBoxLayout(end_row)
        end_row_lay.setContentsMargins(0, 0, 0, 0)
        end_row_lay.setSpacing(8)
        self.batch_schedule_end_time_picker = DailyPoolTimePicker(end_row)
        self.batch_schedule_end_time_picker.setTime(QTime(22, 0))
        for _c in (0, 1):
            self.batch_schedule_end_time_picker.setColumnWidth(_c, _TIME_PICKER_COLUMN_WIDTH)
        self.batch_schedule_end_time_picker.setFixedHeight(30)
        self.batch_schedule_end_time_picker.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        end_row_lay.addWidget(
            self.batch_schedule_end_time_picker, 0, Qt.AlignmentFlag.AlignVCenter)
        end_row_lay.addStretch(1)
        form.addRow(BodyLabel("结束时间：", ch), end_row)

        radio_row = QWidget(ch)
        radio_row_lay = QHBoxLayout(radio_row)
        radio_row_lay.setContentsMargins(0, 0, 0, 0)
        radio_row_lay.setSpacing(12)
        self.radio_batch_time_on_hour = RadioButton("整点", ch)
        self.radio_batch_time_random = RadioButton("随机分钟", ch)
        self.radio_batch_time_random.setChecked(True)
        self._batch_time_minute_mode_group = QButtonGroup(ch)
        self._batch_time_minute_mode_group.setExclusive(True)
        # 显式 id，避免未指定 id 时部分环境下互斥/信号异常导致「整点」无法切换
        self._batch_time_minute_mode_group.addButton(self.radio_batch_time_on_hour, 0)
        self._batch_time_minute_mode_group.addButton(self.radio_batch_time_random, 1)
        radio_row_lay.addWidget(self.radio_batch_time_on_hour)
        radio_row_lay.addWidget(self.radio_batch_time_random)
        radio_row_lay.addStretch(1)
        form.addRow(BodyLabel("分钟模式：", ch), radio_row)

        card_lay.addLayout(form)
        # Ignored 横向：使「①排期日期」卡宽度严格按 stretch 派分，便于底部「排期 X 天」对齐。
        self.batch_date_card.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        lay.addWidget(self.batch_date_card, 6)

        self._batch_pool_column = QWidget(page)
        # Ignored 横向：使「②排期时间」列宽度严格按 stretch 派分，便于底部「每日 X 次」对齐。
        self._batch_pool_column.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._batch_pool_column, 4)
        self._build_batch_pool_column()

        self.stacked_widget.addWidget(page)

        self.days_combo_box.currentIndexChanged.connect(self._sync_batch_slots)
        self.batch_combo_start_date_picker.dateChanged.connect(self._sync_batch_slots)
        self.batch_schedule_start_time_picker.timeChanged.connect(
            self._on_batch_schedule_start_time_changed
        )
        self.batch_schedule_start_time_picker.timeConfirmed.connect(
            self._on_batch_schedule_start_time_changed
        )
        self.batch_schedule_end_time_picker.timeChanged.connect(
            self._on_batch_schedule_start_time_changed
        )
        self.batch_schedule_end_time_picker.timeConfirmed.connect(
            self._on_batch_schedule_start_time_changed
        )
        self._batch_time_minute_mode_group.idClicked.connect(
            self._on_batch_time_minute_mode_changed
        )

    def _build_batch_pool_column(self) -> None:
        """批量 Tab 内「②排期时间」卡（标题栏内时间选择；下方为可滚动时间池）。"""
        col = self._batch_pool_column
        outer = QVBoxLayout(col)
        outer.setContentsMargins(0, 2, 0, 0)
        outer.setSpacing(0)

        header_tools = QWidget(col)
        ht_lay = QHBoxLayout(header_tools)
        ht_lay.setContentsMargins(0, 0, 0, 0)
        ht_lay.setSpacing(8)

        self.daily_time_picker = DailyPoolTimePicker(header_tools)
        self.daily_time_picker.setTime(QTime(8, 0))
        self.daily_time_picker.timeConfirmed.connect(self._on_add_daily_template)
        for _c in (0, 1):
            self.daily_time_picker.setColumnWidth(_c, _TIME_PICKER_COLUMN_WIDTH)
        # 与库内 Picker 列按钮高度一致，避免压扁导致省略号
        self.daily_time_picker.setFixedHeight(30)
        self.daily_time_picker.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        ht_lay.addWidget(self.daily_time_picker, 0, Qt.AlignmentFlag.AlignVCenter)
        ht_lay.addStretch(1)

        self.batch_time_card, ch, content_lay = self._create_module_card(
            col, "②排期时间", header_tools)
        outer.addWidget(self.batch_time_card, 1)

        pool_scroll = QScrollArea(ch)
        self._daily_pool_scroll = pool_scroll
        pool_scroll.setWidgetResizable(True)
        pool_scroll.setFrameShape(QFrame.Shape.NoFrame)
        pool_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        pool_scroll.setMinimumHeight(120)
        pool_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        scroll_inner = QWidget(ch)
        self._daily_pool_scroll_inner = scroll_inner
        scroll_inner_lay = QVBoxLayout(scroll_inner)
        scroll_inner_lay.setContentsMargins(0, 0, 0, 0)
        scroll_inner_lay.setSpacing(0)

        self.daily_pool_table = TableWidget(ch)
        self.daily_pool_table.setObjectName("DailyTimePoolTable")
        self.daily_pool_table.setColumnCount(3)
        self.daily_pool_table.setHorizontalHeaderLabels(["序号", "时间", "操作"])
        self.daily_pool_table.horizontalHeader().setDefaultAlignment(
            Qt.AlignCenter | Qt.AlignVCenter)
        dhh = self.daily_pool_table.horizontalHeader()
        dhh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        dhh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        dhh.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        dhh.setStretchLastSection(False)
        self.daily_pool_table.setColumnWidth(0, 44)
        self.daily_pool_table.setColumnWidth(2, 92)
        self.daily_pool_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        # 与右侧「排期结果」表一致：不显示行选中高亮（仍可双击编辑时间格）
        self.daily_pool_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.daily_pool_table.verticalHeader().setVisible(False)
        self.daily_pool_table.verticalHeader().setDefaultSectionSize(34)
        # 与右侧「③排期结果」一致：Fluent TableWidget 默认无网格线 + 斑马纹（圆角行底）
        self.daily_pool_table.setAlternatingRowColors(True)
        self.daily_pool_table.setShowGrid(False)
        self.daily_pool_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.daily_pool_table.itemChanged.connect(self._on_daily_pool_item_changed)
        self._daily_pool_hour_delegate = DailyPoolRandomHourDelegate(
            self, self.daily_pool_table)
        self.daily_pool_table.setItemDelegateForColumn(
            1, self._daily_pool_hour_delegate)

        self.daily_pool_empty_placeholder = self._create_daily_pool_empty_placeholder(ch)

        self.template_stack = QStackedWidget(ch)
        self.template_stack.setObjectName("DailyPoolTemplateStack")
        self.template_stack.addWidget(self.daily_pool_table)
        self.template_stack.addWidget(self.daily_pool_empty_placeholder)
        self.template_stack.setCurrentWidget(self.daily_pool_empty_placeholder)
        self.template_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        scroll_inner_lay.addWidget(self.template_stack)
        pool_scroll.setWidget(scroll_inner)
        content_lay.addWidget(pool_scroll, 1)

    def _create_daily_pool_empty_placeholder(self, parent: QWidget) -> QWidget:
        """每日时间池无数据时的居中占位（图标 + 主副文案）。"""
        wrap = QWidget(parent)
        wrap.setObjectName("DailyPoolEmptyPlaceholder")
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(8, 16, 8, 24)
        outer.addStretch(1)
        mid = QHBoxLayout()
        mid.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(6)
        col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_w = IconWidget(FluentIcon.CALENDAR, wrap)
        icon_w.setFixedSize(40, 40)
        col.addWidget(icon_w, 0, Qt.AlignmentFlag.AlignCenter)
        title = BodyLabel("暂无时间点", wrap)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #333333; font-weight: 500; font-size: 13px;")
        col.addWidget(title)
        hint = CaptionLabel("在上方选择时间，弹出面板中点击对号确认即可加入", wrap)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999999; font-size: 12px;")
        col.addWidget(hint)
        mid.addLayout(col)
        mid.addStretch(1)
        outer.addLayout(mid)
        outer.addStretch(2)
        return wrap

    def _create_schedule_result_empty_placeholder(self, parent: QWidget) -> QWidget:
        """③排期结果无数据时占位（与左侧时间池空态一致：图标 + 主副文案）。"""
        wrap = QWidget(parent)
        wrap.setObjectName("ScheduleResultEmptyPlaceholder")
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(8, 16, 8, 24)
        outer.addStretch(1)
        mid = QHBoxLayout()
        mid.addStretch(1)
        col = QVBoxLayout()
        col.setSpacing(6)
        col.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_w = IconWidget(FluentIcon.CALENDAR, wrap)
        icon_w.setFixedSize(40, 40)
        col.addWidget(icon_w, 0, Qt.AlignmentFlag.AlignCenter)
        title = BodyLabel("暂无排期", wrap)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #333333; font-weight: 500; font-size: 13px;")
        col.addWidget(title)
        hint = CaptionLabel(
            "暂无排期。在左侧选择日期与时间并添加排期，或添加「立即发布」后，将在此显示完整列表",
            wrap)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #999999; font-size: 12px;")
        col.addWidget(hint)
        mid.addLayout(col)
        mid.addStretch(1)
        outer.addLayout(mid)
        outer.addStretch(2)
        return wrap

    def _hydrate_daily_templates_from_existing_slots(self) -> None:
        """从已有完整排期（time_slots）还原「②排期时间」池，避免再次打开弹窗时中间列为空。

        「整点」模式：按完整时分去重。「随机分钟」下生成时只取模板的小时，故多天的 06:xx
        应对应池中一行 06:00（展示为 06:随机）；若所有时刻分钟均为 0，则按完整 HH:mm 去重即可。
        """
        if not self.time_slots:
            return
        if self.daily_time_templates:
            return

        parsed_times: List[QTime] = []
        for ts in self.time_slots:
            if ts is None:
                continue
            s = (ts or "").strip()
            if not s:
                continue
            dt = QDateTime.fromString(s, "yyyy-MM-dd HH:mm")
            if not dt.isValid():
                continue
            parsed_times.append(dt.time())

        if not parsed_times:
            return

        all_zero_minute = all(
            t.minute() == 0 and t.second() == 0 for t in parsed_times
        )
        random_mode = self.radio_batch_time_random.isChecked()

        uniq: List[str] = []
        seen: set[str] = set()
        if not random_mode:
            for t in parsed_times:
                key = t.toString("HH:mm")
                if key not in seen:
                    seen.add(key)
                    uniq.append(key)
        elif all_zero_minute:
            for t in parsed_times:
                key = t.toString("HH:mm")
                if key not in seen:
                    seen.add(key)
                    uniq.append(key)
        else:
            for t in parsed_times:
                key = f"{t.hour():02d}:00"
                if key not in seen:
                    seen.add(key)
                    uniq.append(key)
        uniq.sort()
        self.daily_time_templates = uniq
        self._template_custom_flags = [False] * len(uniq)

    # ------------------------------------------------------------------ 时间池操作
    def _sort_paired_templates(self) -> None:
        """按时间字符串排序，同步重排 _template_custom_flags。"""
        if not self.daily_time_templates:
            self._template_custom_flags = []
            return
        while len(self._template_custom_flags) < len(self.daily_time_templates):
            self._template_custom_flags.append(False)
        self._template_custom_flags = self._template_custom_flags[
            : len(self.daily_time_templates)
        ]
        pairs = list(zip(self.daily_time_templates, self._template_custom_flags))
        pairs.sort(key=lambda x: x[0])
        self.daily_time_templates = [p[0] for p in pairs]
        self._template_custom_flags = [p[1] for p in pairs]

    def _on_add_daily_template(self):
        t = self.daily_time_picker.time
        if not t.isValid():
            return
        time_str = t.toString("HH:mm")
        if time_str not in self.daily_time_templates:
            self.daily_time_templates.append(time_str)
            self._template_custom_flags.append(True)
            self._sort_paired_templates()
            self._refresh_daily_time_pool_table()
            self._sync_batch_slots()
        else:
            InfoBar.warning("提示", f"{time_str} 已在时间池中",
                            parent=self, position=InfoBarPosition.TOP, duration=2000)

    def _on_clear_daily_template(self):
        self.daily_time_templates.clear()
        self._template_custom_flags.clear()
        if hasattr(self, "quick_schedule_combo"):
            # EditableComboBox：若当前已是 index=-1，setCurrentIndex(-1) 会直接 return，
            # 不会清空手输内容，须先 setText("")。
            combo = self.quick_schedule_combo
            combo.blockSignals(True)
            combo.setText("")
            if combo.currentIndex() >= 0:
                combo.setCurrentIndex(-1)
            combo.blockSignals(False)
            self._update_quick_schedule_summary_label()
        self._pool_render_key = None
        self._refresh_daily_time_pool_table()
        self._sync_batch_slots()

    def _update_quick_schedule_summary_label(self) -> None:
        """右侧说明：未选时「选择次数」，合法数字为「一天N次」，否则短横线。"""
        if not hasattr(self, "_quick_schedule_summary_label"):
            return
        raw = self.quick_schedule_combo.text().strip()
        n = _parse_times_per_day_from_quick_ui(raw)
        if n is not None:
            self._quick_schedule_summary_label.setText(f"一天{n}次")
        elif raw:
            self._quick_schedule_summary_label.setText("—")
        else:
            self._quick_schedule_summary_label.setText("选择次数")

    def _on_quick_schedule_index_changed(self, index: int) -> None:
        if index < 0:
            return
        n = self.quick_schedule_combo.itemData(index)
        if n is None:
            n = _parse_times_per_day_from_quick_ui(self.quick_schedule_combo.currentText())
        if n is None:
            return
        self._apply_quick_templates(int(n))

    def _on_quick_schedule_editing_finished(self) -> None:
        self._try_apply_quick_schedule_from_text()

    def _on_quick_schedule_return_pressed(self) -> None:
        self._try_apply_quick_schedule_from_text()

    def _on_quick_schedule_text_changed(self, text: str) -> None:
        self._update_quick_schedule_summary_label()
        self._apply_quick_schedule_from_text_silent()

    def _apply_quick_schedule_from_text_silent(self) -> None:
        """输入稳定后套用次数；非法或未完成时不弹窗，避免打断输入。"""
        raw = self.quick_schedule_combo.text().strip()
        if not raw:
            return
        n = _parse_times_per_day_from_quick_ui(raw)
        if n is None:
            return
        self._apply_quick_templates(n)

    def _try_apply_quick_schedule_from_text(self) -> None:
        raw = self.quick_schedule_combo.text().strip()
        if not raw:
            return
        n = _parse_times_per_day_from_quick_ui(raw)
        if n is None:
            InfoBar.warning(
                "次数无效",
                f"请输入 {QUICK_UI_TIMES_PER_DAY_MIN}～"
                f"{QUICK_UI_TIMES_PER_DAY_MAX} 之间的整数，或从下拉选择预设。",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2500,
            )
            return
        self._apply_quick_templates(n)

    def _on_batch_schedule_start_time_changed(self) -> None:
        n = _parse_times_per_day_from_quick_ui(self.quick_schedule_combo.currentText())
        if n is not None:
            self._apply_quick_templates(n)

    def _apply_quick_templates(self, times_per_day: int):
        start = self.batch_schedule_start_time_picker.time
        if not start.isValid():
            start = QTime(0, 0)
        h, m = start.hour(), start.minute()
        end = self.batch_schedule_end_time_picker.time
        if not end.isValid():
            end = QTime(22, 0)
        eh, em = end.hour(), end.minute()
        if self.radio_batch_time_on_hour.isChecked():
            tpls, err = generate_daily_templates_whole_hour_axis(
                h, m, times_per_day, end_hour=eh, end_minute=em
            )
        else:
            tpls, err = generate_daily_templates_random_minute_axis(
                h, m, times_per_day, end_hour=eh, end_minute=em
            )
        if err:
            self.daily_time_templates = []
            self._template_custom_flags = []
            self._show_infobar_throttled("排期无效", err, level="warning", duration=3500)
        else:
            self.daily_time_templates = tpls
            self._template_custom_flags = [False] * len(tpls)
        self._refresh_daily_time_pool_table()
        self._sync_batch_slots()
        self._update_quick_schedule_summary_label()

    def _compute_batch_slots(self) -> List[str]:
        if not self.daily_time_templates:
            self._batch_schedule_meta = {}
            return []
        days = self.days_combo_box.currentData()
        now = QDateTime.currentDateTime()
        min_dt = now.addSecs(9000)
        max_dt = now.addDays(15)
        base_date = self.batch_combo_start_date_picker.date
        if not base_date.isValid():
            base_date = now.date().addDays(1)
        random_minutes = self.radio_batch_time_random.isChecked()
        slots, meta = compute_batch_schedule_slots_core(
            list(self.daily_time_templates),
            int(days) if days is not None else 1,
            base_date,
            random_minutes,
            min_dt,
            max_dt,
            rng=random.Random(),
            custom_flags=list(self._template_custom_flags),
        )
        self._batch_schedule_meta = meta
        return slots

    def _sync_batch_slots(self):
        self.time_slots = self._compute_batch_slots()
        self._refresh_time_table()
        self._maybe_hint_batch_schedule_shortfall()

    def _maybe_hint_batch_schedule_shortfall(self) -> None:
        """批量模式下若因 2.5h/15 天规则未排满，提示用户（防抖见 _show_infobar_throttled）。"""
        sw = getattr(self, "stacked_widget", None)
        if sw is None or sw.currentIndex() != 0:
            return
        meta = getattr(self, "_batch_schedule_meta", None) or {}
        if meta.get("shortfall_total", 0) <= 0:
            return
        parts = meta.get("per_date_shortfall") or {}
        if not parts:
            return
        detail = "；".join(f"{d} 少 {c} 条" for d, c in sorted(parts.items())[:6])
        if len(parts) > 6:
            detail += "…"
        self._show_infobar_throttled(
            "排期未满",
            "定时发布须在至少 2.5 小时之后且不超过 15 天，部分日期未能排满与「②排期时间」一致的条数。"
            + (f" {detail}" if detail else ""),
            level="info",
            duration=5000,
        )

    def _on_batch_time_minute_mode_changed(self, _button_id: Optional[int] = None) -> None:
        """整点/随机分钟切换时刷新时间池展示，并与右侧排期一致。

        不从已展开的多天 time_slots 反推每日模板，否则随机分钟产生的多条时刻会被当成多条模板。

        由 QButtonGroup.idClicked(int) 触发；参数可忽略。
        """
        self._pool_render_key = None
        self._refresh_daily_time_pool_table()
        self._sync_batch_slots()

    def _is_template_custom(self, template_hhmm: str) -> bool:
        """标题栏确认添加的行为 True，快捷等分生成的为 False。"""
        if template_hhmm not in self.daily_time_templates:
            return False
        idx = self.daily_time_templates.index(template_hhmm)
        return idx < len(self._template_custom_flags) and self._template_custom_flags[idx]

    def _template_chip_display(
        self, template_hhmm: str, is_custom: bool = False
    ) -> tuple[str, bool, Optional[str]]:
        """返回 (展示文案, 是否只读, 工具提示)。随机分钟模式下非自定义行展示「HH:随机」。"""
        if not self.radio_batch_time_random.isChecked():
            return template_hhmm, False, ""
        if is_custom:
            tip = (
                "标题栏或本行自定义添加：按固定时分参与排期，该小时内不再随机；"
                "可双击编辑具体时分"
            )
            return template_hhmm, False, tip
        base_t = QTime.fromString(template_hhmm, "HH:mm")
        if not base_t.isValid():
            return template_hhmm, False, ""
        disp = f"{base_t.hour():02d}:随机"
        tip = (
            "发布时刻在该小时内的 0–59 分随机（与「HH:随机」一致），再受定时最早/最晚时间限制；"
            "可双击修改小时。选「整点」可编辑具体时分"
        )
        return disp, False, tip

    def _remove_pool_template(self, canonical_hhmm: str) -> None:
        if canonical_hhmm in self.daily_time_templates:
            idx = self.daily_time_templates.index(canonical_hhmm)
            self.daily_time_templates.pop(idx)
            if idx < len(self._template_custom_flags):
                self._template_custom_flags.pop(idx)
            self._refresh_daily_time_pool_table()
            self._sync_batch_slots()

    def _apply_daily_pool_time_change(
        self, item: QTableWidgetItem, old_canon: str, new_canon: str
    ) -> None:
        """将时间池中某格从 old_canon 更新为 new_canon（合法 HH:mm）。重复则还原并提示。"""
        if new_canon == old_canon:
            return
        tbl = self.daily_pool_table
        for r in range(tbl.rowCount()):
            oi = tbl.item(r, 1)
            if oi is None or oi is item:
                continue
            other = oi.data(Qt.ItemDataRole.UserRole)
            if isinstance(other, str) and other == new_canon:
                InfoBar.warning(
                    "提示", f"{new_canon} 已在时间池中",
                    parent=self, position=InfoBarPosition.TOP, duration=2000)
                self._revert_daily_pool_cell(item)
                return
        if old_canon not in self.daily_time_templates:
            self._revert_daily_pool_cell(item)
            return
        idx = self.daily_time_templates.index(old_canon)
        flag = (
            self._template_custom_flags[idx]
            if idx < len(self._template_custom_flags)
            else False
        )
        self.daily_time_templates.pop(idx)
        if idx < len(self._template_custom_flags):
            self._template_custom_flags.pop(idx)
        self.daily_time_templates.append(new_canon)
        self._template_custom_flags.append(flag)
        self._sort_paired_templates()
        self._refresh_daily_time_pool_table()
        self._sync_batch_slots()

    def _on_daily_pool_item_changed(self, item: QTableWidgetItem) -> None:
        if self._pool_table_updating:
            return
        if item.column() != 1:
            return
        old = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(old, str):
            old = _normalize_time_str(item.text()) or item.text()
        if self.radio_batch_time_random.isChecked():
            if isinstance(old, str) and self._is_template_custom(old):
                new_norm = _normalize_time_str(item.text())
                if not new_norm:
                    self._revert_daily_pool_cell(item)
                    self._show_infobar_throttled(
                        "格式不正确",
                        "请输入有效时间，例如 08:00",
                        duration=2000,
                    )
                    return
            else:
                new_norm = _normalize_random_mode_pool_input(item.text())
                if not new_norm:
                    self._revert_daily_pool_cell(item)
                    self._show_infobar_throttled(
                        "格式不正确",
                        "随机分钟模式下请输入小时：如 8、08、09:随机 或 08:00",
                        duration=2000,
                    )
                    return
        else:
            new_norm = _normalize_time_str(item.text())
            if not new_norm:
                self._revert_daily_pool_cell(item)
                self._show_infobar_throttled(
                    "格式不正确", "请输入有效时间，例如 08:00", duration=2000)
                return
        self._apply_daily_pool_time_change(item, old, new_norm)

    def _revert_daily_pool_cell(self, item: QTableWidgetItem) -> None:
        canon = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(canon, str):
            return
        disp, ro, tip = self._template_chip_display(
            canon, self._is_template_custom(canon)
        )
        self.daily_pool_table.blockSignals(True)
        self._pool_table_updating = True
        # 展示文案始终用 disp（随机分钟下非自定义为「HH:随机」；自定义为固定 HH:mm）
        item.setText(disp)
        item.setData(Qt.ItemDataRole.UserRole, canon)
        if tip:
            item.setToolTip(tip)
        self._pool_table_updating = False
        self.daily_pool_table.blockSignals(False)

    def _refresh_daily_time_pool_table(self) -> None:
        has_any = bool(self.daily_time_templates)
        self.template_stack.setCurrentWidget(
            self.daily_pool_table if has_any else self.daily_pool_empty_placeholder)

        tbl = self.daily_pool_table
        tbl.setUpdatesEnabled(False)
        self._pool_table_updating = True
        tbl.blockSignals(True)

        if not has_any:
            tbl.clearContents()
            tbl.setRowCount(0)
            self._pool_render_key = None
            tbl.blockSignals(False)
            self._pool_table_updating = False
            tbl.setUpdatesEnabled(True)
            return

        templates = sorted(self.daily_time_templates)
        rnd = self.radio_batch_time_random.isChecked()
        flags_per_sorted = tuple(
            self._is_template_custom(t) for t in templates
        )
        pool_key: Tuple[bool, Tuple[str, ...], Tuple[bool, ...]] = (
            rnd,
            tuple(templates),
            flags_per_sorted,
        )
        if (
            pool_key == self._pool_render_key
            and tbl.rowCount() == len(templates)
            and len(templates) > 0
        ):
            tbl.blockSignals(False)
            self._pool_table_updating = False
            tbl.setUpdatesEnabled(True)
            return

        tbl.clearContents()
        tbl.setRowCount(0)

        tbl.setRowCount(len(templates))
        for row, t_str in enumerate(templates):
            idx_it = QTableWidgetItem(str(row + 1))
            idx_it.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            idx_it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tbl.setItem(row, 0, idx_it)

            disp, ro, tip = self._template_chip_display(
                t_str, self._is_template_custom(t_str)
            )
            it = QTableWidgetItem(disp)
            it.setData(Qt.ItemDataRole.UserRole, t_str)
            it.setTextAlignment(
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            if ro:
                it.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
            else:
                it.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEditable
                )
            if tip:
                it.setToolTip(tip)
            tbl.setItem(row, 1, it)
            tbl.setRowHeight(row, 34)

            btn_del = PushButton("移除", None)
            btn_del.setFixedSize(56, 28)
            btn_del.setMinimumWidth(56)
            btn_del.clicked.connect(
                lambda _c, s=t_str: self._remove_pool_template(s))
            tbl.setCellWidget(
                row, 2,
                _TableCellCenterHost(btn_del, tbl, row, 2))

        self._pool_render_key = pool_key
        tbl.blockSignals(False)
        self._pool_table_updating = False
        tbl.setUpdatesEnabled(True)

    # ------------------------------------------------------------------ 校验 / 单次添加
    def _show_infobar_throttled(self, title: str, content: str, level: str = "warning", duration: int = 2500):
        now_ms = QDateTime.currentMSecsSinceEpoch()
        if now_ms - getattr(self, "_last_infobar_ms", 0) < 1200:
            return
        self._last_infobar_ms = now_ms
        if self._last_infobar is not None:
            try:
                self._last_infobar.close()  # type: ignore
            except Exception:
                pass
        fn = {"warning": InfoBar.warning, "info": InfoBar.info,
              "success": InfoBar.success, "error": InfoBar.error}.get(level, InfoBar.warning)
        self._last_infobar = fn(title, content, duration=duration,
                                position=InfoBarPosition.TOP, parent=self.window())

    def _validate_schedule_time(self):
        if getattr(self, '_is_validating_time', False):
            return
        current_date = self.batch_date_picker.date
        current_time = self.batch_time_picker.time
        if not current_date.isValid() or not current_time.isValid():
            return
        selected_dt = QDateTime(current_date, current_time)
        now = QDateTime.currentDateTime()
        min_dt = now.addSecs(9000)
        max_dt = now.addDays(15)
        if selected_dt < min_dt:
            self._is_validating_time = True
            target_dt = min_dt.addSecs(300)
            self.batch_date_picker.setDate(target_dt.date())
            self.batch_time_picker.setTime(target_dt.time())
            self._show_infobar_throttled("时间已修正", "定时发布必须至少设置在 2.5 小时以后")
            self._is_validating_time = False
        elif selected_dt > max_dt:
            self._is_validating_time = True
            self.batch_date_picker.setDate(max_dt.date())
            self._show_infobar_throttled("时间已修正", "定时发布最多只能设置在 15 天以内")
            self._is_validating_time = False

    def _on_add_time(self):
        d = self.batch_date_picker.date
        t = self.batch_time_picker.time
        if not d.isValid() or not t.isValid():
            InfoBar.warning("提示", "请先选择有效的日期和时间",
                            parent=self, position=InfoBarPosition.TOP, duration=2000)
            return
        selected_dt = QDateTime(d, t)
        now = QDateTime.currentDateTime()
        min_dt = now.addSecs(9000)
        max_dt = now.addDays(15)
        if selected_dt < min_dt:
            InfoBar.warning("时间不合规", "配置的定时时间必须大于2.5小时",
                            parent=self, position=InfoBarPosition.TOP)
            return
        if selected_dt > max_dt:
            InfoBar.warning("时间不合规", "配置的定时时间不能超过15天",
                            parent=self, position=InfoBarPosition.TOP)
            return
        time_str = selected_dt.toString("yyyy-MM-dd HH:mm")
        if time_str in [s for s in self.time_slots if isinstance(s, str)]:
            InfoBar.info("不再重复添加", f"{time_str} 已存在",
                         parent=self, position=InfoBarPosition.TOP, duration=2000)
            return
        self.time_slots.append(time_str)
        if not any(s is None for s in self.time_slots):
            self.time_slots.sort()
        self._refresh_time_table()
        next_dt = selected_dt.addSecs(3 * 3600)
        if next_dt <= max_dt:
            self.batch_date_picker.setDate(next_dt.date())
            self.batch_time_picker.setTime(next_dt.time())

    def _on_add_immediate(self) -> None:
        """在排期结果中追加一条「立即发布」槽位（与定时混排，顺序参与任务分配）。"""
        self.time_slots.append(None)
        self._refresh_time_table()

    # ------------------------------------------------------------------ 排期表格 / 统计
    def _refresh_time_table(self):
        stack = getattr(self, "schedule_result_stack", None)
        tt = self.time_table
        tt.setUpdatesEnabled(False)
        try:
            if not self.time_slots:
                tt.setRowCount(0)
                self._time_slots_render_snapshot = None
                if stack is not None:
                    stack.setCurrentIndex(0)
                self._update_statistics_panel()
                return

            if stack is not None:
                stack.setCurrentIndex(1)

            new = self.time_slots
            n_new = len(new)

            # 行数不变且末列控件已存在：只更新时间与序号，避免销毁数百个 Fluent 按钮 + Host
            if tt.rowCount() == n_new and n_new > 0:
                can_patch = True
                for i in range(n_new):
                    if tt.item(i, 1) is None or tt.cellWidget(i, 2) is None:
                        can_patch = False
                        break
                if can_patch:
                    for i in range(n_new):
                        it1 = tt.item(i, 1)
                        if it1 is None:
                            can_patch = False
                            break
                        cell_txt = "立即发布" if new[i] is None else str(new[i])
                        tip_txt = (
                            "立即发布（写入发布列表时不指定定时时间）"
                            if new[i] is None
                            else str(new[i])
                        )
                        if it1.text() != cell_txt:
                            it1.setText(cell_txt)
                            it1.setToolTip(tip_txt)
                    if can_patch:
                        for i in range(n_new):
                            it0 = tt.item(i, 0)
                            if it0 is not None:
                                it0.setText(str(i + 1))
                        self._time_slots_render_snapshot = list(new)
                        self._update_statistics_panel()
                        return

            tt.clearContents()
            tt.setRowCount(n_new)
            for row, ts in enumerate(new):
                idx_it = QTableWidgetItem(str(row + 1))
                idx_it.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                idx_it.setFlags(Qt.ItemFlag.ItemIsEnabled)
                tt.setItem(row, 0, idx_it)
                cell_txt = "立即发布" if ts is None else str(ts)
                tip_txt = (
                    "立即发布（写入发布列表时不指定定时时间）"
                    if ts is None
                    else str(ts)
                )
                item = QTableWidgetItem(cell_txt)
                item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                item.setToolTip(tip_txt)
                tt.setItem(row, 1, item)
                btn_del = PushButton("移除", None)
                btn_del.setFixedSize(52, 28)
                btn_del.setMinimumWidth(52)
                btn_del.clicked.connect(lambda _, r=row: self._remove_time(r))
                tt.setCellWidget(
                    row, 2,
                    _TableCellCenterHost(btn_del, tt, row, 2))
                tt.setRowHeight(row, 34)
            self._time_slots_render_snapshot = list(new)
            self._update_statistics_panel()
        finally:
            tt.setUpdatesEnabled(True)

    def _update_statistics_panel(self):
        """底部排期汇总：第一行三色胶囊（排期/每日/任务），第二行详情条（账号/总任务/排期窗口）。"""
        d = getattr(self, "_schedule_stat_pill_days", None)
        a = getattr(self, "_schedule_stat_pill_daily", None)
        t = getattr(self, "_schedule_stat_pill_total", None)
        if d is None or a is None or t is None:
            return
        is_batch_tab = (
            getattr(self, "stacked_widget", None) is not None
            and self.stacked_widget.currentIndex() == 0
        )
        total = len(self.time_slots)
        owner_count = max(0, int(getattr(self, "_owner_count", 0) or 0))

        # ---- 第二行：详情条（账号 / 计划总任务 + 公式 / 排期窗口）----
        chip_owner = getattr(self, "_stat_chip_owner_value", None)
        chip_total_v = getattr(self, "_stat_chip_total_value", None)
        chip_total_h = getattr(self, "_stat_chip_total_hint", None)
        chip_range = getattr(self, "_stat_chip_range_value", None)
        if chip_owner is not None:
            chip_owner.setText(f"{owner_count} 个")
        if chip_total_v is not None:
            chip_total_v.setText(f"{total * owner_count} 个")
        if chip_total_h is not None:
            if total > 0 and owner_count > 0:
                chip_total_h.setVisible(True)
                chip_total_h.setText(f"= {total} 篇 × {owner_count} 个账号")
            else:
                chip_total_h.setVisible(False)
        if chip_range is not None:
            if total == 0:
                chip_range.setText("—")
            else:
                timed_only = [
                    ts for ts in self.time_slots
                    if isinstance(ts, str) and str(ts).strip()
                ]
                if not timed_only:
                    n_imm = sum(1 for ts in self.time_slots if ts is None)
                    chip_range.setText(
                        "含立即发布" if n_imm > 0 else "—"
                    )
                else:
                    _ds = sorted({ts.split(" ")[0] for ts in timed_only})
                    if len(_ds) == 1:
                        chip_range.setText(f"{_ds[0]}（当日）")
                    else:
                        chip_range.setText(f"{_ds[0]} 至 {_ds[-1]}（{len(_ds)} 天）")

        if total == 0:
            d.setText("排期 0 天")
            d.setToolTip("排期天数")
            t.setText("任务 0 篇")
            t.setToolTip("任务总计")
            if is_batch_tab:
                n_pool = len(getattr(self, "daily_time_templates", []) or [])
                a.setText(f"每日 {n_pool} 次（配置）")
                a.setToolTip(
                    f"配置时间点：{n_pool} 档\n"
                    "当前暂无排期结果"
                )
            else:
                a.setText("每日 0 篇")
                a.setToolTip("每日次数（配置）或日均（实际）")
            return
        timed_only = [
            ts for ts in self.time_slots
            if isinstance(ts, str) and str(ts).strip()
        ]
        n_imm = sum(1 for ts in self.time_slots if ts is None)
        dates_sorted = sorted({ts.split(" ")[0] for ts in timed_only})
        days_count = len(dates_sorted)
        if days_count > 0:
            daily_avg = len(timed_only) / days_count
            daily_actual_txt = (
                f"{daily_avg:.1f} 篇" if daily_avg % 1 != 0 else f"{int(daily_avg)} 篇"
            )
            per_day = Counter(ts.split(" ")[0] for ts in timed_only)
            per_day_items = sorted(per_day.items())
            per_lines = "；".join(f"{ds}：{c} 篇" for ds, c in per_day_items[:3])
            if len(per_day_items) > 3:
                per_lines += f"；等 {len(per_day_items)} 天"
            if n_imm > 0:
                per_lines = (per_lines + "；" if per_lines else "") + f"立即发布槽 {n_imm} 个"
        else:
            daily_actual_txt = "—" if n_imm > 0 else "0 篇"
            per_lines = f"立即发布槽 {n_imm} 个" if n_imm > 0 else ""

        d.setText(f"排期 {days_count} 天")
        d.setToolTip(
            "排期覆盖的自然日数（仅统计定时项；含立即发布槽时不计入天数）"
        )

        if is_batch_tab:
            # 以②排期时间表格行数为准（含快捷生成 + 标题栏自定义追加），不用左侧「每日次数」框单独数值
            n_pool = len(getattr(self, "daily_time_templates", []) or [])
            a.setText(f"每日 {n_pool} 次（配置）")
            a.setToolTip(
                f"配置时间点：{n_pool} 档\n"
                f"实际日均：{daily_actual_txt}\n"
                f"按日：{per_lines}"
            )
        else:
            a.setText(f"日均（实际）{daily_actual_txt}")
            a.setToolTip(
                f"按当前结果列表折算\n"
                f"按日：{per_lines}"
            )

        t.setText(f"任务 {total} 篇")
        t.setToolTip(
            f"结果列表共 {total} 条（含定时与立即发布槽）\n"
            f"明细：{per_lines or '—'}"
        )

    def _remove_time(self, row: int):
        if 0 <= row < len(self.time_slots):
            self.time_slots.pop(row)
            self._refresh_time_table()

    def get_schedule_slots(self) -> List[Optional[str]]:
        """返回排期槽列表（顺序与右侧表格一致）；None 表示立即发布。"""
        return list(self.time_slots)

    def get_time_slots(self) -> List[Optional[str]]:
        """与 ``get_schedule_slots`` 相同，保留旧方法名。"""
        return list(self.time_slots)
