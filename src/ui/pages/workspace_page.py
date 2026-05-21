"""
工作台页面
文件路径：src/ui/pages/workspace_page.py
功能：工作台页面，显示概览信息、快速操作、数据图表和最近活动
"""

from typing import Optional, Dict, Any
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import QTimer, Qt, QEvent, Signal
from PySide6.QtGui import QResizeEvent
import logging

from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, TitleLabel,
    CaptionLabel, PrimaryPushButton, PushButton, IndeterminateProgressRing,
    FluentIcon, IconWidget, HyperlinkButton, TransparentToolButton, DisplayLabel,
    isDarkTheme
)
FLUENT_WIDGETS_AVAILABLE = True

from .base_page import BasePage
from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.utils.platform_names import PLATFORM_ID_TO_NAME as PLATFORM_NAME_MAP
from src.services.material.media_library_stats_cache import get_media_library_stats_cache
from src.services.material.media_library_stats_service import get_media_library_stats_service

logger = logging.getLogger(__name__)


class WorkspacePage(BasePage):
    """工作台页面"""

    refreshRequested = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("工作台", parent)
        from src.services.auth import CurrentUserService
        self._current_user_svc = CurrentUserService()
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        self.dashboard_service = None
        self._is_loading = False
        self._refresh_task = None
        self.refreshRequested.connect(self._refresh_data)
        self._init_services()
        self._setup_content()
        self._setup_refresh_timer()
        self._stats_cache = get_media_library_stats_cache()
        self._media_stats_card = None
        try:
            self._stats_cache.statsUpdated.connect(self._on_media_stats_updated)
        except Exception:
            pass
    
    def _init_services(self):
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.services.account.account_manager_async import AccountManagerAsync
            from src.services.workspace.dashboard_service import DashboardService
            from src.infrastructure.common.event.event_bus import EventBus
            
            service_locator = ServiceLocator()
            event_bus = service_locator.get(EventBus)
            
            account_manager = AccountManagerAsync(
                user_id=self.user_id,
                event_bus=event_bus
            )
            
            batch_task_manager = None
            try:
                from src.pro_features.batch.services.batch_task_manager_async import BatchTaskManagerAsync
                batch_task_manager = BatchTaskManagerAsync(
                    user_id=self.user_id,
                    event_bus=event_bus
                )
            except ImportError:
                logger.info("批量任务管理器不可用 (Pro功能未安装)")
            
            self.dashboard_service = DashboardService(
                user_id=self.user_id,
                account_manager=account_manager,
                batch_task_manager=batch_task_manager
            )

            self._publish_queue_event_handler = None
            try:
                def _on_publish_queue_executing_changed(_event) -> None:
                    self.refreshRequested.emit()

                self._publish_queue_event_handler = _on_publish_queue_executing_changed
                event_bus.subscribe(
                    "PublishQueueExecutingCountChangedEvent",
                    self._publish_queue_event_handler,
                )
            except Exception as e:
                logger.debug("订阅发布队列执行中事件失败（可忽略）: %s", e)

            self._account_updated_event_handler = None
            try:
                def _on_account_updated_for_dashboard(_event) -> None:
                    if self.isVisible():
                        self.refreshRequested.emit()

                self._account_updated_event_handler = _on_account_updated_for_dashboard
                event_bus.subscribe("AccountUpdatedEvent", self._account_updated_event_handler)
            except Exception as e:
                logger.debug("订阅账号更新事件失败（可忽略）: %s", e)
            
            logger.debug("工作台服务初始化成功")
        except Exception as e:
            logger.error(f"初始化工作台服务失败: {e}", exc_info=True)
    
    def _setup_refresh_timer(self):
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_data)
        self.refresh_timer.start(60000)

    def hideEvent(self, event):
        if hasattr(self, 'refresh_timer') and self.refresh_timer:
            self.refresh_timer.stop()
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
        super().hideEvent(event)

    def _setup_content(self):
        from ..components.statistics_card import StatisticsCard
        from ..components.quick_action_card import QuickActionCard
        from ..components.announcement_widget import AnnouncementWidget
        from ..components.recent_activity_widget import RecentActivityWidget
        
        try:
            from ..components.charts import PlatformDistributionChart, PublishTrendChart
            CHARTS_AVAILABLE = True
        except ImportError:
            CHARTS_AVAILABLE = False
        
        # 创建滚动区域
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
        
        # ──── 1. 欢迎标题区域 ────
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

        # ──── 2. 统计卡片区域（一行四卡，固定） ────
        self._stats_cards = []
        self._stats_grid_columns = 4
        self._stats_container = QWidget(self)
        self._stats_grid = QGridLayout(self._stats_container)
        self._stats_grid.setContentsMargins(0, 0, 0, 0)
        self._stats_grid.setHorizontalSpacing(12)
        self._stats_grid.setVerticalSpacing(12)

        self.account_card = StatisticsCard("账号总数", "0", "0 在线 | 0 离线", FluentIcon.PEOPLE, self)
        self.publish_card = StatisticsCard("今日发布", "0", "0 成功 | 0 失败", FluentIcon.SEND, self)
        self.task_card = StatisticsCard("待执行任务", "0", "完成率 0%", FluentIcon.FOLDER, self)
        self.success_rate_card = StatisticsCard("发布成功率", "0%", "近7天数据", FluentIcon.ACCEPT, self)

        self._stats_cards = [
            self.account_card,
            self.publish_card,
            self.task_card,
            self.success_rate_card,
        ]
        self._relayout_stats_cards()
        scroll_layout.addWidget(self._stats_container)

        # ──── 2.1 媒体库素材统计（单卡，复用全局缓存） ────
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
        
        # ──── 3. 快捷操作 (左) + 公告栏 (右) + 最近活动 (右) ────
        # 右侧公告栏与最近活动改为左右并排，避免还原窗口高度被对半分后内容被压扁
        mid_row = QHBoxLayout()
        mid_row.setSpacing(12)
        
        # 左侧：两行三列卡片网格
        cards_container = QWidget(self)
        cards_grid = QGridLayout(cards_container)
        cards_grid.setContentsMargins(0, 0, 0, 0)
        cards_grid.setSpacing(12)
        
        self.action_add_account = QuickActionCard(FluentIcon.ADD, "添加账号", "", self)
        self.action_single_video = QuickActionCard(FluentIcon.MOVIE, "创建单视频任务", "", self)
        self.action_batch_video = QuickActionCard(FluentIcon.LIBRARY, "创建多视频任务", "", self)
        
        self.action_add_account.clicked.connect(self._on_add_account_clicked)
        self.action_single_video.clicked.connect(self._on_quick_publish_clicked)
        self.action_batch_video.clicked.connect(self._on_batch_video_clicked)
        
        cards_grid.addWidget(self.action_add_account, 0, 0)
        cards_grid.addWidget(self.action_single_video, 0, 1)
        cards_grid.addWidget(self.action_batch_video, 0, 2)
        
        self.action_publish_list = QuickActionCard(FluentIcon.SEND, "发布任务", "", self)
        self.action_single_image = QuickActionCard(FluentIcon.EDIT, "创建单图文任务", "", self)
        self.action_batch_image = QuickActionCard(FluentIcon.TILES, "创建多图文任务", "", self)
        
        self.action_publish_list.clicked.connect(self._on_publish_list_clicked)
        self.action_single_image.clicked.connect(self._on_single_image_clicked)
        self.action_batch_image.clicked.connect(self._on_batch_image_clicked)
        
        cards_grid.addWidget(self.action_publish_list, 1, 0)
        cards_grid.addWidget(self.action_single_image, 1, 1)
        cards_grid.addWidget(self.action_batch_image, 1, 2)
        
        cards_grid.setColumnStretch(0, 1)
        cards_grid.setColumnStretch(1, 1)
        cards_grid.setColumnStretch(2, 1)
        
        mid_row.addWidget(cards_container, 3)
        
        # 右侧：公告栏 + 最近活动（左右并排，共享同一行高度，纵向可多展示几条）
        right_row = QHBoxLayout()
        right_row.setSpacing(12)
        
        self.announcement = AnnouncementWidget(self)
        self.announcement.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_row.addWidget(self.announcement, 1)
        
        self.recent_activity = RecentActivityWidget(self)
        self.recent_activity.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_row.addWidget(self.recent_activity, 1)
        
        mid_row.addLayout(right_row, 3)
        
        scroll_layout.addLayout(mid_row)
        
        # ──── 4. 图表行 (平台分布 + 发布趋势) ────
        if CHARTS_AVAILABLE:
            charts_layout = QHBoxLayout()
            charts_layout.setSpacing(12)
            
            self.platform_chart = PlatformDistributionChart(self)
            self.platform_chart.setFixedHeight(260)
            self.platform_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            charts_layout.addWidget(self.platform_chart, 1)
            
            self.trend_chart = PublishTrendChart(self)
            self.trend_chart.setFixedHeight(260)
            self.trend_chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            charts_layout.addWidget(self.trend_chart, 1)
            
            scroll_layout.addLayout(charts_layout)
        
        scroll_area.setWidget(scroll_content)
        self.content_layout.addWidget(scroll_area)
        
        self._refresh_data()
        self._refresh_media_stats_async()

    def _relayout_stats_cards(self) -> None:
        """固定一行四卡布局。"""
        if not hasattr(self, "_stats_grid") or self._stats_grid is None:
            return
        cards = getattr(self, "_stats_cards", None) or []
        if not cards:
            return
        columns = 4
        if getattr(self, "_stats_grid_columns", None) == columns and self._stats_grid.count() > 0:
            return
        self._stats_grid_columns = columns

        # 清空 grid（不销毁卡片，只是重新 add）
        while self._stats_grid.count():
            item = self._stats_grid.takeAt(0)
            if item is None:
                break
            ww = None
            try:
                ww = item.widget()
            except Exception:
                ww = None
            if ww is not None:
                ww.setParent(self._stats_container)

        for i, card in enumerate(cards):
            r = i // columns
            c = i % columns
            self._stats_grid.addWidget(card, r, c)

        for c in range(columns):
            self._stats_grid.setColumnStretch(c, 1)

    def _refresh_media_stats_async(self) -> None:
        """触发媒体库素材统计刷新（异步）。"""
        try:
            get_async_task_registry().create_task(
                get_media_library_stats_service().refresh(),
                name="ui.workspace.media_stats_refresh",
                group="ui",
            )
        except Exception:
            return

    def _on_media_stats_updated(self, stats) -> None:
        v_card = getattr(self, "_video_library_card", None)
        i_card = getattr(self, "_image_library_card", None)
        if v_card is None or i_card is None:
            return
        try:
            v_counts = getattr(getattr(stats, "video", None), "counts", None)
            i_counts = getattr(getattr(stats, "image", None), "counts", None)

            if v_counts is None:
                v_card.set_value("—")
                v_card.set_description("总 — | 已占用 — | 未占用 —")
            else:
                vt = int(getattr(v_counts, "total", 0) or 0)
                vu = int(getattr(v_counts, "used", 0) or 0)
                vn = int(getattr(v_counts, "unused", 0) or 0)
                v_card.set_value(str(vt))
                v_card.set_description(f"总 {vt} | 已占用 {vu} | 未占用 {vn}")

            if i_counts is None:
                i_card.set_value("—")
                i_card.set_description("总 — | 已占用 — | 未占用 —")
            else:
                it = int(getattr(i_counts, "total", 0) or 0)
                iu = int(getattr(i_counts, "used", 0) or 0)
                inn = int(getattr(i_counts, "unused", 0) or 0)
                i_card.set_value(str(it))
                i_card.set_description(f"总 {it} | 已占用 {iu} | 未占用 {inn}")
        except Exception:
            return

    # ──── 欢迎语样式 ────

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
    
    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'refresh_timer') and self.refresh_timer and not self.refresh_timer.isActive():
            self.refresh_timer.start()
        self._update_welcome_text()
        self._apply_welcome_title_style()
        self._apply_welcome_desc_style()
        self._sync_recent_activity_layout()
        # 从账号库等页面返回时立即拉取统计，避免仍显示离开前的旧在线/离线数字
        self._schedule_base_page_timer("workspace_refresh", 0, self._refresh_data)
        self._schedule_base_page_timer(
            "workspace_media_stats_refresh",
            0,
            self._refresh_media_stats_async,
        )

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._sync_recent_activity_layout()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_recent_activity_layout()

    def _sync_recent_activity_layout(self) -> None:
        if hasattr(self, "recent_activity") and self.recent_activity is not None:
            self.recent_activity._sync_compact_layout()
    
    # ──── 数据加载 ────

    def _refresh_data(self):
        if not self.dashboard_service or self._is_loading:
            return
        
        self._is_loading = True
        
        async def _load_and_update():
            try:
                data = await self.dashboard_service.get_dashboard_data()
                self._on_data_loaded(data)
            except Exception as e:
                self._on_data_load_error(str(e))
        
        import asyncio
        try:
            # 尝试获取当前正在运行的事件循环（Qt 主线程由 qasync 管理）
            asyncio.get_running_loop()
            # 有运行中的循环，直接创建 task
            self._refresh_task = get_async_task_registry().create_task(
                _load_and_update(),
                name="ui.workspace.refresh",
                group="ui",
            )
        except RuntimeError:
            # 没有运行中的事件循环（如从线程池回调中触发），回到主线程重试
            logger.debug("[WorkspacePage] _refresh_data 在非事件循环线程中调用，已转发到主线程")
            self._is_loading = False  # 重置状态，等主线程执行时重新加锁
            self.refreshRequested.emit()

    def _on_data_loaded(self, dashboard_data: Dict[str, Any]):
        try:
            self._is_loading = False
            
            # 更新账号数量卡片
            account_stats = dashboard_data.get('account', {})
            account_total = account_stats.get('total', 0)
            account_online = account_stats.get('online', 0)
            account_offline = account_stats.get('offline', 0)
            if hasattr(self, 'account_card'):
                self.account_card.set_value(str(account_total))
                self.account_card.set_description(f"{account_online} 在线 | {account_offline} 离线")
            
            # 更新今日发布卡片
            publish_stats = dashboard_data.get('publish', {})
            today_count = publish_stats.get('today_count', 0)
            today_success = publish_stats.get('today_success', 0)
            today_failed = publish_stats.get('today_failed', 0)
            today_pending = publish_stats.get('today_pending', 0)
            today_running = publish_stats.get('today_running', 0)
            if hasattr(self, 'publish_card'):
                self.publish_card.set_value(str(today_count))
                # 口径说明：今日发布仅展示“成功/失败”，不混入等待/执行中（避免用户误解为已发布完成）
                self.publish_card.set_description(f"{today_success} 成功 | {today_failed} 失败")
            
            # 更新待执行任务卡片（无批量任务时与「待发布」页 pending+failed 及发布中队列 UI 状态对齐）
            task_stats = dashboard_data.get('task', {})
            total_pending = task_stats.get('total_pending', 0)
            batch_total = task_stats.get('total', 0)
            completion_rate = task_stats.get('completion_rate', 0)
            if hasattr(self, 'task_card'):
                if batch_total > 0:
                    self.task_card.set_value(str(total_pending))
                    self.task_card.set_description(f"批量任务: {batch_total} | 完成: {completion_rate:.0f}%")
                else:
                    pub_tab = task_stats.get('publish_tab_total', task_stats.get('total_pending', 0))
                    pub_wait = task_stats.get('publish_waiting', task_stats.get('publish_pending', 0))
                    pub_exec = task_stats.get('publish_executing_ui', task_stats.get('publish_running', 0))
                    self.task_card.set_value(str(pub_tab))
                    self.task_card.set_description(f"{pub_wait} 等待 | {pub_exec} 执行中")
            
            # 更新成功率卡片（近 7 天已完成记录的成功率）
            success_rate_7d = publish_stats.get('success_rate_7d', 0)
            finished_7d = publish_stats.get('finished_7d', 0)
            if hasattr(self, 'success_rate_card'):
                self.success_rate_card.set_value(f"{success_rate_7d:.1f}%")
                # 还原窗口下副标题宽度有限，长句易被截断；改为更短的一行口径
                # 完整说明仍可通过 tooltip 查看（StatisticsCard.set_description 会同步 tooltip）
                self.success_rate_card.set_description(f"近7天 {finished_7d}条")
            
            # 更新平台分布
            platform_stats = account_stats.get('by_platform', {})
            if hasattr(self, 'platform_chart'):
                platform_stats_cn = {
                    PLATFORM_NAME_MAP.get(k, k): v
                    for k, v in platform_stats.items()
                }
                self.platform_chart.set_data(platform_stats_cn)
            
            # 更新发布趋势（始终调用以支持空状态展示）
            trend_data = publish_stats.get('daily_stats', [])
            if hasattr(self, 'trend_chart'):
                self.trend_chart.set_data(trend_data)

            # 更新最近发布（在线账号发布提醒）
            reminders = dashboard_data.get('account_publish_reminders', [])
            if hasattr(self, 'recent_activity'):
                self.recent_activity.set_account_reminders(reminders)
                    
        except Exception as e:
            logger.error(f"更新工作台数据失败: {e}", exc_info=True)
            self._is_loading = False

    def _on_data_load_error(self, error: str):
        logger.error(f"加载工作台数据失败: {error}")
        self._is_loading = False
    
    # ──── 导航回调 ────

    def _on_add_account_clicked(self):
        self._navigate_to_page("account_page")
    
    def _on_quick_publish_clicked(self):
        self._navigate_to_page("single_task_creation_page")
    
    def _on_batch_video_clicked(self):
        self._navigate_to_page("batch_task_creation_page")
    
    def _on_single_image_clicked(self):
        self._navigate_to_page("image_single_task_creation_page")
    
    def _on_batch_image_clicked(self):
        self._navigate_to_page("image_batch_task_creation_page")
    
    def _on_publish_list_clicked(self):
        self._navigate_to_page("publish_list_page")

    def _on_navigate_to_browser(self):
        self._navigate_to_page("account_page")
    
    def _navigate_to_page(self, page_name: str):
        """导航到指定页面，优先使用主窗口 navigate_to 以保持导航状态一致"""
        try:
            main_window = self.window()
            if not main_window:
                return
            if hasattr(main_window, 'navigate_to'):
                main_window.navigate_to(page_name)
                return
            page = getattr(main_window, page_name, None)
            if not page:
                logger.warning(f"页面不存在: {page_name}")
                return
            if hasattr(main_window, 'navigationInterface'):
                nav = main_window.navigationInterface
                if hasattr(nav, 'stackedWidget'):
                    idx = nav.stackedWidget.indexOf(page)
                    if idx >= 0:
                        nav.stackedWidget.setCurrentIndex(idx)
        except Exception as e:
            logger.error(f"导航到页面失败: {e}", exc_info=True)
