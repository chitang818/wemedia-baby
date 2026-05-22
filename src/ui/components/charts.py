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
from PySide6.QtCore import Qt, QDateTime, QPointF, QTimer

from qfluentwidgets import CardWidget, SubtitleLabel, CaptionLabel, isDarkTheme

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


class PlatformDistributionChart(ChartBase):
    """平台分布环形图"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("平台分布", parent)
        self._skeleton_items: list = []
        self.series = QPieSeries()
        self.series.setHoleSize(0.55)
        self.chart.addSeries(self.series)
        _apply_chart_animation(self.chart, animate=False)

        self._center_text: Optional[QGraphicsSimpleTextItem] = None
        self._center_sub: Optional[QGraphicsSimpleTextItem] = None

    def _update_center_text(self, total: int):
        tc = _theme_colors()

        if self._center_text:
            self.chart.scene().removeItem(self._center_text)
            self._center_text = None

        text_item = QGraphicsSimpleTextItem()
        text_item.setText(f"{total}")
        font = QFont()
        font.setPixelSize(22)
        font.setBold(True)
        text_item.setFont(font)
        text_item.setBrush(QBrush(QColor(tc["text_primary"])))

        self.chart.scene().addItem(text_item)
        self._center_text = text_item
        self._reposition_center_text()

        sub_item = QGraphicsSimpleTextItem()
        sub_item.setText("个账号")
        sub_font = QFont()
        sub_font.setPixelSize(11)
        sub_item.setFont(sub_font)
        sub_item.setBrush(QBrush(QColor(tc["text_muted"])))
        self.chart.scene().addItem(sub_item)
        self._center_sub = sub_item
        self._reposition_center_text()

    def _reposition_center_text(self):
        plot_area = self.chart.plotArea()
        if plot_area.isEmpty():
            return
        cx = plot_area.center().x()
        cy = plot_area.center().y()

        if self._center_text:
            br = self._center_text.boundingRect()
            self._center_text.setPos(cx - br.width() / 2, cy - br.height() / 2 - 6)

        if self._center_sub:
            br = self._center_sub.boundingRect()
            self._center_sub.setPos(cx - br.width() / 2, cy + 10)

    def _show_chart_skeleton(self) -> None:
        from src.ui.components.skeleton import SkeletonItem

        self._hide_chart_skeleton()
        host = QWidget(self._chart_body)
        host.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(host)
        layout.setAlignment(Qt.AlignCenter)
        ring = SkeletonItem(host, radius=80)
        ring.setFixedSize(140, 140)
        layout.addWidget(ring, alignment=Qt.AlignCenter)
        self._skeleton_items = [ring]
        ring.start_breathing()
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
        self._reposition_center_text()

    def reveal_platform_data(self, data: Dict[str, int], *, animate_entry: bool = True) -> None:
        self.reveal_with_data(
            lambda *, animate=False: self.set_data(data, animate=animate),
            animate_entry=animate_entry,
        )

    def set_data(self, data: Dict[str, int], *, animate: bool = False):
        _apply_chart_animation(self.chart, animate=animate)
        if animate:
            self.chart_view.setRenderHint(QPainter.Antialiasing, True)
        tc = _theme_colors()
        self.series.clear()
        if self._center_sub:
            self.chart.scene().removeItem(self._center_sub)
            self._center_sub = None

        total = sum(data.values())
        idx = 0

        for platform, count in data.items():
            if count > 0:
                slice_ = self.series.append(platform, count)
                slice_.setLabel(f"{platform}  {count}")
                slice_.setLabelVisible(True)
                slice_.setLabelPosition(QPieSlice.LabelOutside)
                label_font = QFont()
                label_font.setPixelSize(11)
                slice_.setLabelFont(label_font)
                slice_.setLabelColor(QColor(tc["text_secondary"]))
                color = _get_platform_color(platform, idx)
                slice_.setColor(color)
                slice_.setBorderColor(color)
                slice_.setBorderWidth(0)
                slice_.hovered.connect(
                    lambda state, s=slice_: self._on_slice_hovered(state, s)
                )
                idx += 1

        if total == 0:
            empty = self.series.append("暂无数据", 1)
            empty.setColor(QColor(tc["empty"]))
            empty.setBorderColor(QColor(tc["empty"]))
            empty.setLabelVisible(False)

        self._update_center_text(total)

    def _on_slice_hovered(self, state: bool, slice_: QPieSlice):
        slice_.setExploded(state)
        if state:
            slice_.setExplodeDistanceFactor(0.06)


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
