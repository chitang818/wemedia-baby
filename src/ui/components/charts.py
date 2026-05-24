"""
图表组件
文件路径：src/ui/components/charts.py
功能：封装PySide6.QtCharts，提供平台分布环形图和发布趋势面积图，自动适配深色/浅色主题
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Callable, Dict, List, Optional, Any

logger = logging.getLogger(__name__)

try:
    import shiboken6 as _shiboken6
except ImportError:
    _shiboken6 = None  # type: ignore[misc, assignment]


def _qobject_alive(obj: Optional[QWidget]) -> bool:
    if obj is None:
        return False
    if _shiboken6 is None:
        return True
    try:
        return bool(_shiboken6.isValid(obj))
    except Exception:
        return True

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGraphicsSimpleTextItem,
    QSizePolicy,
    QLabel,
    QFrame,
    QProgressBar,
    QScrollArea,
)
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QLinearGradient
from PySide6.QtCharts import (
    QChart,
    QChartView,
    QPieSeries,
    QPieSlice,
    QLineSeries,
    QAreaSeries,
    QDateTimeAxis,
    QValueAxis,
)
from PySide6.QtCore import Qt, QDateTime, QPointF, QTimer, QPropertyAnimation, QEasingCurve

from qfluentwidgets import CardWidget, SubtitleLabel, CaptionLabel, BodyLabel, PushButton, isDarkTheme

from src.ui.components.loading_spinner import LoadingOverlay
from src.ui.workspace_chart_animation_prefs import (
    CHART_ENTRY_ANIMATION_MS,
    CHART_OVERLAY_FADE_MS,
)


PLATFORM_BRAND_COLORS = {
    "抖音": "#000000",
    "视频号": "#07C160",
    "快手": "#FF6600",
    "小红书": "#FF2442",
    "哔哩哔哩": "#00A1D6",
    "今日头条": "#ED1C24",
    "百家号": "#2932E1",
    "新浪微博": "#E6162D",
    "多多视频": "#E02E24",
    "企鹅号": "#FAAD14",
}

FALLBACK_COLORS = [
    "#0078D4", "#00B7C3", "#00CC6A", "#FFB900", "#5C2D91",
    "#E81123", "#0099BC", "#8764B8"
]


class ChartLoadState(Enum):
    LOADING = "loading"
    READY = "ready"


def _apply_chart_animation(chart: QChart, *, animate: bool) -> None:
    """loading 阶段 NoAnimation；reveal 入场时短时 SeriesAnimations。"""
    if animate:
        chart.setAnimationDuration(CHART_ENTRY_ANIMATION_MS)
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)
    else:
        chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)


def _theme_colors():
    dark = isDarkTheme()
    return {
        "text_primary": "#FFFFFF" if dark else "#333333",
        "text_secondary": "#AAAAAA" if dark else "#666666",
        "text_muted": "#888888" if dark else "#999999",
        "grid_line": "#3E3E3E" if dark else "#E8E8E8",
        "empty": "#555555" if dark else "#D6DDE3",
        "theme_blue": "#4CC2FF" if dark else "#0078D4",
        "area_top": QColor(76, 194, 255, 100) if dark else QColor(0, 120, 212, 100),
        "area_bottom": QColor(76, 194, 255, 12) if dark else QColor(0, 120, 212, 12),
        "success_line": "#6CCB5F" if dark else "#107C10",
        "success_area_top": QColor(108, 203, 95, 90) if dark else QColor(16, 124, 16, 80),
        "success_area_btm": QColor(108, 203, 95, 8) if dark else QColor(16, 124, 16, 8),
        "failed_line": "#FF6B6B" if dark else "#E81123",
    }


class ChartBase(CardWidget):
    """图表基类：图表区 LoadingOverlay + reveal 入场动画。"""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._load_state = ChartLoadState.READY
        self._loading_shown_at: float = 0.0

        self.chart = QChart()
        self.chart.setBackgroundVisible(False)
        self.chart.layout().setContentsMargins(0, 0, 0, 0)
        self.chart.legend().setVisible(False)
        self.chart.setMargins(self.chart.margins())

        self._chart_body = QWidget(self)
        self._chart_body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        body_layout = QVBoxLayout(self._chart_body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing, False)
        self.chart_view.setStyleSheet("background: transparent;")
        body_layout.addWidget(self.chart_view)

        self._loading_overlay = LoadingOverlay("", ring_size=36, parent=self._chart_body)
        self._loading_overlay.hide_immediate()

        self._skeleton_host: Optional[QWidget] = None
        self._reveal_timer: Optional[QTimer] = None

        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(16, 12, 16, 8)
        self.v_layout.setSpacing(4)

        dark = isDarkTheme()
        title_color = "#FFFFFF" if dark else "#1A1A1A"
        self.title_label = SubtitleLabel(title, self)
        self.title_label.setStyleSheet(f"color: {title_color};")
        self.v_layout.addWidget(self.title_label)
        self.v_layout.addWidget(self._chart_body, 1)

    @property
    def is_loading(self) -> bool:
        return self._load_state == ChartLoadState.LOADING

    def _cancel_reveal_timer(self) -> None:
        if self._reveal_timer is None:
            return
        try:
            self._reveal_timer.stop()
            self._reveal_timer.deleteLater()
        except Exception:
            pass
        self._reveal_timer = None

    def cancel_pending_reveal(self) -> None:
        """页面切换或刷新前取消未完成的 reveal，避免定时器在已销毁控件上改 chart。"""
        self._cancel_reveal_timer()
        try:
            self._loading_overlay.hide_immediate()
        except Exception:
            pass

    def show_loading(self, text: str = "") -> None:
        """等待数据：遮罩 + 转圈（不更新 series）。"""
        import time

        self._cancel_reveal_timer()
        self._load_state = ChartLoadState.LOADING
        self._loading_shown_at = time.monotonic()
        self._loading_overlay.set_text(text)
        self._show_chart_skeleton()
        self._loading_overlay.show_animated()

    def reveal_with_data(
        self,
        apply_fn: Callable[..., None],
        *,
        animate_entry: bool = True,
    ) -> None:
        """数据就绪：遮罩淡出后单次写入 series（避免双次动画触发 Qt 原生崩溃）。"""
        self._cancel_reveal_timer()
        self._load_state = ChartLoadState.READY
        self._hide_chart_skeleton()

        if not _qobject_alive(self):
            return

        if not self._loading_overlay.isVisible():
            try:
                apply_fn(animate=animate_entry)
            except Exception:
                logger.exception("图表 reveal 写入失败")
            _apply_chart_animation(self.chart, animate=False)
            return

        def _after_overlay_hidden() -> None:
            if not _qobject_alive(self):
                return
            try:
                apply_fn(animate=animate_entry)
            except Exception:
                logger.exception("图表 reveal 写入失败")
            _apply_chart_animation(self.chart, animate=False)

        self._loading_overlay.hide_animated()
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setSingleShot(True)
        self._reveal_timer.timeout.connect(_after_overlay_hidden)
        self._reveal_timer.start(CHART_OVERLAY_FADE_MS + 30)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._loading_overlay.isVisible():
            self._loading_overlay._sync_geometry()

    def _show_chart_skeleton(self) -> None:
        """子类可覆盖：在图表区显示形状 skeleton。"""
        pass

    def _hide_chart_skeleton(self) -> None:
        if self._skeleton_host is not None:
            self._skeleton_host.hide()
            self._skeleton_host.setParent(None)
            self._skeleton_host.deleteLater()
            self._skeleton_host = None


def _get_platform_color(name: str, index: int) -> QColor:
    hex_color = PLATFORM_BRAND_COLORS.get(name)
    if not hex_color:
        hex_color = FALLBACK_COLORS[index % len(FALLBACK_COLORS)]
    c = QColor(hex_color)
    if name == "抖音" and isDarkTheme():
        c = QColor("#FFFFFF")
    return c


class _PlatformDistributionRow(QFrame):
    """平台分布排名行，提供轻量 hover 高亮。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._normal_bg = "transparent"
        self._hover_bg = "rgba(0, 120, 212, 0.07)"
        self.setObjectName("platformDistributionRow")
        self.setStyleSheet(
            "QFrame#platformDistributionRow {"
            f"background: {self._normal_bg}; border-radius: 6px;"
            "}"
        )

    def enterEvent(self, event):
        self.setStyleSheet(
            "QFrame#platformDistributionRow {"
            f"background: {self._hover_bg}; border-radius: 6px;"
            "}"
        )
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(
            "QFrame#platformDistributionRow {"
            f"background: {self._normal_bg}; border-radius: 6px;"
            "}"
        )
        super().leaveEvent(event)


class PlatformDistributionChart(ChartBase):
    """平台分布概览卡：总览指标 + 平台排名进度条。"""

    MAX_VISIBLE_ROWS = 6
    COLLAPSED_TOP_ROWS = 5

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("平台分布", parent)
        self._skeleton_items: list = []
        self._bar_animations: List[QPropertyAnimation] = []
        self._row_widgets: List[QWidget] = []
        self._current_data: Dict[str, int] = {}
        self._expanded = False

        self.chart_view.hide()

        title_item = self.v_layout.takeAt(0)
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        if title_item is not None and title_item.widget() is not None:
            header_layout.addWidget(title_item.widget())
        header_layout.addStretch(1)
        self.total_label = CaptionLabel("共 0 个账号", self)
        self.total_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header_layout.addWidget(self.total_label)
        self.expand_button = PushButton("展开", self)
        self.expand_button.setFixedHeight(26)
        self.expand_button.setMinimumWidth(58)
        self.expand_button.clicked.connect(self._toggle_expanded)
        header_layout.addWidget(self.expand_button)
        self.v_layout.insertWidget(0, header)

        tc = _theme_colors()
        self.summary_host = QWidget(self)
        summary_layout = QHBoxLayout(self.summary_host)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(8)
        self.platform_count_label = self._make_metric_label("0 个平台", "已接入")
        self.top_platform_label = self._make_metric_label("暂无", "最多账号")
        summary_layout.addWidget(self.platform_count_label, 1)
        summary_layout.addWidget(self.top_platform_label, 1)
        self.v_layout.insertWidget(1, self.summary_host)

        self._platform_scroll = QScrollArea(self._chart_body)
        self._platform_scroll.setWidgetResizable(True)
        self._platform_scroll.setFrameShape(QFrame.NoFrame)
        self._platform_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._platform_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._platform_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._platform_body = QWidget(self._platform_scroll)
        self._platform_body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._platform_body_layout = QVBoxLayout(self._platform_body)
        self._platform_body_layout.setContentsMargins(0, 4, 0, 0)
        self._platform_body_layout.setSpacing(4)

        self.empty_label = BodyLabel("暂无账号", self._platform_body)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {tc['text_muted']}; font-size: 13px;")

        body_layout = self._chart_body.layout()
        if body_layout is not None:
            body_layout.addWidget(self._platform_scroll)
        self._platform_scroll.setWidget(self._platform_body)
        self.set_data({}, animate=False)

    def _make_metric_label(self, value: str, caption: str) -> QLabel:
        tc = _theme_colors()
        label = QLabel(f"<b>{value}</b><br><span>{caption}</span>", self)
        label.setTextFormat(Qt.RichText)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            "QLabel {"
            f"background: {'rgba(255,255,255,0.06)' if isDarkTheme() else '#F6F8FA'};"
            f"color: {tc['text_primary']};"
            "border-radius: 6px;"
            "padding: 6px 8px;"
            "font-size: 12px;"
            "}"
            f"QLabel span {{ color: {tc['text_muted']}; font-size: 11px; }}"
        )
        return label

    @staticmethod
    def build_distribution_rows(
        data: Dict[str, int],
        *,
        max_rows: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        clean_rows = [
            (str(platform), int(count or 0))
            for platform, count in (data or {}).items()
            if int(count or 0) > 0
        ]
        clean_rows.sort(key=lambda item: (-item[1], item[0]))

        total = sum(count for _, count in clean_rows)
        rows: List[Dict[str, Any]] = []
        for index, (platform, count) in enumerate(clean_rows):
            percent = (count / total * 100.0) if total else 0.0
            color = _get_platform_color(platform, index).name()
            if platform == "其他":
                color = "#8A8F98" if not isDarkTheme() else "#A0A7B0"
            rows.append(
                {
                    "platform": platform,
                    "count": count,
                    "percent": percent,
                    "color": color,
                }
            )
        return rows

    @classmethod
    def build_collapsed_rows(cls, data: Dict[str, int]) -> List[Dict[str, Any]]:
        rows = cls.build_distribution_rows(data)
        if len(rows) <= cls.MAX_VISIBLE_ROWS:
            return rows

        visible = rows[: cls.COLLAPSED_TOP_ROWS]
        other_rows = rows[cls.COLLAPSED_TOP_ROWS :]
        other_count = sum(int(row["count"]) for row in other_rows)
        total = sum(int(row["count"]) for row in rows)
        percent = (other_count / total * 100.0) if total else 0.0
        visible.append(
            {
                "platform": f"其他 {len(other_rows)} 个平台",
                "count": other_count,
                "percent": percent,
                "color": "#8A8F98" if not isDarkTheme() else "#A0A7B0",
                "is_other": True,
                "other_platform_count": len(other_rows),
            }
        )
        return visible

    def _clear_rows(self) -> None:
        for ani in self._bar_animations:
            try:
                ani.stop()
            except Exception:
                pass
        self._bar_animations = []
        while self._platform_body_layout.count():
            item = self._platform_body_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._row_widgets = []

    def _update_metric_labels(self, rows: List[Dict[str, Any]], total: int) -> None:
        platform_count = len(rows)
        top_row = rows[0] if rows else None
        top_text = (
            f"{top_row['platform']} {top_row['count']}"
            if top_row is not None
            else "暂无"
        )
        self.total_label.setText(f"共 {total} 个账号")
        self.platform_count_label.setText(f"<b>{platform_count} 个平台</b><br><span>已接入</span>")
        self.top_platform_label.setText(f"<b>{top_text}</b><br><span>最多账号</span>")

    def _create_row(self, row: Dict[str, Any], *, animate: bool) -> QWidget:
        tc = _theme_colors()
        platform = str(row["platform"])
        count = int(row["count"])
        percent = float(row["percent"])
        color = str(row["color"])
        value_text = (
            f"共 {count} 个账号 · {percent:.1f}%"
            if row.get("is_other")
            else f"{count}  ·  {percent:.1f}%"
        )

        item = _PlatformDistributionRow(self._platform_body)
        item.setToolTip(f"{platform}: {count} 个账号，占比 {percent:.1f}%")
        layout = QVBoxLayout(item)
        layout.setContentsMargins(8, 3, 8, 3)
        layout.setSpacing(3)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        dot = QLabel(item)
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        top_row.addWidget(dot, 0, Qt.AlignVCenter)

        name_label = CaptionLabel(platform, item)
        name_label.setToolTip(platform)
        name_label.setStyleSheet(f"color: {tc['text_primary']}; font-size: 12px;")
        top_row.addWidget(name_label, 1)

        value_label = CaptionLabel(value_text, item)
        value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        value_label.setStyleSheet(f"color: {tc['text_secondary']}; font-size: 12px;")
        top_row.addWidget(value_label, 0)
        layout.addLayout(top_row)

        progress = QProgressBar(item)
        progress.setRange(0, 1000)
        progress.setTextVisible(False)
        progress.setFixedHeight(5)
        progress.setValue(0 if animate else int(percent * 10))
        track_color = "rgba(255,255,255,0.10)" if isDarkTheme() else "#E9EEF3"
        progress.setStyleSheet(
            "QProgressBar {"
            f"background: {track_color}; border: none; border-radius: 3px;"
            "}"
            "QProgressBar::chunk {"
            f"background: {color}; border-radius: 3px;"
            "}"
        )
        layout.addWidget(progress)

        if animate:
            ani = QPropertyAnimation(progress, b"value", self)
            ani.setDuration(360)
            ani.setStartValue(0)
            ani.setEndValue(int(percent * 10))
            ani.setEasingCurve(QEasingCurve.OutCubic)
            self._bar_animations.append(ani)
            ani.start()

        return item

    def _show_chart_skeleton(self) -> None:
        from src.ui.components.skeleton import SkeletonItem

        self._hide_chart_skeleton()
        host = QWidget(self._chart_body)
        host.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.setSpacing(12)
        self._skeleton_items = []
        for width in (0.86, 0.72, 0.64, 0.48):
            row = SkeletonItem(host, radius=5)
            row.setFixedHeight(14)
            layout.addWidget(row)
            layout.addStretch(max(0, int((1 - width) * 10)))
            self._skeleton_items.append(row)
            row.start_breathing()
        layout.addStretch(1)
        host.setGeometry(self._chart_body.rect())
        host.show()
        host.raise_()
        self._skeleton_host = host

    def _hide_chart_skeleton(self) -> None:
        for item in self._skeleton_items:
            try:
                item.stop_breathing()
            except Exception:
                pass
        self._skeleton_items = []
        super()._hide_chart_skeleton()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._skeleton_host is not None:
            self._skeleton_host.setGeometry(self._chart_body.rect())

    def reveal_platform_data(self, data: Dict[str, int], *, animate_entry: bool = True) -> None:
        self.reveal_with_data(
            lambda *, animate=False: self.set_data(data, animate=animate),
            animate_entry=animate_entry,
        )

    def set_data(self, data: Dict[str, int], *, animate: bool = False):
        self._current_data = dict(data or {})
        self._render_current_data(animate=animate)

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._render_current_data(animate=False)

    def _render_current_data(self, *, animate: bool = False) -> None:
        all_rows = self.build_distribution_rows(self._current_data)
        visible_rows = all_rows if self._expanded else self.build_collapsed_rows(self._current_data)
        total = sum(int(row["count"]) for row in all_rows)
        self._clear_rows()
        self._update_metric_labels(all_rows, total)
        can_expand = len(all_rows) > self.MAX_VISIBLE_ROWS
        self.expand_button.setVisible(can_expand)
        self.expand_button.setText("收起" if self._expanded else "展开")

        if total <= 0:
            hint = BodyLabel("暂无账号", self._platform_body)
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet(f"color: {_theme_colors()['text_muted']}; font-size: 13px;")
            self._platform_body_layout.addStretch(1)
            self._platform_body_layout.addWidget(hint)
            self._platform_body_layout.addStretch(1)
            self._row_widgets.append(hint)
            return

        for row in visible_rows:
            widget = self._create_row(row, animate=animate)
            self._platform_body_layout.addWidget(widget)
            self._row_widgets.append(widget)
        self._platform_body_layout.addStretch(1)


class PublishTrendChart(ChartBase):
    """发布趋势图：成功（绿色面积）+ 失败（红色折线）双系列"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("发布趋势", parent)
        self._skeleton_items: list = []
        tc = _theme_colors()

        # 副标题（汇总数字）
        dark = isDarkTheme()
        sub_color = "#AAAAAA" if dark else "#888888"
        self.summary_label = CaptionLabel("", self)
        self.summary_label.setStyleSheet(f"color: {sub_color}; font-size: 12px;")
        self.v_layout.insertWidget(1, self.summary_label)

        # 图例行
        legend_row = QHBoxLayout()
        legend_row.setContentsMargins(0, 0, 0, 0)
        legend_row.setSpacing(16)
        for label_text, color_hex in [("成功", tc["success_line"]), ("失败", tc["failed_line"])]:
            dot = QWidget(self)
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(f"background: {color_hex}; border-radius: 4px;")
            lbl = CaptionLabel(label_text, self)
            lbl.setStyleSheet(f"color: {sub_color}; font-size: 11px;")
            legend_row.addWidget(dot)
            legend_row.addWidget(lbl)
        legend_row.addStretch()
        self.v_layout.insertLayout(2, legend_row)

        # ── 成功面积系列（绿色渐变）──
        self.success_upper = QLineSeries()
        self.success_lower = QLineSeries()
        self.success_area = QAreaSeries(self.success_upper, self.success_lower)
        pen_s = QPen(QColor(tc["success_line"]))
        pen_s.setWidth(2)
        self.success_area.setPen(pen_s)
        self.chart.addSeries(self.success_area)

        # ── 失败折线系列（红色）──
        self.failed_series = QLineSeries()
        pen_f = QPen(QColor(tc["failed_line"]))
        pen_f.setWidth(2)
        self.failed_series.setPen(pen_f)
        self.chart.addSeries(self.failed_series)

        _apply_chart_animation(self.chart, animate=False)

        axis_font = QFont()
        axis_font.setPixelSize(11)
        axis_label_color = QColor(tc["text_secondary"])
        grid_pen = QPen(QColor(tc["grid_line"]), 1, Qt.DashLine)

        self.axis_x = QDateTimeAxis()
        self.axis_x.setTickCount(5)
        self.axis_x.setFormat("MM/dd")
        self.axis_x.setTitleText("")
        self.axis_x.setLabelsFont(axis_font)
        self.axis_x.setLabelsColor(axis_label_color)
        self.axis_x.setGridLineColor(QColor(tc["grid_line"]))
        self.axis_x.setGridLinePen(grid_pen)
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        self.success_area.attachAxis(self.axis_x)
        self.failed_series.attachAxis(self.axis_x)

        self.axis_y = QValueAxis()
        self.axis_y.setLabelFormat("%i")
        self.axis_y.setTitleText("")
        self.axis_y.setMin(0)
        self.axis_y.setLabelsFont(axis_font)
        self.axis_y.setLabelsColor(axis_label_color)
        self.axis_y.setGridLineColor(QColor(tc["grid_line"]))
        self.axis_y.setGridLinePen(grid_pen)
        self.chart.addAxis(self.axis_y, Qt.AlignLeft)
        self.success_area.attachAxis(self.axis_y)
        self.failed_series.attachAxis(self.axis_y)

        self._empty_text: Optional[QGraphicsSimpleTextItem] = None

    def _apply_gradient(self):
        plot_area = self.chart.plotArea()
        if plot_area.isEmpty():
            return
        tc = _theme_colors()
        gradient = QLinearGradient(
            QPointF(0, plot_area.top()),
            QPointF(0, plot_area.bottom())
        )
        gradient.setColorAt(0.0, tc["success_area_top"])
        gradient.setColorAt(1.0, tc["success_area_btm"])
        self.success_area.setBrush(QBrush(gradient))

    def _show_empty_hint(self):
        if self._empty_text:
            return
        tc = _theme_colors()
        item = QGraphicsSimpleTextItem()
        item.setText("暂无发布数据")
        font = QFont()
        font.setPixelSize(13)
        item.setFont(font)
        item.setBrush(QBrush(QColor(tc["text_muted"])))
        self.chart.scene().addItem(item)
        self._empty_text = item
        self._reposition_empty()

    def _hide_empty_hint(self):
        if self._empty_text:
            self.chart.scene().removeItem(self._empty_text)
            self._empty_text = None

    def _reposition_empty(self):
        if not self._empty_text:
            return
        plot_area = self.chart.plotArea()
        if plot_area.isEmpty():
            return
        br = self._empty_text.boundingRect()
        self._empty_text.setPos(
            plot_area.center().x() - br.width() / 2,
            plot_area.center().y() - br.height() / 2,
        )

    def _show_chart_skeleton(self) -> None:
        from src.ui.components.skeleton import SkeletonItem

        self._hide_chart_skeleton()
        host = QWidget(self._chart_body)
        host.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(10)
        self._skeleton_items = []
        for _ in range(4):
            bar = SkeletonItem(host, radius=4)
            bar.setFixedHeight(14)
            layout.addWidget(bar)
            bar.start_breathing()
            self._skeleton_items.append(bar)
        layout.addStretch()
        host.setGeometry(self._chart_body.rect())
        host.show()
        host.raise_()
        self._skeleton_host = host

    def _hide_chart_skeleton(self) -> None:
        for item in self._skeleton_items:
            try:
                item.stop_breathing()
            except Exception:
                pass
        self._skeleton_items = []
        super()._hide_chart_skeleton()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._skeleton_host is not None:
            self._skeleton_host.setGeometry(self._chart_body.rect())
        self._apply_gradient()
        self._reposition_empty()

    def reveal_trend_data(
        self,
        history: List[Dict[str, Any]],
        *,
        animate_entry: bool = True,
    ) -> None:
        self.reveal_with_data(
            lambda *, animate=False: self.set_data(history, animate=animate),
            animate_entry=animate_entry,
        )

    def set_data(self, history: List[Dict[str, Any]], *, animate: bool = False):
        _apply_chart_animation(self.chart, animate=animate)
        if animate:
            self.chart_view.setRenderHint(QPainter.Antialiasing, True)
        self.success_upper.clear()
        self.success_lower.clear()
        self.failed_series.clear()

        if not history:
            self.summary_label.setText("")
            self._show_empty_hint()
            return

        total_all = sum(item.get('count', 0) for item in history)
        if total_all == 0:
            self.summary_label.setText("近期无发布记录")
            self._show_empty_hint()
            return

        self._hide_empty_hint()

        sorted_history = sorted(history, key=lambda x: x['date'])
        total_success = sum(item.get('success', 0) for item in sorted_history)
        total_failed = sum(item.get('failed', 0) for item in sorted_history)
        days = len(sorted_history)
        self.summary_label.setText(
            f"近{days}天：成功 {total_success}  |  失败 {total_failed}  |  共 {total_all}"
        )

        max_val = 0
        has_failed = total_failed > 0

        for item in sorted_history:
            dt = QDateTime.fromString(item['date'], "yyyy-MM-dd")
            ms = dt.toMSecsSinceEpoch()
            s_count = item.get('success', 0)
            f_count = item.get('failed', 0)
            self.success_upper.append(ms, s_count)
            self.success_lower.append(ms, 0)
            if has_failed:
                self.failed_series.append(ms, f_count)
            day_max = max(s_count, f_count)
            if day_max > max_val:
                max_val = day_max

        if sorted_history:
            first_date = QDateTime.fromString(sorted_history[0]['date'], "yyyy-MM-dd")
            last_date = QDateTime.fromString(sorted_history[-1]['date'], "yyyy-MM-dd")
            self.axis_x.setRange(first_date, last_date)

        y_max = max(max_val + 1, 3)
        self.axis_y.setRange(0, y_max)
        self.axis_y.setTickCount(min(y_max + 1, 6))

        self._apply_gradient()
