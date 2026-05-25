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
    # 六卡单行：6×最小宽 + 5×间距
    _quick_action_single_row_min_width = 6 * _quick_action_card_min_width + 5 * _quick_action_spacing
    # 顶部 KPI：四卡单行所需宽度（4×160 + 间距），与下方图表堆叠断点分开
    _stats_compact_width = 520
    _compact_width = 760
    _OVERVIEW_SYNC_DEBOUNCE_MS = 48
    _OVERVIEW_SYNC_POST_ANIMATION_MS = 120
    _OVERVIEW_EVENT_FILTER_DELAY_MS = 150

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
        self._full_content_ready = False
        self._secondary_widgets_created = False
        self._announcement_created = False
        self._recent_activity_created = False
        self._cached_reminders = []
        self._hold_media_stats_updates = False
        self._held_media_stats = None
        self._last_stats_width = 0
        self._quick_action_grid_columns = 6
        self._overview_stacked = False
        self._overview_pair_host_height: Optional[int] = None
        self._last_overview_maximized: Optional[bool] = None
        self._win_state_filter_installed = False
        self._overview_above_height_cache: Optional[int] = None
        self._overview_above_height_signature: Optional[tuple] = None
        self._last_responsive_width: int = 0

        self.refreshRequested.connect(self._on_refresh_requested)
        self.refreshWelcomeRequested.connect(self.refresh_welcome_display)
        self._init_services()
        self._setup_light_shell()
        self._schedule_base_page_timer(
            "workspace_full_content",
            0,
            self._ensure_full_content,
        )
        self._setup_refresh_timer()
        self._orchestrator = WorkspaceLoadOrchestrator(self)

        self._stats_cache = get_media_library_stats_cache()
        try:
            self._stats_cache.statsUpdated.connect(self._on_media_stats_updated)
        except Exception:
            pass

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
            recent = getattr(self, "recent_activity", None)
            if recent is not None:
                try:
                    recent.show_loading()
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
        recent = getattr(self, "recent_activity", None)
        if recent is not None:
            try:
                recent.cancel_pending_reveal()
            except Exception:
                pass

    def _setup_light_shell(self) -> None:
        """首屏轻壳：仅滚动区与顶栏，重组件在下一事件循环帧构建。"""
        scroll_area = create_workspace_scroll_area(self)
        self._workspace_scroll_area = scroll_area

        scroll_content = QWidget()
        scroll_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._scroll_content = scroll_content
        scroll_layout = QVBoxLayout(scroll_content)
        self._scroll_layout = scroll_layout
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(12)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        date_str = ""
        try:
            date_str = datetime.now().strftime("%Y年%m月%d日")
        except Exception:
            pass

        self._header_card = CardWidget(self)
        self._header_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._header_card.setFixedHeight(50)
        header_layout = QHBoxLayout(self._header_card)
        header_layout.setContentsMargins(14, 8, 14, 8)
        header_layout.setSpacing(10)

        self.welcome_line = BodyLabel("", self._header_card)
        self.welcome_line.setObjectName("workspaceWelcomeLine")
        self.welcome_line.setWordWrap(True)
        header_layout.addWidget(self.welcome_line, 1, Qt.AlignmentFlag.AlignVCenter)

        self._welcome_meta_label = CaptionLabel("", self._header_card)
        self._welcome_meta_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        header_layout.addWidget(self._welcome_meta_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._apply_welcome_line_style()
        self._update_welcome_text(date_str)
        scroll_layout.addWidget(self._header_card)

        self._light_placeholder = self._make_panel_placeholder("工作台")
        scroll_layout.addWidget(self._light_placeholder)

        set_workspace_scroll_content(scroll_area, scroll_content)
        self.content_layout.addWidget(scroll_area)

    def _ensure_full_content(self) -> None:
        if self._full_content_ready:
            return
        self._full_content_ready = True
        placeholder = getattr(self, "_light_placeholder", None)
        if placeholder is not None and self._scroll_layout is not None:
            self._scroll_layout.removeWidget(placeholder)
            placeholder.deleteLater()
            self._light_placeholder = None
        self._setup_content()
        self._secondary_widgets_created = True
        self._announcement_created = True
        self._recent_activity_created = True
        if self._orchestrator:
            cached_applied = self._orchestrator.apply_cached_first_paint()
            if cached_applied:
                self._stats_first_reveal_done = True
            else:
                self.begin_stats_loading(top=True, media=True)

    def _setup_content(self) -> None:
        if getattr(self, "_full_content_ready", False) and hasattr(self, "publish_card"):
            return
        from ..components.statistics_card import StatisticsCard
        from ..components.quick_action_card import QuickActionCard
        from ..components.account_platform_overview_card import AccountPlatformOverviewCard
        from ..components.media_library_combined_card import MediaLibraryCombinedCard
        from ..components.collapsible_announcement_panel import CollapsibleAnnouncementPanel
        from ..components.recent_activity_widget import RecentActivityWidget

        scroll_area = getattr(self, "_workspace_scroll_area", None)
        if scroll_area is None:
            scroll_area = create_workspace_scroll_area(self)
            self._workspace_scroll_area = scroll_area
            scroll_content = QWidget()
            scroll_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            self._scroll_content = scroll_content
            scroll_layout = QVBoxLayout(scroll_content)
            self._scroll_layout = scroll_layout
            scroll_layout.setContentsMargins(0, 0, 0, 0)
            scroll_layout.setSpacing(12)
            scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            set_workspace_scroll_content(scroll_area, scroll_content)
            self.content_layout.addWidget(scroll_area)
        scroll_layout = self._scroll_layout

        self._stats_cards = []
        self._stats_grid_columns = 4
        self._stats_container = QWidget(self)
        self._stats_grid = QGridLayout(self._stats_container)
        self._stats_grid.setContentsMargins(0, 0, 0, 0)
        self._stats_grid.setHorizontalSpacing(10)
        self._stats_grid.setVerticalSpacing(10)

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
        self._quick_action_cards = quick_action_cards
        scroll_layout.addWidget(cards_container)

        self.account_platform_card = AccountPlatformOverviewCard(self, half_column=True)
        self.account_platform_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._overview_pair_host = QWidget(self)
        self._overview_pair_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        overview_pair_layout = QGridLayout(self._overview_pair_host)
        overview_pair_layout.setContentsMargins(0, 0, 0, 0)
        overview_pair_layout.setHorizontalSpacing(12)
        overview_pair_layout.setVerticalSpacing(10)
        self._overview_pair_layout = overview_pair_layout

        self.recent_activity = RecentActivityWidget(self)
        self.recent_activity.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.recent_activity.set_narrow_column(True)

        overview_pair_layout.addWidget(self.account_platform_card, 0, 0)
        overview_pair_layout.addWidget(self.recent_activity, 0, 1)
        overview_pair_layout.setColumnStretch(0, 1)
        overview_pair_layout.setColumnStretch(1, 1)
        overview_pair_layout.setRowStretch(0, 1)
        overview_pair_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_layout.addWidget(self._overview_pair_host)
        self._sync_overview_pair_layout()

        self._sync_responsive_layout()

    def _make_panel_placeholder(self, title: str) -> CardWidget:
        card = CardWidget(self)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        dark = isDarkTheme()
        if dark:
            card.setStyleSheet(
                "CardWidget {"
                "background: rgba(255, 255, 255, 0.04);"
                "border: 1px solid rgba(255, 255, 255, 0.08);"
                "border-radius: 8px;"
                "}"
            )
        else:
            card.setStyleSheet(
                "CardWidget {"
                "background: #FFFFFF;"
                "border: 1px solid #EBEEF2;"
                "border-radius: 8px;"
                "}"
            )
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
        self._ensure_full_content()

    def ensure_announcement_created(self) -> None:
        """公告已在构造期以可折叠面板创建。"""
        return

    def ensure_recent_activity_created(self, reminders=None) -> None:
        """发布统计卡已在构造期创建；仅用于兼容旧调用路径。"""
        if reminders is not None:
            self.reveal_publish_reminders(reminders, animate_entry=False)

    def set_cached_reminders(self, reminders) -> None:
        self._cached_reminders = list(reminders or [])

    def reveal_publish_reminders(
        self,
        reminders,
        *,
        animate_entry: bool = False,
    ) -> None:
        rows = list(reminders or [])
        self._cached_reminders = rows
        recent = getattr(self, "recent_activity", None)
        if recent is None:
            return
        recent.reveal_reminders(rows, animate=animate_entry)

    def schedule_noncritical_first_paint(self) -> None:
        self._schedule_base_page_timer(
            "workspace_account_platform_prewarm",
            80,
            lambda: self.apply_account_platform_cache_if_available(),
        )

    @classmethod
    def _create_quick_action_layout(cls, container: QWidget) -> QGridLayout:
        """六张快捷卡片响应式网格：内容区够宽时单行六列，极窄时降级为多行。"""
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(cls._quick_action_spacing)
        layout.setVerticalSpacing(cls._quick_action_spacing)
        layout.setProperty("workspaceQuickActionLayoutKind", "responsive-grid")
        return layout

    @classmethod
    def _add_quick_action_card(cls, layout: QGridLayout, card: QWidget, index: int) -> None:
        card.setMinimumWidth(cls._quick_action_card_min_width)
        card.setMaximumWidth(16777215)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(card, 0, index)

    @classmethod
    def _stats_columns_for_width(cls, width: int) -> int:
        if width < cls._stats_compact_width:
            return 2
        return 4

    def _content_available_width(self) -> int:
        candidates: list[int] = []
        try:
            candidates.append(int(self.width()))
        except Exception:
            pass
        scroll = getattr(self, "_workspace_scroll_area", None)
        if scroll is not None:
            try:
                vp = scroll.viewport()
                if vp is not None:
                    candidates.append(int(vp.width()))
            except Exception:
                pass
        container = getattr(self, "_stats_container", None)
        if container is not None:
            try:
                w = int(container.width())
                if w > 0:
                    candidates.append(w)
            except Exception:
                pass
        return max(candidates) if candidates else 0

    def _quick_action_columns_for_width(self, width: int) -> int:
        if width >= self._quick_action_single_row_min_width:
            return 6
        if width < 420:
            return 2
        return 3

    def _relayout_quick_actions(self, width: Optional[int] = None) -> None:
        layout = getattr(self, "_quick_action_layout", None)
        cards = getattr(self, "_quick_action_cards", None) or ()
        if layout is None or not cards:
            return
        content_width = self._content_available_width() if width is None else width
        columns = self._quick_action_columns_for_width(content_width)
        if self._quick_action_grid_columns == columns and layout.count() == len(cards):
            return
        self._quick_action_grid_columns = columns
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setParent(self._quick_actions_container)
        for i, card in enumerate(cards):
            layout.addWidget(card, i // columns, i % columns)
        for c in range(6):
            layout.setColumnStretch(c, 1 if c < columns else 0)
        for r in range(3):
            layout.setRowStretch(r, 0)

    def _relayout_stats_cards(self, *, force: bool = False) -> None:
        if not hasattr(self, "_stats_grid") or self._stats_grid is None:
            return
        cards = getattr(self, "_stats_cards", None) or []
        if not cards:
            return
        width = self._content_available_width()
        columns = self._stats_columns_for_width(width)
        last_width = getattr(self, "_last_stats_width", 0)
        if (
            not force
            and getattr(self, "_stats_grid_columns", None) == columns
            and self._stats_grid.count() > 0
            and abs(width - last_width) < 8
        ):
            return
        self._last_stats_width = width
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
        for c in range(4):
            self._stats_grid.setColumnStretch(c, 1 if c < columns else 0)

    def _is_overview_maximized(self) -> bool:
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

    def _overview_pair_widgets(self) -> list[QWidget]:
        widgets: list[QWidget] = []
        account_card = getattr(self, "account_platform_card", None)
        if account_card is not None:
            widgets.append(account_card)
        recent = getattr(self, "recent_activity", None)
        if recent is not None:
            widgets.append(recent)
        return widgets

    def _workspace_scroll_viewport_height(self) -> int:
        scroll = getattr(self, "_workspace_scroll_area", None)
        if scroll is None:
            return 0
        try:
            vp = scroll.viewport()
            if vp is not None:
                return max(0, int(vp.height()))
        except Exception:
            pass
        return 0

    def _invalidate_overview_above_cache(self) -> None:
        self._overview_above_height_cache = None
        self._overview_above_height_signature = None

    def _overview_above_layout_signature(self) -> tuple:
        ann = getattr(self, "_announcement_panel", None)
        ann_collapsed = bool(getattr(ann, "is_collapsed", False)) if ann is not None else False
        return (
            self._workspace_scroll_viewport_height(),
            self._content_available_width(),
            ann_collapsed,
        )

    def _scroll_sections_height_before_overview(self) -> int:
        """双列概览区上方各块占位（含块间距），用于计算剩余可视高度。"""
        sig = self._overview_above_layout_signature()
        cached = getattr(self, "_overview_above_height_cache", None)
        if (
            cached is not None
            and getattr(self, "_overview_above_height_signature", None) == sig
        ):
            return int(cached)

        layout = getattr(self, "_scroll_layout", None)
        host = getattr(self, "_overview_pair_host", None)
        if layout is None or host is None:
            return 0
        spacing = int(layout.spacing()) if layout.spacing() >= 0 else 12
        total = 0
        seen_host = False
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            if widget is host:
                seen_host = True
                break
            if not widget.isVisible():
                continue
            h = max(int(widget.height()), int(widget.sizeHint().height()))
            total += max(0, h)
            total += spacing
        if seen_host and total > 0:
            total -= spacing
        self._overview_above_height_cache = total
        self._overview_above_height_signature = sig
        return total

    def _overview_pair_height_budget(self, *, stacked: bool) -> Optional[int]:
        """双列区在滚动视口内的可用高度（上方区块占位之后的剩余空间）。"""
        from ..components.account_platform_overview_card import (
            OVERVIEW_PAIR_HEIGHT_MIN,
            OVERVIEW_PAIR_STACKED_GAP,
            OVERVIEW_VIEWPORT_SAFETY,
        )

        viewport_h = self._workspace_scroll_viewport_height()
        if viewport_h < 240:
            return None
        layout = getattr(self, "_scroll_layout", None)
        spacing = int(layout.spacing()) if layout is not None and layout.spacing() >= 0 else 12
        above = self._scroll_sections_height_before_overview()
        # 概览区与上方最后一块之间还有一次 layout spacing
        remaining = viewport_h - above - spacing - OVERVIEW_VIEWPORT_SAFETY
        if stacked:
            min_host = OVERVIEW_PAIR_HEIGHT_MIN * 2 + OVERVIEW_PAIR_STACKED_GAP
            return max(min_host, remaining)
        return max(OVERVIEW_PAIR_HEIGHT_MIN, remaining)

    def _overview_pair_host_min_height(self, *, stacked: bool) -> int:
        from ..components.account_platform_overview_card import (
            OVERVIEW_PAIR_HEIGHT_MIN,
            OVERVIEW_PAIR_STACKED_GAP,
        )

        if stacked:
            return OVERVIEW_PAIR_HEIGHT_MIN * 2 + OVERVIEW_PAIR_STACKED_GAP
        return OVERVIEW_PAIR_HEIGHT_MIN

    def _scroll_content_height(self) -> int:
        content = getattr(self, "_scroll_content", None)
        if content is None:
            return 0
        try:
            return max(int(content.sizeHint().height()), int(content.height()))
        except Exception:
            return int(content.sizeHint().height())

    def _overview_layout_spacing(self) -> int:
        layout = getattr(self, "_scroll_layout", None)
        if layout is not None and layout.spacing() >= 0:
            return int(layout.spacing())
        return 12

    def _overview_total_scroll_height(self, host_height: int) -> int:
        """按布局公式计算滚动内容总高，避免还原后 content.height() 滞后导致过度收紧。"""
        return (
            self._scroll_sections_height_before_overview()
            + self._overview_layout_spacing()
            + max(0, int(host_height))
        )

    def _clamp_overview_pair_to_viewport(self, host_height: int, *, stacked: bool) -> int:
        """budget 已按视口与上方区块算出剩余高度，与 candidate 取交集即可（O(1)）。"""
        budget = self._overview_pair_height_budget(stacked=stacked)
        if budget is None:
            return host_height
        min_host = self._overview_pair_host_min_height(stacked=stacked)
        return max(min_host, min(host_height, budget))

    def _resolve_effective_overview_pair_height(self, *, stacked: bool, maximized: bool) -> int:
        from ..components.account_platform_overview_card import (
            clamp_overview_pair_height,
            resolve_overview_pair_height,
        )

        preferred = resolve_overview_pair_height(maximized=maximized, stacked=stacked)
        budget = self._overview_pair_height_budget(stacked=stacked)
        # 最大化：在视口预算内尽量撑满；默认：不超过 preferred
        height_cap = 99999 if maximized else preferred
        candidate = clamp_overview_pair_height(height_cap, budget=budget, stacked=stacked)
        return self._clamp_overview_pair_to_viewport(candidate, stacked=stacked)

    def _apply_overview_pair_heights(self, host_height: int, *, stacked: bool) -> None:
        from ..components.account_platform_overview_card import (
            overview_pair_card_height,
            publish_stats_card_height,
        )

        host = getattr(self, "_overview_pair_host", None)
        if host is not None:
            host.setFixedHeight(host_height)
        card_h = overview_pair_card_height(host_height, stacked=stacked)
        publish_h = publish_stats_card_height(card_h)
        account_card = getattr(self, "account_platform_card", None)
        if account_card is not None:
            account_card.setMinimumHeight(card_h)
            account_card.setMaximumHeight(card_h)
        recent = getattr(self, "recent_activity", None)
        if recent is not None:
            recent.setMinimumHeight(publish_h)
            recent.setMaximumHeight(publish_h)

    def _sync_workspace_page_scroll_policy(self) -> None:
        scroll = getattr(self, "_workspace_scroll_area", None)
        if scroll is None:
            return
        viewport_h = self._workspace_scroll_viewport_height()
        if viewport_h <= 0:
            return
        cached_host_h = getattr(self, "_overview_pair_host_height", None)
        if cached_host_h is not None and cached_host_h > 0:
            content_h = self._overview_total_scroll_height(int(cached_host_h))
        else:
            content_h = self._scroll_content_height()
        if content_h <= viewport_h + 2:
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def _ensure_main_window_state_filter(self) -> None:
        win = self.window()
        if win is None or self._win_state_filter_installed:
            return
        win.installEventFilter(self)
        self._win_state_filter_installed = True

    def _schedule_deferred_overview_sync(self, *, post_animation: bool = False) -> None:
        self._schedule_base_page_timer(
            "workspace_overview_layout_debounced",
            self._OVERVIEW_SYNC_DEBOUNCE_MS,
            self._run_deferred_overview_sync_light,
        )
        if post_animation:
            self._schedule_base_page_timer(
                "workspace_overview_layout_post_animation",
                self._OVERVIEW_SYNC_POST_ANIMATION_MS,
                self._run_deferred_overview_sync,
            )

    def _run_deferred_overview_sync_light(self) -> None:
        """防抖：宽度未变时仅同步双列区，避免最大化过渡帧反复重排 KPI。"""
        self._invalidate_overview_above_cache()
        width = self._content_available_width()
        last_width = getattr(self, "_last_responsive_width", 0)
        if abs(width - last_width) >= 8:
            self._last_responsive_width = width
            self._sync_responsive_layout()
        else:
            self._sync_overview_pair_layout(width)
        self._sync_recent_activity_layout()

    def _run_deferred_overview_sync(self) -> None:
        self._invalidate_overview_above_cache()
        self._sync_responsive_layout()
        self._sync_recent_activity_layout()

    def eventFilter(self, obj, event) -> bool:
        if obj is self.window():
            if event.type() == QEvent.Type.WindowStateChange:
                self._invalidate_overview_above_cache()
                self._schedule_deferred_overview_sync(post_animation=True)
            elif event.type() == QEvent.Type.Resize:
                self._schedule_deferred_overview_sync(post_animation=False)
        return super().eventFilter(obj, event)

    def _sync_overview_pair_layout(self, width: Optional[int] = None) -> None:
        layout = getattr(self, "_overview_pair_layout", None)
        if layout is None:
            return
        content_width = self._content_available_width() if width is None else width
        stacked = content_width < self._compact_width
        maximized = self._is_overview_maximized()
        maximized_changed = (
            self._last_overview_maximized is not None
            and self._last_overview_maximized != maximized
        )
        self._last_overview_maximized = maximized
        pair_height = self._resolve_effective_overview_pair_height(
            stacked=stacked,
            maximized=maximized,
        )
        layout_changed = stacked != self._overview_stacked or layout.count() < 2
        height_changed = getattr(self, "_overview_pair_host_height", None) != pair_height
        if not layout_changed and not height_changed and not maximized_changed:
            self._sync_workspace_page_scroll_policy()
            return

        self._overview_stacked = stacked
        self._overview_pair_host_height = pair_height

        if layout_changed:
            widgets = self._overview_pair_widgets()
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.setParent(self._overview_pair_host)
            if stacked:
                for row, widget in enumerate(widgets):
                    layout.addWidget(widget, row, 0)
                layout.setColumnStretch(0, 1)
                layout.setColumnStretch(1, 0)
            else:
                for col, widget in enumerate(widgets):
                    layout.addWidget(widget, 0, col)
                layout.setColumnStretch(0, 1)
                layout.setColumnStretch(1, 1)
        self.setUpdatesEnabled(False)
        try:
            self._apply_overview_pair_heights(pair_height, stacked=stacked)
        finally:
            self.setUpdatesEnabled(True)
        self._sync_workspace_page_scroll_policy()
        self._sync_recent_activity_layout()

    def _sync_responsive_layout(self) -> None:
        width = self._content_available_width()
        self._last_responsive_width = width
        self._relayout_stats_cards()
        self._relayout_quick_actions(width)
        self._sync_overview_pair_layout(width)

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
                self.reveal_publish_reminders(reminder_rows, animate_entry=animate_entry)
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
        primary = "#EAF6FF" if dark else "#1F2937"
        muted = "#A9B7C2" if dark else "#6B7280"
        card_bg = "rgba(255, 255, 255, 0.045)" if dark else "#FFFFFF"
        border = "rgba(255, 255, 255, 0.08)" if dark else "#EBEEF2"
        if hasattr(self, "_header_card") and self._header_card:
            self._header_card.setStyleSheet(
                "CardWidget {"
                f"background: {card_bg};"
                f"border: 1px solid {border};"
                "border-radius: 8px;"
                "}"
            )
        if hasattr(self, "welcome_line") and self.welcome_line:
            self.welcome_line.setStyleSheet(
                f"font-size: 15px; font-weight: 650; color: {primary}; margin: 0; padding: 0;"
            )
        if hasattr(self, "_welcome_meta_label") and self._welcome_meta_label:
            self._welcome_meta_label.setStyleSheet(
                f"font-size: 12px; color: {muted}; font-weight: 400;"
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
        if hasattr(self, "_welcome_meta_label") and self._welcome_meta_label:
            try:
                time_str = datetime.now().strftime("%H:%M")
            except Exception:
                time_str = ""
            self._welcome_meta_label.setText(f"数据自动刷新 · {time_str}" if time_str else "数据自动刷新")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._ensure_full_content()
        if hasattr(self, "refresh_timer") and self.refresh_timer and not self.refresh_timer.isActive():
            self.refresh_timer.start()
        self.refresh_welcome_display()
        self._apply_welcome_line_style()
        # 首帧 viewport 宽度可能仍为 0，显示后再强制按实际宽度排四列 KPI
        self._relayout_stats_cards(force=True)
        self._schedule_base_page_timer(
            "workspace_stats_relayout_deferred",
            0,
            lambda: self._relayout_stats_cards(force=True),
        )
        self._relayout_quick_actions()
        self._last_responsive_width = self._content_available_width()
        if self._workspace_scroll_viewport_height() < 240:
            self._schedule_base_page_timer(
                "workspace_overview_layout_initial",
                0,
                self._sync_overview_pair_layout,
            )
        else:
            self._sync_overview_pair_layout()
        self._schedule_base_page_timer(
            "workspace_overview_event_filter_install",
            self._OVERVIEW_EVENT_FILTER_DELAY_MS,
            self._ensure_main_window_state_filter,
        )
        self.schedule_noncritical_first_paint()
        if self._orchestrator:
            self._orchestrator.schedule_startup_refresh()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if getattr(self, "_win_state_filter_installed", False):
            self._schedule_deferred_overview_sync(post_animation=False)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._invalidate_overview_above_cache()
            self._schedule_deferred_overview_sync(post_animation=True)

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
