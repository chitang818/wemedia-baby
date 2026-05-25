"""
账号统计卡
顶部账号摘要 + 横向条形平台分布（堆叠总览 + 分行进度条）。
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QSizePolicy,
    QProgressBar,
    QLabel,
)
from PySide6.QtCore import Qt, QTimer

from qfluentwidgets import (
    CardWidget,
    SubtitleLabel,
    CaptionLabel,
    BodyLabel,
    isDarkTheme,
)

from src.ui.components.charts import PlatformDistributionChart, _theme_colors
from src.ui.components.skeleton import SkeletonItem
from src.ui.utils.fluent_tooltips import ToolTipPosition, install_fluent_tool_tip
from src.ui.workspace_chart_animation_prefs import STATS_SKELETON_MIN_MS

# 工作台半宽双列统一高度（账号统计 | 发布统计）
OVERVIEW_PAIR_HEIGHT = 300
OVERVIEW_PAIR_HEIGHT_MAXIMIZED = 400
OVERVIEW_PAIR_HEIGHT_MIN = 220
OVERVIEW_PAIR_STACKED_GAP = 10
# 视口预算余量：概览前间距、圆角与布局取整误差
OVERVIEW_VIEWPORT_SAFETY = 16
# 默认窗口下发布统计卡高度上限（与并排双列区单卡高度一致，由页面按视口动态收紧）
PUBLISH_STATS_CARD_MAX_HEIGHT = OVERVIEW_PAIR_HEIGHT
HALF_COLUMN_CARD_HEIGHT = OVERVIEW_PAIR_HEIGHT


def resolve_overview_pair_height(*, maximized: bool, stacked: bool) -> int:
    """并排或上下堆叠时，双列区宿主控件的总高度（未按视口收紧）。"""
    single = OVERVIEW_PAIR_HEIGHT_MAXIMIZED if maximized else OVERVIEW_PAIR_HEIGHT
    if stacked:
        return single * 2 + OVERVIEW_PAIR_STACKED_GAP
    return single


def clamp_overview_pair_height(
    preferred: int,
    *,
    budget: Optional[int],
    stacked: bool,
) -> int:
    """默认窗口：用视口剩余高度收紧双列区，避免工作台整页滚动。"""
    if budget is None:
        return preferred
    if stacked:
        min_host = OVERVIEW_PAIR_HEIGHT_MIN * 2 + OVERVIEW_PAIR_STACKED_GAP
        return max(min_host, min(preferred, budget))
    return max(OVERVIEW_PAIR_HEIGHT_MIN, min(preferred, budget))


def overview_pair_card_height(host_height: int, *, stacked: bool) -> int:
    """堆叠时两张卡平分宿主高度；并排时与宿主同高。"""
    if stacked:
        return (host_height - OVERVIEW_PAIR_STACKED_GAP) // 2
    return host_height


def publish_stats_card_height(pair_card_height: int) -> int:
    """发布统计卡与并排双列区单卡同高（列表在卡片内滚动）。"""
    return pair_card_height

MAX_PLATFORM_ROWS = 5
BAR_ROW_HEIGHT = 36
BAR_TRACK_HEIGHT = 7
STACKED_BAR_HEIGHT = 10

_OVERVIEW_ACCENT_COLORS: Dict[str, str] = {
    "抖音": "#E8437A",
    "视频号": "#2EB872",
    "快手": "#F08A24",
    "小红书": "#E9355E",
    "哔哩哔哩": "#23A3D8",
    "微博": "#E02424",
    "头条": "#E85D04",
    "百家号": "#4B5BDB",
    "多多视频": "#D4380D",
    "企鹅号": "#D48806",
}
_OVERVIEW_ACCENT_FALLBACK = ["#4A90D9", "#36A86B", "#E8A020", "#D85A7A", "#7E57C2"]


class OverviewLoadState(Enum):
    LOADING = "loading"
    READY = "ready"


def _overview_accent_color(platform: str, index: int) -> str:
    name = str(platform or "")
    if name in _OVERVIEW_ACCENT_COLORS:
        return _OVERVIEW_ACCENT_COLORS[name]
    if "其他" in name:
        return "#8A8F98" if not isDarkTheme() else "#A0A7B0"
    return _OVERVIEW_ACCENT_FALLBACK[index % len(_OVERVIEW_ACCENT_FALLBACK)]


def _enrich_overview_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = dict(row)
        platform = str(item.get("platform", ""))
        item["accent_color"] = _overview_accent_color(platform, index)
        enriched.append(item)
    return enriched


def _bar_track_color() -> str:
    return "rgba(255, 255, 255, 0.08)" if isDarkTheme() else "#EEF2F7"


def _set_fluent_tooltip(
    widget: QWidget,
    text: str,
    *,
    position: ToolTipPosition = ToolTipPosition.BOTTOM,
) -> None:
    """Fluent 自绘提示，避免 Windows 原生 QToolTip 黑底深字不可读。"""
    tip = (text or "").strip()
    widget.setToolTip(tip)
    if tip:
        install_fluent_tool_tip(widget, position=position)


def _lighten_hex(hex_color: str, factor: float = 0.35) -> str:
    """生成进度条渐变末端色（略浅）。"""
    c = (hex_color or "#888888").lstrip("#")
    if len(c) != 6:
        return hex_color
    try:
        r = int(c[0:2], 16)
        g = int(c[2:4], 16)
        b = int(c[4:6], 16)
    except ValueError:
        return hex_color
    r = min(255, int(r + (255 - r) * factor))
    g = min(255, int(g + (255 - g) * factor))
    b = min(255, int(b + (255 - b) * factor))
    return f"#{r:02X}{g:02X}{b:02X}"


def build_overview_platform_rows(data: Dict[str, int]) -> List[Dict[str, Any]]:
    """概览用平台行（供测试）；条形列表最多 5 行。"""
    rows = PlatformDistributionChart.build_distribution_rows(data)
    if len(rows) <= MAX_PLATFORM_ROWS:
        return rows
    visible = rows[: MAX_PLATFORM_ROWS - 1]
    other_rows = rows[MAX_PLATFORM_ROWS - 1 :]
    other_count = sum(int(row["count"]) for row in other_rows)
    total = sum(int(row["count"]) for row in rows)
    percent = (other_count / total * 100.0) if total else 0.0
    visible.append(
        {
            "platform": f"其他 {len(other_rows)} 个",
            "count": other_count,
            "percent": percent,
            "color": "#8A8F98" if not isDarkTheme() else "#A0A7B0",
            "is_other": True,
        }
    )
    return visible


class PlatformStackedBar(QWidget):
    """顶部堆叠比例条：一眼看清各平台占比。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(STACKED_BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

    def set_segments(self, rows: List[Dict[str, Any]]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        total = sum(int(r.get("count", 0)) for r in rows)
        if total <= 0:
            placeholder = QFrame(self)
            placeholder.setStyleSheet(
                f"background: {_bar_track_color()}; border-radius: {STACKED_BAR_HEIGHT // 2}px;"
            )
            self._layout.addWidget(placeholder, 1)
            return

        for row in rows:
            count = int(row.get("count", 0))
            if count <= 0:
                continue
            accent = str(row.get("accent_color") or row.get("color", "#888"))
            seg = QFrame(self)
            seg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            seg.setFixedHeight(STACKED_BAR_HEIGHT)
            end = _lighten_hex(accent, 0.4)
            seg.setStyleSheet(
                f"QFrame {{"
                f"background: qlineargradient("
                f"x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {end});"
                f"border-radius: {STACKED_BAR_HEIGHT // 2}px;"
                f"border: none;"
                f"}}"
            )
            _set_fluent_tooltip(
                seg,
                f"{row.get('platform', '')}: {count} 个账号 "
                f"（{float(row.get('percent', 0)):.1f}%）",
                position=ToolTipPosition.TOP,
            )
            self._layout.addWidget(seg, max(1, count))


class PlatformDistributionBarRow(QFrame):
    """单行平台横向统计：色点 + 名称 + 数量/占比 + 渐变进度条。"""

    def __init__(self, row: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("platformBarRow")
        platform = str(row.get("platform", ""))
        count = int(row.get("count", 0))
        accent = str(row.get("accent_color") or row.get("color", "#888888"))
        percent = float(row.get("percent", 0))
        percent_clamped = max(0.0, min(100.0, percent))

        _set_fluent_tooltip(
            self,
            f"{platform}: {count} 个账号（{percent:.1f}%）",
            position=ToolTipPosition.BOTTOM,
        )
        self.setFixedHeight(BAR_ROW_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(5)

        tc = _theme_colors()
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)

        dot = QLabel(self)
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {accent}; border-radius: 4px;")

        name_lbl = CaptionLabel(platform, self)
        name_lbl.setStyleSheet(
            f"color: {tc['text_primary']}; font-size: 12px; font-weight: 600;"
        )

        count_lbl = BodyLabel(str(count), self)
        count_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        count_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {accent}; min-width: 20px;"
        )

        pct_lbl = CaptionLabel(f"{percent:.1f}%", self)
        pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pct_lbl.setFixedWidth(42)
        pct_lbl.setStyleSheet(f"color: {tc['text_muted']}; font-size: 11px;")

        top.addWidget(dot, 0, Qt.AlignVCenter)
        top.addWidget(name_lbl, 1, Qt.AlignVCenter)
        top.addWidget(count_lbl, 0, Qt.AlignVCenter)
        top.addWidget(pct_lbl, 0, Qt.AlignVCenter)
        root.addLayout(top)

        track = _bar_track_color()
        end_color = _lighten_hex(accent, 0.45)
        progress = QProgressBar(self)
        progress.setRange(0, 1000)
        progress.setTextVisible(False)
        progress.setFixedHeight(BAR_TRACK_HEIGHT)
        progress.setValue(int(percent_clamped * 10))
        progress.setStyleSheet(
            "QProgressBar {"
            f"background: {track};"
            "border: none;"
            f"border-radius: {BAR_TRACK_HEIGHT // 2}px;"
            "}"
            "QProgressBar::chunk {"
            f"background: qlineargradient("
            f"x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {end_color});"
            f"border-radius: {BAR_TRACK_HEIGHT // 2}px;"
            "}"
        )
        root.addWidget(progress)


class AccountPlatformOverviewCard(CardWidget):
    """账号总量 + 横向条形平台分布。"""

    def __init__(self, parent: Optional[QWidget] = None, *, half_column: bool = False):
        super().__init__(parent)
        self._half_column = half_column
        self._load_state = OverviewLoadState.READY
        self._loading_shown_at = 0.0
        self._reveal_timer: Optional[QTimer] = None
        self._bar_widgets: List[QWidget] = []
        self._stacked_bar: Optional[PlatformStackedBar] = None
        self._current_data: Dict[str, int] = {}
        self._account_stats: Dict[str, Any] = {}

        card_h = HALF_COLUMN_CARD_HEIGHT if half_column else 220
        self.setMinimumHeight(card_h)
        self.setMaximumHeight(card_h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        self._title_label = SubtitleLabel("账号统计", self)
        root.addWidget(self._title_label)

        summary = QWidget(self)
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(12)
        summary_layout.setAlignment(Qt.AlignVCenter)

        self._total_label = BodyLabel("—", summary)
        self._online_badge = CaptionLabel("—", summary)
        self._offline_badge = CaptionLabel("", summary)
        self._platform_hint_label = CaptionLabel("", summary)

        summary_layout.addWidget(self._total_label, 0, Qt.AlignVCenter)
        summary_layout.addWidget(self._online_badge, 0, Qt.AlignVCenter)
        summary_layout.addWidget(self._offline_badge, 0, Qt.AlignVCenter)
        summary_layout.addStretch(1)
        summary_layout.addWidget(self._platform_hint_label, 0, Qt.AlignVCenter)
        root.addWidget(summary)

        self._bars_host = QWidget(self)
        self._bars_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._bars_layout = QVBoxLayout(self._bars_host)
        self._bars_layout.setContentsMargins(0, 0, 0, 0)
        self._bars_layout.setSpacing(2)

        self._empty_label = BodyLabel("暂无账号", self._bars_host)
        self._empty_label.setAlignment(Qt.AlignCenter)
        tc = _theme_colors()
        self._empty_label.setStyleSheet(f"color: {tc['text_muted']}; font-size: 13px;")

        root.addWidget(self._bars_host, 1)

        self._skeleton_host: Optional[QWidget] = None
        self._apply_theme()

    @property
    def is_loading(self) -> bool:
        return self._load_state == OverviewLoadState.LOADING

    def _apply_theme(self) -> None:
        dark = isDarkTheme()
        total_color = "#4CC2FF" if dark else "#0078D4"
        total_px = 28 if self._half_column else 32
        self._total_label.setStyleSheet(
            f"font-size: {total_px}px; font-weight: 700; color: {total_color};"
        )
        muted = "#AAAAAA" if dark else "#757575"
        online_color = "#6CCB5F" if dark else "#107C10"
        offline_color = "#888888" if dark else "#999999"
        self._online_badge.setStyleSheet(
            f"color: {online_color}; font-size: 12px; font-weight: 500;"
        )
        self._offline_badge.setStyleSheet(f"color: {offline_color}; font-size: 12px;")
        self._platform_hint_label.setStyleSheet(f"color: {muted}; font-size: 11px;")
        title_color = "#FFFFFF" if dark else "#1A1A1A"
        self._title_label.setStyleSheet(
            f"font-weight: 600; font-size: 15px; color: {title_color};"
        )
        if dark:
            self.setStyleSheet(
                "CardWidget {"
                "background: rgba(255, 255, 255, 0.04);"
                "border: 1px solid rgba(255, 255, 255, 0.08);"
                "border-radius: 8px;"
                "}"
            )
        else:
            self.setStyleSheet(
                "CardWidget {"
                "background: #FFFFFF;"
                "border: 1px solid #EBEEF2;"
                "border-radius: 8px;"
                "}"
            )

    def show_loading(self) -> None:
        self.cancel_pending_reveal()
        self._load_state = OverviewLoadState.LOADING
        self._loading_shown_at = time.monotonic()
        self._total_label.setText("—")
        self._online_badge.setText("加载中…")
        self._offline_badge.setText("")
        self._platform_hint_label.setText("")
        self._clear_bars()
        self._show_skeleton()

    def reveal(
        self,
        account_stats: Dict[str, Any],
        platform_data_cn: Dict[str, int],
        *,
        animate: bool = False,
    ) -> None:
        self.cancel_pending_reveal()
        if self._load_state == OverviewLoadState.LOADING and animate:
            elapsed_ms = (time.monotonic() - self._loading_shown_at) * 1000.0
            delay = max(0, int(STATS_SKELETON_MIN_MS - elapsed_ms))

            def _commit() -> None:
                self._finish_reveal(account_stats, platform_data_cn)

            self._reveal_timer = QTimer(self)
            self._reveal_timer.setSingleShot(True)
            self._reveal_timer.timeout.connect(_commit)
            self._reveal_timer.start(delay)
            return
        self._finish_reveal(account_stats, platform_data_cn)

    def cancel_pending_reveal(self) -> None:
        if self._reveal_timer is None:
            return
        try:
            self._reveal_timer.stop()
            self._reveal_timer.deleteLater()
        except Exception:
            pass
        self._reveal_timer = None

    def _finish_reveal(
        self,
        account_stats: Dict[str, Any],
        platform_data_cn: Dict[str, int],
    ) -> None:
        self._reveal_timer = None
        self._hide_skeleton()
        self._load_state = OverviewLoadState.READY
        self._account_stats = dict(account_stats or {})
        self._current_data = dict(platform_data_cn or {})
        self._apply_account_labels()
        self._render_platform_bars()

    def _apply_account_labels(self) -> None:
        total = int(self._account_stats.get("total", 0) or 0)
        online = int(self._account_stats.get("online", 0) or 0)
        offline = int(self._account_stats.get("offline", 0) or 0)
        by_platform = self._account_stats.get("by_platform") or {}
        platform_count = sum(1 for v in by_platform.values() if int(v or 0) > 0)

        self._total_label.setText(str(total))
        self._online_badge.setText(f"● {online} 在线")
        self._offline_badge.setText(f"○ {offline} 离线" if offline > 0 else "")
        if platform_count > 0:
            self._platform_hint_label.setText(f"{platform_count} 个平台已接入")
        else:
            self._platform_hint_label.setText("暂无已接入平台")

    def _render_platform_bars(self) -> None:
        self._clear_bars()
        rows = _enrich_overview_rows(build_overview_platform_rows(self._current_data))

        if not rows:
            self._bars_layout.addWidget(self._empty_label)
            self._empty_label.show()
            return

        self._empty_label.hide()

        if len(rows) > 1:
            self._stacked_bar = PlatformStackedBar(self._bars_host)
            self._stacked_bar.set_segments(rows[:MAX_PLATFORM_ROWS])
            self._bar_widgets.append(self._stacked_bar)
            self._bars_layout.addWidget(self._stacked_bar)
            self._bars_layout.addSpacing(6)

        for row in rows[:MAX_PLATFORM_ROWS]:
            bar_row = PlatformDistributionBarRow(row, self._bars_host)
            self._bar_widgets.append(bar_row)
            self._bars_layout.addWidget(bar_row)

        self._bars_layout.addStretch(0)

    def _clear_bars(self) -> None:
        self._stacked_bar = None
        while self._bars_layout.count():
            item = self._bars_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None and widget is not self._empty_label:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._bar_widgets = []

    def _show_skeleton(self) -> None:
        self._hide_skeleton()
        self._clear_bars()
        host = QWidget(self._bars_host)
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        stacked_sk = SkeletonItem(host, radius=5)
        stacked_sk.setFixedHeight(STACKED_BAR_HEIGHT)
        stacked_sk.start_breathing()
        layout.addWidget(stacked_sk)

        for _ in range(4):
            row_sk = SkeletonItem(host, radius=4)
            row_sk.setFixedHeight(BAR_TRACK_HEIGHT + 18)
            row_sk.start_breathing()
            layout.addWidget(row_sk)

        self._bars_layout.addWidget(host)
        self._skeleton_host = host

    def _hide_skeleton(self) -> None:
        if self._skeleton_host is None:
            return
        host = self._skeleton_host
        self._skeleton_host = None
        try:
            self._bars_layout.removeWidget(host)
        except Exception:
            pass
        host.deleteLater()

    def hideEvent(self, event) -> None:
        self.cancel_pending_reveal()
        super().hideEvent(event)
