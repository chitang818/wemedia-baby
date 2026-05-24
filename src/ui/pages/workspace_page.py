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
    QSizePolicy,
)
from PySide6.QtCore import QTimer, Qt, QEvent, Signal
from PySide6.QtGui import QResizeEvent
import logging

from qfluentwidgets import (
    CardWidget,
    SubtitleLabel,
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    isDarkTheme,
)

from .base_page import BasePage
from ..components.workspace_scroll_area import (
    create_workspace_scroll_area,
    set_workspace_scroll_content,
)
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
    _quick_action_card_min_width = 96
    _quick_action_spacing = 10

    refreshRequested = Signal()
    refreshWelcomeRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("工作台", parent)
        self._needs_show_transition = False

        from src.services.auth import CurrentUserService

        self._current_user_svc = CurrentUserService()
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        self.dashboard_service = None
        self._orchestrator: Optional[WorkspaceLoadOrchestrator] = None
        self._stats_first_reveal_done = False
        self._secondary_widgets_created = False
        self._announcement_created = False
        self._recent_activity_created = False
        self._cached_reminders = []
        self._hold_media_stats_updates = False
        self._held_media_stats = None

        self.refreshRequested.connect(self._on_refresh_requested)
        self.refreshWelcomeRequested.connect(self.refresh_welcome_display)
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

            def _on_current_user_changed(_event) -> None:
                self.refreshWelcomeRequested.emit()

            try:
                event_bus.subscribe("CurrentUserChangedEvent", _on_current_user_changed)
            except Exception as e:
                logger.debug("订阅软件账号变更事件失败（可忽略）: %s", e)

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
        self._cancel_base_page_timer("workspace_recent_activity_create")
        self._cancel_base_page_timer("workspace_account_platform_prewarm")
        super().hideEvent(event)

    def _cancel_chart_pending_reveals(self) -> None:
        overview = getattr(self, "account_platform_card", None)
        if overview is not None:
            try:
                overview.cancel_pending_reveal()
            except Exception:
                pass

    def begin_stats_loading(self, *, top: bool = True, media: bool = True) -> None:
        """数据管道开始：顶部 KPI、账号平台概览与素材库卡进入加载态。"""
        if top:
            overview = getattr(self, "account_platform_card", None)
            if overview is not None:
                try:
                    overview.show_loading()
                except Exception:
                    pass
            for card in (
                getattr(self, "publish_card", None),
                getattr(self, "task_card", None),
                getattr(self, "success_rate_card", None),
            ):
                if card is None:
                    continue
                try:
                    card.show_value_loading()
                except Exception:
                    pass
        if media:
            media_card = getattr(self, "_media_library_card", None)
            if media_card is not None:
                try:
                    media_card.show_value_loading()
                except Exception:
                    pass

    def _cancel_stats_pending_reveals(self) -> None:
        overview = getattr(self, "account_platform_card", None)
        if overview is not None:
            try:
                overview.cancel_pending_reveal()
            except Exception:
                pass
        for card in (
            getattr(self, "publish_card", None),
            getattr(self, "task_card", None),
            getattr(self, "success_rate_card", None),
            getattr(self, "_media_library_card", None),
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
        from ..components.account_platform_overview_card import (
            AccountPlatformOverviewCard,
            OVERVIEW_PAIR_HEIGHT,
        )
        from ..components.media_library_combined_card import MediaLibraryCombinedCard
        from ..components.collapsible_announcement_panel import CollapsibleAnnouncementPanel

        scroll_area = create_workspace_scroll_area(self)

        scroll_content = QWidget()
        scroll_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(12, 12, 12, 12)
        scroll_layout.setSpacing(10)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        date_str = ""
        try:
            date_str = datetime.now().strftime("%Y年%m月%d日")
        except Exception:
            pass

        self.welcome_line = BodyLabel("", self)
        self.welcome_line.setObjectName("workspaceWelcomeLine")
        self.welcome_line.setWordWrap(True)
        self._apply_welcome_line_style()
        self._update_welcome_text(date_str)
        scroll_layout.addWidget(self.welcome_line)

        self._stats_cards = []
        self._stats_grid_columns = 4
        self._stats_container = QWidget(self)
        self._stats_grid = QGridLayout(self._stats_container)
        self._stats_grid.setContentsMargins(0, 0, 0, 0)
        self._stats_grid.setHorizontalSpacing(12)
        self._stats_grid.setVerticalSpacing(12)

        self.publish_card = StatisticsCard("今日发布", "—", "—", FluentIcon.SEND, self, compact=True)
        self.task_card = StatisticsCard("待执行任务", "—", "—", FluentIcon.FOLDER, self, compact=True)
        self.success_rate_card = StatisticsCard("发布成功率", "—", "—", FluentIcon.ACCEPT, self, compact=True)
        self._media_library_card = MediaLibraryCombinedCard(self)

        self._stats_cards = [
            self.publish_card,
            self.task_card,
            self.success_rate_card,
            self._media_library_card,
        ]
        self._relayout_stats_cards()
        scroll_layout.addWidget(self._stats_container)

        self._announcement_panel = CollapsibleAnnouncementPanel(self, collapsed=False)
        self._announcement_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        scroll_layout.addWidget(self._announcement_panel)
        self._announcement_created = True
        self.announcement = self._announcement_panel._content

        mid_row = QHBoxLayout()
        mid_row.setSpacing(12)

        cards_container = QWidget(self)
        cards_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._quick_actions_container = cards_container
        quick_action_layout = self._create_quick_action_layout(cards_container)
        self._quick_action_layout = quick_action_layout

        _qa_kw = {"compact": True}
        self.action_add_account = QuickActionCard(FluentIcon.ADD, "添加账号", "", self, **_qa_kw)
        self.action_single_video = QuickActionCard(FluentIcon.MOVIE, "创建单视频任务", "", self, **_qa_kw)
        self.action_batch_video = QuickActionCard(FluentIcon.LIBRARY, "创建多视频任务", "", self, **_qa_kw)
        self.action_add_account.clicked.connect(self._on_add_account_clicked)
        self.action_single_video.clicked.connect(self._on_quick_publish_clicked)
        self.action_batch_video.clicked.connect(self._on_batch_video_clicked)

        self.action_publish_list = QuickActionCard(FluentIcon.SEND, "发布任务", "", self, **_qa_kw)
        self.action_single_image = QuickActionCard(FluentIcon.EDIT, "创建单图文任务", "", self, **_qa_kw)
        self.action_batch_image = QuickActionCard(FluentIcon.TILES, "创建多图文任务", "", self, **_qa_kw)
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
        mid_row.addWidget(cards_container, 1)
        scroll_layout.addLayout(mid_row)

        self.account_platform_card = AccountPlatformOverviewCard(self, half_column=True)
        self.account_platform_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.account_platform_card.setMinimumHeight(OVERVIEW_PAIR_HEIGHT)
        self.account_platform_card.setMaximumHeight(OVERVIEW_PAIR_HEIGHT)

        self._overview_pair_host = QWidget(self)
        self._overview_pair_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._overview_pair_host.setFixedHeight(OVERVIEW_PAIR_HEIGHT)
        overview_pair_row = QHBoxLayout(self._overview_pair_host)
        overview_pair_row.setContentsMargins(0, 0, 0, 0)
        overview_pair_row.setSpacing(12)
        self._overview_pair_layout = overview_pair_row

        self._recent_activity_placeholder = self._make_panel_placeholder("发布统计")
        self._recent_activity_placeholder.setMinimumHeight(OVERVIEW_PAIR_HEIGHT)
        self._recent_activity_placeholder.setMaximumHeight(OVERVIEW_PAIR_HEIGHT)
        self._recent_activity_placeholder.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )

        overview_pair_row.addWidget(self.account_platform_card, 1)
        overview_pair_row.addWidget(self._recent_activity_placeholder, 1)
        scroll_layout.addWidget(self._overview_pair_host)

        set_workspace_scroll_content(scroll_area, scroll_content)
        self.content_layout.addWidget(scroll_area)

    def _make_panel_placeholder(self, title: str) -> CardWidget:
        card = CardWidget(self)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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
        self.ensure_recent_activity_created()

    def ensure_announcement_created(self) -> None:
        """公告已在构造期以可折叠面板创建。"""
        return

    def ensure_recent_activity_created(self, reminders=None) -> None:
        if self._recent_activity_created:
            if reminders is not None:
                self.set_cached_reminders(reminders)
            return
        try:
            from ..components.recent_activity_widget import RecentActivityWidget

            placeholder = getattr(self, "_recent_activity_placeholder", None)
            if placeholder is not None:
                parent = placeholder.parentWidget()
                parent_layout = parent.layout() if parent is not None else None
                if parent_layout is not None:
                    parent_layout.removeWidget(placeholder)
                placeholder.hide()
                placeholder.setParent(None)
                placeholder.deleteLater()
                self._recent_activity_placeholder = None

                self.recent_activity = RecentActivityWidget(parent or self)
                self.recent_activity.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                from ..components.account_platform_overview_card import OVERVIEW_PAIR_HEIGHT

                self.recent_activity.setMinimumHeight(OVERVIEW_PAIR_HEIGHT)
                self.recent_activity.setMaximumHeight(OVERVIEW_PAIR_HEIGHT)
                if hasattr(self.recent_activity, "set_narrow_column"):
                    self.recent_activity.set_narrow_column(True)
                if parent_layout is not None:
                    parent_layout.addWidget(self.recent_activity, 1)

            self._recent_activity_created = True
            self._secondary_widgets_created = self._recent_activity_created

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
            "workspace_recent_activity_create",
            0,
            self.ensure_recent_activity_created,
        )
        self._schedule_base_page_timer(
            "workspace_account_platform_prewarm",
            80,
            lambda: self.apply_account_platform_cache_if_available(),
        )

    @classmethod
    def _create_quick_action_layout(cls, container: QWidget) -> QHBoxLayout:
        """六张快捷卡片单行等分，随窗口宽度同比例拉伸。"""
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(cls._quick_action_spacing)
        layout.setProperty("workspaceQuickActionLayoutKind", "equal")
        return layout

    @classmethod
    def _add_quick_action_card(cls, layout: QHBoxLayout, card: QWidget, index: int) -> None:
        del index  # 保留参数以兼容调用方
        card.setMinimumWidth(cls._quick_action_card_min_width)
        card.setMaximumWidth(16777215)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(card, 1)

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
        """统一提交首页 KPI、素材库与账号平台概览卡，避免错峰出现。"""
        self._apply_snapshot(
            dashboard_snapshot,
            animate_entry=animate_entry,
            reminders=reminders,
        )
        self._on_media_stats_updated(media_stats, animate_entry=animate_entry)

    def _apply_snapshot(
        self,
        snapshot: DashboardSnapshot,
        *,
        animate_entry: bool = False,
        reminders: bool = True,
    ) -> None:
        try:
            data = snapshot.to_legacy_dict()
            account_stats = data.get("account", {})
            if account_stats:
                self.reveal_account_platform(account_stats, animate_entry=animate_entry)

            task_stats = data.get("task", {})
            if task_stats:
                self._apply_task_stats(task_stats, animate_entry=animate_entry)

            publish_stats = data.get("publish", {})
            if publish_stats:
                self._apply_publish_stats(publish_stats, animate_entry=animate_entry)

            reminder_rows = data.get("account_publish_reminders", []) if reminders else []
            if reminders:
                self.set_cached_reminders(reminder_rows)
        except Exception as e:
            logger.error("应用工作台快照失败: %s", e, exc_info=True)

    def reveal_account_platform(
        self,
        account_stats: Dict[str, Any],
        *,
        animate_entry: bool = True,
    ) -> None:
        card = getattr(self, "account_platform_card", None)
        if card is None:
            return
        data = self._platform_stats_cn(account_stats)
        card.reveal(account_stats, data, animate=animate_entry)

    def reveal_platform_chart(
        self,
        account_stats: Dict[str, Any],
        *,
        animate_entry: bool = True,
    ) -> None:
        """兼容旧调用路径。"""
        self.reveal_account_platform(account_stats, animate_entry=animate_entry)

    def _platform_stats_cn(self, account_stats: Dict[str, Any]) -> Dict[str, int]:
        return {
            PLATFORM_NAME_MAP.get(k, k): int(v)
            for k, v in (account_stats.get("by_platform") or {}).items()
        }

    def apply_account_platform_cache_if_available(self) -> bool:
        snapshot = None
        if self._orchestrator is not None:
            try:
                snapshot = self._orchestrator.get_latest_snapshot()
            except Exception:
                snapshot = None
        if snapshot is None or not snapshot.account:
            return False
        self.reveal_account_platform(snapshot.account, animate_entry=False)
        return True

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
        media_card = getattr(self, "_media_library_card", None)
        if media_card is None:
            return
        if animate_entry is None:
            animate_entry = bool(media_card.is_value_loading)
        try:
            v_counts = getattr(getattr(stats, "video", None), "counts", None)
            i_counts = getattr(getattr(stats, "image", None), "counts", None)
            if v_counts is None or i_counts is None:
                media_card.reveal(0, 0, 0, 0, 0, 0, animate=animate_entry)
                return
            vt = int(getattr(v_counts, "total", 0) or 0)
            vu = int(getattr(v_counts, "used", 0) or 0)
            vn = int(getattr(v_counts, "unused", 0) or 0)
            it = int(getattr(i_counts, "total", 0) or 0)
            iu = int(getattr(i_counts, "used", 0) or 0)
            inn = int(getattr(i_counts, "unused", 0) or 0)
            media_card.reveal(vt, vu, vn, it, iu, inn, animate=animate_entry)
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

    def _apply_welcome_line_style(self) -> None:
        dark = isDarkTheme()
        primary = "#4FC3F7" if dark else "#0078D4"
        muted = "#90A4AE" if dark else "#5E6B73"
        if hasattr(self, "welcome_line") and self.welcome_line:
            self.welcome_line.setStyleSheet(
                f"font-size: 15px; font-weight: 600; color: {primary}; margin: 0; padding: 0;"
                f" QLabel span {{ color: {muted}; font-weight: 400; }}"
            )

    def _resolve_welcome_username(self) -> Optional[str]:
        user = self._current_user_svc.get_user()
        if user and user.get("username"):
            username = str(user["username"]).strip()
            if username:
                return username
        try:
            from src.services.auth.auth_remember import get_remembered_credentials

            remembered, username, _password = get_remembered_credentials()
            if remembered and username:
                remembered_name = str(username).strip()
                if remembered_name:
                    return remembered_name
        except Exception:
            pass
        return None

    def refresh_welcome_display(self, date_str: str = "") -> None:
        self._update_welcome_text(date_str)

    def _update_welcome_text(self, date_str: str = "") -> None:
        if not date_str:
            try:
                date_str = datetime.now().strftime("%Y年%m月%d日")
            except Exception:
                date_str = ""
        username = self._resolve_welcome_username()
        name = f"{username}，欢迎回来" if username else "欢迎回来"
        if hasattr(self, "welcome_line") and self.welcome_line:
            self.welcome_line.setText(
                f"{name} · 今天是 {date_str}"
            )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "refresh_timer") and self.refresh_timer and not self.refresh_timer.isActive():
            self.refresh_timer.start()
        self.refresh_welcome_display()
        self._apply_welcome_line_style()
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
        try:
            main_window = self.window()
            if main_window and hasattr(main_window, "navigate_to"):
                main_window.navigate_to("account_page", open_add_account=True)
                return
        except Exception as e:
            logger.error("跳转账号管理失败: %s", e, exc_info=True)
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
