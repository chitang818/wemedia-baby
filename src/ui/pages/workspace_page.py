"""
工作台页面
文件路径：src/ui/pages/workspace_page.py
功能：渐进式仪表盘——静态壳立即可见，数据分阶段加载
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QScrollArea,
    QFrame,
    QSizePolicy,
)
from PySide6.QtCore import QTimer, Qt, QEvent, Signal
from PySide6.QtGui import QResizeEvent
import logging

from qfluentwidgets import (
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    TitleLabel,
    CaptionLabel,
    FluentIcon,
    isDarkTheme,
)

from .base_page import BasePage
from .workspace.workspace_load_orchestrator import WorkspaceLoadOrchestrator
from src.services.material.media_library_stats_cache import get_media_library_stats_cache
from src.services.material.media_library_stats_types import MediaLibraryStats
from src.services.workspace.dashboard_snapshot import DashboardSnapshot
from src.utils.platform_names import PLATFORM_ID_TO_NAME as PLATFORM_NAME_MAP

logger = logging.getLogger(__name__)


class WorkspacePage(BasePage):
    """工作台页面（默认首页：禁用首显冻结，分阶段加载数据）"""

    _freeze_on_first_show = False
    _enable_show_fade = False
    _quick_action_card_min_width = 150
    _quick_action_card_max_width = 170

    refreshRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("工作台", parent)
        self._needs_show_transition = False

        from src.services.auth import CurrentUserService

        self._current_user_svc = CurrentUserService()
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        self.dashboard_service = None
        self._orchestrator: Optional[WorkspaceLoadOrchestrator] = None
        self._charts_created = False
        self._chart_first_reveal_done = False
        self._stats_first_reveal_done = False
        self._secondary_widgets_created = False
        self._announcement_created = False
        self._recent_activity_created = False
        self._cached_reminders = []
        self._hold_media_stats_updates = False
        self._held_media_stats = None

        self.refreshRequested.connect(self._on_refresh_requested)
        self._init_services()
        self._setup_content()
        self._setup_refresh_timer()
        self._orchestrator = WorkspaceLoadOrchestrator(self)

        self._stats_cache = get_media_library_stats_cache()
        try:
            self._stats_cache.statsUpdated.connect(self._on_media_stats_updated)
        except Exception:
            pass
        cached_applied = self._orchestrator.apply_cached_first_paint()
        if cached_applied:
            self._stats_first_reveal_done = True
        else:
            self.begin_stats_loading(top=True, media=True)

    def _init_services(self) -> None:
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.services.account.account_manager_async import AccountManagerAsync
            from src.services.workspace.dashboard_service import DashboardService
            from src.infrastructure.common.event.event_bus import EventBus

            service_locator = ServiceLocator()
            event_bus = service_locator.get(EventBus)

            account_manager = AccountManagerAsync(
                user_id=self.user_id,
                event_bus=event_bus,
            )

            batch_task_manager = None
            try:
                from src.pro_features.batch.services.batch_task_manager_async import BatchTaskManagerAsync

                batch_task_manager = BatchTaskManagerAsync(
                    user_id=self.user_id,
                    event_bus=event_bus,
                )
            except ImportError:
                logger.info("批量任务管理器不可用 (Pro功能未安装)")

            self.dashboard_service = DashboardService(
                user_id=self.user_id,
                account_manager=account_manager,
                batch_task_manager=batch_task_manager,
            )

            def _on_publish_queue_executing_changed(_event) -> None:
                self.refreshRequested.emit()

            try:
                event_bus.subscribe(
                    "PublishQueueExecutingCountChangedEvent",
                    _on_publish_queue_executing_changed,
                )
            except Exception as e:
                logger.debug("订阅发布队列执行中事件失败（可忽略）: %s", e)

            def _on_account_updated_for_dashboard(_event) -> None:
                if self.isVisible():
                    self.refreshRequested.emit()

            try:
                event_bus.subscribe("AccountUpdatedEvent", _on_account_updated_for_dashboard)
            except Exception as e:
                logger.debug("订阅账号更新事件失败（可忽略）: %s", e)

            logger.debug("工作台服务初始化成功")
        except Exception as e:
            logger.error("初始化工作台服务失败: %s", e, exc_info=True)

    def _setup_refresh_timer(self) -> None:
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(
            lambda: self._orchestrator.request_refresh() if self._orchestrator else None
        )
        self.refresh_timer.start(60000)

    def hideEvent(self, event) -> None:
        if hasattr(self, "refresh_timer") and self.refresh_timer:
            self.refresh_timer.stop()
        self._cancel_chart_pending_reveals()
        self._cancel_stats_pending_reveals()
        if self._orchestrator:
            self._orchestrator.cancel_pending()
        self._cancel_base_page_timer("workspace_secondary_widgets")
        self._cancel_base_page_timer("workspace_announcement_create")
        self._cancel_base_page_timer("workspace_recent_activity_create")
        self._cancel_base_page_timer("workspace_platform_chart_prewarm")
        self._cancel_base_page_timer("workspace_trend_chart_prewarm")
        super().hideEvent(event)

    def _cancel_chart_pending_reveals(self) -> None:
        for chart in (getattr(self, "platform_chart", None), getattr(self, "trend_chart", None)):
            if chart is None:
                continue
            try:
                chart.cancel_pending_reveal()
            except Exception:
                pass

    def begin_stats_loading(self, *, top: bool = True, media: bool = True) -> None:
        """数据管道开始：顶部四卡与媒体库卡统一进入骨架屏加载态。"""
        cards = []
        if top:
            cards.extend(
                (
                    getattr(self, "account_card", None),
                    getattr(self, "publish_card", None),
                    getattr(self, "task_card", None),
                    getattr(self, "success_rate_card", None),
                )
            )
        if media:
            cards.extend(
                (
                    getattr(self, "_video_library_card", None),
                    getattr(self, "_image_library_card", None),
                )
            )
        for card in cards:
            if card is None:
                continue
            try:
                card.show_value_loading()
            except Exception:
                pass

    def _cancel_stats_pending_reveals(self) -> None:
        for card in (
            getattr(self, "account_card", None),
            getattr(self, "publish_card", None),
            getattr(self, "task_card", None),
            getattr(self, "success_rate_card", None),
            getattr(self, "_video_library_card", None),
            getattr(self, "_image_library_card", None),
        ):
            if card is None:
                continue
            try:
                card.cancel_pending_reveal()
            except Exception:
                pass

    def _setup_content(self) -> None:
        from ..components.statistics_card import StatisticsCard
        from ..components.quick_action_card import QuickActionCard

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("QWidget { background: transparent; }")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(16, 16, 16, 16)
        scroll_layout.setSpacing(12)

        title_widget = QWidget()
        title_row = QHBoxLayout(title_widget)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        date_str = ""
        try:
            date_str = datetime.now().strftime("%Y年%m月%d日")
        except Exception:
            pass

        self.welcome_title = TitleLabel("", self)
        self.welcome_title.setObjectName("workspaceWelcomeTitle")
        self.welcome_title.setWordWrap(False)
        self._apply_welcome_title_style()
        title_row.addWidget(self.welcome_title)

        self.welcome_desc = BodyLabel("", self)
        self.welcome_desc.setObjectName("workspaceWelcomeDesc")
        self.welcome_desc.setWordWrap(False)
        self._apply_welcome_desc_style()
        title_row.addWidget(self.welcome_desc)

        self._update_welcome_text(date_str)
        scroll_layout.addWidget(title_widget)

        self._stats_cards = []
        self._stats_grid_columns = 4
        self._stats_container = QWidget(self)
        self._stats_grid = QGridLayout(self._stats_container)
        self._stats_grid.setContentsMargins(0, 0, 0, 0)
        self._stats_grid.setHorizontalSpacing(12)
        self._stats_grid.setVerticalSpacing(12)

        self.account_card = StatisticsCard("账号总数", "—", "—", FluentIcon.PEOPLE, self)
        self.publish_card = StatisticsCard("今日发布", "—", "—", FluentIcon.SEND, self)
        self.task_card = StatisticsCard("待执行任务", "—", "—", FluentIcon.FOLDER, self)
        self.success_rate_card = StatisticsCard("发布成功率", "—", "—", FluentIcon.ACCEPT, self)

        self._stats_cards = [
            self.account_card,
            self.publish_card,
            self.task_card,
            self.success_rate_card,
        ]
        self._relayout_stats_cards()
        scroll_layout.addWidget(self._stats_container)

        media_layout = QHBoxLayout()
        media_layout.setSpacing(12)
        self._video_library_card = StatisticsCard(
            "视频库",
            "—",
            "总 — | 已占用 — | 未占用 —",
            FluentIcon.MOVIE,
            self,
        )
        _img_icon = getattr(FluentIcon, "PHOTO", getattr(FluentIcon, "PICTURE", FluentIcon.DOCUMENT))
        self._image_library_card = StatisticsCard(
            "图片库",
            "—",
            "总 — | 已占用 — | 未占用 —",
            _img_icon,
            self,
        )
        media_layout.addWidget(self._video_library_card)
        media_layout.addWidget(self._image_library_card)
        scroll_layout.addLayout(media_layout)

        mid_row = QHBoxLayout()
        mid_row.setSpacing(12)

        cards_container = QWidget(self)
        cards_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._quick_actions_container = cards_container
        quick_action_layout = self._create_quick_action_layout(cards_container)
        self._quick_action_layout = quick_action_layout

        self.action_add_account = QuickActionCard(FluentIcon.ADD, "添加账号", "", self)
        self.action_single_video = QuickActionCard(FluentIcon.MOVIE, "创建单视频任务", "", self)
        self.action_batch_video = QuickActionCard(FluentIcon.LIBRARY, "创建多视频任务", "", self)
        self.action_add_account.clicked.connect(self._on_add_account_clicked)
        self.action_single_video.clicked.connect(self._on_quick_publish_clicked)
        self.action_batch_video.clicked.connect(self._on_batch_video_clicked)

        self.action_publish_list = QuickActionCard(FluentIcon.SEND, "发布任务", "", self)
        self.action_single_image = QuickActionCard(FluentIcon.EDIT, "创建单图文任务", "", self)
        self.action_batch_image = QuickActionCard(FluentIcon.TILES, "创建多图文任务", "", self)
        self.action_publish_list.clicked.connect(self._on_publish_list_clicked)
        self.action_single_image.clicked.connect(self._on_single_image_clicked)
        self.action_batch_image.clicked.connect(self._on_batch_image_clicked)
        quick_action_cards = (
            self.action_add_account,
            self.action_single_video,
            self.action_batch_video,
            self.action_publish_list,
            self.action_single_image,
            self.action_batch_image,
        )
        for index, card in enumerate(quick_action_cards):
            self._add_quick_action_card(quick_action_layout, card, index)
        mid_row.addWidget(cards_container, 3)

        right_row = QHBoxLayout()
        right_row.setSpacing(12)
        self._secondary_widgets_layout = right_row
        self._announcement_placeholder = self._make_panel_placeholder("公告栏")
        self._recent_activity_placeholder = self._make_panel_placeholder("最近发布")
        right_row.addWidget(self._announcement_placeholder, 1)
        right_row.addWidget(self._recent_activity_placeholder, 1)
        mid_row.addLayout(right_row, 3)
        scroll_layout.addLayout(mid_row)

        self._charts_host = QWidget(self)
        self._charts_layout = QHBoxLayout(self._charts_host)
        self._charts_layout.setContentsMargins(0, 0, 0, 0)
        self._charts_layout.setSpacing(12)
        self._platform_chart_placeholder = self._make_chart_placeholder("平台分布")
        self._trend_chart_placeholder = self._make_chart_placeholder("发布趋势")
        self._charts_layout.addWidget(self._platform_chart_placeholder, 1)
        self._charts_layout.addWidget(self._trend_chart_placeholder, 1)
        scroll_layout.addWidget(self._charts_host)

        self.platform_chart = None
        self.trend_chart = None

        scroll_area.setWidget(scroll_content)
        self.content_layout.addWidget(scroll_area)

    def _make_panel_placeholder(self, title: str) -> CardWidget:
        card = CardWidget(self)
        card.setMinimumHeight(120)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        title_lbl = SubtitleLabel(title, card)
        title_lbl.setStyleSheet(
            f"font-weight: 600; font-size: 16px; color: {'#FFFFFF' if isDarkTheme() else '#1A1A1A'};"
        )
        layout.addWidget(title_lbl)
        layout.addStretch(1)
        hint = CaptionLabel("加载中…", card)
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {'#888888' if isDarkTheme() else '#999999'};")
        layout.addWidget(hint)
        layout.addStretch(1)
        return card

    def ensure_secondary_widgets_created(self) -> None:
        self.ensure_announcement_created()
        self.ensure_recent_activity_created()

    def ensure_announcement_created(self) -> None:
        if self._announcement_created:
            return
        try:
            from ..components.announcement_widget import AnnouncementWidget

            placeholder = getattr(self, "_announcement_placeholder", None)
            if placeholder is not None:
                self._secondary_widgets_layout.removeWidget(placeholder)
                placeholder.hide()
                placeholder.setParent(None)
                placeholder.deleteLater()
                self._announcement_placeholder = None

            self.announcement = AnnouncementWidget(self)
            self.announcement.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._secondary_widgets_layout.insertWidget(0, self.announcement, 1)
            self._announcement_created = True
            self._secondary_widgets_created = (
                self._announcement_created and self._recent_activity_created
            )
        except Exception as e:
            logger.debug("工作台公告栏创建失败（可忽略）: %s", e)

    def ensure_recent_activity_created(self, reminders=None) -> None:
        if self._recent_activity_created:
            if reminders is not None:
                self.set_cached_reminders(reminders)
            return
        try:
            from ..components.recent_activity_widget import RecentActivityWidget

            placeholder = getattr(self, "_recent_activity_placeholder", None)
            if placeholder is not None:
                self._secondary_widgets_layout.removeWidget(placeholder)
                placeholder.hide()
                placeholder.setParent(None)
                placeholder.deleteLater()
                self._recent_activity_placeholder = None

            self.recent_activity = RecentActivityWidget(self)
            self.recent_activity.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._secondary_widgets_layout.insertWidget(1, self.recent_activity, 1)
            self._recent_activity_created = True
            self._secondary_widgets_created = (
                self._announcement_created and self._recent_activity_created
            )

            rows = self._cached_reminders if reminders is None else reminders
            self.set_cached_reminders(rows or [])
            self._sync_recent_activity_layout()
        except Exception as e:
            logger.debug("工作台最近发布创建失败（可忽略）: %s", e)

    def set_cached_reminders(self, reminders) -> None:
        self._cached_reminders = list(reminders or [])
        if hasattr(self, "recent_activity") and self.recent_activity is not None:
            self.recent_activity.set_account_reminders(self._cached_reminders)

    def schedule_noncritical_first_paint(self) -> None:
        self._schedule_base_page_timer(
            "workspace_announcement_create",
            0,
            self.ensure_announcement_created,
        )
        self._schedule_base_page_timer(
            "workspace_recent_activity_create",
            80,
            self.ensure_recent_activity_created,
        )
        self._schedule_base_page_timer(
            "workspace_platform_chart_prewarm",
            180,
            lambda: self.apply_chart_cache_if_available(kind="platform"),
        )
        self._schedule_base_page_timer(
            "workspace_trend_chart_prewarm",
            320,
            lambda: self.apply_chart_cache_if_available(kind="trend"),
        )

    @classmethod
    def _create_quick_action_layout(cls, container: QWidget):
        layout_cls = None
        layout_kind = "grid"

        for module_name, class_name in (
            ("qfluentwidgets", "AdaptiveFlowLayout"),
            ("qfluentwidgets.components.layout.flow_layout", "AdaptiveFlowLayout"),
            ("qfluentwidgets", "FlowLayout"),
            ("qfluentwidgets.components.layout.flow_layout", "FlowLayout"),
        ):
            try:
                module = __import__(module_name, fromlist=[class_name])
                layout_cls = getattr(module, class_name)
                layout_kind = "adaptive" if class_name == "AdaptiveFlowLayout" else "flow"
                break
            except (ImportError, AttributeError):
                continue

        if layout_cls is None:
            layout = QGridLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(12)
            for column in range(3):
                layout.setColumnStretch(column, 1)
        else:
            try:
                layout = layout_cls(container, needAni=False, isTight=True)
            except TypeError:
                layout = layout_cls(container)
                if hasattr(layout, "needAni"):
                    layout.needAni = False
                if hasattr(layout, "isTight"):
                    layout.isTight = True
            layout.setContentsMargins(0, 0, 0, 0)
            if hasattr(layout, "setHorizontalSpacing"):
                layout.setHorizontalSpacing(12)
            if hasattr(layout, "setVerticalSpacing"):
                layout.setVerticalSpacing(12)
            if layout_kind == "adaptive":
                if hasattr(layout, "setWidgetMinimumWidth"):
                    layout.setWidgetMinimumWidth(cls._quick_action_card_min_width)
                if hasattr(layout, "setWidgetMaximumWidth"):
                    layout.setWidgetMaximumWidth(cls._quick_action_card_max_width)

        layout.setProperty("workspaceQuickActionLayoutKind", layout_kind)
        return layout

    @classmethod
    def _add_quick_action_card(cls, layout, card: QWidget, index: int) -> None:
        card.setMinimumWidth(cls._quick_action_card_min_width)
        card.setMaximumWidth(cls._quick_action_card_max_width)

        if isinstance(layout, QGridLayout):
            layout.addWidget(card, index // 3, index % 3)
        else:
            layout.addWidget(card)

    def _make_chart_placeholder(self, title: str) -> CardWidget:
        card = CardWidget(self)
        card.setProperty("workspaceChartPlaceholderKind", title)
        card.setFixedHeight(260)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)
        dark = isDarkTheme()
        title_color = "#FFFFFF" if dark else "#1A1A1A"
        title_lbl = SubtitleLabel(title, card)
        title_lbl.setStyleSheet(f"color: {title_color};")
        layout.addWidget(title_lbl)

        from src.ui.components.skeleton import SkeletonItem

        host = QWidget(card)
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 8, 0, 4)
        host_layout.setSpacing(10)
        if "平台" in title:
            host_layout.addStretch(1)
            ring_row = QHBoxLayout()
            ring_row.addStretch(1)
            ring = SkeletonItem(host, radius=70)
            ring.setFixedSize(128, 128)
            ring.setProperty("workspaceChartSkeleton", "platform-ring")
            ring_row.addWidget(ring)
            ring_row.addStretch(1)
            host_layout.addLayout(ring_row)
            legend_row = QHBoxLayout()
            legend_row.setSpacing(8)
            for i in range(3):
                item = SkeletonItem(host, radius=5)
                item.setFixedHeight(10)
                item.setProperty("workspaceChartSkeleton", f"platform-legend-{i}")
                legend_row.addWidget(item)
            host_layout.addLayout(legend_row)
            host_layout.addStretch(1)
        else:
            for width in (0.92, 0.78, 0.86, 0.62):
                row = QHBoxLayout()
                row.setSpacing(8)
                line = SkeletonItem(host, radius=4)
                line.setFixedHeight(12)
                line.setProperty("workspaceChartSkeleton", "trend-grid")
                row.addWidget(line, int(width * 100))
                row.addStretch(max(1, int((1 - width) * 100)))
                host_layout.addLayout(row)
            host_layout.addSpacing(8)
            trend = SkeletonItem(host, radius=6)
            trend.setFixedHeight(44)
            trend.setProperty("workspaceChartSkeleton", "trend-line")
            host_layout.addWidget(trend)
            host_layout.addStretch(1)
        layout.addWidget(host, 1)
        return card

    def _relayout_stats_cards(self) -> None:
        if not hasattr(self, "_stats_grid") or self._stats_grid is None:
            return
        cards = getattr(self, "_stats_cards", None) or []
        if not cards:
            return
        columns = 4
        if getattr(self, "_stats_grid_columns", None) == columns and self._stats_grid.count() > 0:
            return
        self._stats_grid_columns = columns
        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            if item is None:
                break
            try:
                ww = item.widget()
            except Exception:
                ww = None
            if ww is not None:
                ww.setParent(self._stats_container)
        for i, card in enumerate(cards):
            self._stats_grid.addWidget(card, i // columns, i % columns)
        for c in range(columns):
            self._stats_grid.setColumnStretch(c, 1)

    def _on_refresh_requested(self) -> None:
        if self._orchestrator:
            self._orchestrator.request_refresh()

    def apply_stats_batch(
        self,
        dashboard_snapshot: DashboardSnapshot,
        media_stats: MediaLibraryStats,
        *,
        animate_entry: bool = False,
        reminders: bool = False,
    ) -> None:
        """统一提交首页 6 张统计卡，避免第一行和媒体库卡片错峰出现。"""
        self._apply_snapshot(
            dashboard_snapshot,
            charts=False,
            animate_entry=animate_entry,
            reminders=reminders,
        )
        self._on_media_stats_updated(media_stats, animate_entry=animate_entry)

    def _apply_snapshot(
        self,
        snapshot: DashboardSnapshot,
        *,
        charts: bool = True,
        animate_entry: bool = False,
        reminders: bool = True,
    ) -> None:
        try:
            data = snapshot.to_legacy_dict()
            account_stats = data.get("account", {})
            if account_stats:
                self._apply_account_stats(account_stats, animate_entry=animate_entry)

            task_stats = data.get("task", {})
            if task_stats:
                self._apply_task_stats(task_stats, animate_entry=animate_entry)

            publish_stats = data.get("publish", {})
            if publish_stats:
                self._apply_publish_stats(publish_stats, animate_entry=animate_entry)

            reminder_rows = data.get("account_publish_reminders", []) if reminders else []
            if reminders:
                self.set_cached_reminders(reminder_rows)

            if charts and account_stats:
                self.reveal_platform_chart(account_stats, animate_entry=True)
            if charts and publish_stats:
                self.reveal_trend_chart(publish_stats, animate_entry=True)
        except Exception as e:
            logger.error("应用工作台快照失败: %s", e, exc_info=True)

    def begin_charts_loading(self) -> None:
        """数据管道开始：两图同时显示 loading 遮罩。"""
        if self.platform_chart is not None:
            self.platform_chart.show_loading()
        if self.trend_chart is not None:
            self.trend_chart.show_loading()

    def reveal_platform_chart(
        self,
        account_stats: Dict[str, Any],
        *,
        animate_entry: bool = True,
    ) -> None:
        self._ensure_platform_chart_created()
        if self.platform_chart is None:
            return
        data = self._platform_stats_cn(account_stats)
        if animate_entry:
            self.platform_chart.reveal_platform_data(data, animate_entry=True)
        else:
            self.platform_chart.set_data(data, animate=False)

    def reveal_trend_chart(
        self,
        publish_stats: Dict[str, Any],
        *,
        animate_entry: bool = True,
    ) -> None:
        self._ensure_trend_chart_created()
        if self.trend_chart is None:
            return
        trend_data = publish_stats.get("daily_stats", [])
        if animate_entry:
            self.trend_chart.reveal_trend_data(trend_data, animate_entry=True)
        else:
            self.trend_chart.set_data(trend_data, animate=False)

    def _platform_stats_cn(self, account_stats: Dict[str, Any]) -> Dict[str, int]:
        return {
            PLATFORM_NAME_MAP.get(k, k): int(v)
            for k, v in (account_stats.get("by_platform") or {}).items()
        }

    def _prewarm_chart_widgets(self) -> None:
        """空闲时预创建 QtCharts 控件，避免数据就绪时才首次 import/实例化。"""
        try:
            self._ensure_chart_widgets_created()
        except Exception as e:
            logger.debug("工作台图表预创建失败（可忽略）: %s", e)

    def apply_chart_cache_if_available(self, *, kind: str | None = None) -> bool:
        snapshot = None
        if self._orchestrator is not None:
            try:
                snapshot = self._orchestrator.get_latest_snapshot()
            except Exception:
                snapshot = None
        if snapshot is None:
            return False

        applied = False
        if kind in (None, "platform") and snapshot.account:
            self.reveal_platform_chart(snapshot.account, animate_entry=False)
            applied = True
        if kind in (None, "trend") and snapshot.publish:
            self.reveal_trend_chart(snapshot.publish, animate_entry=False)
            applied = True
        return applied

    def _ensure_chart_widgets_created(self) -> None:
        self._ensure_platform_chart_created()
        self._ensure_trend_chart_created()
        self._charts_created = self.platform_chart is not None and self.trend_chart is not None

    def _profile_chart_creation(self, label: str, create_fn) -> None:
        try:
            import time
            from src.utils.startup_profiler import (
                is_page_load_profiler_enabled,
                log_page_create_timing,
            )

            t0 = time.perf_counter() if is_page_load_profiler_enabled() else 0.0
        except Exception:
            t0 = 0.0
            is_page_load_profiler_enabled = lambda: False  # type: ignore[assignment]
            log_page_create_timing = lambda *_args, **_kwargs: None  # type: ignore[assignment]
        create_fn()
        try:
            if is_page_load_profiler_enabled():
                log_page_create_timing(label, time.perf_counter() - t0)
        except Exception:
            pass

    def _remove_chart_placeholder(self, attr_name: str) -> None:
        placeholder = getattr(self, attr_name, None)
        if placeholder is None:
            return
        self._charts_layout.removeWidget(placeholder)
        placeholder.hide()
        placeholder.setParent(None)
        placeholder.deleteLater()
        setattr(self, attr_name, None)

    def _ensure_platform_chart_created(self) -> None:
        if self.platform_chart is not None:
            return

        def _create() -> None:
            from ..components.charts import PlatformDistributionChart

            self._remove_chart_placeholder("_platform_chart_placeholder")
            self.platform_chart = PlatformDistributionChart(self)
            self.platform_chart.setFixedHeight(260)
            self.platform_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._charts_layout.insertWidget(0, self.platform_chart, 1)
            self._charts_created = self.platform_chart is not None and self.trend_chart is not None

        self._profile_chart_creation("workspace_platform_chart", _create)

    def _ensure_trend_chart_created(self) -> None:
        if self.trend_chart is not None:
            return

        def _create() -> None:
            from ..components.charts import PublishTrendChart

            self._remove_chart_placeholder("_trend_chart_placeholder")
            self.trend_chart = PublishTrendChart(self)
            self.trend_chart.setFixedHeight(260)
            self.trend_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self._charts_layout.insertWidget(1, self.trend_chart, 1)
            self._charts_created = self.platform_chart is not None and self.trend_chart is not None

        self._profile_chart_creation("workspace_trend_chart", _create)

    def _apply_account_stats(self, account_stats: Dict[str, Any], *, animate_entry: bool = False) -> None:
        if not hasattr(self, "account_card"):
            return
        value = str(account_stats.get("total", 0))
        desc = f"{account_stats.get('online', 0)} 在线 | {account_stats.get('offline', 0)} 离线"
        self.account_card.reveal(value, desc, animate=animate_entry)

    def _apply_task_stats(self, task_stats: Dict[str, Any], *, animate_entry: bool = False) -> None:
        if not hasattr(self, "task_card"):
            return
        batch_total = task_stats.get("total", 0)
        total_pending = task_stats.get("total_pending", 0)
        completion_rate = task_stats.get("completion_rate", 0)
        if batch_total > 0:
            value = str(total_pending)
            desc = f"批量任务: {batch_total} | 完成: {completion_rate:.0f}%"
        else:
            pub_tab = task_stats.get("publish_tab_total", task_stats.get("total_pending", 0))
            pub_wait = task_stats.get("publish_waiting", task_stats.get("publish_pending", 0))
            pub_exec = task_stats.get("publish_executing_ui", task_stats.get("publish_running", 0))
            value = str(pub_tab)
            desc = f"{pub_wait} 等待 | {pub_exec} 执行中"
        self.task_card.reveal(value, desc, animate=animate_entry)

    def _apply_publish_stats(self, publish_stats: Dict[str, Any], *, animate_entry: bool = False) -> None:
        if hasattr(self, "publish_card"):
            value = str(publish_stats.get("today_count", 0))
            desc = (
                f"{publish_stats.get('today_success', 0)} 成功 | "
                f"{publish_stats.get('today_failed', 0)} 失败"
            )
            self.publish_card.reveal(value, desc, animate=animate_entry)
        if hasattr(self, "success_rate_card"):
            value = f"{publish_stats.get('success_rate_7d', 0):.1f}%"
            desc = f"近7天 {publish_stats.get('finished_7d', 0)}条"
            self.success_rate_card.reveal(value, desc, animate=animate_entry)

    def _on_media_stats_updated(self, stats, *, animate_entry: Optional[bool] = None) -> None:
        if getattr(self, "_hold_media_stats_updates", False):
            self._held_media_stats = stats
            return
        v_card = getattr(self, "_video_library_card", None)
        i_card = getattr(self, "_image_library_card", None)
        if v_card is None or i_card is None:
            return
        if animate_entry is None:
            animate_entry = bool(
                (v_card.is_value_loading if v_card else False)
                or (i_card.is_value_loading if i_card else False)
            )
        try:
            v_counts = getattr(getattr(stats, "video", None), "counts", None)
            i_counts = getattr(getattr(stats, "image", None), "counts", None)
            if v_counts is None:
                v_card.reveal("—", "总 — | 已占用 — | 未占用 —", animate=animate_entry)
            else:
                vt = int(getattr(v_counts, "total", 0) or 0)
                vu = int(getattr(v_counts, "used", 0) or 0)
                vn = int(getattr(v_counts, "unused", 0) or 0)
                v_card.reveal(str(vt), f"总 {vt} | 已占用 {vu} | 未占用 {vn}", animate=animate_entry)
            if i_counts is None:
                i_card.reveal("—", "总 — | 已占用 — | 未占用 —", animate=animate_entry)
            else:
                it = int(getattr(i_counts, "total", 0) or 0)
                iu = int(getattr(i_counts, "used", 0) or 0)
                inn = int(getattr(i_counts, "unused", 0) or 0)
                i_card.reveal(str(it), f"总 {it} | 已占用 {iu} | 未占用 {inn}", animate=animate_entry)
        except Exception:
            return

    def set_media_stats_update_hold(self, hold: bool) -> None:
        self._hold_media_stats_updates = bool(hold)
        if hold:
            self._held_media_stats = None

    def take_held_media_stats(self):
        stats = self._held_media_stats
        self._held_media_stats = None
        return stats

    def _apply_welcome_title_style(self) -> None:
        dark = isDarkTheme()
        color = "#4FC3F7" if dark else "#0078D4"
        self.welcome_title.setStyleSheet(
            f"font-size: 24px; font-weight: 700; color: {color}; "
            f"letter-spacing: 0.5px; margin: 0; padding: 0;"
        )

    def _apply_welcome_desc_style(self) -> None:
        dark = isDarkTheme()
        color = "#90A4AE" if dark else "#5E6B73"
        self.welcome_desc.setStyleSheet(
            f"font-size: 13px; font-weight: 400; color: {color}; "
            f"margin: 0; padding: 0;"
        )

    def _update_welcome_text(self, date_str: str = "") -> None:
        if not date_str:
            try:
                date_str = datetime.now().strftime("%Y年%m月%d日")
            except Exception:
                date_str = ""
        user = self._current_user_svc.get_user()
        if hasattr(self, "welcome_title") and self.welcome_title:
            if user and user.get("username"):
                self.welcome_title.setText(f"{user['username']}，欢迎回来")
            else:
                self.welcome_title.setText("欢迎回来")
        if hasattr(self, "welcome_desc") and self.welcome_desc:
            self.welcome_desc.setText(f"今天是 {date_str}。以下是您的账号概览。")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "refresh_timer") and self.refresh_timer and not self.refresh_timer.isActive():
            self.refresh_timer.start()
        self._update_welcome_text()
        self._apply_welcome_title_style()
        self._apply_welcome_desc_style()
        self._sync_recent_activity_layout()
        self.schedule_noncritical_first_paint()
        if self._orchestrator:
            self._orchestrator.schedule_startup_refresh()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_recent_activity_layout()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_recent_activity_layout()

    def _sync_recent_activity_layout(self) -> None:
        if hasattr(self, "recent_activity") and self.recent_activity is not None:
            self.recent_activity._sync_compact_layout()

    def _on_data_load_error(self, error: str) -> None:
        logger.error("加载工作台数据失败: %s", error)

    def _on_add_account_clicked(self) -> None:
        self._navigate_to_page("account_page")

    def _on_quick_publish_clicked(self) -> None:
        self._navigate_to_page("single_task_creation_page")

    def _on_batch_video_clicked(self) -> None:
        self._navigate_to_page("batch_task_creation_page")

    def _on_single_image_clicked(self) -> None:
        self._navigate_to_page("image_single_task_creation_page")

    def _on_batch_image_clicked(self) -> None:
        self._navigate_to_page("image_batch_task_creation_page")

    def _on_publish_list_clicked(self) -> None:
        self._navigate_to_page("publish_list_page")

    def _navigate_to_page(self, page_name: str) -> None:
        try:
            main_window = self.window()
            if not main_window:
                return
            if hasattr(main_window, "navigate_to"):
                main_window.navigate_to(page_name)
                return
            page = getattr(main_window, page_name, None)
            if not page:
                logger.warning("页面不存在: %s", page_name)
                return
            if hasattr(main_window, "navigationInterface"):
                nav = main_window.navigationInterface
                if hasattr(nav, "stackedWidget"):
                    idx = nav.stackedWidget.indexOf(page)
                    if idx >= 0:
                        nav.stackedWidget.setCurrentIndex(idx)
        except Exception as e:
            logger.error("导航到页面失败: %s", e, exc_info=True)
