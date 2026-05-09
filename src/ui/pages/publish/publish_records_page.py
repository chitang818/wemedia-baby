"""
已发布任务记录页面（导航：「已发布」）
文件路径：src/ui/pages/publish/publish_records_page.py
功能：显示已成功发布的任务列表；子类 PublishListPage 用于「待发布」。
"""

from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidgetItem,
    QMenu,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QSize, QEvent, QObject, QPoint, QUrl
from PySide6.QtGui import QKeyEvent, QResizeEvent, QDesktopServices
import logging
import os
import json as _json_module

from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, PushButton,
    LineEdit, ComboBox, InfoBar, FluentIcon, IconWidget,
    PrimaryPushButton, CheckBox,
)
FLUENT_WIDGETS_AVAILABLE = True

from ..base_page import BasePage
from src.ui.components.rubber_band_row_table import RubberBandRowSelectTable
from src.ui.utils.fluent_tooltips import (
    ToolTipPosition,
    install_fluent_tool_tip,
    apply_instructional_tooltip,
)
from src.utils.date_utils import format_schedule_time_st_str
from src.ui.pages.publish.poi_info_display import format_poi_table_cell_display
from src.ui.pages.publish.task_field_display import (
    TASK_FIELD_EMPTY_DISPLAY,
    format_cart_info_table_cell,
    task_field_str_or_dash,
)

logger = logging.getLogger(__name__)


class _TableViewportResizeDispatcher(QObject):
    """表格 viewport 级别单一 Resize 事件分发器。

    替代原先「每个 _TableCellCenterHost 各装一个 viewport eventFilter」的方案。
    5000 行时原方案会在 viewport 上累积 5000 个过滤器，每次鼠标/Resize 事件都走
    5000 次 eventFilter 链，严重拖慢 UI。
    此分发器只安装一次，viewport Resize 时批量通知所有已注册的 _TableCellCenterHost。
    """

    def __init__(self, viewport: QWidget):
        super().__init__(viewport)
        self._viewport = viewport
        self._hosts: List["_TableCellCenterHost"] = []
        viewport.installEventFilter(self)

    def register(self, host: "_TableCellCenterHost") -> None:
        self._hosts.append(host)

    def unregister(self, host: "_TableCellCenterHost") -> None:
        try:
            self._hosts.remove(host)
        except ValueError:
            pass

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._viewport and event.type() == QEvent.Type.Resize:
            for host in self._hosts:
                try:
                    host._on_viewport_resize()
                except RuntimeError:
                    pass
        return False


class _TableCellCenterHost(QWidget):
    """将单个子控件按父控件几何矩形摆放（默认水平居中）。

    Fluent TableWidget 末列由 TableItemDelegate 绘制圆角背景时与 QTableWidget
    的 indexWidget 布局存在偏置，嵌套 QLayout + stretch 在部分环境下仍会水平靠右；
    用 resize/show 时根据父尺寸直接 move 子控件，不依赖布局分配剩余空间。

    非最大化/拖拽改窗体大小时，QTableWidget 往往在首帧或视口 resize 之后才落定单元格
    几何；仅处理本控件 resizeEvent 会偶发错过最终尺寸。此处：立即居中 + 0ms 防抖再居中
    一次，并监听表格 viewport 的 Resize 再触发（与行内子控件 resize 互补）。

    竖直方向：indexWidget 偶发高于「行高」，仍用整高做 (h-h_btn)/2 会把按钮算得过低；
    用 min(自身高度, 当前行 rowHeight) 作为有效高度，并减去与 TableItemDelegate.margin(2)
    一致的上边距，使与相邻列文字区视觉中线对齐。

    水平方向：在「中间列 Stretch + 末列 Fixed」的窄表（如发布时间排期弹窗）中，末列
    indexWidget 偶发获得接近整行宽度的几何，此时若仍对子控件水平居中，按钮会落在行中
    央并压在「时间」列文字上。末列操作按钮应传 horizontal=\"right\"，将子控件贴齐宿主右缘。

    viewport 事件监听由 _TableViewportResizeDispatcher 统一管理，不再每行自行
    installEventFilter，避免大数据量下 5000 个过滤器堆积在同一 viewport 上。
    """

    # 与 qfluentwidgets.components.widgets.table_view.TableItemDelegate.margin 一致
    _FLUENT_CELL_V_MARGIN = 2

    # 表格 -> 分发器 弱引用字典，确保同一个 viewport 只装一次过滤器
    _dispatcher_map: Dict = {}

    def __init__(
        self,
        inner: QWidget,
        table,
        row: int,
        col: int,
        *,
        horizontal: str = "center",
        horizontal_margin: int = 4,
    ):
        super().__init__(table)
        self._table = table
        self._row = row
        self._col = col
        self._horizontal = horizontal if horizontal in ("center", "right") else "center"
        self._horizontal_margin = max(0, int(horizontal_margin))
        self._inner = inner
        self._dispatcher: Optional["_TableViewportResizeDispatcher"] = None
        inner.setParent(self)
        inner.show()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.timeout.connect(self._relayout_inner)
        vp = table.viewport() if callable(getattr(table, "viewport", None)) else None
        if vp is not None:
            # 获取或创建共享分发器（每个 viewport 实例只创建一次）
            dispatcher = _TableCellCenterHost._dispatcher_map.get(id(vp))
            if dispatcher is None or not self._is_dispatcher_alive(dispatcher):
                dispatcher = _TableViewportResizeDispatcher(vp)
                _TableCellCenterHost._dispatcher_map[id(vp)] = dispatcher
            dispatcher.register(self)
            self._dispatcher = dispatcher

    @staticmethod
    def _is_dispatcher_alive(obj) -> bool:
        try:
            obj.parent()
            return True
        except RuntimeError:
            return False

    def __del__(self):
        if self._dispatcher is not None:
            try:
                self._dispatcher.unregister(self)
            except Exception:
                pass

    def _on_viewport_resize(self) -> None:
        """由 _TableViewportResizeDispatcher 在 viewport Resize 时调用。"""
        self._schedule_relayout()

    def _effective_row_height(self) -> int:
        tw = self._table
        if tw is None:
            return 0
        vp = tw.viewport()
        if vp is None or not self.isVisible():
            if 0 <= self._row < tw.rowCount():
                return tw.rowHeight(self._row)
            return 0
        try:
            y_vp = self.mapTo(vp, QPoint(self.width() // 2, 1)).y()
            r = tw.rowAt(y_vp)
        except Exception:
            r = -1
        if r < 0 and 0 <= self._row < tw.rowCount():
            return tw.rowHeight(self._row)
        if r < 0:
            return 0
        return tw.rowHeight(r)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_relayout()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_relayout()

    def _schedule_relayout(self) -> None:
        self._relayout_inner()
        self._relayout_timer.stop()
        self._relayout_timer.start(0)

    def _relayout_inner(self) -> None:
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        sz = self._inner.size()
        if sz.width() <= 0 or sz.height() <= 0:
            return
        if self._horizontal == "right":
            x = max(0, w - sz.width() - self._horizontal_margin)
        else:
            x = max(0, (w - sz.width()) // 2)
        rh = self._effective_row_height()
        h_v = min(h, rh) if rh > 0 else h
        # 与 delegate 上下各 inset 后的文字区中线对齐，略向上修正
        y = max(0, (h_v - sz.height()) // 2 - self._FLUENT_CELL_V_MARGIN)
        self._inner.move(x, y)
        self._inner.raise_()


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


def _record_task_type_label(record: dict) -> str:
    """表格「类型」列展示：图文 / 视频。"""
    return "图文" if _record_is_image_task(record) else "视频"


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


def _format_record_timestamp_display(value) -> str:
    """表格日期时间列：支持 datetime 或 ISO 字符串。"""
    if value is None:
        return "—"
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    s = str(value).replace("T", " ")
    return s[:19] if len(s) >= 19 else (s or "—")


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


def _extract_folder_marker(fp: str) -> Optional[str]:
    """从 file_path 中提取文件夹来源路径；若非文件夹来源则返回 None。"""
    for part in fp.split(","):
        part = part.strip()
        if part.startswith(_FOLDER_MARKER_PREFIX):
            return part[len(_FOLDER_MARKER_PREFIX):]
    return None


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


def _short_path_after_account_library(full_dir: str) -> str:
    """仅用于表格展示：只保留路径中「\\账号库\\」之后的片段（如 账号组_xxx\\视频\\未发布）。"""
    if not full_dir:
        return ""
    p = os.path.normpath(full_dir).replace("/", "\\")
    needle = "\\账号库\\"
    pos = p.find(needle)
    if pos >= 0:
        return p[pos + len(needle) :]
    return p


def _record_media_folder_cell(record: dict) -> Tuple[str, str]:
    """表格「文件位置」列：(展示文案, 悬停提示全文)。单元格只显示账号库之后的路径；悬停仍为完整绝对路径。"""
    fp = (record.get("file_path") or "").strip()
    if _file_path_is_deleted(fp):
        return "已删除", ""
    full = _record_media_folder_path(record)
    if not full:
        return "—", ""
    short = _short_path_after_account_library(full)
    display = short if short else full
    return display, full


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

        self.target_statuses = target_statuses if target_statuses is not None else ["success"]
        # 已发布页（仅 success）首次只加载最近 500 条以提升响应；待发布页保持全量加载
        self._records_load_limit: int = 500 if self.target_statuses == ["success"] else 5000
        self._records_load_step: int = 500  # 每次「加载更多」增加的条数
        self._has_more_records: bool = False  # 是否还有更多记录可加载
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
        # id→record 索引字典：避免 next(r for r in publish_records if r.get('id')==rid) 的 O(n) 扫描
        self._records_by_id: Dict[int, Any] = {}

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
        QTimer.singleShot(0, self._sync_filter_bar_layout)
        
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

        self.records_table = RubberBandRowSelectTable(table_container)
        # 统一 ::item padding = 2px；完全绕过 Fluent setBorderVisible/setBorderRadius，
        # 避免触发 StyleSheetManager watcher 在懒加载 showEvent / 动画期间崩溃。
        self.records_table.setObjectName("PublishRecordsTable")
        self.records_table.setWordWrap(False)
        # RubberBandRowSelectTable 自带 NoDragDrop；显式设置选择模式
        self.records_table.setSelectionBehavior(self.records_table.SelectionBehavior.SelectRows)
        self.records_table.setSelectionMode(self.records_table.SelectionMode.ExtendedSelection)
        self.records_table.setEditTriggers(self.records_table.EditTrigger.NoEditTriggers)

        self.records_table.setColumnCount(19)
        first_time_header = (
            "发布时间"
            if self.target_statuses == ["success"]
            else "创建时间"
        )
        self.records_table.setHorizontalHeaderLabels([
            first_time_header,
            "类型",
            "平台",
            "账号组",
            "任务源",
            "平台昵称",
            "文件/文件夹",
            "封面",
            "作品标题",
            "作品描述",
            "定时时间",
            "声明原创",
            "音乐",
            "购物车",
            "团购",
            "位置",
            "状态",
            "文件位置",
            "操作",
        ])

        # 各列均可拖拽调整宽度；操作列固定
        _rh = self.records_table.horizontalHeader()
        from PySide6.QtWidgets import QHeaderView as _QHV
        for _c in range(19):
            _rh.setSectionResizeMode(_c, _QHV.ResizeMode.Interactive)
        _rh.setSectionResizeMode(self.COL_ACTION, _QHV.ResizeMode.Fixed)
        _rh.setMinimumSectionSize(52)
        _rh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        # 列宽设置（适配 1400+ 内容区）
        self.records_table.setColumnWidth(self.COL_CREATE_TIME, 140)    # 创建时间 / 发布时间
        self.records_table.setColumnWidth(self.COL_TYPE, 52)            # 类型  图文/视频
        self.records_table.setColumnWidth(self.COL_PLATFORM, 72)        # 平台      抖音/快手等
        self.records_table.setColumnWidth(self.COL_ACCOUNT_GROUP, 88)   # 账号组
        self.records_table.setColumnWidth(self.COL_TASK_SOURCE, 72)     # 任务源    账号/账号组
        self.records_table.setColumnWidth(self.COL_ACCOUNT_NAME, 120)   # 平台昵称
        self.records_table.setColumnWidth(self.COL_FILE, 140)           # 文件      省略号截断
        self.records_table.setColumnWidth(self.COL_COVER, 65)           # 封面      首帧/本地
        self.records_table.setColumnWidth(self.COL_TITLE, 100)          # 作品标题  省略号截断
        self.records_table.setColumnWidth(self.COL_DESCRIPTION, 140)    # 作品描述  省略号截断
        self.records_table.setColumnWidth(self.COL_SCHEDULED_TIME, 120) # 定时时间  立即发布/排期
        self.records_table.setColumnWidth(self.COL_ORIGINAL, 70)        # 声明原创  ✅/—
        self.records_table.setColumnWidth(self.COL_MUSIC, 100)          # 音乐      歌曲名/—
        self.records_table.setColumnWidth(self.COL_CART, 100)           # 购物车    短标题/✅/—
        self.records_table.setColumnWidth(self.COL_GROUP_BUY, 55)       # 团购      ✅/—
        self.records_table.setColumnWidth(self.COL_LOCATION, 88)        # 位置      POI
        self.records_table.setColumnWidth(self.COL_STATUS, 78)          # 状态      ✅成功等
        self.records_table.setColumnWidth(self.COL_FILE_LOCATION, 200)  # 文件位置  媒体所在文件夹
        self.records_table.setColumnWidth(self.COL_ACTION, 76)          # 操作列「编辑」按钮（固定略宽避免裁切）
        self.records_table.verticalHeader().setDefaultSectionSize(42)

        self.records_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.records_table.customContextMenuRequested.connect(self._on_context_menu)
        self.records_table.cellDoubleClicked.connect(self._on_view_record_detail)
        self.records_table.installEventFilter(self)
        self.records_table.selectionModel().selectionChanged.connect(self._on_table_selection_changed)

        table_layout.addWidget(self.records_table)

        # 「加载更多」底栏（仅已发布等分页场景显示）
        self._load_more_bar = QHBoxLayout()
        self._load_more_bar.setContentsMargins(8, 4, 8, 8)
        self._load_more_btn = PushButton("加载更多历史记录…")
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
        """点击「加载更多」按钮：增加 limit 并重新加载。"""
        self._records_load_limit += self._records_load_step
        self._load_publish_records()

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
        self._records_by_id = {r.get("id"): r for r in records if r.get("id") is not None}
        self._data_stale = False
        if hasattr(self, "records_table"):
            self._apply_filters()
            # 数据就绪后预创建右键菜单，消除首次右键的一次性延迟
            QTimer.singleShot(200, self._ensure_records_table_round_menu)
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
        key_to_disp: Dict[str, str] = {}
        for r in self.publish_records or []:
            st = r.get("status", "")
            if self.target_statuses and st not in self.target_statuses:
                continue
            k = _record_account_filter_key(r)
            if k not in key_to_disp:
                key_to_disp[k] = _record_account_filter_display(r)
        labels = _disambiguate_account_filter_labels(key_to_disp)
        ordered: List[Tuple[str, str]] = sorted(labels.items(), key=lambda it: it[1])
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

    def _apply_filters(self, *, skip_account_rebuild: bool = False):
        """应用筛选。

        skip_account_rebuild=True 时跳过账号下拉重建，适用于发布循环中仅更新状态的刷新，
        避免每次都对全量 publish_records 扫描重建下拉选项。
        大数据量时使用分批渲染，每批 150 行后让出事件循环，避免 UI 冻结。
        """
        if not hasattr(self, 'records_table'):
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
        from src.utils.platform_names import get_platform_display_name
        status_map = {"成功": "success", "失败": "failed", "待发布": "pending"}
        
        filtered = []
        for r in self.publish_records:
            r_status = r.get('status', '')
            if self.target_statuses and r_status not in self.target_statuses:
                continue
                
            if platform_filter != "全部" and r.get('platform') != platform_map.get(platform_filter):
                continue
            if account_key is not None and _record_account_filter_key(r) != account_key:
                continue
            if status_filter != "全部" and r_status != status_map.get(status_filter):
                continue
            if task_type_filter_text == "视频" and _record_is_image_task(r):
                continue
            if task_type_filter_text == "图文" and not _record_is_image_task(r):
                continue
            if publish_timing_text == "定时发布" and not _record_is_scheduled_publish(r):
                continue
            if publish_timing_text == "立即发布" and _record_is_scheduled_publish(r):
                continue
            filtered.append(r)
        
        filtered = self._sort_filtered(filtered)
        self._filtered_records = filtered  # 供子类（如发布列表）做任务统计等

        # 递增渲染代次，取消正在进行中的旧批次
        self._render_generation += 1
        render_gen = self._render_generation

        table = self.records_table
        table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        table.blockSignals(True)
        table.setRowCount(0)
        table.setRowCount(len(filtered))
        table.blockSignals(False)

        _cell_center = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        _cell_left_v = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        is_success_page = self.target_statuses == ["success"]
        btn_text = self._record_table_action_button_text()

        # ---------- 分批渲染（文本 + 按钮）----------
        # 小数据量（≤200）同步填充文本保证即时可见；大数据量分批避免卡主线程
        _TEXT_BATCH = 200
        _BTN_BATCH = 15
        total = len(filtered)

        def _render_text_batch(start: int) -> None:
            if render_gen != self._render_generation:
                return
            end = min(start + _TEXT_BATCH, total)
            table.blockSignals(True)
            for row in range(start, end):
                self._fill_table_row_text(
                    row, filtered[row], is_success_page,
                    get_platform_display_name, _cell_center, _cell_left_v,
                )
            table.blockSignals(False)
            if end < total:
                QTimer.singleShot(0, lambda: _render_text_batch(end))
            else:
                table.setSortingEnabled(True)
                table.setUpdatesEnabled(True)
                QTimer.singleShot(0, lambda: _render_btn_batch(0))

        def _render_btn_batch(start: int) -> None:
            if render_gen != self._render_generation:
                return
            end = min(start + _BTN_BATCH, total)
            for row in range(start, end):
                self._fill_table_row_btn(row, filtered[row], btn_text)
            if end < total:
                QTimer.singleShot(0, lambda: _render_btn_batch(end))

        if total <= _TEXT_BATCH:
            table.blockSignals(True)
            for row in range(total):
                self._fill_table_row_text(
                    row, filtered[row], is_success_page,
                    get_platform_display_name, _cell_center, _cell_left_v,
                )
            table.blockSignals(False)
            table.setSortingEnabled(True)
            table.setUpdatesEnabled(True)
            QTimer.singleShot(0, lambda: _render_btn_batch(0))
        else:
            _render_text_batch(0)

    def _fill_table_row_text(
        self,
        row: int,
        r: dict,
        is_success_page: bool,
        get_platform_display_name,
        _cell_center,
        _cell_left_v,
    ) -> None:
        """填充单行纯文本单元格（不含操作按钮，速度快）。"""
        table = self.records_table

        ts = (r.get("updated_at") or r.get("created_at")) if is_success_page else r.get("created_at")
        item_created = QTableWidgetItem(_format_record_timestamp_display(ts))
        item_created.setData(Qt.UserRole, r.get('id'))
        item_created.setTextAlignment(_cell_center)
        table.setItem(row, 0, item_created)

        item_type = QTableWidgetItem(_record_task_type_label(r))
        item_type.setTextAlignment(_cell_center)
        table.setItem(row, 1, item_type)

        p_display = task_field_str_or_dash(get_platform_display_name(r.get("platform", "") or ""))
        item_plat = QTableWidgetItem(p_display)
        item_plat.setTextAlignment(_cell_center)
        table.setItem(row, 2, item_plat)

        grp = (r.get("account_group_name") or "").strip()
        item_grp = QTableWidgetItem(grp or TASK_FIELD_EMPTY_DISPLAY)
        item_grp.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_ACCOUNT_GROUP, item_grp)

        _ts_val = r.get("task_source") or ""
        _ts_display = "账号组" if _ts_val == "group" else ("账号" if _ts_val == "account" else TASK_FIELD_EMPTY_DISPLAY)
        item_src = QTableWidgetItem(_ts_display)
        item_src.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_TASK_SOURCE, item_src)

        item_name = QTableWidgetItem(task_field_str_or_dash(r.get("platform_username")))
        item_name.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_ACCOUNT_NAME, item_name)

        _fp_raw = r.get("file_path", "") or ""
        if _file_path_is_deleted(_fp_raw):
            fname = "已删除"
        elif _fp_raw:
            _folder = _extract_folder_marker(_fp_raw)
            if _folder:
                fname = os.path.basename(_folder.rstrip("/\\")) or os.path.basename(_folder)
            else:
                fname = os.path.basename(_fp_raw.split(",")[0].strip())
        else:
            fname = ""
        item_file = QTableWidgetItem(task_field_str_or_dash(fname))
        item_file.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_FILE, item_file)

        cover_path = r.get('cover_path', '')
        if cover_path:
            cache = getattr(self, '_cover_exists_cache', None)
            if cache is None:
                cache = self._cover_exists_cache = {}
            if cover_path not in cache:
                cache[cover_path] = os.path.exists(cover_path)
            cover_text = "本地封面" if cache[cover_path] else "首帧封面"
        else:
            cover_text = "首帧封面"
        item_cover = QTableWidgetItem(cover_text)
        item_cover.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_COVER, item_cover)

        item_title = QTableWidgetItem(task_field_str_or_dash(r.get("title")))
        item_title.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_TITLE, item_title)

        item_desc = QTableWidgetItem(task_field_str_or_dash(r.get("description")))
        item_desc.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_DESCRIPTION, item_desc)

        time_display = format_schedule_time_st_str(r.get('scheduled_publish_time')) or "立即发布"
        item_sched = QTableWidgetItem(time_display)
        item_sched.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_SCHEDULED_TIME, item_sched)

        platform_id = (r.get("platform") or "").strip()
        is_original = False
        if platform_id == 'wechat_video':
            try:
                ps_raw = r.get('privacy_settings') or '{}'
                ps = _json_module.loads(ps_raw) if isinstance(ps_raw, str) else (ps_raw or {})
                is_original = bool(ps.get('is_original', False))
            except Exception:
                pass
        item_orig = QTableWidgetItem("✅ 原创" if is_original else TASK_FIELD_EMPTY_DISPLAY)
        item_orig.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_ORIGINAL, item_orig)

        if _record_is_image_task(r):
            music_info_raw = (r.get('music_info') or '').strip()
            music_display = TASK_FIELD_EMPTY_DISPLAY
            if music_info_raw:
                try:
                    _mi = _json_module.loads(music_info_raw)
                    if _mi.get('music_type') == 'random':
                        music_display = "随机"
                    else:
                        music_display = _mi.get('music_name') or _mi.get('name') or _mi.get('title') or "✅"
                except Exception:
                    music_display = "✅"
        else:
            music_display = TASK_FIELD_EMPTY_DISPLAY
        item_music = QTableWidgetItem(music_display)
        item_music.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_MUSIC, item_music)

        goods_display = format_cart_info_table_cell((r.get('cart_info') or '').strip())
        item_cart = QTableWidgetItem(goods_display)
        item_cart.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_CART, item_cart)

        anchor_display = "✅" if (r.get('anchor_info') or '').strip() else TASK_FIELD_EMPTY_DISPLAY
        item_anchor = QTableWidgetItem(anchor_display)
        item_anchor.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_GROUP_BUY, item_anchor)

        poi_display = format_poi_table_cell_display(
            r.get("poi_info"),
            platform=platform_id,
            wechat_empty_location_open_picker=r.get("wechat_empty_location_open_picker"),
        )
        item_poi = QTableWidgetItem(poi_display)
        item_poi.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_LOCATION, item_poi)

        status = (r.get("status") or "").strip()
        s_display = {
            "success": "✅ 成功",
            "failed": "❌ 失败",
            "pending": "⏳ 待发布",
        }.get(status, status) if status else TASK_FIELD_EMPTY_DISPLAY
        item_status = QTableWidgetItem(s_display)
        item_status.setTextAlignment(_cell_center)
        table.setItem(row, self.COL_STATUS, item_status)

        folder_text, folder_tip = _record_media_folder_cell(r)
        item_folder = QTableWidgetItem(folder_text)
        item_folder.setTextAlignment(_cell_left_v)
        if folder_tip:
            item_folder.setToolTip(folder_tip)
        table.setItem(row, self.COL_FILE_LOCATION, item_folder)

    def _fill_table_row_btn(self, row: int, r: dict, btn_text: str) -> None:
        """延后创建操作按钮（QWidget 开销大，单独分批执行）。"""
        table = self.records_table
        btn_view = PushButton(btn_text, None)
        btn_view.setFixedSize(56, 30)
        btn_view.clicked.connect(lambda checked, rec=r: self._on_view_detail(rec))
        table.setCellWidget(
            row, self.COL_ACTION,
            _TableCellCenterHost(btn_view, table, row, self.COL_ACTION)
        )

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
                rec = next((r for r in self.publish_records if r.get('id') == rid), None)
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
        return self._records_by_id.get(rid) or next(
            (r for r in self.publish_records if r.get("id") == rid), None
        )

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
            rec = self._records_by_id.get(rid) or next(
                (r for r in self.publish_records if r.get("id") == rid), None
            )
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
            QTimer.singleShot(0, self._sync_filter_bar_layout)
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
            
        selected_rows = self.records_table.selectionModel().selectedRows()
        if not selected_rows:
            InfoBar.warning("未选择", "请先选择要删除的发布任务", parent=self)
            return
            
        # 获取选中行的ID
        record_ids = []
        for index in selected_rows:
            # ID存储在第0列（平台）的 UserRole 中
            item = self.records_table.item(index.row(), 0)
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

