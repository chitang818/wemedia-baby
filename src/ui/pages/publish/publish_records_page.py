"""
已发布任务记录页面（导航：「已发布」）
文件路径：src/ui/pages/publish/publish_records_page.py
功能：显示已成功发布的任务列表；子类 PublishListPage 用于「待发布」。
"""

from typing import Callable, Optional, List, Dict, Any, Tuple
from collections import defaultdict
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
)
from PySide6.QtCore import Qt, QTimer, QSize, QEvent, QUrl
from PySide6.QtGui import QKeyEvent, QResizeEvent, QDesktopServices
import logging
import os

from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, PushButton,
    LineEdit, ComboBox, InfoBar, FluentIcon, IconWidget,
    PrimaryPushButton, CheckBox,
)
FLUENT_WIDGETS_AVAILABLE = True

from ..base_page import BasePage
from src.ui.pages.publish.publish_records_controller import PublishRecordsController
from src.ui.pages.publish.publish_record_table_view import PublishRecordTableView
from src.ui.utils.fluent_tooltips import (
    ToolTipPosition,
    install_fluent_tool_tip,
    apply_instructional_tooltip,
)
from src.utils.date_utils import format_schedule_time_st_str

logger = logging.getLogger(__name__)


def notify_publish_records_history_tab_refresh(source_widget: QWidget) -> None:
    """发布列表等更新数据库后，使「发布记录」页缓存失效；若该页当前可见则立即重新拉库。"""
    try:
        win = source_widget.window()
        if not hasattr(win, "_get_or_create_page"):
            return
        rec_page = win._get_or_create_page("publish_records_page")
        if rec_page is None:
            return
        if hasattr(rec_page, "mark_data_stale"):
            rec_page.mark_data_stale()
        if rec_page.isVisible() and hasattr(rec_page, "_load_publish_records"):
            rec_page._load_publish_records()
    except Exception:
        logger.debug("notify_publish_records_history_tab_refresh 忽略异常", exc_info=True)


def notify_publish_recycle_bin_refresh(source_widget: QWidget) -> None:
    """待发布/已发布页软删除后，使回收站缓存失效；若该页可见则立即拉库。"""
    try:
        win = source_widget.window()
        if not hasattr(win, "_get_or_create_page"):
            return
        bin_page = win._get_or_create_page("publish_recycle_bin_page")
        if bin_page is None:
            return
        if hasattr(bin_page, "mark_data_stale"):
            bin_page.mark_data_stale()
        if bin_page.isVisible() and hasattr(bin_page, "_load_deleted_records"):
            bin_page._load_deleted_records()
    except Exception:
        logger.debug("notify_publish_recycle_bin_refresh 忽略异常", exc_info=True)


def notify_publish_list_and_records_refresh(source_widget: QWidget) -> None:
    """回收站恢复任务后刷新「待发布」「已发布」页。"""
    try:
        win = source_widget.window()
        if not hasattr(win, "_get_or_create_page"):
            return
        for key in ("publish_list_page", "publish_records_page"):
            p = win._get_or_create_page(key)
            if p is None:
                continue
            if hasattr(p, "mark_data_stale"):
                p.mark_data_stale()
            if p.isVisible() and hasattr(p, "_load_publish_records"):
                p._load_publish_records()
    except Exception:
        logger.debug("notify_publish_list_and_records_refresh 忽略异常", exc_info=True)


def _record_is_image_task(record: dict) -> bool:
    """与发布列表一致：优先 file_type，否则按路径扩展名推断图文。"""
    ft = (record.get("file_type") or "").lower()
    if ft == "image":
        return True
    if ft == "video":
        return False
    fp = record.get("file_path") or ""
    paths = [p.strip().lower() for p in str(fp).split(",") if p.strip()]
    return any(
        p.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))
        for p in paths
    )


def _record_is_scheduled_publish(record: dict) -> bool:
    """是否与表格「定时时间」列一致：有有效 scheduled_publish_time 视为定时发布，否则立即发布。"""
    return bool(format_schedule_time_st_str(record.get("scheduled_publish_time")))


def _record_account_filter_key(record: dict) -> str:
    """账号筛选用稳定键：优先 platform_account_id，否则平台+组+昵称兜底。"""
    pid = record.get("platform_account_id")
    if pid is not None:
        try:
            return f"id:{int(pid)}"
        except (TypeError, ValueError):
            pass
    plat = (record.get("platform") or "").strip()
    user = (record.get("platform_username") or "").strip()
    grp = (record.get("account_group_name") or "").strip()
    return f"leg:{plat}|{grp}|{user}"


def _record_account_filter_display(record: dict) -> str:
    """账号筛选项展示：平台 · 昵称（无昵称时用组名）。"""
    from src.utils.platform_names import get_platform_display_name

    plat_disp = get_platform_display_name(record.get("platform", "") or "").strip() or "—"
    user = (record.get("platform_username") or "").strip()
    grp = (record.get("account_group_name") or "").strip()
    if user:
        return f"{plat_disp} · {user}"
    if grp:
        return f"{plat_disp} · {grp}"
    return f"{plat_disp} · （无昵称）"


def _disambiguate_account_filter_labels(key_to_display: Dict[str, str]) -> Dict[str, str]:
    """同一展示文案对应多个账号时加后缀区分（下拉项需唯一文本）。"""
    by_disp: Dict[str, List[str]] = defaultdict(list)
    for k, d in key_to_display.items():
        by_disp[d].append(k)
    out: Dict[str, str] = {}
    for k, d in key_to_display.items():
        coll = by_disp[d]
        if len(coll) == 1:
            out[k] = d
        elif k.startswith("id:"):
            out[k] = f"{d} (#{k[3:]})"
        else:
            out[k] = f"{d} ({coll.index(k) + 1})"
    return out



_FILE_DELETED_MARKER = "__DELETED__"
_FOLDER_MARKER_PREFIX = "__FOLDER__:"


def _file_path_is_deleted(fp: str) -> bool:
    """file_path 字段所有非文件夹标记分段均为 __DELETED__ 标记时，视为已删除。"""
    if not fp:
        return False
    parts = [
        p.strip() for p in fp.split(",")
        if p.strip() and not p.strip().startswith(_FOLDER_MARKER_PREFIX)
    ]
    return bool(parts) and all(p == _FILE_DELETED_MARKER for p in parts)


def _record_media_folder_path(record: dict) -> str:
    """任务主文件（视频或首张图）所在目录的绝对路径；无效时返回空串。"""
    fp = (record.get("file_path") or "").strip()
    if not fp or _file_path_is_deleted(fp):
        return ""
    real_parts = [
        p.strip() for p in fp.split(",")
        if p.strip() and not p.strip().startswith(_FOLDER_MARKER_PREFIX)
    ]
    first = real_parts[0] if real_parts else ""
    if not first or first == _FILE_DELETED_MARKER:
        return ""
    try:
        p = os.path.abspath(os.path.normpath(first))
        parent = os.path.dirname(p)
        return parent if parent else ""
    except Exception:
        return ""


def open_record_media_folder(parent: QWidget, record: dict) -> None:
    """在系统文件管理器中打开任务视频/图片所在目录；失败时弹出提示。"""
    folder = _record_media_folder_path(record)
    if not folder:
        InfoBar.warning("无法打开文件夹", "该任务没有有效的文件路径", parent=parent)
        return
    if not os.path.isdir(folder):
        InfoBar.warning(
            "无法打开文件夹",
            "文件夹不存在或已被移动，请核对「文件」路径是否仍然有效。",
            parent=parent,
        )
        return
    url = QUrl.fromLocalFile(os.path.abspath(folder))
    if not QDesktopServices.openUrl(url):
        InfoBar.warning("无法打开文件夹", "系统未能打开该路径", parent=parent)


def open_record_primary_media_file(parent: QWidget, record: dict) -> None:
    """用系统默认程序打开任务主文件：视频由默认播放器播放，图片由默认看图软件打开。

    多路径（逗号分隔，常见于图文多图）时仅打开第一项，与「打开所在文件夹」取主文件逻辑一致。
    """
    fp = (record.get("file_path") or "").strip()
    if not fp:
        InfoBar.warning("无法打开文件", "该任务没有有效的文件路径", parent=parent)
        return
    first = fp.split(",")[0].strip()
    if not first:
        InfoBar.warning("无法打开文件", "该任务没有有效的文件路径", parent=parent)
        return
    try:
        path = os.path.abspath(os.path.normpath(first))
    except Exception:
        InfoBar.warning("无法打开文件", "文件路径无效", parent=parent)
        return
    if not os.path.isfile(path):
        InfoBar.warning(
            "无法打开文件",
            "文件不存在或已被移动，请核对「文件」列路径是否仍然有效。",
            parent=parent,
        )
        return
    url = QUrl.fromLocalFile(path)
    if not QDesktopServices.openUrl(url):
        InfoBar.error(
            "打开失败",
            "系统未能用默认程序打开该文件。请确认已安装播放器或看图软件，并在系统中关联该文件类型。",
            parent=parent,
            duration=4000,
        )


class PublishRecordsPage(BasePage):
    """发布记录页面"""

    _lazy_content = True
    _enable_show_fade = False

    # 表格列索引常量，统一管理，避免子类硬编码列号导致列顺序调整后出错
    COL_CREATE_TIME = 0
    COL_TYPE = 1
    COL_PLATFORM = 2
    COL_ACCOUNT_GROUP = 3
    COL_TASK_SOURCE = 4
    COL_ACCOUNT_NAME = 5
    COL_FILE = 6
    COL_COVER = 7
    COL_TITLE = 8
    COL_DESCRIPTION = 9
    COL_SCHEDULED_TIME = 10
    COL_ORIGINAL = 11
    COL_MUSIC = 12
    COL_CART = 13
    COL_GROUP_BUY = 14
    COL_LOCATION = 15
    COL_STATUS = 16
    COL_FILE_LOCATION = 17
    COL_ACTION = 18

    def __init__(self, parent: Optional[QWidget] = None, title: str = "已发布", target_statuses: List[str] = None):
        """初始化"""
        super().__init__(title, parent)
        from src.services.auth import CurrentUserService
        self._current_user_svc = CurrentUserService()
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        self.publish_records = []
        self._active_workers = []
        self._records_controller = PublishRecordsController(self)

        self.target_statuses = target_statuses if target_statuses is not None else ["success"]
        # 已发布页（仅 success）首次只加载最近 500 条以提升响应；待发布页保持全量加载
        self._records_load_limit: int = 500
        self._records_load_step: int = 500  # 每次「加载更多」增加的条数
        self._has_more_records: bool = False  # 是否还有更多记录可加载
        self._loading_more_records: bool = False
        self._filter_bar_compact = None
        self._filter_single_line_built = False  # 筛选控件已铺到单行（不再按宽度拆成两行）
        self._enable_task_type_filter = True
        # 切换「平台」筛选时重置「账号」为全部，避免组合条件无结果
        self._last_platform_for_account_reset: Optional[str] = None
        self._data_stale = True
        # 连续触发加载时只采纳最后一次结果，避免旧请求晚到覆盖新数据
        self._load_publish_generation = 0
        # 表格右键：复用 RoundMenu（与《右键菜单标准化规范》一致）
        self._records_table_ctx_menu = None
        self._records_table_ctx_view = None
        self._records_table_ctx_open_file = None
        self._records_table_ctx_open_folder = None
        self._records_table_ctx_readd = None
        self._records_table_ctx_delete = None
        self._records_table_ctx_pending_rows: List[int] = []
        # 选区缓存：selectionChanged 信号维护，右键直接读，避免每次扫描
        self._selected_rows_cache: List[int] = []
        # 分批渲染：当前渲染代次，用于取消旧批次
        self._render_generation: int = 0
        self._render_batch_timers: List[QTimer] = []
        # id→record 索引字典：避免 next(r for r in publish_records if r.get('id')==rid) 的 O(n) 扫描
        self._records_by_id: Dict[int, Any] = {}
        self._account_filter_options_cache: Optional[List[Tuple[str, str]]] = None
        self._record_filter_meta_by_id: Dict[int, Dict[str, Any]] = {}
        self._records_version: int = 0
        self._last_filter_render_state: Optional[tuple] = None
        self._last_filter_criteria: Optional[tuple] = None
        self._last_rendered_record_ids: List[int] = []
        # id→当前表格行号：发布队列局部状态更新时避免全表扫描
        self._row_by_record_id: Dict[int, int] = {}
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(120)
        self._filter_timer.timeout.connect(self._apply_filters)

    def closeEvent(self, event):
        self._cancel_render_batch_timers()
        super().closeEvent(event)

    def _schedule_render_batch(self, callback: Callable[[], None]) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)

        def _fire() -> None:
            try:
                self._render_batch_timers.remove(timer)
            except ValueError:
                pass
            timer.deleteLater()
            callback()

        timer.timeout.connect(_fire)
        self._render_batch_timers.append(timer)
        timer.start(0)

    def _cancel_render_batch_timers(self) -> None:
        for timer in list(getattr(self, "_render_batch_timers", [])):
            timer.stop()
            timer.deleteLater()
        self._render_batch_timers = []

    def _show_publish_queue_toolbar(self) -> bool:
        """待发布列表需要发布队列控制；已发布（仅 success）为历史记录，不展示发布相关按钮与选项。"""
        return self.target_statuses != ["success"]

    def _record_table_action_button_text(self) -> str:
        """表格末列操作按钮文案（待发布 / 已发布统一为「编辑」）。"""
        return "编辑"

    def _setup_content(self):
        """设置内容"""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        
        # 筛选和搜索区域：顶行操作按钮 + 下一行全部筛选（固定两行，避免窄屏占三行高度）
        self.filter_card = CardWidget(self)
        filter_card = self.filter_card
        self._filter_card_outer_layout = QVBoxLayout(filter_card)
        self._filter_card_outer_layout.setContentsMargins(12, 10, 12, 10)
        self._filter_card_outer_layout.setSpacing(8)

        # —— 操作行（待发布：删除+发布+停止+暂停+自动发布；已发布：不显示本行，删除放在筛选行左侧）——
        self._filter_toolbar_widget = QWidget(filter_card)
        self._filter_toolbar_layout = QHBoxLayout(self._filter_toolbar_widget)
        self._filter_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_toolbar_layout.setSpacing(10)

        btn_delete = PushButton(FluentIcon.DELETE, "删除", filter_card)
        btn_delete.clicked.connect(self._on_delete_records)
        self._btn_delete = btn_delete

        if self._show_publish_queue_toolbar():
            self._filter_toolbar_layout.addWidget(btn_delete)
            self.btn_start_publish = PrimaryPushButton(FluentIcon.PLAY, "发布", filter_card)
            self.btn_start_publish.clicked.connect(self._on_start_publish)
            self._filter_toolbar_layout.addWidget(self.btn_start_publish)

            self.btn_stop_publish = PushButton(FluentIcon.PAUSE, "停止", filter_card)
            self.btn_stop_publish.setEnabled(False)
            self.btn_stop_publish.clicked.connect(self._on_stop_publish)
            self._filter_toolbar_layout.addWidget(self.btn_stop_publish)

            self.btn_pause_publish = PushButton(FluentIcon.GAME, "暂停", filter_card)
            self.btn_pause_publish.setEnabled(False)
            self.btn_pause_publish.clicked.connect(self._on_pause_publish)
            self._filter_toolbar_layout.addWidget(self.btn_pause_publish)

            _ap_row = QWidget(filter_card)
            _apr = QHBoxLayout(_ap_row)
            _apr.setContentsMargins(0, 0, 0, 0)
            _apr.setSpacing(4)
            self.auto_publish_check = CheckBox("自动发布", filter_card)
            _apr.addWidget(self.auto_publish_check)
            
            self.btn_reset_status = PushButton("复位状态", filter_card)
            self.btn_reset_status.clicked.connect(self._on_reset_status_clicked)
            _apr.addWidget(self.btn_reset_status)

            _tip_ap = "勾选后，只要列表中有待发布任务，将自动开始发布"
            apply_instructional_tooltip(
                _tip_ap,
                self.auto_publish_check,
                position=ToolTipPosition.BOTTOM,
            )
            self.auto_publish_check.setChecked(False)
            self._filter_toolbar_layout.addWidget(_ap_row)
            self._filter_toolbar_layout.addStretch(1)
            self._filter_toolbar_widget.setVisible(True)
        else:
            self._filter_toolbar_widget.setVisible(False)

        self._filter_card_outer_layout.addWidget(self._filter_toolbar_widget)

        # —— 筛选：始终单行（与操作行合计两行）；窄屏靠紧凑样式缩窄下拉 ——
        self._filter_one_line_widget = QWidget(filter_card)
        self._filter_one_line_layout = QHBoxLayout(self._filter_one_line_widget)
        self._filter_one_line_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_one_line_layout.setSpacing(10)

        self._filter_extra_widgets: List[QWidget] = []
        for w in self._get_extra_filter_widgets():
            self._filter_extra_widgets.append(w)

        # 有序列表：用于在单行/双行间搬运（标签+下拉成对）
        self._filter_widgets_order: List[QWidget] = []

        # 发布列表页：任务类型筛选（视频 / 图文）
        self.task_type_filter = None
        if getattr(self, "_enable_task_type_filter", False):
            lt = BodyLabel("任务类型", filter_card)
            self.task_type_filter = ComboBox(filter_card)
            self.task_type_filter.addItems(["全部", "视频", "图文"])
            self.task_type_filter.setFixedWidth(95)
            self.task_type_filter.currentTextChanged.connect(self._on_filter_changed)
            self._filter_widgets_order.extend((lt, self.task_type_filter))

        # 待发布页：定时发布 / 立即发布
        self.publish_timing_filter = None
        if getattr(self, "_enable_publish_timing_filter", False):
            lp = BodyLabel("发布方式", filter_card)
            self.publish_timing_filter = ComboBox(filter_card)
            self.publish_timing_filter.addItems(["全部", "定时发布", "立即发布"])
            self.publish_timing_filter.setFixedWidth(95)
            self.publish_timing_filter.currentTextChanged.connect(self._on_filter_changed)
            self._filter_widgets_order.extend((lp, self.publish_timing_filter))

        lplat = BodyLabel("平台", filter_card)
        self.platform_filter = ComboBox(filter_card)
        self.platform_filter.addItems(["全部", "抖音", "快手", "小红书", "视频号"])
        self.platform_filter.setFixedWidth(95)
        self.platform_filter.currentTextChanged.connect(self._on_filter_changed)
        self._filter_widgets_order.extend((lplat, self.platform_filter))

        lac = BodyLabel("账号", filter_card)
        self.account_filter = ComboBox(filter_card)
        self.account_filter.setFixedWidth(150)
        self.account_filter.currentTextChanged.connect(self._on_filter_changed)
        self._filter_widgets_order.extend((lac, self.account_filter))

        lst = BodyLabel("状态", filter_card)
        self.status_filter = ComboBox(filter_card)
        status_items = ["全部"]
        status_map_rev = {"success": "成功", "failed": "失败", "pending": "待发布"}
        for s in self.target_statuses:
            if s in status_map_rev:
                status_items.append(status_map_rev[s])
        self.status_filter.addItems(status_items)
        self.status_filter.setFixedWidth(95)
        self.status_filter.currentTextChanged.connect(self._on_filter_changed)
        self._filter_widgets_order.extend((lst, self.status_filter))

        self._filter_card_outer_layout.addWidget(self._filter_one_line_widget)

        # 兼容旧代码：指向筛选行布局（紧凑模式改间距时用）
        self.filter_layout = self._filter_one_line_layout

        layout.addWidget(filter_card)

        # 根据当前宽度应用筛选行单行/双行与紧凑样式
        self._schedule_base_page_timer(
            "records_sync_filter_layout",
            0,
            self._sync_filter_bar_layout,
        )
        
        # 记录表格
        table_container = CardWidget(self)
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)

        # 顶部加载进度条：异步拉数据时显示，数据就绪后隐藏
        from qfluentwidgets import IndeterminateProgressBar
        self._table_loading_bar = IndeterminateProgressBar(table_container)
        self._table_loading_bar.setFixedHeight(3)
        self._table_loading_bar.setVisible(False)
        table_layout.addWidget(self._table_loading_bar)

        self.records_table = PublishRecordTableView(
            table_container,
            success_page=self.target_statuses == ["success"],
            action_text=self._record_table_action_button_text(),
        )
        # 统一 ::item padding = 2px；完全绕过 Fluent setBorderVisible/setBorderRadius，
        # 避免触发 StyleSheetManager watcher 在懒加载 showEvent / 动画期间崩溃。
        self.records_table.setObjectName("PublishRecordsTable")
        self.records_table.setWordWrap(False)
        # Model/View 表格保持原行选择交互。
        self.records_table.setSelectionBehavior(self.records_table.SelectionBehavior.SelectRows)
        self.records_table.setSelectionMode(self.records_table.SelectionMode.ExtendedSelection)
        self.records_table.setEditTriggers(self.records_table.EditTrigger.NoEditTriggers)

        self.records_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.records_table.customContextMenuRequested.connect(self._on_context_menu)
        self.records_table.cellClicked.connect(self._on_record_table_cell_clicked)
        self.records_table.cellDoubleClicked.connect(self._on_view_record_detail)
        self.records_table.installEventFilter(self)
        self.records_table.selectionModel().selectionChanged.connect(self._on_table_selection_changed)

        table_layout.addWidget(self.records_table)

        # 「加载更多」底栏（仅已发布等分页场景显示）
        self._load_more_bar = QHBoxLayout()
        self._load_more_bar.setContentsMargins(8, 4, 8, 8)
        self._load_more_btn = PushButton(self._load_more_button_text())
        self._load_more_btn.setFixedHeight(32)
        self._load_more_btn.clicked.connect(self._on_load_more_clicked)
        self._load_more_btn.setVisible(False)
        self._load_more_label = QLabel("")
        self._load_more_label.setStyleSheet("color: #888; font-size: 12px;")
        self._load_more_label.setVisible(False)
        self._load_more_bar.addStretch(1)
        self._load_more_bar.addWidget(self._load_more_label)
        self._load_more_bar.addWidget(self._load_more_btn)
        self._load_more_bar.addStretch(1)
        table_layout.addLayout(self._load_more_bar)

        layout.addWidget(table_container)
        
        self.content_layout.addLayout(layout)

        # 异步拉库完成前也保证账号下拉有「全部」，避免空白
        self._rebuild_account_filter_options(None)

    def eventFilter(self, obj, event):
        """表格聚焦时按 Delete 触发软删除（与工具栏删除一致）。"""
        if (
            obj is getattr(self, "records_table", None)
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Delete
        ):
            self._on_delete_records()
            return True
        return super().eventFilter(obj, event)

    def _load_publish_records(self):
        """加载发布记录（在主事件循环中执行，避免 Tortoise 跨事件循环锁错误）"""
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
        from src.ui.utils.async_helper import run_async_task
        import asyncio
        
        service_locator = ServiceLocator()
        if not service_locator.is_registered(PublishRecordRepositoryAsync):
            logger.warning("PublishRecordRepositoryAsync 未注册")
            return
            
        publish_repo = service_locator.get(PublishRecordRepositoryAsync)

        self._load_publish_generation += 1
        load_gen = self._load_publish_generation

        if hasattr(self, '_table_loading_bar'):
            self._table_loading_bar.setVisible(True)

        target_statuses = getattr(self, "target_statuses", None)
        load_limit = getattr(self, "_records_load_limit", 5000)

        async def load_async():
            try:
                records = await publish_repo.find_records(
                    user_id=None,
                    status_in=target_statuses if target_statuses else None,
                    limit=load_limit,
                )
                total = await publish_repo.count_records(
                    user_id=None,
                    status_in=target_statuses if target_statuses else None,
                )
                return records, total
            except Exception as e:
                logger.error(f"查询记录异常: {e}")
                return [], 0

        def on_done(task):
            if load_gen != self._load_publish_generation:
                return
            try:
                records, total = task.result()
                self._has_more_records = len(records) < total
                self._total_record_count = total
                self._on_records_loaded(records)
                self._update_load_more_bar()
            except Exception as e:
                logger.error(f"加载发布记录失败: {e}", exc_info=True)
                self._on_records_loaded([])

        task = run_async_task(load_async)
        task.add_done_callback(on_done)

    def _on_load_more_clicked(self):
        """点击「加载更多」按钮：按 offset 追加下一页，避免重复拉取旧记录。"""
        self._records_controller.load_more()

    def _load_more_button_text(self) -> str:
        return "加载更多历史记录…" if self.target_statuses == ["success"] else "加载更多待发布任务…"

    def _load_more_publish_records(self) -> None:
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
        from src.ui.utils.async_helper import run_async_task

        if getattr(self, "_loading_more_records", False):
            return
        service_locator = ServiceLocator()
        if not service_locator.is_registered(PublishRecordRepositoryAsync):
            logger.warning("PublishRecordRepositoryAsync 未注册")
            return

        repo = service_locator.get(PublishRecordRepositoryAsync)
        target_statuses = getattr(self, "target_statuses", None)
        offset = len(self.publish_records or [])
        step = int(getattr(self, "_records_load_step", 500) or 500)
        self._loading_more_records = True
        btn = getattr(self, "_load_more_btn", None)
        if btn is not None:
            btn.setEnabled(False)
            btn.setText("加载中…")

        self._load_publish_generation += 1
        load_gen = self._load_publish_generation

        async def load_async():
            try:
                records = await repo.find_records(
                    user_id=None,
                    status_in=target_statuses if target_statuses else None,
                    limit=step,
                    offset=offset,
                )
                total = await repo.count_records(
                    user_id=None,
                    status_in=target_statuses if target_statuses else None,
                )
                return records, total
            except Exception as e:
                logger.error("加载更多发布记录异常: %s", e, exc_info=True)
                return [], getattr(self, "_total_record_count", 0)

        def on_done(task):
            self._loading_more_records = False
            if btn is not None:
                btn.setEnabled(True)
                btn.setText(self._load_more_button_text())
            if load_gen != self._load_publish_generation:
                return
            try:
                records, total = task.result()
                self._append_records_loaded(records or [], total)
            except Exception as e:
                logger.error("加载更多发布记录失败: %s", e, exc_info=True)
                self._update_load_more_bar()

        task = run_async_task(load_async)
        task.add_done_callback(on_done)

    def _update_load_more_bar(self):
        """根据已加载/总数更新底部提示条可见性和文案。"""
        btn = getattr(self, "_load_more_btn", None)
        label = getattr(self, "_load_more_label", None)
        if btn is None:
            return
        has_more = getattr(self, "_has_more_records", False)
        total = getattr(self, "_total_record_count", 0)
        loaded = len(self.publish_records)
        btn.setVisible(has_more)
        if label:
            if has_more:
                label.setText(f"当前显示最近 {loaded} 条，共 {total} 条")
                label.setVisible(True)
            else:
                label.setVisible(False)

    def _remove_worker(self, worker):
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def _on_records_loaded(self, records):
        if hasattr(self, '_table_loading_bar'):
            self._table_loading_bar.setVisible(False)
        self._cover_exists_cache = {}
        self.publish_records = records
        self._records_version += 1
        self._last_filter_render_state = None
        self._last_filter_criteria = None
        self._last_rendered_record_ids = []
        records_by_id: Dict[int, Any] = {}
        for r in records:
            try:
                records_by_id[int(r.get("id"))] = r
            except (TypeError, ValueError):
                continue
        self._records_by_id = records_by_id
        self._account_filter_options_cache = None
        self._record_filter_meta_by_id = {
            rid: self._build_record_filter_meta(record)
            for rid, record in records_by_id.items()
        }
        self._data_stale = False
        if hasattr(self, "records_table"):
            self._apply_filters()
            # 数据就绪后预创建右键菜单，消除首次右键的一次性延迟
            self._schedule_base_page_timer(
                "records_prepare_context_menu",
                200,
                self._ensure_records_table_round_menu,
            )
        # 记录数超过 1000 时提示用户清理（每个页面实例只提示一次）
        total = getattr(self, "_total_record_count", 0)
        if total > 1000 and not getattr(self, "_over_limit_warned", False):
            self._over_limit_warned = True
            status_label = "已发布" if self.target_statuses == ["success"] else "待发布"
            InfoBar.warning(
                "记录较多",
                f"当前「{status_label}」共有 {total} 条记录，建议定期清理旧记录以保持软件流畅运行。",
                parent=self,
                duration=6000,
            )

    def _append_records_loaded(self, records: List[dict], total: int) -> None:
        """追加分页加载结果，保留当前表格视觉路径但避免数据库重复取旧页。"""
        existing_ids = set()
        for r in self.publish_records or []:
            try:
                existing_ids.add(int(r.get("id")))
            except (TypeError, ValueError):
                continue
        new_records: List[dict] = []
        for r in records or []:
            try:
                rid = int(r.get("id"))
            except (TypeError, ValueError):
                continue
            if rid in existing_ids:
                continue
            existing_ids.add(rid)
            new_records.append(r)

        if new_records:
            self.publish_records.extend(new_records)
            for r in new_records:
                try:
                    rid = int(r.get("id"))
                except (TypeError, ValueError):
                    continue
                self._records_by_id[rid] = r
                self._record_filter_meta_by_id[rid] = self._build_record_filter_meta(r)
            self._account_filter_options_cache = None
            self._records_version += 1
            self._last_filter_render_state = None
            if hasattr(self, "records_table"):
                self._apply_filters()

        self._total_record_count = int(total or len(self.publish_records))
        self._has_more_records = len(self.publish_records) < self._total_record_count
        self._update_load_more_bar()

    def _ensure_content(self):
        """懒加载创建表格后：若拉库早于建表完成，在此补一次 _apply_filters；否则按 _data_stale 拉库。"""
        first_init = not self._content_initialized
        super()._ensure_content()
        if not first_init:
            return
        if not hasattr(self, "records_table"):
            return
        if self.publish_records:
            self._apply_filters()
        elif self._data_stale:
            self._load_publish_records()

    def _rebuild_account_filter_options(self, prev_key: Any) -> None:
        """根据当前页数据重建账号下拉；prev_key 为恢复选中项的 userData（None 表示「全部」）。"""
        combo = getattr(self, "account_filter", None)
        if combo is None:
            return
        combo.blockSignals(True)
        combo.clear()
        ordered = getattr(self, "_account_filter_options_cache", None)
        if ordered is None:
            key_to_disp: Dict[str, str] = {}
            for r in self.publish_records or []:
                st = r.get("status", "")
                if self.target_statuses and st not in self.target_statuses:
                    continue
                k = _record_account_filter_key(r)
                if k not in key_to_disp:
                    key_to_disp[k] = _record_account_filter_display(r)
            labels = _disambiguate_account_filter_labels(key_to_disp)
            ordered = sorted(labels.items(), key=lambda it: it[1])
            self._account_filter_options_cache = ordered
        combo.addItem("全部", userData=None)
        for k, text in ordered:
            combo.addItem(text, userData=k)
        restore_idx = 0
        if prev_key is not None:
            idx = combo.findData(prev_key)
            if idx >= 0:
                restore_idx = idx
        combo.setCurrentIndex(restore_idx)
        combo.blockSignals(False)

    def _build_record_filter_meta(self, record: dict) -> Dict[str, Any]:
        try:
            rid = int(record.get("id"))
        except (TypeError, ValueError):
            rid = -1
        return {
            "id": rid,
            "status": record.get("status", ""),
            "platform": record.get("platform"),
            "account_key": _record_account_filter_key(record),
            "is_image": _record_is_image_task(record),
            "is_scheduled": _record_is_scheduled_publish(record),
        }

    def _record_filter_meta(self, record: dict) -> Dict[str, Any]:
        try:
            rid = int(record.get("id"))
        except (TypeError, ValueError):
            return self._build_record_filter_meta(record)
        meta = self._record_filter_meta_by_id.get(rid)
        if meta is None:
            meta = self._build_record_filter_meta(record)
            self._record_filter_meta_by_id[rid] = meta
        return meta

    def _filtered_record_ids(self, records: List[dict]) -> List[int]:
        ids: List[int] = []
        for r in records or []:
            try:
                ids.append(int(r.get("id")))
            except (TypeError, ValueError):
                ids.append(-1)
        return ids

    def _table_has_active_sort(self) -> bool:
        table = getattr(self, "records_table", None)
        if table is None:
            return False
        try:
            section = table.horizontalHeader().sortIndicatorSection()
        except Exception:
            return False
        return section is not None and int(section) >= 0


    def _apply_filters(self, *, skip_account_rebuild: bool = False):
        """Apply filters and render records through the Model/View table path."""
        if not hasattr(self, "records_table"):
            return

        platform_filter = self.platform_filter.currentText()
        account_prev_key: Any = None
        af = getattr(self, "account_filter", None)
        if af is not None:
            last_pf = getattr(self, "_last_platform_for_account_reset", None)
            if last_pf is not None and last_pf != platform_filter:
                account_prev_key = None
            else:
                account_prev_key = af.currentData()
            self._last_platform_for_account_reset = platform_filter
            if not skip_account_rebuild:
                self._rebuild_account_filter_options(account_prev_key)

        status_filter = self.status_filter.currentText()
        task_type_filter_text = "全部"
        if getattr(self, "task_type_filter", None) is not None:
            task_type_filter_text = self.task_type_filter.currentText()
        publish_timing_text = "全部"
        if getattr(self, "publish_timing_filter", None) is not None:
            publish_timing_text = self.publish_timing_filter.currentText()

        account_key = af.currentData() if af is not None else None

        from src.utils.platform_names import PLATFORM_NAME_TO_ID as platform_map

        status_map = {"成功": "success", "失败": "failed", "待发布": "pending"}
        filter_criteria = (
            tuple(self.target_statuses or []),
            platform_filter,
            account_key,
            status_filter,
            task_type_filter_text,
            publish_timing_text,
        )
        filter_render_state = (
            *filter_criteria,
            getattr(self, "_records_version", 0),
        )
        if filter_render_state == getattr(self, "_last_filter_render_state", None):
            return

        filtered = []
        for record in self.publish_records:
            meta = self._record_filter_meta(record)
            r_status = meta["status"]
            if self.target_statuses and r_status not in self.target_statuses:
                continue
            if platform_filter != "全部" and meta["platform"] != platform_map.get(platform_filter):
                continue
            if account_key is not None and meta["account_key"] != account_key:
                continue
            if status_filter != "全部" and r_status != status_map.get(status_filter):
                continue
            if task_type_filter_text == "视频" and meta["is_image"]:
                continue
            if task_type_filter_text == "图文" and not meta["is_image"]:
                continue
            if publish_timing_text == "定时发布" and not meta["is_scheduled"]:
                continue
            if publish_timing_text == "立即发布" and meta["is_scheduled"]:
                continue
            filtered.append(record)

        filtered = self._sort_filtered(filtered)
        self._filtered_records = filtered
        filtered_ids = self._filtered_record_ids(filtered)
        self._last_filter_render_state = filter_render_state
        self._last_filter_criteria = filter_criteria
        self._last_rendered_record_ids = filtered_ids

        self._cancel_render_batch_timers()
        self._render_generation += 1

        table = self.records_table
        table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        table.blockSignals(True)
        try:
            table.set_success_page(self.target_statuses == ["success"])
            table.set_action_text(self._record_table_action_button_text())
            table.set_records(filtered)
            self._row_by_record_id = {
                rid: row
                for row, rid in enumerate(filtered_ids)
                if rid is not None and rid >= 0
            }
        finally:
            table.blockSignals(False)
            table.setSortingEnabled(True)
            table.setUpdatesEnabled(True)

    def _on_record_table_cell_clicked(self, row: int, col: int) -> None:
        if col == self.COL_ACTION and self.records_table.cellWidget(row, col) is None:
            self._on_view_record_detail(row, col)

    def _get_extra_filter_widgets(self):
        """子类可重写，在状态筛选右侧插入额外控件（如列表设置按钮）。返回 widget 列表。"""
        return []

    @staticmethod
    def _clear_hbox_layout(lay: QHBoxLayout) -> None:
        while lay.count():
            lay.takeAt(0)

    def _rebuild_filter_row_placement(self) -> None:
        """将全部筛选控件铺到同一行（已发布页无操作栏时删除按钮也在本行最前）。"""
        self._clear_hbox_layout(self._filter_one_line_layout)

        ord_list = self._filter_widgets_order
        if not self._show_publish_queue_toolbar():
            self._filter_one_line_layout.addWidget(self._btn_delete)
        for w in ord_list:
            self._filter_one_line_layout.addWidget(w)
        self._filter_one_line_layout.addStretch(1)
        for ew in self._filter_extra_widgets:
            self._filter_one_line_layout.addWidget(ew)

    def _ensure_filter_row_built(self) -> None:
        if not getattr(self, "_filter_widgets_order", None):
            return
        if self._filter_single_line_built:
            return
        self._filter_single_line_built = True
        self._rebuild_filter_row_placement()

    def _sync_filter_bar_layout(self) -> None:
        """宽度变化：紧凑样式；筛选始终单行。"""
        if not hasattr(self, "_filter_widgets_order") or not self._filter_widgets_order:
            return
        self._ensure_filter_row_built()
        self._apply_filter_compact_style()

    def _sort_filtered(self, filtered):
        """子类可重写，对过滤后的记录排序。默认保持原顺序。"""
        return filtered

    def _on_filter_changed(self):
        try:
            self._filter_timer.start()
        except Exception:
            self._apply_filters()

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._sync_filter_bar_layout()

    # 低于此宽度启用紧凑样式（缩小字体/图标/下拉宽）
    FILTER_BAR_COMPACT_WIDTH = 1000
    # 更窄时进一步缩窄下拉
    FILTER_BAR_ULTRA_COMPACT_WIDTH = 860

    def _apply_filter_compact_style(self) -> None:
        if not hasattr(self, "filter_card") or not self.filter_card:
            return
        w = self.width()
        compact = w < self.FILTER_BAR_COMPACT_WIDTH
        if compact == self._filter_bar_compact:
            return
        self._filter_bar_compact = compact
        if compact:
            self._apply_compact_filter_bar()
        else:
            self._apply_normal_filter_bar()

    def _apply_compact_filter_bar(self):
        """窄窗口：缩小筛选栏字体、图标、下拉宽度与间距，避免堆叠遮挡。"""
        card = self.filter_card
        card.setStyleSheet("font-size: 11px;")
        self._filter_card_outer_layout.setSpacing(6)
        self._filter_card_outer_layout.setContentsMargins(10, 8, 10, 8)
        self._filter_toolbar_layout.setSpacing(6)
        self._filter_one_line_layout.setSpacing(6)
        combo_w = 82 if self.width() < self.FILTER_BAR_ULTRA_COMPACT_WIDTH else 92
        combo_row = [self.platform_filter, self.account_filter, self.status_filter]
        if getattr(self, "publish_timing_filter", None) is not None:
            combo_row.insert(0, self.publish_timing_filter)
        if getattr(self, "task_type_filter", None) is not None:
            combo_row.insert(0, self.task_type_filter)
        for cb in combo_row:
            cb.setFixedWidth(combo_w)
        icon_sz = QSize(16, 16)
        for w in card.findChildren(QWidget):
            if hasattr(w, "setIconSize") and hasattr(w, "icon") and callable(getattr(w, "icon")):
                try:
                    if not w.icon().isNull():
                        w.setIconSize(icon_sz)
                except Exception:
                    pass

    def _apply_normal_filter_bar(self):
        """宽窗口：恢复筛选栏默认字体、图标、下拉宽度与间距（适配 1600 默认窗口不遮挡）。"""
        card = self.filter_card
        card.setStyleSheet("")
        self._filter_card_outer_layout.setSpacing(8)
        self._filter_card_outer_layout.setContentsMargins(12, 10, 12, 10)
        self._filter_toolbar_layout.setSpacing(10)
        self._filter_one_line_layout.setSpacing(10)
        self.platform_filter.setFixedWidth(95)
        self.account_filter.setFixedWidth(150)
        self.status_filter.setFixedWidth(95)
        if getattr(self, "publish_timing_filter", None) is not None:
            self.publish_timing_filter.setFixedWidth(95)
        if getattr(self, "task_type_filter", None) is not None:
            self.task_type_filter.setFixedWidth(95)
        icon_sz = QSize(20, 20)
        for w in card.findChildren(QWidget):
            if hasattr(w, "setIconSize") and hasattr(w, "icon") and callable(getattr(w, "icon")):
                try:
                    if not w.icon().isNull():
                        w.setIconSize(icon_sz)
                except Exception:
                    pass

    def _on_view_record_detail(self, row, col):
        # 从该行第0列获取 UserRole 存储的 ID (因为封面变到了第3列)
        rid_item = self.records_table.item(row, 0)
        if rid_item:
            try:
                rid = int(rid_item.data(Qt.UserRole))
                rec = self._records_by_id.get(rid)
                if rec:
                    self._on_view_detail(rec)
            except (ValueError, TypeError):
                logger.warning(f"无法获取行 {row} 的记录ID")

    def _ensure_records_table_round_menu(self) -> bool:
        try:
            from qfluentwidgets import RoundMenu, Action, FluentIcon as _FI
        except ImportError:
            return False
        from src.ui.components.fluent_context_menu import (
            install_round_menu_close_on_app_inactive,
            is_round_menu_alive,
            round_menu_parent,
        )

        if self._records_table_ctx_menu is not None and is_round_menu_alive(self._records_table_ctx_menu):
            return True
        parent = round_menu_parent(self)
        if parent is None:
            return False
        self._records_table_ctx_menu = RoundMenu(parent=parent)
        self._records_table_ctx_view = Action(_FI.EDIT, "编辑任务", parent)
        self._records_table_ctx_open_file = Action(_FI.DOCUMENT, "打开文件", parent)
        self._records_table_ctx_open_folder = Action(_FI.FOLDER, "打开所在文件夹", parent)
        self._records_table_ctx_readd = Action(_FI.ADD, "重新添加到发布列表", parent)
        self._records_table_ctx_delete = Action(_FI.DELETE, "删除此记录", parent)
        self._records_table_ctx_view.triggered.connect(self._on_records_table_ctx_view_clicked)
        self._records_table_ctx_open_file.triggered.connect(
            self._on_records_table_ctx_open_file_clicked
        )
        self._records_table_ctx_open_folder.triggered.connect(
            self._on_records_table_ctx_open_folder_clicked
        )
        self._records_table_ctx_readd.triggered.connect(self._on_records_table_ctx_readd_clicked)
        self._records_table_ctx_delete.triggered.connect(self._on_records_table_ctx_delete_clicked)
        self._records_table_ctx_menu.addAction(self._records_table_ctx_view)
        self._records_table_ctx_menu.addAction(self._records_table_ctx_open_file)
        self._records_table_ctx_menu.addAction(self._records_table_ctx_open_folder)
        self._records_table_ctx_menu.addSeparator()
        self._records_table_ctx_menu.addAction(self._records_table_ctx_readd)
        self._records_table_ctx_menu.addSeparator()
        self._records_table_ctx_menu.addAction(self._records_table_ctx_delete)
        install_round_menu_close_on_app_inactive(self._records_table_ctx_menu)
        return True

    def _get_record_by_row(self, row: int) -> Optional[Dict]:
        """从表格行号取记录，优先查 id 索引字典（O(1)），兜底走内存线性查找。"""
        rid_item = self.records_table.item(row, 0)
        if not rid_item:
            return None
        try:
            rid = int(rid_item.data(Qt.UserRole))
        except (ValueError, TypeError):
            return None
        return self._records_by_id.get(rid)

    def _on_records_table_ctx_view_clicked(self) -> None:
        rows = getattr(self, "_records_table_ctx_pending_rows", None) or []
        if len(rows) != 1:
            return
        rec = self._get_record_by_row(rows[0])
        if rec:
            self._on_view_detail(rec)

    def _on_records_table_ctx_open_file_clicked(self) -> None:
        rows = getattr(self, "_records_table_ctx_pending_rows", None) or []
        if len(rows) != 1:
            return
        rec = self._get_record_by_row(rows[0])
        if rec:
            open_record_primary_media_file(self, rec)

    def _on_records_table_ctx_open_folder_clicked(self) -> None:
        rows = getattr(self, "_records_table_ctx_pending_rows", None) or []
        if len(rows) != 1:
            return
        rec = self._get_record_by_row(rows[0])
        if rec:
            open_record_media_folder(self, rec)

    def _on_records_table_ctx_readd_clicked(self):
        rows = getattr(self, "_records_table_ctx_pending_rows", None) or []
        self._handle_readd_to_list(rows)

    def _on_records_table_ctx_delete_clicked(self):
        self._on_delete_records()

    def _on_table_selection_changed(self):
        """selectionChanged 信号：维护选区行号缓存，右键菜单直接读缓存，避免每次重扫。"""
        if not hasattr(self, "records_table"):
            return
        sm = self.records_table.selectionModel()
        if sm is None:
            return
        self._selected_rows_cache = sorted({idx.row() for idx in sm.selectedRows()})

    def _on_context_menu(self, pos):
        """记录表格的右键菜单（支持多选：重新添加 / 删除均针对当前选中行）"""
        table = self.records_table
        # 优先读选区缓存（selectionChanged 已维护），比每次 selectedRows() 更快
        selected_rows = self._selected_rows_cache
        if not selected_rows:
            item = table.itemAt(pos)
            if not item:
                return
            sm = table.selectionModel()
            sm.blockSignals(True)
            try:
                table.selectRow(item.row())
            finally:
                sm.blockSignals(False)
            selected_rows = [item.row()]
            self._selected_rows_cache = selected_rows

        n_sel = len(selected_rows)
        self._records_table_ctx_pending_rows = selected_rows

        readd_label = (
            "重新添加到发布列表"
            if n_sel <= 1
            else f"重新添加到发布列表（{n_sel} 条）"
        )
        del_label = (
            "删除此记录"
            if n_sel <= 1
            else f"删除选中记录（{n_sel} 条）"
        )

        if self._ensure_records_table_round_menu():
            single = n_sel == 1
            tip_single = "" if single else "请只选择一条任务时使用"
            self._records_table_ctx_view.setEnabled(single)
            self._records_table_ctx_view.setToolTip(tip_single)
            self._records_table_ctx_open_file.setEnabled(single)
            self._records_table_ctx_open_file.setToolTip(
                "使用系统默认程序打开；视频用默认播放器播放，图片用默认看图软件"
                if single
                else "请只选择一条任务时使用"
            )
            self._records_table_ctx_open_folder.setEnabled(single)
            self._records_table_ctx_open_folder.setToolTip(tip_single)
            self._records_table_ctx_readd.setText(readd_label)
            self._records_table_ctx_delete.setText(del_label)
            self._records_table_ctx_menu.exec(table.viewport().mapToGlobal(pos))
            return

        menu = QMenu(self)
        action_view = None
        action_open_file = None
        action_open_folder = None
        if n_sel == 1:
            action_view = menu.addAction("编辑任务")
            if FLUENT_WIDGETS_AVAILABLE:
                action_view.setIcon(FluentIcon.EDIT.icon())
            action_open_file = menu.addAction("打开文件")
            if FLUENT_WIDGETS_AVAILABLE:
                action_open_file.setIcon(FluentIcon.DOCUMENT.icon())
            action_open_folder = menu.addAction("打开所在文件夹")
            if FLUENT_WIDGETS_AVAILABLE:
                action_open_folder.setIcon(FluentIcon.FOLDER.icon())
            menu.addSeparator()
        action_readd = menu.addAction(readd_label)
        action_delete = menu.addAction(del_label)
        if FLUENT_WIDGETS_AVAILABLE:
            action_readd.setIcon(FluentIcon.ADD.icon())
            action_delete.setIcon(FluentIcon.DELETE.icon())
        action = menu.exec(table.viewport().mapToGlobal(pos))
        if action_view is not None and action == action_view:
            self._on_records_table_ctx_view_clicked()
        elif action_open_file is not None and action == action_open_file:
            self._on_records_table_ctx_open_file_clicked()
        elif action_open_folder is not None and action == action_open_folder:
            self._on_records_table_ctx_open_folder_clicked()
        elif action == action_readd:
            self._handle_readd_to_list(selected_rows)
        elif action == action_delete:
            self._on_delete_records()

    def _handle_readd_to_list(self, rows: List[int]):
        """将选中行的历史记录批量复制为新的待发布任务（每条一条新记录）。"""
        records_to_copy: List[Dict[str, Any]] = []
        for row in rows:
            rid_item = self.records_table.item(row, 0)
            if not rid_item:
                continue
            try:
                rid = int(rid_item.data(Qt.UserRole))
            except (ValueError, TypeError):
                continue
            rec = self._records_by_id.get(rid)
            if rec:
                records_to_copy.append(rec)

        if not records_to_copy:
            InfoBar.warning("无法添加", "未找到可复制的记录，请重试", parent=self)
            return

        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.domain.repositories.publish_record_repository_async import (
            PublishRecordRepositoryAsync,
        )
        from src.ui.utils.async_helper import run_async_task

        repo = ServiceLocator().get(PublishRecordRepositoryAsync)

        async def copy_and_create_batch():
            for rec in records_to_copy:
                sched = rec.get("scheduled_publish_time")
                if sched is not None:
                    sched = format_schedule_time_st_str(sched)
                await repo.create(
                    user_id=rec.get("user_id", 1),
                    platform_username=rec.get("platform_username", ""),
                    platform=rec.get("platform", "douyin"),
                    platform_account_id=rec.get("platform_account_id"),
                    file_path=rec.get("file_path", ""),
                    file_type=rec.get("file_type", "video"),
                    title=rec.get("title", ""),
                    description=rec.get("description", ""),
                    tags=rec.get("tags", ""),
                    cover_path=rec.get("cover_path", ""),
                    poi_info=rec.get("poi_info", ""),
                    micro_app_info=rec.get("micro_app_info", ""),
                    cart_info=rec.get("cart_info", ""),
                    anchor_info=rec.get("anchor_info", ""),
                    privacy_settings=rec.get("privacy_settings", "{}"),
                    scheduled_publish_time=sched,
                )

        def on_done(t):
            try:
                t.result()
                n = len(records_to_copy)
                InfoBar.success(
                    "添加成功",
                    f"已将 {n} 条记录作为新任务加入发布列表",
                    parent=self,
                )
                self._load_publish_records()
                try:
                    win = self.window()
                    if hasattr(win, "_get_or_create_page"):
                        list_page = win._get_or_create_page("publish_list_page")
                        if list_page and hasattr(list_page, "mark_data_stale"):
                            list_page.mark_data_stale()
                except Exception:
                    pass
            except Exception as e:
                InfoBar.error("添加失败", f"重新添加失败: {e}", parent=self)

        task = run_async_task(copy_and_create_batch)
        task.add_done_callback(on_done)

    def _on_view_detail(self, record, *, edit_return_route: str = "publish_records_page"):
        """编辑任务：跳转到单视频或单个图文发布页并回填数据

        edit_return_route: 单任务页点「返回」时回到的发布管理子页路由（待发布/已发布/回收站）。
        """
        try:
            main_window = self.window()
            is_image = _record_is_image_task(record)
            route_key = "image_single_task_creation_page" if is_image else "single_task_creation_page"

            target_page = None
            if hasattr(main_window, "_get_or_create_page"):
                target_page = main_window._get_or_create_page(route_key)
            elif is_image and hasattr(main_window, "image_single_task_creation_page"):
                target_page = main_window.image_single_task_creation_page
            elif hasattr(main_window, "single_task_creation_page"):
                target_page = main_window.single_task_creation_page

            if target_page and hasattr(main_window, 'switchTo'):
                # 回填数据
                if hasattr(target_page, 'set_publish_data'):
                    target_page.set_publish_data(record, edit_return_route=edit_return_route)
                    
                # 跳转和更新导航高亮
                main_window.switchTo(target_page)
                if hasattr(main_window, 'navigationInterface'):
                    main_window.navigationInterface.setCurrentItem(route_key)
            else:
                # Fallback: 使用之前的弹窗
                from src.ui.dialogs.publish_record_detail_dialog import PublishRecordDetailDialog
                PublishRecordDetailDialog(record, self).exec()
        except Exception as e:
            logger.error(f"跳转发布页面失败: {e}")
            # Fallback
            from src.ui.dialogs.publish_record_detail_dialog import PublishRecordDetailDialog
            PublishRecordDetailDialog(record, self).exec()

    def mark_data_stale(self):
        """外部调用此方法标记数据需要刷新（发布完成/删除记录后）"""
        self._data_stale = True

    def showEvent(self, event):
        """页面显示时刷新 user_id；数据加载由 MainWindow.switchTo / 导航或 mark_data_stale 触发，避免与 switchTo 重复拉库。"""
        super().showEvent(event)
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        if hasattr(self, "_filter_widgets_order") and self._filter_widgets_order:
            self._schedule_base_page_timer(
                "records_sync_filter_layout",
                0,
                self._sync_filter_bar_layout,
            )
        # 仅在表格已创建（_setup_content 已执行）后才立即加载，避免时序问题
        if self._data_stale and hasattr(self, 'records_table'):
            self._load_publish_records()

    def _on_export_records(self):
        # 简化版导出，逻辑与之前类似
        from src.ui.utils.fluent_dialogs import show_info
        show_info(self, "导出", "导出功能暂时未迁移，请联系管理员")

    def _on_delete_records(self):
        """删除选中记录"""
        if not hasattr(self, 'records_table'):
            return
            
        selected_rows = list(getattr(self, "_selected_rows_cache", None) or [])
        if not selected_rows:
            selected_rows = [
                index.row()
                for index in self.records_table.selectionModel().selectedRows()
            ]
        if not selected_rows:
            InfoBar.warning("未选择", "请先选择要删除的发布任务", parent=self)
            return
            
        # 获取选中行的ID
        record_ids = []
        for row in selected_rows:
            # ID存储在第0列（平台）的 UserRole 中
            item = self.records_table.item(row, 0)
            if item:
                try:
                    rid = item.data(Qt.UserRole)
                    if rid is not None:
                        record_ids.append(int(rid))
                except (ValueError, TypeError):
                    pass
                    
        if not record_ids:
            return
            
        title = "确认删除"
        content = (
            f"确定将选中的 {len(record_ids)} 条任务移入「任务回收站」吗？"
            " 可在回收站中恢复；回收站内永久删除后无法找回。"
        )
        from src.ui.utils.fluent_dialogs import show_confirm
        if not show_confirm(self.window(), title, content):
            return

        # 软删除（移入回收站）
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
        from src.ui.utils.async_helper import run_async_task

        service_locator = ServiceLocator()
        publish_repo = service_locator.get(PublishRecordRepositoryAsync)

        async def delete_async():
            return await publish_repo.soft_delete_batch(record_ids)
        
        def on_done(t):
            try:
                success = t.result()
                self._on_delete_finished(success)
            except Exception as e:
                logger.error(f"删除发布记录失败: {e}", exc_info=True)
                self._on_delete_finished(False)
            
        task = run_async_task(delete_async)
        task.add_done_callback(on_done)
        
    def _on_delete_finished(self, success):
        if success:
            InfoBar.success("已移入回收站", "选中的任务已放入任务回收站，可随时恢复", parent=self)
            self._load_publish_records()
            notify_publish_recycle_bin_refresh(self)
        else:
            InfoBar.error("删除失败", "移入回收站时发生错误", parent=self)

    def _on_reset_status_clicked(self):
        """复位状态：将当前列表中状态为 failed 的任务，批量修改为 pending"""
        failed_ids = []
        for rec in self.publish_records:
            if rec.get("status") == "failed":
                rid = rec.get("id")
                if rid is not None:
                    try:
                        failed_ids.append(int(rid))
                    except (ValueError, TypeError):
                        pass

        if not failed_ids:
            InfoBar.info("无失败任务", "当前列表中没有状态为出错/失败的发布任务", parent=self)
            return

        title = "确认复位状态"
        content = f"确定将列表中 {len(failed_ids)} 条失败的任务状态修改为「待发布」吗？"
        from src.ui.utils.fluent_dialogs import show_confirm
        if not show_confirm(self.window(), title, content):
            return

        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
        from src.ui.utils.async_helper import run_async_task

        repo = ServiceLocator().get(PublishRecordRepositoryAsync)

        async def update_status_async():
            for rid in failed_ids:
                await repo.update_status(rid, status="pending", error_message="")

        def on_done(t):
            try:
                t.result()
                InfoBar.success("复位成功", f"已成功将 {len(failed_ids)} 条失败任务修改为待发布", parent=self)
                self._load_publish_records()
                try:
                    win = self.window()
                    if hasattr(win, "_get_or_create_page"):
                        list_page = win._get_or_create_page("publish_list_page")
                        if list_page and hasattr(list_page, "mark_data_stale"):
                            list_page.mark_data_stale()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"复位状态失败: {e}", exc_info=True)
                InfoBar.error("复位失败", f"复位状态时发生异常: {e}", parent=self)

        task = run_async_task(update_status_async)
        task.add_done_callback(on_done)

    def _on_start_publish(self):
        """开始发布任务（约定：与文档一致，发布前需登录）"""
        from src.services.auth import CurrentUserService
        curr = CurrentUserService()
        if not curr.is_logged_in():
            InfoBar.warning("请先登录", "开始发布需要先登录软件", parent=self)
            return
        pending_records = [r for r in self.publish_records if r.get('status') == 'pending']
        if not pending_records:
            InfoBar.warning("无任务", "当前没有待发布的任务", parent=self)
            return
        
        # 按创建时间排序，获取第一个任务
        pending_records.sort(key=lambda x: x.get('created_at', ''))
        first_task = pending_records[0]
        
        # 获取任务信息
        platform_username = first_task.get('platform_username', '')
        platform = first_task.get('platform', '')
        
        if not platform_username or not platform:
            InfoBar.error("任务信息不完整", "第一个待发布任务缺少账号或平台信息", parent=self)
            return
        
        logger.info(f"开始发布任务：账号={platform_username}, 平台={platform}")
        
        # 获取账号ID（在主事件循环执行，避免 Tortoise 跨事件循环错误）
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.domain.repositories.account_repository_async import AccountRepositoryAsync
        from src.ui.utils.async_helper import run_async_task
        
        service_locator = ServiceLocator()
        account_repo = service_locator.get(AccountRepositoryAsync)
        
        async def get_account_info():
            """异步获取账号信息"""
            accounts = await account_repo.find_all(user_id=None)
            logger.info(f"查询到 {len(accounts)} 个账号")
            for acc in accounts:
                if acc.get('platform') == platform and acc.get('platform_username') == platform_username:
                    logger.info(f"找到匹配账号: {acc}")
                    return acc
            logger.warning(f"未找到匹配账号: platform_username={platform_username}, platform={platform}")
            return None
        
        def on_account_loaded(account_info):
            """账号信息加载完成"""
            if not account_info:
                InfoBar.error("账号不存在", f"未找到账号: {platform_username} ({platform})", parent=self)
                return
            
            account_id = account_info.get('id')
            
            # 平台URL映射
            platform_urls = {
                'douyin': 'https://creator.douyin.com/',
                'kuaishou': 'https://cp.kuaishou.com/',
                'xiaohongshu': 'https://creator.xiaohongshu.com/',
                'wechat_video': 'https://channels.weixin.qq.com/'
            }
            
            platform_url = platform_urls.get(platform)
            if not platform_url:
                InfoBar.error("不支持的平台", f"平台 {platform} 暂不支持", parent=self)
                return
            
            # 跳转到浏览器页面并打开账号
            try:
                main_window = self.window()
                
                # 获取配置的浏览器方案
                service_locator = ServiceLocator()
                from src.infrastructure.common.config.config_center import ConfigCenter
                config_center = service_locator.get(ConfigCenter)
                app_config = config_center.get_app_config()
                # 仅使用 Playwright 打开本地浏览器
                if hasattr(main_window, 'account_page'):
                    logger.info(f"使用外部浏览器打开账号: {platform_username}")
                    main_window.account_page._open_playwright_browser_for_account(
                        account_id=account_id,
                        platform_username=platform_username,
                        platform=platform,
                        platform_url=platform_url
                    )
                    InfoBar.success(
                        "开始发布",
                        f"正在启动外部浏览器打开 {platform_username} 的创作者中心...",
                        parent=self
                    )
                else:
                    InfoBar.warning("无法跳转", "未找到账号管理页面", parent=self)
            except Exception as e:
                logger.error(f"打开浏览器页面失败: {e}", exc_info=True)
                InfoBar.error("跳转失败", f"打开浏览器页面时发生错误: {str(e)}", parent=self)
        
        def on_done(t):
            try:
                account_info = t.result()
                on_account_loaded(account_info)
            except Exception as e:
                logger.error(f"获取账号信息失败: {e}", exc_info=True)
                InfoBar.error("加载失败", f"获取账号信息失败: {str(e)}", parent=self)
        
        task = run_async_task(get_account_info)
        task.add_done_callback(on_done)
    
    def _on_open_browser(self):
        """浏览器已从导航移除；提示用户到账号管理双击账号打开 Playwright 浏览器"""
        try:
            main_window = self.window()
            if hasattr(main_window, 'navigate_to'):
                main_window.navigate_to("account_page")
            InfoBar.info("打开浏览器", "请在左侧「账号管理」中双击账号，将使用本地 Chrome 打开", parent=self, duration=4000)
        except Exception as e:
            logger.error(f"跳转账号页失败: {e}")
            InfoBar.error("跳转失败", str(e), parent=self)

    def _on_stop_publish(self):
        """停止发布（子类重写）"""
        pass

    def _on_pause_publish(self):
        """暂停/继续发布（子类重写）"""
        pass
    
    # 速度设置已移至发布设置弹窗（list_settings_dialog），通过 get_speed_rate() 读取
