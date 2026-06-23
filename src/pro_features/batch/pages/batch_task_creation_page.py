"""
批量视频发布任务创建页面
文件路径：src/pro_features/batch/pages/batch_task_creation_page.py

功能：多账号 × 多视频 × 多时间，批量生成待发布任务并写入发布列表。
      不在此页执行平台上传；执行发布在「发布管理 → 发布列表」。
"""
from typing import Any, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.pro_features.batch.services.material_auto_matcher import MaterialAutoMatcher as _MaterialAutoMatcherType
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QFileDialog, QHeaderView, QAbstractItemView,
    QTableWidgetItem, QDialog, QSizePolicy,
)
from PySide6.QtCore import (
    Qt,
    QDateTime,
    QEasingCurve,
    QTimer,
    QSize,
    QUrl,
)
from PySide6.QtGui import QDesktopServices, QFontMetrics, QShortcut, QKeySequence
import logging
import os
import json
import asyncio

from qfluentwidgets import (
    CardWidget, BodyLabel, PrimaryPushButton,
    PushButton, FluentIcon,
    ComboBox, InfoBar, InfoBarPosition, CheckBox,
    CaptionLabel,
    SmoothScrollArea,
    SubtitleLabel,
)

from src.ui.components.rubber_band_row_table import RubberBandRowSelectTable
from src.ui.pages.base_page import BasePage
from src.ui.components.base_dialog import AppMessageBoxBase
from src.ui.utils.task_tracking import TrackedTaskMixin
from src.pro_features.batch.menus import BatchPreviewContextMenu
from src.ui.pages.publish.batch_task_creation_actions import (
    batch_create_publish_records,
)
from src.ui.pages.publish.batch_preview_exclusion import PreviewExclusionSet
from src.ui.pages.publish.batch_preview_builder import build_preview_tasks
from src.ui.pages.publish.batch_publish_builder import build_publish_tasks_for_batch
from src.ui.pages.publish.poi_info_display import format_poi_table_cell_display
from src.ui.pages.publish.task_field_display import (
    TASK_FIELD_EMPTY_DISPLAY,
    format_cart_info_table_cell,
    task_field_str_or_dash,
)
from src.utils.date_utils import format_schedule_time_st_str
from src.utils.platform_names import platform_id_is_wechat_video
from src.domain.publish.promotion_limits import YELLOW_CART_SHORT_TITLE_MAX_LEN
from src.pro_features.batch.copywriting_helpers import (
    parse_topic_list,
    extract_work_id_from_filename,
    merge_title_desc_from_copywriting_item,
)
from src.pro_features.batch.batch_auto_match_prefs import (
    load_auto_match_pref,
    save_auto_match_pref,
)
from src.pro_features.batch.batch_location_prefs import (
    load_batch_location_prefs,
    save_batch_location_prefs,
)
from src.pro_features.batch.publish_description_mapping import (
    combo_index_from_flags,
    flags_from_combo_index,
)
from src.pro_features.batch.pages.batch_task_creation_controller import BatchTaskCreationController
from src.infrastructure.common.media_assign_strategy import (
    AssignStrategy,
    load_assign_strategy,
    distribute_items_to_targets,
)
from src.pro_features.batch.dialogs.add_batch_media_dialog import (
    AddBatchMediaChoiceDialog,
    LibraryMediaSelectDialog,
)
from qasync import asyncSlot

from src.domain.publish.work_declaration import (
    KEY_DOUYIN,
    KEY_DOUYIN_AUTO,
    KEY_KUAISHOU,
    KEY_KUAISHOU_AUTO,
    KEY_XHS_CONTENT_ATTR,
    KEY_XHS_CONTENT_ATTR_AUTO,
    KEY_XHS_ORIGINAL,
    ellipsize,
    format_work_declaration_preview_cell,
    format_work_declaration_table_cell,
    normalize_douyin_value,
    normalize_kuaishou_value,
    normalize_xhs_content_attr,
    parse_privacy_settings_dict,
)
from src.ui.publish.work_description import (
    load_persisted_declare_original,
    load_persisted_publish_description_prefs,
    load_persisted_work_declaration,
    save_persisted_declare_original,
    save_persisted_publish_description_prefs,
    save_persisted_work_declaration,
)
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.services.material.media_library_stats_cache import get_media_library_stats_cache
from src.services.material.media_library_stats_service import get_media_library_stats_service

logger = logging.getLogger(__name__)


SUPPORTED_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.flv', '.mkv', '.wmv', '.m4v', '.webm'}
SUPPORTED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
FOLDER_MARKER_PREFIX = "__FOLDER__:"
TITLE_MAX_LENGTH = 30
# 预览表行高：低于发布列表 42px，单行文字 + 略紧内边距，同屏多显示几行
BATCH_PREVIEW_TABLE_ROW_HEIGHT = 30
# 顶部工具栏主按钮/清空按钮统一宽度（与单视频任务页 BUTTON_FIXED_WIDTH 一致，避免按内容宽窄不一）

def _preview_table_cell_alignment(_column: int) -> Qt.AlignmentFlag:
    """任务预览表单元格对齐：与其它业务表格一致，统一居中。"""
    return Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter


class BatchTaskCreationPage(TrackedTaskMixin, BasePage):
    """批量视频任务创建页面"""

    _lazy_content = True
    _enable_show_fade = False

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        media_type: str = "video",
        page_title: Optional[str] = None,
    ):
        self._media_type = "image" if media_type == "image" else "video"
        self._media_label = "图片" if self._media_type == "image" else "视频"
        self._task_label = "图文" if self._media_type == "image" else "视频"
        self._media_library_label = "图文库" if self._media_type == "image" else "视频库"
        self._file_type = "image" if self._media_type == "image" else "video"
        self._supported_media_extensions = (
            SUPPORTED_IMAGE_EXTENSIONS
            if self._media_type == "image"
            else SUPPORTED_VIDEO_EXTENSIONS
        )
        super().__init__(title=page_title or f"批量{self._task_label}任务", parent=parent)  # type: ignore
        from src.services.auth import CurrentUserService
        self._current_user_svc = CurrentUserService()
        self.user_id = self._current_user_svc.get_user_id_or_default(1)

        self.account_manager = None
        self.group_service = None
        self.available_accounts: List[dict] = []
        self.selected_accounts: List[dict] = []
        self.video_list: List[dict] = []
        self.time_slots: List[Optional[str]] = []
        self._batch_controller = BatchTaskCreationController(self)

        self._lazy_video_auto_matcher: Optional["_MaterialAutoMatcherType"] = None
        self._cached_groups: List[dict] = []
        self._library_assign_strategy: AssignStrategy = load_assign_strategy("batch")
        self.cover_type = "first_frame"
        self.cover_path = ""

        # 作品描述配置属性
        self.same_title_text = ""
        self.same_desc_text = ""
        self.apply_description_to_all_tasks: bool = True
        self.use_library_title: bool = False
        self.use_library_desc: bool = False
        # 自动匹配配置（需在任何导入/重算路径前具备默认值）
        self.auto_match_enabled: bool = False
        self.match_mode: str = "standard"
        self.random_category_id = None
        self.copywriting_assign_strategy: str = AssignStrategy.ROUND_ROBIN.value

        _desc_prefs = load_persisted_publish_description_prefs()
        if _desc_prefs:
            self.same_title_text = _desc_prefs.get("title", "") or ""
            self.same_desc_text = _desc_prefs.get("desc", "") or ""
            self.apply_description_to_all_tasks = bool(
                _desc_prefs.get("apply_to_all_tasks", True)
            )
            self.use_library_title = bool(_desc_prefs.get("use_library_title", False))
            self.use_library_desc = bool(_desc_prefs.get("use_library_desc", False))
            self.auto_match_enabled = bool(_desc_prefs.get("auto_match_enabled", False))
            self.match_mode = str(_desc_prefs.get("match_mode", "standard") or "standard")
            self.random_category_id = _desc_prefs.get("random_category_id")
            self.copywriting_assign_strategy = str(
                _desc_prefs.get("copywriting_assign_strategy", AssignStrategy.ROUND_ROBIN.value)
                or AssignStrategy.ROUND_ROBIN.value
            )

        # 扩展信息配置属性（位置：按钮+弹窗分层二选一，见 BatchLocationDialog；偏好见配置中心 batch_publish.location）
        _loc_poi, _loc_wx = load_batch_location_prefs()
        self.location_text = _loc_poi
        self._batch_wechat_empty_location_open_picker: bool = _loc_wx
        self.goods_text = ""
        self.anchor_text = ""
        self.music_info = '{"music_type": "random"}' if self._media_type == "image" else ""
        self.declare_original_checked = load_persisted_declare_original()
        _wdecl = load_persisted_work_declaration()
        self.douyin_work_declaration = normalize_douyin_value(_wdecl.get(KEY_DOUYIN))
        self.kuaishou_work_declaration = normalize_kuaishou_value(_wdecl.get(KEY_KUAISHOU))
        self.douyin_work_declaration_auto = bool(_wdecl.get(KEY_DOUYIN_AUTO, False))
        self.kuaishou_work_declaration_auto = bool(_wdecl.get(KEY_KUAISHOU_AUTO, False))
        self.xiaohongshu_is_original = bool(_wdecl.get(KEY_XHS_ORIGINAL, False))
        self.xiaohongshu_content_attribute = normalize_xhs_content_attr(
            _wdecl.get(KEY_XHS_CONTENT_ATTR)
        )
        self.xiaohongshu_content_attribute_auto = bool(
            _wdecl.get(KEY_XHS_CONTENT_ATTR_AUTO, False)
        )

        self._preview_tasks: List[dict] = []
        self._preview_exclusion = PreviewExclusionSet()
        self._preview_delete_row_specs: List[dict] = []
        self._preview_row_video_path_hint: List[Optional[str]] = []
        self._preview_refresh_timer: Optional[QTimer] = None
        self._preview_refresh_skip_material_stats_reminder: bool = False
        self._init_task_tracking()
        self._material_stats_token: int = 0
        self._material_account_row_counter: int = 0
        self._media_stats_cache = get_media_library_stats_cache()
        try:
            self._media_stats_cache.statsUpdated.connect(self._on_media_stats_updated)
        except Exception:
            pass
        self._init_services()

    def _get_video_auto_matcher(self) -> "_MaterialAutoMatcherType":
        """首次需要自动匹配/预览时再创建，减轻页面 __init__ 与首次 import 链上的同步开销。"""
        if self._lazy_video_auto_matcher is None:
            from src.pro_features.batch.services.material_auto_matcher import MaterialAutoMatcher

            self._lazy_video_auto_matcher = MaterialAutoMatcher(media_type=self._media_type)
        return self._lazy_video_auto_matcher

    def _material_display_name_for_path(self, file_path: str) -> str:
        """图文文件夹任务显示文件夹名；其它任务显示文件名。"""
        raw = (file_path or "").strip()
        if self._media_type == "image":
            for part in raw.split(","):
                part = part.strip()
                if part.startswith(FOLDER_MARKER_PREFIX):
                    folder = part[len(FOLDER_MARKER_PREFIX):].strip()
                    if folder:
                        return os.path.basename(folder)
        first = raw.split(",", 1)[0].strip()
        return os.path.basename(first)

    def _media_paths_from_folder(self, folder: str) -> List[str]:
        """按单图文页规则读取文件夹内图片（一层），返回排序后的绝对路径。"""
        paths: List[str] = []
        try:
            for fn in sorted(os.listdir(folder)):
                fp = os.path.join(folder, fn)
                if not os.path.isfile(fp):
                    continue
                if os.path.splitext(fn)[1].lower() in SUPPORTED_IMAGE_EXTENSIONS:
                    paths.append(os.path.abspath(fp))
        except OSError:
            return []
        return paths

    def _image_folder_composite_path(self, folder: str) -> str:
        images = self._media_paths_from_folder(folder)
        return ",".join([f"{FOLDER_MARKER_PREFIX}{os.path.abspath(folder)}", *images])

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self.available_accounts:
            self._track_task(asyncio.create_task(self._load_accounts()))
        # 从发布列表等页面返回时重新拉取占用数，避免列表已删任务仍显示旧「已用」
        if hasattr(self, "_material_stats_rows_layout"):
            self._refresh_task_status_reminder()

    def _ensure_content(self):
        """懒加载建 UI 后，与可能已提前完成的 _load_accounts 对齐（避免 setEnabled 在控件创建前被跳过）。"""
        first_init = not self._content_initialized
        super()._ensure_content()
        if not first_init:
            return
        if hasattr(self, "btn_select_account"):
            self.btn_select_account.setEnabled(bool(self.available_accounts))

    def _track_task(self, task: asyncio.Task) -> asyncio.Task:
        return super()._track_task(task)

    def _on_task_done(self, task: asyncio.Task):
        super()._on_task_done(task)

    def closeEvent(self, event):
        self._cancel_tracked_tasks()
        super().closeEvent(event)

    def shutdown(self):
        self._cancel_tracked_tasks()

    # ------------------------------------------------------------------
    # 服务初始化
    # ------------------------------------------------------------------

    def _init_services(self):
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.services.account.account_manager_async import AccountManagerAsync
            from src.infrastructure.common.event.event_bus import EventBus
            from src.services.account.account_group_service import AccountGroupService

            service_locator = ServiceLocator()
            event_bus = service_locator.get(EventBus)
            self.account_manager = AccountManagerAsync(
                user_id=self.user_id, event_bus=event_bus,
            )
            self.group_service = AccountGroupService()
        except Exception as e:
            logger.error("初始化批量发布页面服务失败: %s", e, exc_info=True)

    async def _load_accounts(self):
        if not self.account_manager:
            return
        try:
            accounts = await self.account_manager.get_accounts() if self.account_manager else []
            self.available_accounts = accounts or []
            if hasattr(self, 'btn_select_account'):
                self.btn_select_account.setEnabled(bool(self.available_accounts))
        except Exception as e:
            logger.error("加载账号列表失败: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # 页面内容
    # ------------------------------------------------------------------

    def _setup_content(self):
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(16, 0, 16, 24)
        root_layout.setSpacing(16)

        # 先构建第三排操作按钮卡片，使控件在预览表与异步刷新前已存在
        action_buttons_card = self._create_action_buttons_card()
        account_import_card = self._create_account_import_card()
        batch_publish_settings_card = self._create_batch_publish_settings_card()
        task_status_reminder_card = self._create_task_status_reminder_card()

        # 第一排：基础配置操作栏
        root_layout.addWidget(account_import_card)

        # 第二排：预览表格卡片（布局对齐「待发布」列表：表格外层 Card 零边距、无标题栏）
        root_layout.addWidget(self._create_preview_card(), stretch=1)

        # 第三排：素材提醒 + 批量发布设置 + 操作按钮，宽度比例 1:2:1，整行与预览表同宽
        row2 = QHBoxLayout()
        row2.setSpacing(16)
        row2.setContentsMargins(0, 0, 0, 0)
        row2.addWidget(task_status_reminder_card, 1)     # 素材提醒：占 1 份
        row2.addWidget(batch_publish_settings_card, 2)   # 批量设置：占 2 份（内容最多）
        row2.addWidget(action_buttons_card, 1)           # 快捷操作：占 1 份
        root_layout.addLayout(row2)

        self.content_layout.addLayout(root_layout)
        self._refresh_task_status_reminder()

    # ==================================================================
    # 1. 顶部工具栏：卡片 A = 四步流程 ①→④；卡片 B = 作品申明及位置/购物车等
    # ==================================================================

    def _create_account_import_card(self) -> QWidget:
        """左侧卡片串联 ①→②→③→④；右侧卡片为作品申明及位置设置等快捷项。"""
        container = QWidget(self)
        root = QHBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        def _toolbar_btn_style(btn) -> None:
            """高度固定；宽度随图标+文案自然占位，避免统一 140px 造成两侧留白过大。"""
            btn.setFixedHeight(30)
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        def _flow_arrow(parent: QWidget) -> QLabel:
            lab = QLabel("→", parent)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setFixedWidth(18)
            lab.setStyleSheet("color: palette(mid); font-weight: 600;")
            return lab

        card_flow = CardWidget(container)
        card_flow.setMinimumHeight(0)
        # 仅包裹四按钮 + 箭头，不参与横向拉伸（避免按钮在宽卡片内被拉散）
        card_flow.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        flow_l = QHBoxLayout(card_flow)
        flow_l.setContentsMargins(10, 8, 10, 8)
        flow_l.setSpacing(6)

        self.btn_select_account = PrimaryPushButton(FluentIcon.PEOPLE, "①选择账号", card_flow)
        self.btn_select_account.clicked.connect(self._on_select_account)
        _toolbar_btn_style(self.btn_select_account)
        flow_l.addWidget(self.btn_select_account, 0, Qt.AlignmentFlag.AlignVCenter)

        flow_l.addWidget(_flow_arrow(card_flow), 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_publish_time = PrimaryPushButton(FluentIcon.CALENDAR, "②配置时间", card_flow)
        self.btn_publish_time.clicked.connect(self._on_publish_time_clicked)
        _toolbar_btn_style(self.btn_publish_time)
        self.btn_publish_time.setEnabled(False)
        _tip_pt = "请先①选择账号，再配置发布时间"
        apply_instructional_tooltip(
            _tip_pt, self.btn_publish_time,
            position=ToolTipPosition.BOTTOM,
        )
        flow_l.addWidget(self.btn_publish_time, 0, Qt.AlignmentFlag.AlignVCenter)

        flow_l.addWidget(_flow_arrow(card_flow), 0, Qt.AlignmentFlag.AlignVCenter)

        add_icon = FluentIcon.PHOTO if self._media_type == "image" else FluentIcon.VIDEO
        self.btn_add_video = PrimaryPushButton(add_icon, f"③添加{self._media_label}", card_flow)
        self.btn_add_video.clicked.connect(self._on_add_video_clicked)
        _toolbar_btn_style(self.btn_add_video)
        self.btn_add_video.setEnabled(False)
        flow_l.addWidget(self.btn_add_video, 0, Qt.AlignmentFlag.AlignVCenter)

        flow_l.addWidget(_flow_arrow(card_flow), 0, Qt.AlignmentFlag.AlignVCenter)

        self.btn_publish_description = PrimaryPushButton(FluentIcon.EDIT, "④配置描述", card_flow)
        self.btn_publish_description.clicked.connect(self._on_publish_description_clicked)
        _toolbar_btn_style(self.btn_publish_description)
        self.btn_publish_description.setEnabled(False)
        _tip_pd = "请先完成①②步，再配置作品标题与简介"
        apply_instructional_tooltip(
            _tip_pd,
            self.btn_publish_description,
            position=ToolTipPosition.BOTTOM,
        )
        flow_l.addWidget(self.btn_publish_description, 0, Qt.AlignmentFlag.AlignVCenter)
        # 若卡片仍有余宽，空白留在最右侧，不把间距摊到按钮之间
        flow_l.addStretch(1)

        card_extra = CardWidget(container)
        card_extra.setMinimumHeight(0)
        card_extra.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred)
        extra_l = QHBoxLayout(card_extra)
        extra_l.setContentsMargins(10, 8, 10, 8)
        extra_l.setSpacing(10)

        self._btn_work_declaration = PushButton("作品申明", card_extra)
        self._btn_work_declaration.setFixedHeight(30)
        self._btn_work_declaration.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed,
        )
        self._btn_work_declaration.clicked.connect(self._on_work_declaration_clicked)
        apply_instructional_tooltip(
            "设置抖音、快手、视频号的作品申明（与对应平台任务关联）",
            self._btn_work_declaration,
            position=ToolTipPosition.BOTTOM,
        )
        extra_l.addWidget(self._btn_work_declaration, 0, Qt.AlignmentFlag.AlignVCenter)

        self._btn_music_settings = PushButton("音乐设置", card_extra)
        self._btn_music_settings.setFixedHeight(30)
        self._btn_music_settings.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed,
        )
        self._btn_music_settings.clicked.connect(self._on_music_settings_clicked)
        self._btn_music_settings.setVisible(self._media_type == "image")
        apply_instructional_tooltip(
            "设置图文任务音乐；当前仅支持随机音乐",
            self._btn_music_settings,
            position=ToolTipPosition.BOTTOM,
        )
        extra_l.addWidget(self._btn_music_settings, 0, Qt.AlignmentFlag.AlignVCenter)

        self._chk_batch_location = CheckBox("位置设置", card_extra)
        self._chk_batch_location.stateChanged.connect(
            self._on_batch_location_check_changed
        )
        _row_loc = QWidget(card_extra)
        _rloc = QHBoxLayout(_row_loc)
        _rloc.setContentsMargins(0, 0, 0, 0)
        _rloc.setSpacing(4)
        _rloc.addWidget(self._chk_batch_location)
        _tip_loc = (
            "勾选后弹出设置：选择是否需要填写地理位置；不需要时还可配置仅视频号生效的展示方式。"
            "取消勾选表示清空位置相关配置（与未填写地理且未选「不展示位置」一致）。"
        )
        apply_instructional_tooltip(
            _tip_loc,
            self._chk_batch_location,
            position=ToolTipPosition.BOTTOM,
        )
        extra_l.addWidget(_row_loc, 0, Qt.AlignmentFlag.AlignVCenter)

        self._chk_batch_yellow_cart = CheckBox("购物车", card_extra)
        self._chk_batch_yellow_cart.stateChanged.connect(
            self._on_batch_yellow_cart_check_changed
        )
        _row_yc = QWidget(card_extra)
        _ryc = QHBoxLayout(_row_yc)
        _ryc.setContentsMargins(0, 0, 0, 0)
        _ryc.setSpacing(4)
        _ryc.addWidget(self._chk_batch_yellow_cart)
        _tip_yc = (
            "勾选后弹出设置：从购物车推广商品库选择商品；"
            f"商品短标题（最多{YELLOW_CART_SHORT_TITLE_MAX_LEN}字）仅存于购物车挂载数据，"
            "与「④配置描述」中的作品简介无关；取消勾选表示不挂载购物车。"
        )
        apply_instructional_tooltip(
            _tip_yc,
            self._chk_batch_yellow_cart,
            position=ToolTipPosition.BOTTOM,
        )
        extra_l.addWidget(_row_yc, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lbl_batch_yellow_cart_summary = CaptionLabel("", card_extra)
        self._lbl_batch_yellow_cart_summary.setTextColor("#888888", "#888888")
        extra_l.addWidget(self._lbl_batch_yellow_cart_summary, 0, Qt.AlignmentFlag.AlignVCenter)

        self._chk_batch_group_buy = CheckBox("团购", card_extra)
        self._chk_batch_group_buy.stateChanged.connect(
            self._on_batch_group_buy_check_changed
        )
        _row_gb = QWidget(card_extra)
        _rgb = QHBoxLayout(_row_gb)
        _rgb.setContentsMargins(0, 0, 0, 0)
        _rgb.setSpacing(4)
        _rgb.addWidget(self._chk_batch_group_buy)
        _tip_gb = "勾选后弹出设置：填写团购主内容与推广标题；取消勾选表示不挂载团购。"
        apply_instructional_tooltip(
            _tip_gb,
            self._chk_batch_group_buy,
            position=ToolTipPosition.BOTTOM,
        )
        extra_l.addWidget(_row_gb, 0, Qt.AlignmentFlag.AlignVCenter)
        self._lbl_batch_group_buy_summary = CaptionLabel("", card_extra)
        self._lbl_batch_group_buy_summary.setTextColor("#888888", "#888888")
        extra_l.addWidget(self._lbl_batch_group_buy_summary, 0, Qt.AlignmentFlag.AlignVCenter)

        extra_l.addStretch(1)

        root.addWidget(card_flow, 0)
        root.addWidget(card_extra, 1)
        return container

    @asyncSlot()
    async def _on_select_account(self):
        await self._load_accounts()
        if not self.available_accounts:
            InfoBar.warning("暂无账号", "请先在账号管理页面添加并登录账号",
                            parent=self, position=InfoBarPosition.TOP, duration=3000)
            return

        try:
            groups = []
            if self.group_service:
                groups = await self.group_service.get_groups(user_id=None)
            self._cached_groups = groups

            # 重开弹窗时，按内存中存储的账号/组占位回填初始勾选状态
            initial_account_ids = [
                aid for acc in self.selected_accounts if acc.get("_type") != "group" and (aid := acc.get("id")) is not None
            ]
            initial_group_ids = [
                gid for acc in self.selected_accounts if acc.get("_type") == "group" and (gid := acc.get("group_id")) is not None
            ]

            from src.pro_features.batch.dialogs.publish_target_selection_dialog import select_publish_targets
            result = await select_publish_targets(
                self, 
                self.available_accounts, 
                groups,
                initial_account_ids=initial_account_ids,
                initial_group_ids=initial_group_ids,
            )

            if result:
                # defer_material_db_refresh：避免 _refresh_preview 内 create_task 与当前 @asyncSlot 重叠（qasync 报错）
                self._apply_selection_result(result, defer_material_db_refresh=True)
                # 从「账号列表」选择单个或多个平台账号时：始终检查各账号「视频/未发布」目录并匹配；
                # 「账号组」选择仍仅在使用者开启「自动从视频库添加视频」时拉取素材。
                if result.get("type") == "account":
                    await self._sync_unpublished_videos_for_plain_accounts()
                else:
                    await self._try_auto_match_videos()
                self._schedule_preview_refresh(skip_material_stats_reminder=True)
                await self._refresh_task_status_reminder_async()
        except Exception as e:
            logger.error("显示账号选择弹窗失败: %s", e, exc_info=True)

    def _apply_selection_result(
        self, result: dict, *, defer_material_db_refresh: bool = False
    ):
        """将选择结果以组占位形式存入已选账号列表（UI 展示层）。

        账号组在此以整体占位 dict 保存，便于 UI 显示"账号组"而不是展开成员。
        实际生成任务时（添加到发布列表）才通过 batch_publish_targets 展开为真实账号。

        defer_material_db_refresh：为 True 时不经 _refresh_preview 调度异步查库（供 @asyncSlot 内由调用方 await）。
        """
        new_accounts: List[dict] = []
        source = ""
        if result["type"] == "account":
            data = result.get("data")
            if isinstance(data, list):
                new_accounts = data  # type: ignore
                source = "多选"
            else:
                new_accounts = [data]  # type: ignore
                source = "单选"
        elif result["type"] == "group":
            data = result.get("data")
            groups = data if isinstance(data, list) else ([data] if data else [])
            source = "账号组"
            for g in groups:
                if not g:
                    continue
                gid = g.get("id")
                gname = g.get("group_name", "") or "未命名账号组"
                new_accounts.append({
                    "id": f"group:{gid}",
                    "_type": "group",
                    "group_id": gid,
                    "group_name": gname,
                    "platform": "account_group",
                    "platform_username": gname,
                    # 保存原始 group 数据，供展开时直接使用成员列表
                    "_group_data": g,
                })

        for acc in new_accounts:
            acc["_source"] = source  # type: ignore

        self.selected_accounts = new_accounts
        self._schedule_preview_refresh(
            skip_material_stats_reminder=defer_material_db_refresh
        )

    # ------------------------------------------------------------------
    # 素材自动匹配
    # ------------------------------------------------------------------

    def _is_auto_match_enabled(self) -> bool:
        return load_auto_match_pref(self._media_type)

    def _show_material_shortage_dialog(self, message: str, *, title: str = "素材不足") -> None:
        """素材不足或无待发布视频时使用模态弹窗提醒（替代顶部 InfoBar）。"""
        parent = self.window() or self
        w = AppMessageBoxBase(parent, header_title=title)
        body = BodyLabel((message or "").strip() or "请补充素材。", w)
        body.setWordWrap(True)
        w.viewLayout.addWidget(body)
        w.widget.setMinimumWidth(420)

        w.yesButton.setText("确定")
        w.cancelButton.setVisible(False)
        button_layout = getattr(w, "buttonLayout", None)
        if button_layout is None:
            button_layout = w.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(w.cancelButton)
            button_layout.removeWidget(w.yesButton)
            button_layout.addWidget(w.yesButton)

        w.exec()

    def _schedule_auto_match_if_enabled(self, *, force_run: bool = False) -> None:
        """弹窗或设置区将「自动从视频库」打开后立即执行匹配（需已有选中账号）。

        force_run: 为 True 时表示调用方刚把开关设为开启；因 ``save_auto_match_pref`` 异步落盘，
        此时 ``load_auto_match_pref`` 可能仍为旧值，故跳过偏好检查仍执行一次匹配。
        """
        if not force_run and not self._is_auto_match_enabled():
            return
        if not self.selected_accounts:
            return

        async def _run():
            try:
                await self._try_auto_match_videos(skip_pref_check=force_run)
            finally:
                self._schedule_preview_refresh()

        def _start_match_task() -> None:
            self._track_task(asyncio.create_task(_run()))

        # 避免在 @asyncSlot 等协程未让出时直接 create_task（同 _refresh_task_status_reminder）
        self._schedule_base_page_timer("batch.auto_match_videos", 10, _start_match_task)

    async def _load_publish_list_exclude_paths(self) -> set:
        """查询发布列表中待发布/进行中任务已占用的 file_path 集合。

        用于素材自动匹配前排除已分配的视频，避免同一视频重复添加到发布列表。
        查询范围：当前所选账号（含账号组展开后的成员账号）的 pending/running 记录。
        """
        try:
            from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
            repo = PublishRecordRepositoryAsync()

            def _coerce_account_id(v) -> Optional[int]:
                if isinstance(v, int):
                    return v
                if isinstance(v, str):
                    s = v.strip()
                    if s.isdigit():
                        try:
                            return int(s)
                        except Exception:
                            return None
                return None

            account_ids: list[int] = []
            for acc in self.selected_accounts:
                if acc.get("_type") == "group":
                    gd = acc.get("_group_data") or {}
                    for m in gd.get("accounts") or []:
                        aid = _coerce_account_id(m.get("id"))
                        if isinstance(aid, int):
                            account_ids.append(aid)
                    if not account_ids:
                        gid = acc.get("group_id")
                        for cg in getattr(self, "_cached_groups", None) or []:
                            if cg.get("id") == gid or cg.get("group_id") == gid:
                                for m in cg.get("accounts") or []:
                                    aid = _coerce_account_id(m.get("id"))
                                    if isinstance(aid, int):
                                        account_ids.append(aid)
                else:
                    aid = _coerce_account_id(acc.get("id"))
                    if isinstance(aid, int):
                        account_ids.append(aid)

            if not account_ids:
                return set()

            return await repo.get_active_file_paths_for_accounts(
                self.user_id, account_ids
            )
        except Exception as e:
            logger.warning("查询发布列表已占用文件失败: %s", e, exc_info=True)
            return set()

    async def _sync_unpublished_videos_for_plain_accounts(self) -> None:
        """从所选平台账号的媒体库「视频/未发布」目录拉取素材（不依赖「自动从视频库」开关）。

        逐个账号独立拉取，并为每条视频打上 _assigned_account_id 标签，
        供任务生成时按账号隔离分配（每个账号只用自己目录的视频）。
        """
        if not self.selected_accounts:
            return
        if any(acc.get("_type") == "group" for acc in self.selected_accounts):
            return

        from src.infrastructure.common.material_library_manager import MaterialLibraryManager
        from src.pro_features.batch.services.batch_unpublished_sync import sync_unpublished_for_accounts

        if MaterialLibraryManager.get_root_dir() is None:
            self._show_material_shortage_dialog(
                "未配置媒体库路径，请先在「设置」中选择媒小宝媒体库存储位置。",
                title="提示",
            )
            return

        n_time = max(1, len(self.time_slots))
        self.video_list = [v for v in self.video_list if not v.get("_auto_matched")]
        self._get_video_auto_matcher().reset()

        exclude_paths = await self._load_publish_list_exclude_paths()
        self._get_video_auto_matcher().set_exclude_paths(exclude_paths)

        existing_paths = {v["file_path"] for v in self.video_list}
        all_issues_outcome = None

        for acc in self.selected_accounts:
            outcome = sync_unpublished_for_accounts(
                [acc],
                self._get_video_auto_matcher(),
                existing_paths,
                n_time,
                self._cached_groups,
            )
            acc_id = acc.get("id")
            for m in outcome.new_items:
                fp = m["file_path"]
                title, desc = await self._resolve_title_desc_async(fp)
                entry: dict = {
                    "file_path": fp,
                    "file_name": m["file_name"],
                    "file_size": m.get("file_size", 0),
                    "title": title,
                    "description": desc,
                    "tags": ",".join(parse_topic_list(desc)) if desc else "",
                    "_auto_matched": True,
                    "_assigned_account_id": acc_id,
                }
                self.video_list.append(entry)

            if outcome.has_issues:
                if all_issues_outcome is None:
                    all_issues_outcome = outcome
                else:
                    all_issues_outcome.shortage_messages.extend(outcome.shortage_messages)
                    all_issues_outcome.empty_owner_labels.extend(outcome.empty_owner_labels)

        if all_issues_outcome is not None and all_issues_outcome.has_issues:
            self._show_material_shortage_dialog(
                all_issues_outcome.build_dialog_message(self._media_type),
                title=all_issues_outcome.dialog_title(),
            )

    async def _try_auto_match_videos(self, *, skip_pref_check: bool = False) -> None:
        """在选择账号或配置时间后，自动从视频库匹配素材（仅当开关开启时生效）。

        委托 batch_unpublished_sync.auto_match_for_accounts 完成纯数据同步。
        当选中的是账号组时，为每条视频打上 _group_id 标签，供任务生成时按组隔离使用。

        skip_pref_check: 与 ``_schedule_auto_match_if_enabled(force_run=True)`` 配套，避免异步保存
        偏好尚未完成时误跳过匹配。
        """
        if not skip_pref_check and not self._is_auto_match_enabled():
            return
        if not self.selected_accounts:
            return

        from src.pro_features.batch.services.batch_unpublished_sync import auto_match_for_accounts

        n_time = max(1, len(self.time_slots))
        schedule_mode = getattr(self, "schedule_mode", "reuse")
        n_acc = len(self.selected_accounts)
        
        acc_target_counts = []
        if schedule_mode == "shared":
            acc_target_counts = [0] * n_acc
            if n_acc > 0:
                for i in range(n_time):
                    acc_target_counts[i % n_acc] += 1
        else:
            acc_target_counts = [n_time] * n_acc

        self.video_list = [v for v in self.video_list if not v.get("_auto_matched")]
        self._get_video_auto_matcher().reset()

        exclude_paths = await self._load_publish_list_exclude_paths()
        self._get_video_auto_matcher().set_exclude_paths(exclude_paths)

        existing_paths = {v["file_path"] for v in self.video_list}
        all_shortage_messages: list = []
        
        matched_videos_per_account = []

        for acc_idx, acc in enumerate(self.selected_accounts):
            target_count = acc_target_counts[acc_idx] if acc_idx < len(acc_target_counts) else 0
            if target_count == 0:
                matched_videos_per_account.append([])
                continue

            outcome = auto_match_for_accounts(
                [acc],
                self._get_video_auto_matcher(),
                existing_paths,
                target_count,
                self._cached_groups,
            )
            if outcome.shortage_messages:
                all_shortage_messages.extend(outcome.shortage_messages)

            current_acc_matched = []
            for m in outcome.new_items:
                fp = m["file_path"]
                title, desc = await self._resolve_title_desc_async(fp)
                entry: dict = {
                    "file_path": fp,
                    "file_name": m["file_name"],
                    "file_size": m.get("file_size", 0),
                    "title": title,
                    "description": desc,
                    "tags": ",".join(parse_topic_list(desc)) if desc else "",
                    "_auto_matched": True,
                }
                if acc.get("_type") == "group":
                    entry["_group_id"] = acc.get("group_id")
                current_acc_matched.append(entry)
            matched_videos_per_account.append(current_acc_matched)
            
        if schedule_mode == "shared" and n_acc > 0:
            interleaved = []
            cursors = [0] * n_acc
            for i in range(n_time):
                acc_idx = i % n_acc
                lst = matched_videos_per_account[acc_idx]
                if cursors[acc_idx] < len(lst):
                    interleaved.append(lst[cursors[acc_idx]])
                    cursors[acc_idx] += 1
            self.video_list.extend(interleaved)
        else:
            for lst in matched_videos_per_account:
                self.video_list.extend(lst)

        if all_shortage_messages:
            self._show_material_shortage_dialog("\n".join(all_shortage_messages))

    async def _resolve_title_desc_async(
        self, file_path: str, name_for_work_id: Optional[str] = None
    ) -> tuple[str, str]:
        """异步版本的标题/简介解析，用于在 async 上下文中安全调用（避免嵌套事件循环）。"""
        from src.services.copywriting.copywriting_match_service import CopywritingMatchService

        res = await CopywritingMatchService.match(
            mode=self.match_mode if getattr(self, "auto_match_enabled", False) else "none",
            file_path=file_path,
            category_id=getattr(self, "random_category_id", None),
            assign_strategy=getattr(self, "copywriting_assign_strategy", "round_robin"),
            apply_all=self.apply_description_to_all_tasks,
            same_title=self.same_title_text,
            same_desc=self.same_desc_text,
            use_lib_title=self.use_library_title,
            use_lib_desc=self.use_library_desc,
        )
        if res:
            return res.get("title", ""), res.get("description", "")
        return "", ""

    def _on_add_video_clicked(self):
        """点击「添加视频」时弹出 Fluent 风格选择弹窗"""
        dlg = AddBatchMediaChoiceDialog(
            self.window() or self,
            batch_page=self,
            media_label=self._media_label,
            auto_match_label=f"自动从{self._media_library_label}添加{self._task_label}",
            load_pref=lambda: load_auto_match_pref(self._media_type),
            save_pref=lambda v: save_auto_match_pref(v, self._media_type),
        )
        accepted = dlg.exec() == int(QDialog.DialogCode.Accepted)
        if accepted:
            # 从弹窗同步最新策略选择（用户可能在弹窗内更改了策略）
            self._library_assign_strategy = dlg.selected_strategy
            # 让弹窗先完成关闭/重绘，再打开系统文件选择框，避免“选完后消失慢/卡顿”的观感
            if dlg.choice == "files":
                self._schedule_base_page_timer("batch.import_files", 0, self._on_import_files)
            elif dlg.choice == "folder":
                self._schedule_base_page_timer("batch.import_folder", 0, self._on_import_folder)
            elif dlg.choice == "library":
                self._schedule_base_page_timer(
                    "batch.choose_from_library",
                    0,
                    self._on_choose_from_library,
                )
        # 无论点选添加方式还是 ESC 关闭，均以弹窗最终勾选同步「视频配置」（偏好异步落盘，不能仅依赖 load_pref）
        self._sync_batch_publish_settings_ui(video_auto_match=dlg.auto_match_enabled)

    def _on_publish_time_clicked(self):
        """打开并配置发布时间设置弹窗。

        使用同步方式 ``dialog.exec()``：若在 ``@asyncSlot`` 协程内进入模态对话框，
        qasync 心跳任务等会尝试进入事件循环，与当前正在执行的任务嵌套冲突，触发
        ``Cannot enter into task ... while another task is being executed``。
        确认后的异步刷新单独 ``run_async_from_ui`` 调度。
        """
        from src.pro_features.batch.dialogs.publish_time_dialog import PublishTimeDialog
        from src.ui.utils.async_helper import run_async_from_ui

        dialog = PublishTimeDialog(
            self.time_slots,
            owner_count=len(getattr(self, "selected_accounts", []) or []),
            initial_schedule_mode=getattr(self, "schedule_mode", "reuse"),
            parent=self.window() or self,
        )
        if dialog.exec() == int(QDialog.DialogCode.Accepted):
            self.time_slots = dialog.get_schedule_slots()
            self.schedule_mode = dialog.get_schedule_mode()
            run_async_from_ui(self._after_publish_time_dialog_accepted)

    async def _after_publish_time_dialog_accepted(self) -> None:
        await self._try_auto_match_videos()
        self._schedule_preview_refresh()

    def _open_publish_description_dialog(self) -> None:
        """打开配置描述弹窗（「配置描述」按钮与描述配置选「手动」时共用）。

        使用同步方式 ``dialog.exec()``：若在 ``@asyncSlot`` 协程内进入模态对话框，弹窗内
        ``save_persisted_publish_description_prefs`` 会通过 ``run_async_from_ui`` 再 ``create_task``，
        与 qasync 当前任务嵌套冲突，触发 ``Cannot enter into task ... while another task is being executed``。
        确认后的异步刷新单独 ``run_async_from_ui`` 调度。
        """
        from src.ui.publish.work_description import PublishDescriptionDialog
        from src.ui.utils.async_helper import run_async_from_ui

        # 用页面状态对齐下拉索引（不用 currentIndex()），避免控件与 use_library_* 短暂不一致时弹窗勾选被错误覆盖
        desc_idx: Optional[int] = None
        if hasattr(self, "_combo_batch_desc"):
            desc_idx = self._desc_config_combo_index() if hasattr(self, '_desc_config_combo_index') else 0
            self._combo_batch_desc.blockSignals(True)
            try:
                self._combo_batch_desc.setCurrentIndex(desc_idx)
            finally:
                self._combo_batch_desc.blockSignals(False)

        dialog = PublishDescriptionDialog(
            initial_title=self.same_title_text,
            initial_desc=self.same_desc_text,
            initial_apply_to_all_tasks=self.apply_description_to_all_tasks,
            parent=self.window() or self,
        )
        if dialog.exec() == int(QDialog.DialogCode.Accepted):
            before_state = self._description_settings_state_key()
            result = dialog.get_description_settings()
            self.same_title_text = result["same_title"]
            self.same_desc_text = result["same_desc"]
            self.apply_description_to_all_tasks = bool(
                result.get("apply_to_all_tasks", self.apply_description_to_all_tasks)
            )
            self.use_library_title = bool(result.get("use_library_title", False))
            self.use_library_desc = bool(result.get("use_library_desc", False))
            
            # 更新新字段
            self.auto_match_enabled = bool(result.get("auto_match_enabled", False))
            self.match_mode = str(result.get("match_mode") or "standard")
            self.random_category_id = result.get("random_category_id")
            self.copywriting_assign_strategy = str(
                result.get("copywriting_assign_strategy") or AssignStrategy.ROUND_ROBIN.value
            )

            # 与卡片下拉变更保持同一持久化入口，避免字段集合漂移。
            self._persist_publish_description_prefs_from_page()
            self._sync_batch_publish_settings_ui()

            # 每次有改动并确认，立即执行一次描述重算；无改动则不重复执行。
            if self._description_settings_state_key() != before_state:
                run_async_from_ui(self._after_publish_description_dialog_accepted)

    def _on_publish_description_clicked(self):
        self._open_publish_description_dialog()

    async def _after_publish_description_dialog_accepted(self) -> None:
        await self._reapply_description_to_all_videos()
        self._schedule_preview_refresh()

    def _description_settings_state_key(self) -> tuple:
        """用于判定「配置描述」确认后是否发生了实际改动。"""
        return (
            self.same_title_text or "",
            self.same_desc_text or "",
            self.apply_description_to_all_tasks,
            self.use_library_title,
            self.use_library_desc,
            bool(getattr(self, "auto_match_enabled", False)),
            str(getattr(self, "match_mode", "standard") or "standard"),
            getattr(self, "random_category_id", None),
            str(
                getattr(self, "copywriting_assign_strategy", AssignStrategy.ROUND_ROBIN.value)
                or AssignStrategy.ROUND_ROBIN.value
            ),
        )

    async def _reapply_description_to_all_videos(self) -> None:
        """根据当前描述设置刷新 video_list 中每条记录的 title/description/tags。
        
        随机模式下使用 batch_match，一次性按分配策略批量获取文案并分配给各视频。
        """
        from src.services.copywriting.copywriting_match_service import CopywritingMatchService

        # 1. 构造任务列表
        match_tasks = [{"file_path": v.get("file_path") or ""} for v in self.video_list]

        # 2. 调用批量匹配服务（支持文案库分配策略）
        matches = await CopywritingMatchService.batch_match(
            tasks=match_tasks,
            mode=self.match_mode if getattr(self, "auto_match_enabled", False) else "none",
            category_id=getattr(self, "random_category_id", None),
            assign_strategy=getattr(self, "copywriting_assign_strategy", "round_robin"),
            apply_all=self.apply_description_to_all_tasks,
            same_title=self.same_title_text,
            same_desc=self.same_desc_text,
            use_lib_title=self.use_library_title,
            use_lib_desc=self.use_library_desc,
        )

        # 3. 逐条应用匹配结果
        for v, res in zip(self.video_list, matches):
            if res:
                v["title"] = res.get("title", "")
                v["description"] = res.get("description", "")
                d = v["description"]
                v["tags"] = ",".join(parse_topic_list(d)) if d else ""
            else:
                # 若匹配失败/未匹配到文案：
                # 如果开启了自动匹配，说明此时确实无文案可用，应清空残留；
                # 如果是手动匹配且未勾选统一应用，也应清空。
                is_auto_match = getattr(self, "auto_match_enabled", False)
                if is_auto_match or not self.apply_description_to_all_tasks:
                    v["title"] = ""
                    v["description"] = ""
                    v["tags"] = ""

    def _on_import_files(self):
        return self._batch_controller.import_files()

    def _on_import_files_legacy(self):
        from src.ui.dialogs.file_select_dialog import FileSelectDialog
        files = FileSelectDialog.select_files(self)
        if files:
            if self._media_type == "image":
                image_files = [
                    os.path.abspath(p) for p in files
                    if os.path.splitext(p)[1].lower() in SUPPORTED_IMAGE_EXTENSIONS
                ]
                if image_files:
                    self._schedule_add_video_files([",".join(image_files)], apply_assign_strategy=True)
            else:
                self._schedule_add_video_files(files, apply_assign_strategy=True)

    def _on_import_folder(self):
        return self._batch_controller.import_folder()

    def _on_import_folder_legacy(self):
        from src.ui.dialogs.file_select_dialog import FileSelectDialog
        folder = FileSelectDialog.select_folder(self)
        if folder:
            if self._media_type == "image":
                image_files = self._media_paths_from_folder(folder)
                if image_files:
                    self._schedule_add_video_files([self._image_folder_composite_path(folder)], apply_assign_strategy=True)
                else:
                    InfoBar.info(
                        "提示",
                        "所选文件夹中没有支持的图片文件",
                        parent=self,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                    )
                return
            video_files = []
            for root, _, filenames in os.walk(folder):
                for fn in sorted(filenames):
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in SUPPORTED_VIDEO_EXTENSIONS:
                        video_files.append(os.path.join(root, fn))
            if video_files:
                self._schedule_add_video_files(video_files, apply_assign_strategy=True)
            else:
                InfoBar.info("提示", "所选文件夹中没有支持的视频文件",
                             parent=self, position=InfoBarPosition.TOP, duration=3000)

    def _resolve_video_assign_pairs(self, file_paths: List[str]) -> List[tuple[str, Optional[dict]]]:
        """按当前策略为导入视频分配账号，返回 (file_path, assigned_account) 列表。"""
        plain_accounts = [a for a in self.selected_accounts if a.get("_type") != "group"]
        if not plain_accounts:
            plain_accounts = self.selected_accounts
        if len(plain_accounts) <= 1:
            one = plain_accounts[0] if plain_accounts else None
            return [(p, one) for p in file_paths]
        pairs = distribute_items_to_targets(file_paths, plain_accounts, self._library_assign_strategy)
        return [(item, account) for item, account in pairs]

    def _normalize_media_input_path(self, file_path: str) -> str:
        if self._media_type != "image":
            return os.path.abspath(file_path)
        parts: List[str] = []
        for raw in file_path or "".split(","):
            part = raw.strip()
            if not part:
                continue
            if part.startswith(FOLDER_MARKER_PREFIX):
                folder = part[len(FOLDER_MARKER_PREFIX):].strip()
                parts.append(f"{FOLDER_MARKER_PREFIX}{os.path.abspath(folder)}")
            else:
                parts.append(os.path.abspath(part))
        return ",".join(parts)

    def _media_real_paths(self, file_path: str) -> List[str]:
        paths: List[str] = []
        for raw in file_path or "".split(","):
            part = raw.strip()
            if not part or part.startswith(FOLDER_MARKER_PREFIX):
                continue
            paths.append(part)
        return paths

    def _media_folder_marker(self, file_path: str) -> Optional[str]:
        for raw in file_path or "".split(","):
            part = raw.strip()
            if part.startswith(FOLDER_MARKER_PREFIX):
                return part[len(FOLDER_MARKER_PREFIX):].strip() or None
        return None

    def _media_input_is_supported(self, file_path: str) -> bool:
        if self._media_type == "image":
            return any(
                os.path.splitext(p)[1].lower() in SUPPORTED_IMAGE_EXTENSIONS
                for p in self._media_real_paths(file_path)
            )
        ext = os.path.splitext(file_path)[1].lower()
        return ext in SUPPORTED_VIDEO_EXTENSIONS

    def _media_input_size(self, file_path: str) -> int:
        total = 0
        if self._media_type == "image":
            for p in self._media_real_paths(file_path):
                try:
                    total += os.path.getsize(p)
                except OSError:
                    pass
            return total
        return os.path.getsize(file_path)

    def _media_input_is_occupied(self, file_path: str, occupied_paths: set[str]) -> bool:
        from src.infrastructure.common.path_utils import normalize_media_path
        if self._media_type == "image":
            folder = self._media_folder_marker(file_path)
            if folder and normalize_media_path(folder) in occupied_paths:
                return True
            return normalize_media_path(file_path) in occupied_paths
        return normalize_media_path(file_path) in occupied_paths

    def _schedule_add_video_files(
        self, file_paths: List[str], *, apply_assign_strategy: bool = False
    ) -> None:
        if not file_paths:
            return

        def _start() -> None:
            self._track_task(asyncio.create_task(
                self._add_video_files_async(
                    file_paths,
                    apply_assign_strategy=apply_assign_strategy,
                )
            ))

        self._schedule_base_page_timer("batch.add_video_files", 0, _start)

    async def _add_video_files_async(
        self, file_paths: List[str], *, apply_assign_strategy: bool = False
    ) -> None:
        from src.infrastructure.common.path_utils import normalize_media_path
        existing_paths = {v["file_path"] for v in self.video_list}
        active_paths = await self._load_publish_list_exclude_paths()
        occupied_paths = {
            normalize_media_path(p)
            for p in active_paths
            if p
        }
        for active in active_paths:
            for part in str(active or "").split(","):
                part = part.strip()
                if part.startswith(FOLDER_MARKER_PREFIX):
                    part = part[len(FOLDER_MARKER_PREFIX):].strip()
                norm = normalize_media_path(part)
                if norm:
                    occupied_paths.add(norm)
        added = 0
        blocked_paths: List[str] = []
        pairs = (
            self._resolve_video_assign_pairs(file_paths)
            if apply_assign_strategy else [(fp, None) for fp in file_paths]
        )
        for fp, assigned_account in pairs:
            fp = self._normalize_media_input_path(fp)
            if not self._media_input_is_supported(fp):
                continue
            if self._media_input_is_occupied(fp, occupied_paths):
                blocked_paths.append(fp)
                continue
            if fp in existing_paths:
                continue
            try:
                size = self._media_input_size(fp)
            except OSError:
                size = 0
            title, desc = await self._resolve_title_desc_async(fp)
            self.video_list.append({
                "file_path": fp,
                "file_name": self._material_display_name_for_path(fp),
                "file_size": size,
                "title": title,
                "description": desc,
                "tags": ",".join(parse_topic_list(desc)) if desc else "",
                "_assigned_account_id": assigned_account.get("id") if assigned_account else None,
            })
            existing_paths.add(fp)
            added += 1  # type: ignore

        if added:
            self._schedule_preview_refresh()
        if blocked_paths:
            show_lines = "\n".join(os.path.basename(p) for p in blocked_paths[:8])
            extra = ""
            if len(blocked_paths) > 8:
                extra = f"\n...其余 {len(blocked_paths) - 8} 个文件已省略"
            InfoBar.warning(
                f"{self._task_label}已被占用",
                f"以下{self._task_label}已在待发布/发布中任务中使用，已自动过滤：\n{show_lines}{extra}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4500,
            )

    # ------------------------------------------------------------------
    # 媒体库逻辑
    # ------------------------------------------------------------------

    def _on_choose_from_library(self):
        return self._batch_controller.choose_from_library()

    def _on_choose_from_library_legacy(self):
        """从媒体库弹窗选择素材，并按当前策略将素材与已选账号配对后加入发布列表。"""
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager

        if MaterialLibraryManager.get_root_base_dir() is None:
            InfoBar.warning(
                "提示",
                "未配置媒体库路径，请先在「设置」中选择媒小宝媒体库存储位置。",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
            return

        if not self.selected_accounts:
            InfoBar.warning(
                "提示",
                f"请先选择账号，媒体库将只显示已添加账号的{self._task_label}素材。",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return

        try:
            if self._media_type == "image":
                files = MaterialLibraryManager.list_image_entries_for_accounts(
                    self.selected_accounts
                )
            else:
                files = MaterialLibraryManager.list_video_entries_for_accounts(
                    self.selected_accounts
                )
        except Exception as e:
            logger.error("扫描媒体库%s失败: %s", self._task_label, e, exc_info=True)
            InfoBar.error(
                "错误",
                f"读取媒体库{self._task_label}列表失败，请稍后重试。",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )
            return

        if not files:
            InfoBar.info("提示", f"已选账号的{self._media_library_label}中暂无未发布{self._task_label}，请先为对应账号分配素材",
                         parent=self, position=InfoBarPosition.TOP, duration=3000)
            return

        dlg = LibraryMediaSelectDialog(files, self.window() or self, media_label=self._media_label)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return

        selected = dlg.selected_files
        if not selected:
            return

        # 展开账号组为真实账号列表，用于策略配对
        plain_accounts = [a for a in self.selected_accounts if a.get("_type") != "group"]
        if not plain_accounts:
            plain_accounts = self.selected_accounts

        if len(plain_accounts) > 1:
            # 多账号时按策略配对：每个视频分配一个对应账号
            pairs = distribute_items_to_targets(selected, plain_accounts, self._library_assign_strategy)
        else:
            # 单账号直接配对
            acc = plain_accounts[0] if plain_accounts else None
            pairs = [(f, acc) for f in selected]

        self._schedule_add_from_library(pairs)

    def _schedule_add_from_library(
        self, pairs: List[tuple[dict, Optional[dict]]]
    ) -> None:
        if not pairs:
            return

        def _start() -> None:
            self._track_task(asyncio.create_task(self._add_from_library_async(pairs)))

        self._schedule_base_page_timer("batch.add_from_library", 0, _start)

    async def _add_from_library_async(
        self, pairs: List[tuple[dict, Optional[dict]]]
    ) -> None:
        """从媒体库批量添加素材，异步解析文案并合并一次预览刷新。"""
        existing_paths = {v["file_path"] for v in self.video_list}
        added = 0
        for file_info, assigned_account in pairs:
            fp = file_info.get("file_path", "")
            if not fp or fp in existing_paths:
                continue
            try:
                size = file_info.get("file_size", 0) or os.path.getsize(fp)
            except OSError:
                size = 0
            name = file_info.get("file_name") or file_info.get("original_name") or self._material_display_name_for_path(fp)
            title, desc = await self._resolve_title_desc_async(fp, name_for_work_id=name)
            entry: dict = {
                "file_path": fp,
                "file_name": self._material_display_name_for_path(fp),
                "file_size": size,
                "title": title,
                "description": desc,
                "tags": ",".join(parse_topic_list(desc)) if desc else "",
            }
            if assigned_account is not None:
                entry["_assigned_account_id"] = assigned_account.get("id")
            self.video_list.append(entry)
            existing_paths.add(fp)
            added += 1

        if not added:
            return

        self._schedule_preview_refresh()
        strategy_name = self._library_assign_strategy.display_name()
        InfoBar.success(
            "已添加",
            f"按{strategy_name}策略从媒体库添加 {added} 个{self._task_label}",
            parent=self,
            position=InfoBarPosition.TOP,
            duration=2000,
        )

    # ==================================================================
    # 3. 素材库数量提醒卡片（各目标「视频 → 未发布」目录 + 发布列表占用）
    # ==================================================================

    _stat_pill_counter = 0

    @staticmethod
    def _stat_pill(
        label: str,
        color: str,
        bg: str,
        border: str,
        parent: QWidget,
        *,
        val_font_px: int = 20,
        lbl_font_px: int = 11,
    ):
        """一个统计方块：大数字 + 彩色小标签，返回 (容器, 数值 QLabel)。"""
        from PySide6.QtWidgets import QFrame
        BatchTaskCreationPage._stat_pill_counter += 1
        obj_name = f"TSRBlock_{BatchTaskCreationPage._stat_pill_counter}"
        block = QFrame(parent)
        block.setObjectName(obj_name)
        block.setStyleSheet(
            f"#{obj_name} {{ background:{bg}; border:1px solid {border}; border-radius:6px; }}"
        )
        v = QVBoxLayout(block)
        v.setContentsMargins(4, 6, 4, 6)
        v.setSpacing(2)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val = QLabel("—", block)
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val.setStyleSheet(
            f"font-size:{val_font_px}px; font-weight:700; color:{color}; border:none; background:transparent;"
        )
        lbl = QLabel(label, block)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"font-size:{lbl_font_px}px; color:{color}; border:none; background:transparent;"
        )
        v.addWidget(val)
        v.addWidget(lbl)
        return block, val

    @staticmethod
    def _stat_chip(
        short_label: str,
        tooltip: str,
        color: str,
        bg: str,
        border: str,
        parent: QWidget,
    ):
        """单行横向色块：数字 + 短标签，高度远小于纵向 _stat_pill，避免在滚动区内被裁切。"""
        from PySide6.QtWidgets import QFrame
        BatchTaskCreationPage._stat_pill_counter += 1
        obj_name = f"TSRChip_{BatchTaskCreationPage._stat_pill_counter}"
        block = QFrame(parent)
        block.setObjectName(obj_name)
        block.setStyleSheet(
            f"#{obj_name} {{ background:{bg}; border:1px solid {border}; border-radius:4px; }}"
        )
        block.setFixedHeight(24)
        block.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        h = QHBoxLayout(block)
        h.setContentsMargins(5, 0, 6, 0)
        h.setSpacing(3)
        val = QLabel("—", block)
        val.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        val.setStyleSheet(
            f"font-size:12px; font-weight:700; color:{color}; border:none; background:transparent;"
        )
        lbl = QLabel(short_label, block)
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lbl.setWordWrap(False)
        lbl.setStyleSheet(
            f"font-size:9px; color:{color}; border:none; background:transparent;"
        )
        h.addWidget(val, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        apply_instructional_tooltip(tooltip, block, position=ToolTipPosition.BOTTOM)
        return block, val

    def _clear_material_stats_rows_layout(self) -> None:
        lay = self._material_stats_rows_layout
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render_material_stats_message(self, text: str, *, warn: bool = False) -> None:
        self._clear_material_stats_rows_layout()
        lbl = BodyLabel(text, self._material_stats_rows_host)
        lbl.setWordWrap(True)
        if warn:
            lbl.setStyleSheet("font-size: 12px; color: #e67700;")
        else:
            lbl.setStyleSheet("font-size: 12px; color: #999;")
        self._material_stats_rows_layout.addWidget(lbl)

    def _create_material_account_row(
        self, name: str, total: int, occupied: int, available: int
    ) -> QWidget:
        """单个账号/账号组一行：左侧名称 + 右侧三个低矮色块（同一水平线）。"""
        from PySide6.QtWidgets import QFrame

        row = QFrame(self._material_stats_rows_host)
        self._material_account_row_counter += 1
        _rn = f"MatAccRow_{self._material_account_row_counter}"
        row.setObjectName(_rn)
        row.setStyleSheet(
            f"#{_rn} {{ background-color: #fafafa; border: 1px solid #ececec; border-radius: 8px; }}"
        )
        outer = QHBoxLayout(row)
        outer.setContentsMargins(10, 6, 10, 6)
        outer.setSpacing(14)

        name_lbl = QLabel(name, row)
        name_lbl.setWordWrap(False)
        apply_instructional_tooltip(name, name_lbl, position=ToolTipPosition.BOTTOM)
        # 名称占必要宽度即可，过长省略；不与右侧统计块之间插 stretch，避免宽卡片时出现大块空白
        _name_elide_px = 300
        name_lbl.setMaximumWidth(_name_elide_px + 8)
        name_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 600; color: #333; border: none; background: transparent;"
        )
        name_lbl.setText(
            QFontMetrics(name_lbl.font()).elidedText(
                name, Qt.TextElideMode.ElideRight, _name_elide_px,
            )
        )
        name_lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        outer.addWidget(name_lbl, 0, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        pill_row = QHBoxLayout()
        pill_row.setSpacing(6)
        pill_row.setContentsMargins(0, 0, 0, 0)
        b1, v1 = self._stat_chip(
            "总数",
            f"{self._task_label}总数：该账号/账号组媒体库「{self._task_label} → 未发布」目录中的素材数",
            "#444444", "#f5f5f5", "#ddd", row,
        )
        b2, v2 = self._stat_chip(
            "已用",
            "已占用：发布列表中待发布/失败/执行中任务引用的占用",
            "#e65100", "#fff3e0", "#ffcc80", row,
        )
        b3, v3 = self._stat_chip(
            "可配",
            "未占用：扣除占用后仍可参与自动匹配的数量",
            "#2e7d32", "#e8f5e9", "#a5d6a7", row,
        )
        v1.setText(str(total))
        v2.setText(str(occupied))
        v3.setText(str(available))
        for b in (b1, b2, b3):
            pill_row.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        outer.addLayout(pill_row, 0)
        # 余白留在「名称+统计」整组右侧，数字块紧跟账号名
        outer.addStretch(1)
        return row

    def _render_material_stats_rows(self, rows: List[Tuple[str, int, int, int]]) -> None:
        """按账号分别渲染，不合并总数。"""
        self._clear_material_stats_rows_layout()
        for name, total, occupied, available in rows:
            self._material_stats_rows_layout.addWidget(
                self._create_material_account_row(name, total, occupied, available)
            )

    def _create_task_status_reminder_card(self) -> QWidget:
        from PySide6.QtWidgets import QFrame

        card = CardWidget(self)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QWidget(card)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(0, 0, 0, 6)
        h_lay.setSpacing(0)
        title = QLabel("素材库数量提醒", header)
        title.setObjectName("UnifiedCardTitle")
        h_lay.addWidget(title)
        h_lay.addStretch(1)
        layout.addWidget(header)

        sep = QFrame(card)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("SettingsCardSep")
        layout.addWidget(sep)
        layout.addSpacing(4)

        scroll = SmoothScrollArea(card)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(SmoothScrollArea.Shape.NoFrame)
        scroll.setMinimumHeight(52)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.setStyleSheet("SmoothScrollArea{background:transparent;border:none;}")
        scroll.viewport().setStyleSheet("background:transparent;")

        self._material_stats_rows_host = QWidget(scroll)
        self._material_stats_rows_host.setStyleSheet("background:transparent;")
        self._material_stats_rows_layout = QVBoxLayout(self._material_stats_rows_host)
        self._material_stats_rows_layout.setContentsMargins(0, 0, 0, 0)
        self._material_stats_rows_layout.setSpacing(6)
        scroll.setWidget(self._material_stats_rows_host)
        # 与同行卡片对齐高度时由列表区吃满纵向空间，避免视口过矮把色块裁掉
        layout.addWidget(scroll, stretch=1)

        return card

    def _material_stats_begin_refresh(self) -> Optional[int]:
        """同步刷新磁盘统计并递增 token；返回 token 表示需要再跑发布列表异步段，None 表示已处理或跳过。"""
        if not hasattr(self, "_material_stats_rows_layout"):
            return None
        if not self.selected_accounts:
            self._render_material_stats_message("请先选择账号")
            return None

        from src.infrastructure.common.material_library_manager import MaterialLibraryManager

        if MaterialLibraryManager.get_root_dir() is None:
            self._render_material_stats_message(
                "未配置媒体库路径，请先在「设置」中选择。", warn=True,
            )
            return None

        # 先用缓存快速刷新（避免空白），再异步触发 refresh 获取最新占用数据
        self._update_task_status_from_cache()
        self._material_stats_token += 1
        return self._material_stats_token

    def _refresh_task_status_reminder(self) -> None:
        token = self._material_stats_begin_refresh()
        if token is None:
            return
        # 同步路径：Qt 定时器 + create_task；勿在 @asyncSlot 执行期间触发（见 _on_select_account）
        def _schedule_status_update() -> None:
            self._track_task(asyncio.create_task(self._update_task_status_with_stats_service(token)))

        self._schedule_base_page_timer("batch.update_material_stats", 10, _schedule_status_update)

    async def _refresh_task_status_reminder_async(self) -> None:
        """在 @asyncSlot 内 await，避免与父协程重叠时 create_task 触发 qasync 嵌套任务错误。"""
        token = self._material_stats_begin_refresh()
        if token is None:
            return
        await self._update_task_status_with_stats_service(token)

    def _resolve_selected_owner_counts_from_stats(self, stats) -> List[Tuple[str, int, int, int]]:
        """将选中账号/账号组映射为 (name,total,occupied,available) 行。"""
        matcher = self._get_video_auto_matcher()
        rows: List[Tuple[str, int, int, int]] = []
        if stats is None:
            for acc in self.selected_accounts or []:
                rows.append((matcher.owner_display_name(acc), 0, 0, 0))
            return rows

        media_stats = getattr(stats, "image" if self._media_type == "image" else "video", None)
        video_by_acc = getattr(media_stats, "by_account_id", {}) or {}
        video_by_grp = getattr(media_stats, "by_group_id", {}) or {}

        for acc in self.selected_accounts or []:
            name = matcher.owner_display_name(acc)
            if isinstance(acc, dict) and acc.get("_type") == "group":
                gid = acc.get("group_id") or acc.get("id")
                try:
                    gid_int = int(gid) if gid is not None else None
                except Exception:
                    gid_int = None
                c = video_by_grp.get(gid_int) if gid_int is not None else None
            else:
                aid = acc.get("id") if isinstance(acc, dict) else None
                try:
                    aid_int = int(aid) if aid is not None else None
                except Exception:
                    aid_int = None
                c = video_by_acc.get(aid_int) if aid_int is not None else None
            if c is None:
                rows.append((name, 0, 0, 0))
            else:
                rows.append((name, int(c.total), int(c.used), int(c.unused)))
        return rows

    def _update_task_status_from_cache(self) -> None:
        """先读缓存快速刷新（不扫盘、不查库）。"""
        stats = self._media_stats_cache.get()
        rows = self._resolve_selected_owner_counts_from_stats(stats)
        self._render_material_stats_rows(rows)

    async def _update_task_status_with_stats_service(self, token: int) -> None:
        """异步刷新统计服务后，更新各账号/账号组的总/占用/未占用。"""
        if not hasattr(self, "_material_stats_rows_layout"):
            return
        if not self.selected_accounts:
            return
        if token != self._material_stats_token:
            return
        try:
            stats = await get_media_library_stats_service().refresh()
        except Exception:
            return
        if token != self._material_stats_token:
            return
        rows = self._resolve_selected_owner_counts_from_stats(stats)
        self._render_material_stats_rows(rows)

    def _on_media_stats_updated(self, _stats: object) -> None:
        """当全局统计缓存更新时，若本页可见则同步刷新提醒卡片。"""
        try:
            if hasattr(self, "_material_stats_rows_layout") and self.isVisible():
                self._update_task_status_from_cache()
        except Exception:
            return

    def _persist_publish_description_prefs_from_page(self) -> None:
        base = load_persisted_publish_description_prefs() or {}
        save_persisted_publish_description_prefs(
            {
                "title": self.same_title_text,
                "desc": self.same_desc_text,
                "apply_to_all_tasks": self.apply_description_to_all_tasks,
                "use_library_title": self.use_library_title,
                "use_library_desc": self.use_library_desc,
                "manual_title_backup": str(base.get("manual_title_backup", "") or ""),
                "manual_desc_backup": str(base.get("manual_desc_backup", "") or ""),
                "auto_match_enabled": self.auto_match_enabled,
                "match_mode": self.match_mode or "standard",
                "random_category_id": self.random_category_id,
                "copywriting_assign_strategy": self.copywriting_assign_strategy or AssignStrategy.ROUND_ROBIN.value,
            }
        )

    def _persist_publish_description_prefs_from_page(self) -> None:
        base = load_persisted_publish_description_prefs() or {}
        save_persisted_publish_description_prefs(
            {
                "title": self.same_title_text,
                "desc": self.same_desc_text,
                "apply_to_all_tasks": self.apply_description_to_all_tasks,
                "use_library_title": self.use_library_title,
                "use_library_desc": self.use_library_desc,
                "manual_title_backup": str(base.get("manual_title_backup", "") or ""),
                "manual_desc_backup": str(base.get("manual_desc_backup", "") or ""),
                "auto_match_enabled": self.auto_match_enabled,
                "match_mode": self.match_mode or "standard",
                "random_category_id": self.random_category_id,
                "copywriting_assign_strategy": self.copywriting_assign_strategy or AssignStrategy.ROUND_ROBIN.value,
            }
        )

    def _sync_batch_cover_combo_from_state(self) -> None:
        if not hasattr(self, "_combo_batch_cover"):
            return
        self._combo_batch_cover.blockSignals(True)
        try:
            is_custom = (
                getattr(self, "cover_type", "first_frame") == "custom"
                and (getattr(self, "cover_path", "") or "").strip()
            )
            self._combo_batch_cover.setCurrentIndex(1 if is_custom else 0)
            tip = "使用视频首帧作为封面" if self._media_type == "video" else "使用首张图片作为封面"
            if is_custom:
                tip = f"本地封面：{os.path.basename(self.cover_path)}"
            apply_instructional_tooltip(
                tip, self._combo_batch_cover, position=ToolTipPosition.TOP
            )
        finally:
            self._combo_batch_cover.blockSignals(False)

    def _sync_batch_publish_settings_ui(self, *, video_auto_match: Optional[bool] = None) -> None:
        """刷新批量发布设置卡片上的控件。"""
        if not hasattr(self, "_combo_batch_video"):
            return
        self._combo_batch_video.blockSignals(True)
        self._combo_batch_desc_mode.blockSignals(True)
        self._combo_batch_desc_category.blockSignals(True)
        self._check_batch_use_lib_title.blockSignals(True)
        self._check_batch_use_lib_desc.blockSignals(True)

        try:
            # 1. 视频配置
            use_auto_vid = (
                video_auto_match
                if video_auto_match is not None
                else load_auto_match_pref(self._media_type)
            )
            self._combo_batch_video.setCurrentIndex(0 if use_auto_vid else 1)
            
            # 2. 描述配置 - 模式
            from src.services.copywriting.copywriting_match_service import CopywritingMatchMode
            mode = self.match_mode if self.auto_match_enabled else CopywritingMatchMode.NONE
            target_mode_idx = 0
            for i in range(self._combo_batch_desc_mode.count()):
                if self._combo_batch_desc_mode.itemData(i) == mode:
                    target_mode_idx = i
                    break
            self._combo_batch_desc_mode.setCurrentIndex(target_mode_idx)
            
            # 3. 描述配置 - 分类 (显隐与选中)
            is_cat_mode = (mode == CopywritingMatchMode.RANDOM_CATEGORY)
            self._combo_batch_desc_category.setVisible(is_cat_mode)
            if is_cat_mode:
                # 若分类列表为空，尝试触发一次刷新
                if self._combo_batch_desc_category.count() <= 1:
                    self._refresh_batch_desc_categories()
                else:
                    target_cat_idx = 0
                    for i in range(self._combo_batch_desc_category.count()):
                        if self._combo_batch_desc_category.itemData(i) == self.random_category_id:
                            target_cat_idx = i
                            break
                    self._combo_batch_desc_category.setCurrentIndex(target_cat_idx)
            
            # 4. 描述配置 - 内容勾选
            self._check_batch_use_lib_title.setChecked(self.use_library_title)
            self._check_batch_use_lib_desc.setChecked(self.use_library_desc)
            # 非手动模式才允许勾选标题/描述来源（手动模式下由于是直接输入，这两个勾选无意义，但在弹窗逻辑中它们控制回填）
            # 根据用户需求，这里保持启用即可，与弹窗同步
            self._check_batch_use_lib_title.setEnabled(mode != CopywritingMatchMode.NONE)
            self._check_batch_use_lib_desc.setEnabled(mode != CopywritingMatchMode.NONE)

            self._sync_batch_cover_combo_from_state()
        finally:
            self._combo_batch_video.blockSignals(False)
            self._combo_batch_desc_mode.blockSignals(False)
            self._combo_batch_desc_category.blockSignals(False)
            self._check_batch_use_lib_title.blockSignals(False)
            self._check_batch_use_lib_desc.blockSignals(False)

    def _on_batch_video_combo_changed(self, _index: int) -> None:
        auto = self._combo_batch_video.currentIndex() == 0
        save_auto_match_pref(auto, self._media_type)
        if auto:
            self._schedule_auto_match_if_enabled(force_run=True)

    @asyncSlot()
    async def _refresh_batch_desc_categories(self) -> None:
        """异步加载描述配置中的随机分类列表。"""
        from src.infrastructure.storage.repositories.random_copywriting_repository import RandomCopywritingRepository
        try:
            cats = await RandomCopywritingRepository.list_categories()
            self._combo_batch_desc_category.blockSignals(True)
            self._combo_batch_desc_category.clear()
            self._combo_batch_desc_category.addItem("选择分类...", userData=None)
            target_idx = 0
            for i, cat in enumerate(cats, start=1):
                self._combo_batch_desc_category.addItem(cat["name"], userData=cat["id"])
                if cat["id"] == self.random_category_id:
                    target_idx = i
            self._combo_batch_desc_category.setCurrentIndex(target_idx)
            self._combo_batch_desc_category.blockSignals(False)
        except Exception as e:
            logger.error("卡片加载随机分类失败: %s", e)

    def _on_batch_desc_mode_changed(self, _index: int) -> None:
        from src.services.copywriting.copywriting_match_service import CopywritingMatchMode
        mode = self._combo_batch_desc_mode.currentData()
        
        self.auto_match_enabled = (mode != CopywritingMatchMode.NONE)
        if self.auto_match_enabled:
            self.match_mode = mode.value if hasattr(mode, 'value') else str(mode)
            
        # 显隐分类
        is_cat = (mode == CopywritingMatchMode.RANDOM_CATEGORY)
        self._combo_batch_desc_category.setVisible(is_cat)
        if is_cat:
            self._refresh_batch_desc_categories()
            
        # 联动勾选：开启自动匹配时，默认勾选标题和描述（若之前全没勾）
        if self.auto_match_enabled and not (self.use_library_title or self.use_library_desc):
            self.use_library_title = True
            self.use_library_desc = True
            
        self._after_desc_setting_changed_on_page()
        
        # 手动：弹出配置描述便于填写
        if mode == CopywritingMatchMode.NONE:
            self._schedule_base_page_timer(
                "batch.open_publish_description_dialog",
                100,
                self._open_publish_description_dialog,
            )

    def _on_batch_desc_category_changed(self, _index: int) -> None:
        cat_id = self._combo_batch_desc_category.currentData()
        self.random_category_id = cat_id
        self._after_desc_setting_changed_on_page()

    def _on_batch_desc_content_checks_changed(self, _state: int) -> None:
        self.use_library_title = self._check_batch_use_lib_title.isChecked()
        self.use_library_desc = self._check_batch_use_lib_desc.isChecked()
        self._after_desc_setting_changed_on_page()

    def _after_desc_setting_changed_on_page(self) -> None:
        """卡片描述配置变更后的统一处理：同步 UI、持久化、重算预览。"""
        self._sync_batch_publish_settings_ui()
        self._persist_publish_description_prefs_from_page()
        from src.ui.publish.work_description import clear_publish_description_dialog_session
        from src.ui.utils.async_helper import run_async_from_ui
        
        # 清理会话避免弹窗打开时旧数据回刷
        clear_publish_description_dialog_session()
        run_async_from_ui(self._after_publish_description_dialog_accepted)

    def _on_batch_cover_combo_changed(self, index: int) -> None:
        if index == 0:
            self.cover_type = "first_frame"
            self.cover_path = ""
            self._sync_batch_cover_combo_from_state()
            self._schedule_preview_refresh()
            return

        from src.pro_features.batch.dialogs.publish_cover_dialog import PublishCoverDialog

        dialog = PublishCoverDialog(
            initial_cover_type=getattr(self, "cover_type", "first_frame"),
            initial_cover_path=getattr(self, "cover_path", ""),
            parent=self.window() or self,
        )
        if dialog.exec() == int(QDialog.DialogCode.Accepted):
            self.cover_type, self.cover_path = dialog.get_cover_settings()
            self._sync_batch_cover_combo_from_state()
            self._schedule_preview_refresh()
        else:
            self._combo_batch_cover.blockSignals(True)
            self._sync_batch_cover_combo_from_state()
            self._combo_batch_cover.blockSignals(False)

    def _on_music_settings_clicked(self) -> None:
        """批量图文音乐设置；当前仅支持随机音乐。"""
        if self._media_type != "image":
            return

        dlg = AppMessageBoxBase(self.window() or self, header_title="音乐设置")
        hint = BodyLabel("当前仅支持随机音乐设置", dlg)
        hint.setWordWrap(True)
        dlg.viewLayout.addWidget(hint)

        chk_random = CheckBox("随机音乐", dlg)
        current = (getattr(self, "music_info", "") or "").strip()
        checked = False
        if current:
            try:
                md = json.loads(current)
                checked = isinstance(md, dict) and md.get("music_type") == "random"
            except (json.JSONDecodeError, TypeError):
                checked = False
        chk_random.setChecked(checked)
        dlg.viewLayout.addWidget(chk_random)

        dlg.yesButton.setText("确定")
        dlg.cancelButton.setText("取消")
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return

        if chk_random.isChecked():
            self.music_info = json.dumps({"music_type": "random"}, ensure_ascii=False)
        else:
            self.music_info = ""
        self._sync_music_settings_button_state()
        self._schedule_preview_refresh()

    def _sync_music_settings_button_state(self) -> None:
        btn = getattr(self, "_btn_music_settings", None)
        if btn is None:
            return
        has_music = bool((getattr(self, "music_info", "") or "").strip())
        btn.setText("音乐设置：随机" if has_music else "音乐设置")
        apply_instructional_tooltip(
            "已启用随机音乐" if has_music else "设置图文任务音乐；当前仅支持随机音乐",
            btn,
            position=ToolTipPosition.BOTTOM,
        )

    def _on_work_declaration_clicked(self) -> None:
        from src.pro_features.batch.dialogs.work_declaration_dialog import (
            show_work_declaration_dialog,
        )

        r = show_work_declaration_dialog(
            douyin_value=getattr(self, "douyin_work_declaration", ""),
            kuaishou_value=getattr(self, "kuaishou_work_declaration", ""),
            douyin_auto=bool(getattr(self, "douyin_work_declaration_auto", False)),
            kuaishou_auto=bool(getattr(self, "kuaishou_work_declaration_auto", False)),
            wechat_is_original=bool(getattr(self, "declare_original_checked", True)),
            xhs_is_original=bool(getattr(self, "xiaohongshu_is_original", False)),
            xhs_content_attr=getattr(self, "xiaohongshu_content_attribute", "") or "",
            xhs_content_attr_auto=bool(
                getattr(self, "xiaohongshu_content_attribute_auto", False)
            ),
            parent=self.window() or self,
        )
        if r is None:
            return
        dy, ks, wx_orig, dy_auto, ks_auto, xhs_o, xhs_attr, xhs_attr_auto = r
        self.douyin_work_declaration = dy
        self.kuaishou_work_declaration = ks
        self.declare_original_checked = wx_orig
        self.douyin_work_declaration_auto = dy_auto
        self.kuaishou_work_declaration_auto = ks_auto
        self.xiaohongshu_is_original = xhs_o
        self.xiaohongshu_content_attribute = xhs_attr
        self.xiaohongshu_content_attribute_auto = xhs_attr_auto
        save_persisted_work_declaration({
            KEY_DOUYIN: dy,
            KEY_KUAISHOU: ks,
            KEY_DOUYIN_AUTO: dy_auto,
            KEY_KUAISHOU_AUTO: ks_auto,
            KEY_XHS_ORIGINAL: xhs_o,
            KEY_XHS_CONTENT_ATTR: xhs_attr,
            KEY_XHS_CONTENT_ATTR_AUTO: xhs_attr_auto,
        })
        save_persisted_declare_original(wx_orig)
        self._schedule_preview_refresh()

    def _on_batch_location_check_changed(self, _state: int = 0) -> None:
        """未勾选：清空位置与视频号空位策略；勾选：弹出位置设置弹窗。"""
        chk = getattr(self, "_chk_batch_location", None)
        if chk is None:
            return
        if not chk.isChecked():
            self.location_text = ""
            self._batch_wechat_empty_location_open_picker = False
            save_batch_location_prefs("", False)
            self._schedule_preview_refresh()
            return

        from src.ui.publish.location import BatchLocationDialog
        from src.domain.publish.location_settings import parse_poi_info_storage

        dlg = BatchLocationDialog(
            self.window() or self,
            poi_info_initial=getattr(self, "location_text", "") or "",
            wx_pick_initial=self._batch_wechat_empty_location_open_picker,
            show_wechat_no_poi_subchoice=True,
        )
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
            return

        poi, wx = dlg.outcome()
        self.location_text = poi or ""
        self._batch_wechat_empty_location_open_picker = (
            wx if wx is not None else False
        )
        save_batch_location_prefs(
            self.location_text,
            self._batch_wechat_empty_location_open_picker,
        )
        loc_t, _ = parse_poi_info_storage(self.location_text or "")
        has_poi = bool((loc_t or "").strip())
        wx_hide = self._batch_wechat_empty_location_open_picker is True
        if not has_poi and not wx_hide:
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
        self._schedule_preview_refresh()

    def _yellow_cart_short_name_from_goods_text(self) -> str:
        """从 cart_info 存储串解析购物车商品简称（与单条页 JSON 标记一致）。"""
        s = (getattr(self, "goods_text", "") or "").strip()
        if not s.startswith("{"):
            return ""
        try:
            d = json.loads(s)
            if isinstance(d, dict):
                return (d.get("cart_short_name") or d.get("yellow_cart_short_name") or "").strip()
        except (json.JSONDecodeError, TypeError):
            pass
        return ""

    def _on_batch_yellow_cart_check_changed(self, _state: int = 0) -> None:
        """未勾选：清空购物车；勾选：弹出设置弹窗（取消或未选商品则恢复未勾选）。"""
        chk = getattr(self, "_chk_batch_yellow_cart", None)
        if chk is None:
            return
        if not chk.isChecked():
            self.goods_text = ""
            self._update_batch_promotion_summary_labels()
            self._schedule_preview_refresh()
            return

        from src.ui.publish.promotion.batch_cart_dialog import BatchCartDialog

        initial = self._yellow_cart_short_name_from_goods_text()
        dlg = BatchCartDialog(
            self.window() or self,
            initial_short_name=initial,
        )
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
            return

        gjson = dlg.outcome()
        self.goods_text = gjson or ""
        if not (self.goods_text or "").strip():
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
            self._update_batch_promotion_summary_labels()
            self._schedule_preview_refresh()
            return

        if (self.goods_text or "").strip():
            self.anchor_text = ""
        self._update_batch_promotion_summary_labels()
        self._schedule_preview_refresh()

    def _on_batch_group_buy_check_changed(self, _state: int = 0) -> None:
        """未勾选：清空团购；勾选：弹出设置弹窗（取消或主内容为空则恢复未勾选）。"""
        chk = getattr(self, "_chk_batch_group_buy", None)
        if chk is None:
            return
        if not chk.isChecked():
            self.anchor_text = ""
            self._update_batch_promotion_summary_labels()
            self._schedule_preview_refresh()
            return

        from src.ui.publish.promotion.batch_group_buy_dialog import BatchGroupBuyDialog

        dlg = BatchGroupBuyDialog(
            self.window() or self,
            anchor_info_initial=getattr(self, "anchor_text", "") or "",
        )
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
            return

        self.anchor_text = dlg.outcome() or ""
        if not (self.anchor_text or "").strip():
            chk.blockSignals(True)
            chk.setChecked(False)
            chk.blockSignals(False)
            self._update_batch_promotion_summary_labels()
            self._schedule_preview_refresh()
            return

        if (self.anchor_text or "").strip():
            self.goods_text = ""
        self._update_batch_promotion_summary_labels()
        self._schedule_preview_refresh()

    def _update_batch_promotion_summary_labels(self) -> None:
        if getattr(self, "_lbl_batch_yellow_cart_summary", None):
            from src.domain.publish.promotion_settings.cart import (
                cart_preview_display,
            )

            g = (getattr(self, "goods_text", "") or "").strip()
            disp = cart_preview_display(g)
            if disp:
                self._lbl_batch_yellow_cart_summary.setText(f"已选：{disp}")
            elif g:
                self._lbl_batch_yellow_cart_summary.setText("已配置")
            else:
                self._lbl_batch_yellow_cart_summary.setText("")
        if getattr(self, "_lbl_batch_group_buy_summary", None):
            a = (getattr(self, "anchor_text", "") or "").strip()
            if not a:
                self._lbl_batch_group_buy_summary.setText("")
            else:
                disp = a if len(a) <= 14 else a[:11] + "…"
                self._lbl_batch_group_buy_summary.setText(disp)

        chk_yc = getattr(self, "_chk_batch_yellow_cart", None)
        chk_gb = getattr(self, "_chk_batch_group_buy", None)
        g_set = bool((getattr(self, "goods_text", "") or "").strip())
        a_set = bool((getattr(self, "anchor_text", "") or "").strip())

        if chk_yc:
            want_yc = g_set
            if chk_yc.isChecked() != want_yc:
                chk_yc.blockSignals(True)
                chk_yc.setChecked(want_yc)
                chk_yc.blockSignals(False)
        if chk_gb:
            want_gb = a_set
            if chk_gb.isChecked() != want_gb:
                chk_gb.blockSignals(True)
                chk_gb.setChecked(want_gb)
                chk_gb.blockSignals(False)

        # 购物车与团购互斥：已配置一侧则禁用另一侧复选框；两侧异常同时有值时仍可勾选修正
        if chk_yc and chk_gb:
            if g_set and a_set:
                chk_yc.setEnabled(True)
                chk_gb.setEnabled(True)
            else:
                chk_gb.setEnabled(not g_set)
                chk_yc.setEnabled(not a_set)
            _yc_tip_on = (
                "勾选后弹出设置：从购物车推广商品库选择商品；"
                f"商品短标题仅存于购物车数据，与作品简介分开配置；"
                "取消勾选表示不挂载购物车。"
            )
            _tuan_tip_on = (
                "勾选后弹出设置：填写团购主内容与推广标题；取消勾选表示不挂载团购。"
            )
            if not chk_yc.isEnabled():
                _t_yc = "已配置团购，请先取消勾选「团购」后再使用购物车。"
            else:
                _t_yc = _yc_tip_on
            if not chk_gb.isEnabled():
                _t_gb = "已配置购物车，请先取消勾选「购物车」后再使用团购。"
            else:
                _t_gb = _tuan_tip_on
            apply_instructional_tooltip(
                _t_yc, chk_yc, position=ToolTipPosition.BOTTOM
            )
            apply_instructional_tooltip(
                _t_gb, chk_gb, position=ToolTipPosition.BOTTOM
            )


    def _create_batch_publish_settings_card(self) -> QWidget:
        """与「待发布」页发布设置卡片同系的批量选项：视频/描述匹配方式、原创、封面摘要。"""
        from PySide6.QtWidgets import QFrame

        card = CardWidget(self)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(card)
        # 与素材提醒卡片保持完全一致的内边距与顶端对齐，以防分割线错位
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        label_w = 72

        # 统一的标题头部区域（与素材提醒卡片结构一致）
        header = QWidget(card)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(0, 0, 0, 6)
        h_lay.setSpacing(0)
        title = QLabel("批量发布设置", header)
        title.setObjectName("UnifiedCardTitle")
        h_lay.addWidget(title)
        h_lay.addStretch(1)
        layout.addWidget(header)

        sep = QFrame(card)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("SettingsCardSep")
        layout.addWidget(sep)
        layout.addSpacing(10)  # 分隔线与内容之间的间距

        video_row = QHBoxLayout()
        video_row.setSpacing(12)
        v_lab = BodyLabel(f"{self._task_label}配置", card)
        v_lab.setFixedWidth(label_w)
        self._combo_batch_video = ComboBox(card)
        self._combo_batch_video.addItems(["自动匹配", "手动匹配"])
        self._combo_batch_video.setMinimumWidth(160)
        self._combo_batch_video.setFixedHeight(32)
        _tip_vid = (
            f"自动匹配：选账号或添加{self._media_label}时，从各账号媒体库「{self._task_label} → 未发布」拉取素材\n"
            f"手动匹配：仅从「添加{self._media_label}」手动选择或从库挑选，不自动批量拉取"
        )
        apply_instructional_tooltip(
            _tip_vid,
            v_lab,
            self._combo_batch_video,
            position=ToolTipPosition.TOP,
        )
        self._combo_batch_video.currentIndexChanged.connect(self._on_batch_video_combo_changed)
        video_row.addWidget(v_lab)
        video_row.addWidget(self._combo_batch_video, 0, Qt.AlignmentFlag.AlignLeft)
        video_row.addStretch(1)
        layout.addLayout(video_row)
        layout.addSpacing(14)

        # --- 第1行：描述来源 ---
        desc_row1 = QHBoxLayout()
        desc_row1.setSpacing(12)
        d_lab1 = BodyLabel("描述来源", card)
        d_lab1.setFixedWidth(label_w)
        
        # 1. 匹配模式下拉框
        self._combo_batch_desc_mode = ComboBox(card)
        # 注意：UserData 需要与 CopywritingMatchMode 常量一致
        from src.services.copywriting.copywriting_match_service import CopywritingMatchMode
        self._combo_batch_desc_mode.addItem("手动配置", userData=CopywritingMatchMode.NONE)
        self._combo_batch_desc_mode.addItem("自动标准库 (按编号)", userData=CopywritingMatchMode.STANDARD)
        self._combo_batch_desc_mode.addItem("自动随机库 (全库)", userData=CopywritingMatchMode.RANDOM_ALL)
        self._combo_batch_desc_mode.addItem("自动随机库 (指定分类)", userData=CopywritingMatchMode.RANDOM_CATEGORY)
        self._combo_batch_desc_mode.setMinimumWidth(150)
        self._combo_batch_desc_mode.setFixedHeight(32)
        self._combo_batch_desc_mode.currentIndexChanged.connect(self._on_batch_desc_mode_changed)
        
        # 2. 分类下拉框 (默认隐藏)
        self._combo_batch_desc_category = ComboBox(card)
        self._combo_batch_desc_category.setMinimumWidth(110)
        self._combo_batch_desc_category.setFixedHeight(32)
        self._combo_batch_desc_category.setVisible(False)
        self._combo_batch_desc_category.currentIndexChanged.connect(self._on_batch_desc_category_changed)
        
        desc_row1.addWidget(d_lab1)
        desc_row1.addWidget(self._combo_batch_desc_mode, 0, Qt.AlignmentFlag.AlignLeft)
        desc_row1.addWidget(self._combo_batch_desc_category, 0, Qt.AlignmentFlag.AlignLeft)
        desc_row1.addStretch(1)
        layout.addLayout(desc_row1)
        layout.addSpacing(14)

        # --- 第2行：应用范围 ---
        desc_row2 = QHBoxLayout()
        desc_row2.setSpacing(12)
        d_lab2 = BodyLabel("应用范围", card)
        d_lab2.setFixedWidth(label_w)

        # 3. 内容勾选框 (标题/描述)
        self._check_batch_use_lib_title = CheckBox("作品标题", card)
        self._check_batch_use_lib_desc = CheckBox("作品简介", card)
        self._check_batch_use_lib_title.stateChanged.connect(self._on_batch_desc_content_checks_changed)
        self._check_batch_use_lib_desc.stateChanged.connect(self._on_batch_desc_content_checks_changed)
        
        desc_row2.addWidget(d_lab2)
        desc_row2.addWidget(self._check_batch_use_lib_title)
        desc_row2.addSpacing(4)
        desc_row2.addWidget(self._check_batch_use_lib_desc)
        desc_row2.addStretch(1)
        layout.addLayout(desc_row2)
        layout.addSpacing(14)

        cover_row = QHBoxLayout()
        cover_row.setSpacing(12)
        c_lab = BodyLabel("封面配置", card)
        c_lab.setFixedWidth(label_w)
        self._combo_batch_cover = ComboBox(card)
        self._combo_batch_cover.addItems(["视频首帧" if self._media_type == "video" else "首张图片", "本地图片"])
        self._combo_batch_cover.setMinimumWidth(160)
        self._combo_batch_cover.setFixedHeight(32)
        _tip_cov = (
            ("视频首帧：发布时使用视频第一帧\n" if self._media_type == "video" else "首张图片：发布时使用图文素材首图\n")
            + "本地图片：打开封面设置，可选择或更换本地封面图"
        )
        apply_instructional_tooltip(
            _tip_cov,
            c_lab,
            self._combo_batch_cover,
            position=ToolTipPosition.TOP,
        )
        self._combo_batch_cover.currentIndexChanged.connect(self._on_batch_cover_combo_changed)
        cover_row.addWidget(c_lab)
        cover_row.addWidget(self._combo_batch_cover, 0, Qt.AlignmentFlag.AlignLeft)
        cover_row.addStretch(1)
        layout.addLayout(cover_row)

        self._sync_batch_publish_settings_ui()
        return card

    # ==================================================================
    # 7. 第三排操作按钮
    # ==================================================================

    def _create_action_buttons_card(self) -> QWidget:
        """快捷操作：删除预览任务 / 发布纵向排列（与素材提醒同排）；进度与结果用 InfoBar。"""
        from PySide6.QtWidgets import QFrame

        card = CardWidget(self)
        # 垂直策略改为 Expanding，确保在 QHBoxLayout 中与其他卡片等高拉伸
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(card)
        # 与素材提醒卡片保持一致的内边距并保持顶对齐以对齐标题和分割线
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 统一的标题头部区域
        header = QWidget(card)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(0, 0, 0, 6)
        h_lay.setSpacing(0)
        title_lbl = QLabel("快捷操作功能", header)
        title_lbl.setObjectName("UnifiedCardTitle")
        h_lay.addWidget(title_lbl)
        h_lay.addStretch(1)
        layout.addWidget(header)

        sep = QFrame(card)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("SettingsCardSep")
        layout.addWidget(sep)
        layout.addSpacing(8)

        # 内容区：使用独立容器承载按钮
        content = QWidget(card)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 按钮1：清空视频
        self.btn_clear_videos = PushButton(FluentIcon.DELETE, f"清空{self._task_label}", content)
        self.btn_clear_videos.setFixedHeight(32)
        self.btn_clear_videos.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )
        apply_instructional_tooltip(
            f"仅清空{self._task_label}与描述配置，不清空账号和发布时间。",
            self.btn_clear_videos,
            position=ToolTipPosition.BOTTOM,
        )
        self.btn_clear_videos.clicked.connect(self._on_clear_videos_only)
        content_layout.addWidget(self.btn_clear_videos)

        # 按钮2：删除选中任务
        self.btn_delete_preview_tasks = PushButton(FluentIcon.DELETE, "删除选中", content)
        self.btn_delete_preview_tasks.setFixedHeight(32)
        self.btn_delete_preview_tasks.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )
        _tip_del_sel = (
            f"从预览中移除选中任务（不写回发布列表）；不取消已选账号、不删除本地{self._task_label}素材。"
            "快捷键：Delete / Backspace"
        )
        apply_instructional_tooltip(
            _tip_del_sel,
            self.btn_delete_preview_tasks,
            position=ToolTipPosition.BOTTOM,
        )
        self.btn_delete_preview_tasks.clicked.connect(self._on_preview_delete_selected)
        content_layout.addWidget(self.btn_delete_preview_tasks)

        # 按钮3：删除全部任务
        self.btn_clear = PushButton(FluentIcon.DELETE, "删除全部", content)
        self.btn_clear.setFixedHeight(32)
        self.btn_clear.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )
        _tip_clr = (
            f"从预览中移除当前表格里的全部任务（无需选中行）；不取消已选账号、不删除本地{self._task_label}素材。"
        )
        apply_instructional_tooltip(
            _tip_clr, self.btn_clear, position=ToolTipPosition.BOTTOM
        )
        self.btn_clear.clicked.connect(self._on_preview_delete_all)
        content_layout.addWidget(self.btn_clear)

        # 按钮4：添加到发布列表（主操作按钮，突出显示）
        self.btn_publish = PrimaryPushButton(FluentIcon.ADD, "添加到发布列表", content)
        self.btn_publish.setFixedHeight(32)
        self.btn_publish.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed,
        )
        self.btn_publish.clicked.connect(self._on_batch_publish)
        content_layout.addWidget(self.btn_publish)

        # content 充满卡片剩余纵向空间
        layout.addWidget(content, 1)

        return card


    # ==================================================================
    # 8. 任务预览卡片
    # ==================================================================

    def _create_preview_card(self) -> QWidget:
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        # 与 publish_records_page 中表格外层 Card 一致：表区域零边距，无「任务预览」标题栏
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.preview_table = RubberBandRowSelectTable(card)
        self.preview_table.setWordWrap(False)
        self.preview_table.setColumnCount(11)
        self.preview_table.setHorizontalHeaderLabels([
            "平台", "平台昵称", "文件", "封面", "作品标题", "作品简介", "发布时间", "作品申明", "购物车", "团购", "位置"
        ])
        # RubberBandRowSelectTable.__init__ 已内置左右 2px；此处收紧上下内边距以压缩行高
        self.preview_table.setObjectName("BatchPreviewTable")
        self.preview_table.setStyleSheet(
            self.preview_table.styleSheet()
            + "\nQTableView::item { padding: 0px 2px; }\n"
        )
        header = self.preview_table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        header.setFixedHeight(30)
        # 各列均可拖拽表头边界调整宽度
        for col in range(self.preview_table.columnCount()):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(55)
        _vh = self.preview_table.verticalHeader()
        _vh.setDefaultSectionSize(BATCH_PREVIEW_TABLE_ROW_HEIGHT)
        _vh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        self.preview_table.setColumnWidth(0, 90)   # 平台
        self.preview_table.setColumnWidth(1, 110)  # 平台昵称
        self.preview_table.setColumnWidth(2, 190)  # 文件（文件名通常较长）
        self.preview_table.setColumnWidth(3, 70)   # 封面
        self.preview_table.setColumnWidth(4, 160)  # 作品标题
        self.preview_table.setColumnWidth(5, 190)  # 作品简介
        self.preview_table.setColumnWidth(6, 130)  # 发布时间（含日期+时间）
        self.preview_table.setColumnWidth(7, 118)  # 作品申明
        self.preview_table.setColumnWidth(8, 120)  # 购物车    短标题/✅/—
        self.preview_table.setColumnWidth(9, 60)   # 团购      ✅/—
        self.preview_table.setColumnWidth(10, 80)  # 位置
        self.preview_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.preview_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.preview_table.customContextMenuRequested.connect(self._on_preview_context_menu)
        # 选中行后按 Delete 删除（与「删除选中任务」按钮一致）
        del_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.preview_table)
        del_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        del_shortcut.activated.connect(self._on_preview_delete_selected)
        # 部分键盘布局下退格键也用于删除选中项
        bs_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Backspace), self.preview_table)
        bs_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        bs_shortcut.activated.connect(self._on_preview_delete_selected)
        # 使用左侧行号展示"序号"（与发布管理页一致）
        self.preview_table.verticalHeader().setVisible(True)
        self.preview_table.setMinimumHeight(360)
        # 勿对整表 setToolTip：在 Fluent/深色主题下易出现黑底长条提示，遮挡表格
        layout.addWidget(self.preview_table, 1)

        # 下部：任务统计栏（彩色徽章 + 状态 + 已选行数）
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(12, 8, 12, 10)
        footer_layout.setSpacing(8)

        pill_colors = {
            "task":    ("#0078D4", "rgba(0,120,212,0.10)",  "rgba(0,120,212,0.18)"),
            "account": ("#107C10", "rgba(16,124,16,0.10)",  "rgba(16,124,16,0.18)"),
            "video":   ("#8764B8", "rgba(135,100,184,0.10)","rgba(135,100,184,0.18)"),
            "time":    ("#F7630C", "rgba(247,99,12,0.10)",  "rgba(247,99,12,0.18)"),
        }
        from qfluentwidgets import isDarkTheme
        _dark = isDarkTheme()
        self._stat_pills: dict[str, QLabel] = {}
        for key, (fg, bg_light, bg_dark) in pill_colors.items():
            lbl = QLabel(card)
            lbl.setFixedHeight(24)
            bg = bg_dark if _dark else bg_light
            lbl.setStyleSheet(
                f"QLabel{{background:{bg};color:{fg};border-radius:12px;"
                f"padding:2px 12px;font-size:12px;font-weight:500;}}"
            )
            footer_layout.addWidget(lbl)
            self._stat_pills[key] = lbl

        self._stat_status_label = QLabel(card)
        self._stat_status_label.setStyleSheet(
            "QLabel{color:#C42B1C;font-size:12px;font-weight:500;padding:0 4px;}"
        )
        footer_layout.addWidget(self._stat_status_label)

        self.preview_selection_count_label = QLabel(card)
        self.preview_selection_count_label.setFixedHeight(24)
        sel_fg = "#C42B1C" if not _dark else "#FF6B5B"
        sel_bg = "rgba(196,43,28,0.10)" if not _dark else "rgba(255,107,91,0.18)"
        self.preview_selection_count_label.setStyleSheet(
            f"QLabel{{background:{sel_bg};color:{sel_fg};border-radius:12px;"
            f"padding:2px 12px;font-size:12px;font-weight:700;}}"
        )
        self.preview_selection_count_label.setVisible(False)
        footer_layout.addWidget(self.preview_selection_count_label)

        footer_layout.addStretch(1)

        self._update_preview_stats(0, 0, 0, 0, "")
        layout.addLayout(footer_layout)

        _psm = self.preview_table.selectionModel()
        if _psm is not None:
            _psm.selectionChanged.connect(self._update_preview_selection_badge)
        self._preview_ctx_menu = BatchPreviewContextMenu(self)
        self._update_preview_selection_badge()

        return card

    def _update_preview_stats(
        self,
        n_tasks: int,
        n_acc: int,
        n_vid: int,
        n_time: int,
        status_text: str,
        *,
        time_pill_text: Optional[str] = None,
    ) -> None:
        """刷新预览表底部的统计徽章。"""
        time_label = time_pill_text if time_pill_text is not None else f"{n_time} 个时间点"
        mapping = {
            "task":    f"{n_tasks} 条任务",
            "account": f"{n_acc} 个账号",
            "video":   f"{n_vid} 个{self._task_label}",
            "time":    time_label,
        }
        for key, text in mapping.items():
            pill = self._stat_pills.get(key)
            if pill is not None:
                pill.setText(text)
        self._stat_status_label.setText(status_text)
        self._stat_status_label.setVisible(bool(status_text))

    def _account_entry_is_wechat_video(self, acc: Optional[dict]) -> bool:
        if not acc:
            return False
        return platform_id_is_wechat_video(acc.get("platform"))

    @staticmethod
    def _account_entry_platform_equals(acc: Optional[dict], platform_id: str) -> bool:
        if not acc:
            return False
        return (acc.get("platform") or "").strip() == platform_id

    def _group_placeholder_has_platform(self, acc: dict, platform_id: str) -> bool:
        """账号组占位行是否包含指定平台（用于预览「作品申明」列）。"""
        if acc.get("_type") != "group":
            return False
        gd = acc.get("_group_data") or {}
        for p in gd.get("platforms") or []:
            if str(p).strip() == platform_id:
                return True
        for m in gd.get("accounts") or []:
            if self._account_entry_platform_equals(m, platform_id):
                return True
        gid = acc.get("group_id")
        if gid is None:
            return False
        for g in getattr(self, "_cached_groups", None) or []:
            if not self._batch_group_id_match(g, gid):
                continue
            for p in g.get("platforms") or []:
                if str(p).strip() == platform_id:
                    return True
            for m in g.get("accounts") or []:
                if self._account_entry_platform_equals(m, platform_id):
                    return True
            break
        return False

    @staticmethod
    def _batch_group_id_match(cached: dict, gid) -> bool:
        """组 id 在缓存里可能是 int/str，避免 == 误判导致漏判/错判。"""
        if gid is None or not isinstance(cached, dict):
            return False
        for key in ("id", "group_id"):
            v = cached.get(key)
            if v is None:
                continue
            if v == gid:
                return True
            try:
                if int(v) == int(gid):
                    return True
            except (TypeError, ValueError):
                if str(v).strip() == str(gid).strip():
                    return True
        return False

    def _group_placeholder_has_wechat_video(self, acc: dict) -> bool:
        if acc.get("_type") != "group":
            return False
        gd = acc.get("_group_data") or {}
        for p in gd.get("platforms") or []:
            if platform_id_is_wechat_video(p):
                return True
        for m in gd.get("accounts") or []:
            if self._account_entry_is_wechat_video(m):
                return True
        gid = acc.get("group_id")
        if gid is None:
            return False
        for g in getattr(self, "_cached_groups", None) or []:
            if not self._batch_group_id_match(g, gid):
                continue
            for p in g.get("platforms") or []:
                if platform_id_is_wechat_video(p):
                    return True
            for m in g.get("accounts") or []:
                if self._account_entry_is_wechat_video(m):
                    return True
            break
        return False

    def _selected_targets_include_wechat_video(self) -> bool:
        for acc in self.selected_accounts:
            if acc.get("_type") == "group":
                if self._group_placeholder_has_wechat_video(acc):
                    return True
            elif self._account_entry_is_wechat_video(acc):
                return True
        return False

    def _preview_time_column_text(self, task: dict) -> str:
        """与发布列表「定时时间」一致：待配置 / 具体排期 / 立即发布；不出现空白单元格。"""
        st = task.get("scheduled_publish_time")
        if st == "待配置" or (isinstance(st, str) and st.strip() == "待配置"):
            return "待配置"
        formatted = format_schedule_time_st_str(st)
        if formatted:
            return formatted
        return "立即发布"

    def _preview_work_declaration_texts(self, task: dict) -> Tuple[str, str]:
        """预览「作品申明」列：(省略显示, 完整 Tooltip 文案)。"""
        raw_ps = task.get("privacy_settings") or "{}"
        ps = parse_privacy_settings_dict(raw_ps)
        plat = str(task.get("platform") or "")
        if plat == "account_group":
            acc_like = task
            full = format_work_declaration_preview_cell(
                plat,
                ps,
                account_group_includes_wechat=self._group_placeholder_has_wechat_video(acc_like),
                account_group_includes_douyin=self._group_placeholder_has_platform(acc_like, "douyin"),
                account_group_includes_kuaishou=self._group_placeholder_has_platform(acc_like, "kuaishou"),
                account_group_includes_xiaohongshu=self._group_placeholder_has_platform(
                    acc_like, "xiaohongshu"
                ),
                empty_display=TASK_FIELD_EMPTY_DISPLAY,
            )
        else:
            full = format_work_declaration_table_cell(
                plat, raw_ps, empty_display=TASK_FIELD_EMPTY_DISPLAY,
            )
        return ellipsize(full, 14), full

    def _preview_account_selection_key(self, acc: dict) -> Tuple[str, str]:
        """与任务 dict 中 platform / platform_username 一致，用于预览排除。"""
        return (
            str(acc.get("platform") or ""),
            str(acc.get("platform_username") or ""),
        )

    def _preview_placeholder_media_time_pair(self, row: int) -> Tuple[str, str]:
        """未选账号时，第 row 行占位对应的 (file_path, sched_str)，与指纹后两段对齐。"""
        n_vid = len(self.video_list)
        n_time = len(self.time_slots)
        path = str((self.video_list[row].get("file_path") or "")) if row < n_vid else ""
        if row < n_time:
            slot = self.time_slots[row]
            st = "立即发布" if slot is None else slot
        else:
            st = "待配置"
        return (path, st)

    def _preview_task_is_excluded(self, task: dict) -> bool:
        """该任务是否被用户从预览中移除（不参与预览行与写入发布列表）。"""
        return self._preview_exclusion.is_task_excluded(task)

    def _preview_can_delete_visible_rows(self) -> bool:
        return bool(getattr(self, "preview_table", None) and self.preview_table.rowCount() > 0)

    def _reset_batch_draft_to_step_one(self) -> None:
        """清空当前批量草稿（账号/时间/视频、预览排除、统一标题简介文案），回到仅①可用。

        保留底部「批量发布设置」与文案库描述偏好（use_library_* / apply_to_all）。"""
        from src.ui.publish.work_description import (
            clear_publish_description_dialog_session,
        )

        self._preview_exclusion.clear()
        self.selected_accounts.clear()
        self.video_list.clear()
        self.time_slots.clear()
        self._get_video_auto_matcher().reset()
        self.same_title_text = ""
        self.same_desc_text = ""
        self.goods_text = ""
        self.anchor_text = ""
        self.music_info = ""
        self._sync_music_settings_button_state()
        clear_publish_description_dialog_session()
        save_persisted_publish_description_prefs(
            {
                "title": "",
                "desc": "",
                "apply_to_all_tasks": self.apply_description_to_all_tasks,
                "use_library_title": self.use_library_title,
                "use_library_desc": self.use_library_desc,
                "manual_title_backup": "",
                "manual_desc_backup": "",
            }
        )

    def _update_step_buttons_state(self) -> None:
        """根据标准步骤进度联动启用/禁用操作按钮。
        ①选账号 → ②配置时间 → ③添加视频 / ④配置描述（③④在②完成后同时可用）。
        """
        has_accounts = bool(self.selected_accounts)
        has_time = bool(self.time_slots)
        step23_ok = has_accounts and has_time
        if hasattr(self, "btn_publish_time"):
            self.btn_publish_time.setEnabled(has_accounts)
            _tip_time = (
                "配置各任务的定时发布排期"
                if has_accounts
                else "请先①选择账号，再配置发布时间"
            )
            apply_instructional_tooltip(
                _tip_time,
                self.btn_publish_time,
                position=ToolTipPosition.BOTTOM,
            )
        if hasattr(self, "btn_add_video"):
            self.btn_add_video.setEnabled(step23_ok)
        if hasattr(self, "btn_publish_description"):
            self.btn_publish_description.setEnabled(step23_ok)
            _tip_desc = (
                "打开弹窗配置标题、简介与文案库联动"
                if step23_ok
                else "请先完成①②步，再配置作品标题与简介"
            )
            apply_instructional_tooltip(
                _tip_desc,
                self.btn_publish_description,
                position=ToolTipPosition.BOTTOM,
            )

    def _refresh_preview(self, *, skip_material_stats_reminder: bool = False):
        """根据当前配置重新计算并刷新任务预览。"""
        from src.utils.platform_names import get_platform_display_name

        common = self._collect_common_fields()
        br = build_preview_tasks(
            self.selected_accounts,
            self.video_list,
            self.time_slots,
            common,
            False,
            self._preview_exclusion,
            file_type=self._file_type,
            media_label=self._media_label,
            schedule_mode=getattr(self, "schedule_mode", "reuse"),
        )
        # 预览已无行但草稿里仍有账号等数据时，步骤②③④会误判为可点；与「删除全部任务」一致回到①
        if (
            br.n_preview == 0
            and br.n_acc > 0
            and br.branch in ("full", "no_video", "no_time")
        ):
            logger.info(
                "批量预览：无可见行但仍有账号/时间/视频草稿，已自动清空并回到步骤①"
            )
            self._reset_batch_draft_to_step_one()
            self._refresh_preview(skip_material_stats_reminder=skip_material_stats_reminder)
            return

        logger.info(
            "批量%s预览刷新: branch=%s n_preview=%s n_acc=%s n_time=%s n_vid=%s status=%r",
            self._task_label,
            br.branch, br.n_preview, br.n_acc, br.n_time, br.n_vid, br.status_text,
        )

        self._preview_delete_row_specs = br.row_specs
        self._preview_row_video_path_hint = br.video_path_hints

        preview_title = self.same_title_text if self.apply_description_to_all_tasks else ""
        preview_desc = self.same_desc_text if self.apply_description_to_all_tasks else ""
        default_cover_text = "首图" if self._media_type == "image" else "首帧"
        cover_text = "本地" if getattr(self, "cover_type", "first_frame") == "custom" and getattr(self, "cover_path", "") else default_cover_text
        n_vid = br.n_vid
        n_time = br.n_time

        if br.branch == "full":
            self._preview_tasks = br.tasks
            self._update_preview_stats(
                br.n_preview, br.n_acc, n_vid, n_time,
                br.status_text, time_pill_text=br.time_pill_text,
            )
            self.preview_table.setRowCount(br.n_preview)
            for row, t in enumerate(br.tasks):
                raw_file = (t.get("file_path", "") or "").strip()
                file_display = self._material_display_name_for_path(raw_file)
                if "待配置" in file_display:
                    file_cell = "待配置"
                else:
                    file_cell = task_field_str_or_dash(file_display)
                plat = t.get("platform", "")
                plat_cell = (
                    "账号组"
                    if plat == "account_group"
                    else task_field_str_or_dash(get_platform_display_name(str(plat)))
                )
                title_cell = task_field_str_or_dash(
                    (t.get("title") or "").strip() or preview_title
                )
                desc_cell = task_field_str_or_dash(
                    (t.get("description") or "").strip() or preview_desc
                )
                wd_short, wd_tip = self._preview_work_declaration_texts(t)
                self._fill_preview_row(row, [
                    plat_cell,
                    task_field_str_or_dash(t.get("platform_username")),
                    file_cell,
                    cover_text,
                    title_cell,
                    desc_cell,
                    self._preview_time_column_text(t),
                    wd_short,
                    format_cart_info_table_cell(t.get("cart_info")),
                    "✅" if (t.get("anchor_info") or "").strip() else TASK_FIELD_EMPTY_DISPLAY,
                    format_poi_table_cell_display(
                        t.get("poi_info"),
                        platform=t.get("platform"),
                        wechat_empty_location_open_picker=t.get(
                            "wechat_empty_location_open_picker"
                        ),
                    ),
                ])
                _wd_it = self.preview_table.item(row, 7)
                if _wd_it is not None and wd_tip:
                    _wd_it.setToolTip(wd_tip)

        elif br.branch == "no_video":
            # 有账号+时间，尚未添加视频：显示占位行（视频列"待配置"），引导用户③添加视频
            self._preview_tasks = []
            self._update_preview_stats(
                br.n_preview, br.n_acc, n_vid, n_time,
                br.status_text, time_pill_text=br.time_pill_text,
            )
            self.preview_table.setRowCount(br.n_preview)
            for row, t in enumerate(br.no_video_placeholder_rows):
                plat = t.get("platform", "")
                plat_cell = (
                    "账号组"
                    if plat == "account_group"
                    else task_field_str_or_dash(get_platform_display_name(str(plat)))
                )
                wd_short, wd_tip = self._preview_work_declaration_texts(t)
                self._fill_preview_row(row, [
                    plat_cell,
                    task_field_str_or_dash(t.get("platform_username")),
                    "待配置",
                    cover_text,
                    task_field_str_or_dash(
                        (t.get("title") or "").strip() or preview_title
                    ),
                    task_field_str_or_dash(
                        (t.get("description") or "").strip() or preview_desc
                    ),
                    self._preview_time_column_text(t),
                    wd_short,
                    format_cart_info_table_cell(t.get("cart_info")),
                    "✅" if (t.get("anchor_info") or "").strip() else TASK_FIELD_EMPTY_DISPLAY,
                    format_poi_table_cell_display(
                        t.get("poi_info"),
                        platform=t.get("platform"),
                        wechat_empty_location_open_picker=t.get(
                            "wechat_empty_location_open_picker"
                        ),
                    ),
                ])
                _wd_it = self.preview_table.item(row, 7)
                if _wd_it is not None and wd_tip:
                    _wd_it.setToolTip(wd_tip)

        elif br.branch == "no_time":
            # 已选账号但未配时间：每账号一行占位，引导②配置时间
            self._preview_tasks = []
            self._update_preview_stats(
                br.n_preview, br.n_acc, n_vid, n_time,
                br.status_text, time_pill_text=br.time_pill_text,
            )
            self.preview_table.setRowCount(br.n_preview)
            for row, t in enumerate(br.no_time_placeholder_rows):
                plat = t.get("platform", "")
                plat_cell = (
                    "账号组"
                    if plat == "account_group"
                    else task_field_str_or_dash(get_platform_display_name(str(plat)))
                )
                wd_short, wd_tip = self._preview_work_declaration_texts(t)
                self._fill_preview_row(row, [
                    plat_cell,
                    task_field_str_or_dash(t.get("platform_username")),
                    "待配置",
                    cover_text,
                    task_field_str_or_dash(
                        (t.get("title") or "").strip() or preview_title
                    ),
                    task_field_str_or_dash(
                        (t.get("description") or "").strip() or preview_desc
                    ),
                    self._preview_time_column_text(t),
                    wd_short,
                    format_cart_info_table_cell(t.get("cart_info")),
                    "✅" if (t.get("anchor_info") or "").strip() else TASK_FIELD_EMPTY_DISPLAY,
                    format_poi_table_cell_display(
                        t.get("poi_info"),
                        platform=t.get("platform"),
                        wechat_empty_location_open_picker=t.get(
                            "wechat_empty_location_open_picker"
                        ),
                    ),
                ])
                _wd_it = self.preview_table.item(row, 7)
                if _wd_it is not None and wd_tip:
                    _wd_it.setToolTip(wd_tip)

        else:
            # empty：未选账号
            self._preview_tasks = []
            self._update_preview_stats(
                0, br.n_acc, n_vid, n_time,
                br.status_text, time_pill_text=br.time_pill_text,
            )
            self.preview_table.setRowCount(0)

        if hasattr(self, "btn_delete_preview_tasks"):
            self.btn_delete_preview_tasks.setEnabled(True)
        self._update_preview_selection_badge()
        self._update_step_buttons_state()
        self._update_batch_promotion_summary_labels()

        if hasattr(self, "_material_stats_rows_layout") and not skip_material_stats_reminder:
            self._refresh_task_status_reminder()

    def _schedule_preview_refresh(
        self, *, skip_material_stats_reminder: bool = False, delay_ms: int = 120
    ) -> None:
        """合并短时间内的多次预览刷新，降低表格重建和素材统计重复触发。"""
        if self._preview_refresh_timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._run_scheduled_preview_refresh)
            self._preview_refresh_timer = timer

        if not self._preview_refresh_timer.isActive():
            self._preview_refresh_skip_material_stats_reminder = skip_material_stats_reminder
        else:
            self._preview_refresh_skip_material_stats_reminder = (
                self._preview_refresh_skip_material_stats_reminder
                and skip_material_stats_reminder
            )

        self._preview_refresh_timer.start(max(0, delay_ms))

    def _run_scheduled_preview_refresh(self) -> None:
        skip_material_stats_reminder = self._preview_refresh_skip_material_stats_reminder
        self._preview_refresh_skip_material_stats_reminder = False
        self._refresh_preview(
            skip_material_stats_reminder=skip_material_stats_reminder
        )

    def _fill_preview_row(self, row: int, values: list) -> None:
        """将字符串列表写入预览表指定行，统一对齐方式。"""
        for col, text in enumerate(values):
            it = QTableWidgetItem(str(text))
            it.setTextAlignment(_preview_table_cell_alignment(col))
            self.preview_table.setItem(row, col, it)

    def _update_preview_selection_badge(self) -> None:
        """预览表选区变化或行数刷新时更新「已选 N 行」提示。"""
        if not hasattr(self, "preview_selection_count_label"):
            return
        if not hasattr(self, "preview_table"):
            return
        n_rows = self.preview_table.rowCount()
        if n_rows == 0:
            self.preview_selection_count_label.setText("")
            self.preview_selection_count_label.setVisible(False)
            return
        sm = self.preview_table.selectionModel()
        n_sel = len(sm.selectedRows()) if sm is not None else 0
        if n_sel > 0:
            self.preview_selection_count_label.setText(f"已选 {n_sel} 行")
            self.preview_selection_count_label.setVisible(True)
        else:
            self.preview_selection_count_label.setText("")
            self.preview_selection_count_label.setVisible(False)

    def _on_preview_delete_selected(self):
        if not self._preview_can_delete_visible_rows():
            InfoBar.warning(
                "提示", "当前没有可删除的预览行",
                parent=self, position=InfoBarPosition.TOP,
            )
            return
        sm = self.preview_table.selectionModel()
        if sm is None:
            return
        rows = sorted({idx.row() for idx in sm.selectedRows()}, reverse=True)
        if not rows:
            InfoBar.warning(
                "提示", "请先选中要删除的任务",
                parent=self, position=InfoBarPosition.TOP,
            )
            return

        specs = getattr(self, "_preview_delete_row_specs", None) or []
        added = 0
        for r in rows:
            if r < 0 or r >= len(specs):
                continue
            if self._preview_exclusion.record_deletion(specs[r]):
                added += 1

        if added == 0:
            InfoBar.warning(
                "提示", "未选中有效预览行",
                parent=self, position=InfoBarPosition.TOP,
            )
            return

        self._refresh_preview()
        self.preview_table.clearSelection()
        self._refresh_task_status_reminder()
        InfoBar.success(
            "已移除",
            f"已从预览中移除 {added} 条任务（已选账号与视频列表未改动）",
            parent=self, position=InfoBarPosition.TOP, duration=2500,
        )

    def _on_preview_delete_all(self):
        """删除预览中的全部行，并清空当前批量草稿，使流程回到仅①选择账号可用。"""
        if not self._preview_can_delete_visible_rows():
            InfoBar.warning(
                "提示", "当前没有可删除的预览任务",
                parent=self, position=InfoBarPosition.TOP,
            )
            return
        n = self.preview_table.rowCount()
        self._reset_batch_draft_to_step_one()
        self._refresh_preview()
        self.preview_table.clearSelection()
        self._refresh_task_status_reminder()
        InfoBar.success(
            "已清空",
            f"已移除预览中的 {n} 条任务，并清空账号/时间/视频选择；请从①选择账号重新开始",
            parent=self, position=InfoBarPosition.TOP, duration=3500,
        )

    def _on_clear_videos_only(self):
        """清空素材与描述配置，保留账号与时间。"""
        n = len(self.video_list)
        self.video_list.clear()
        self._get_video_auto_matcher().reset()
        self.same_title_text = ""
        self.same_desc_text = ""
        self.use_library_title = False
        self.use_library_desc = False
        self.apply_description_to_all_tasks = True
        self._refresh_preview()
        self._sync_batch_publish_settings_ui()
        InfoBar.success(
            f"已清空{self._task_label}",
            f"已清空 {n} 个{self._task_label}，并重置描述配置；账号与发布时间已保留。",
            parent=self, position=InfoBarPosition.TOP, duration=3000,
        )

    def _preview_resolve_video_path_for_row(self, row: int) -> Optional[str]:
        hints = getattr(self, "_preview_row_video_path_hint", None) or []
        if 0 <= row < len(hints):
            h = hints[row]
            return h if h else None
        return None

    def _preview_primary_selected_video_path(self) -> Optional[str]:
        if not hasattr(self, "preview_table"):
            return None
        sm = self.preview_table.selectionModel()
        if sm is None:
            return None
        rows = sorted({idx.row() for idx in sm.selectedRows()})
        if not rows:
            return None
        raw = self._preview_resolve_video_path_for_row(rows[0])
        if not raw or "待配置" in raw:
            return None
        if self._media_type == "image":
            folder = self._media_folder_marker(raw)
            if folder:
                return os.path.normpath(folder)
            real_paths = self._media_real_paths(raw)
            if real_paths:
                return os.path.normpath(real_paths[0])
        path = os.path.normpath(raw)
        return path if path else None

    def _batch_preview_ctx_open_flags(self) -> Tuple[bool, bool]:
        path = self._preview_primary_selected_video_path()
        if not path or not (os.path.isfile(path) or os.path.isdir(path)):
            return False, False
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        folder_ok = bool(folder and os.path.isdir(folder))
        return folder_ok, os.path.isfile(path)

    def _on_preview_open_video_folder(self) -> None:
        path = self._preview_primary_selected_video_path()
        if not path or not (os.path.isfile(path) or os.path.isdir(path)):
            InfoBar.warning(
                "提示", f"当前选中行没有可用的本地{self._task_label}素材路径",
                parent=self, position=InfoBarPosition.TOP,
            )
            return
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if not folder or not os.path.isdir(folder):
            InfoBar.warning(
                "提示", f"无法解析{self._task_label}素材所在文件夹",
                parent=self, position=InfoBarPosition.TOP,
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
            InfoBar.error(
                "错误", "打开文件夹失败，请检查系统默认文件管理器。",
                parent=self, position=InfoBarPosition.TOP, duration=4000,
            )

    def _on_preview_open_file(self) -> None:
        """预览表右键：用系统默认程序打开当前选中行对应的本地视频文件。"""
        path = self._preview_primary_selected_video_path()
        if not path or not os.path.isfile(path):
            InfoBar.warning(
                "提示", f"当前选中行没有可用的本地{self._task_label}文件或文件已不存在",
                parent=self, position=InfoBarPosition.TOP,
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
            InfoBar.error(
                "错误", "打开文件失败，请检查系统关联的默认播放器。",
                parent=self, position=InfoBarPosition.TOP, duration=4000,
            )

    def _on_preview_open_video_file(self) -> None:
        """兼容旧名；与 _on_preview_open_file 相同。"""
        self._on_preview_open_file()

    def _on_preview_context_menu(self, pos):
        if not self._preview_can_delete_visible_rows():
            return
        item = self.preview_table.itemAt(pos)
        if item is not None:
            sm = self.preview_table.selectionModel()
            if sm is not None:
                clicked_row = item.row()
                selected_rows = {idx.row() for idx in sm.selectedRows()}
                # 无选中时选中右键行；多选时点在已选行上则保留多选，点在选中外则改为只选该行
                need_single = (not selected_rows) or (clicked_row not in selected_rows)
                if need_single:
                    sm.blockSignals(True)
                    try:
                        self.preview_table.selectRow(clicked_row)
                    finally:
                        sm.blockSignals(False)
        global_pos = self.preview_table.viewport().mapToGlobal(pos)
        mgr = getattr(self, "_preview_ctx_menu", None)
        if mgr is not None:
            mgr.exec_at(global_pos, self.preview_table)
        else:
            self._preview_ctx_menu = BatchPreviewContextMenu(self)
            self._preview_ctx_menu.exec_at(global_pos, self.preview_table)

    # ==================================================================
    # 公共字段收集
    # ==================================================================

    def _collect_common_fields(self) -> dict:
        if self.apply_description_to_all_tasks:
            title_text = self.same_title_text
            desc_text = self.same_desc_text
            tags = parse_topic_list(desc_text)
            tags_str = ",".join(tags)
        else:
            title_text = ""
            desc_text = ""
            tags_str = ""

        cover = None
        if getattr(self, "cover_type", "first_frame") == "custom":
            cover = getattr(self, "cover_path", "") or None

        privacy = "public"
        if hasattr(self, 'privacy_combo'):
            p = self.privacy_combo.currentText()
            if "\u597d\u53cb" in p:
                privacy = "friend"
            elif "\u79c1\u5bc6" in p:
                privacy = "private"
        allow_dl = self.allow_download_check.isChecked() if hasattr(self, 'allow_download_check') else True
        is_orig = getattr(self, "declare_original_checked", True)
        dy_decl = normalize_douyin_value(getattr(self, "douyin_work_declaration", None))
        ks_decl = normalize_kuaishou_value(getattr(self, "kuaishou_work_declaration", None))
        dy_auto = bool(getattr(self, "douyin_work_declaration_auto", False))
        ks_auto = bool(getattr(self, "kuaishou_work_declaration_auto", False))
        xhs_o = bool(getattr(self, "xiaohongshu_is_original", False))
        xhs_attr = normalize_xhs_content_attr(
            getattr(self, "xiaohongshu_content_attribute", None)
        )
        xhs_attr_auto = bool(getattr(self, "xiaohongshu_content_attribute_auto", False))

        privacy_settings = json.dumps({
            "privacy": privacy,
            "allow_download": allow_dl,
            "is_original": is_orig,
            KEY_DOUYIN: dy_decl,
            KEY_KUAISHOU: ks_decl,
            KEY_DOUYIN_AUTO: dy_auto,
            KEY_KUAISHOU_AUTO: ks_auto,
            KEY_XHS_ORIGINAL: xhs_o,
            KEY_XHS_CONTENT_ATTR: xhs_attr,
            KEY_XHS_CONTENT_ATTR_AUTO: xhs_attr_auto,
        }, ensure_ascii=False)

        from src.domain.publish.location_settings import (
            location_publish_fields_from_batch_persisted,
        )

        loc_fields = location_publish_fields_from_batch_persisted(
            getattr(self, "location_text", "") or "",
            self._batch_wechat_empty_location_open_picker,
        )
        loc_part = loc_fields.to_common_fields_dict()

        goods_out = (self.goods_text or "").strip()
        anchor_out = (getattr(self, "anchor_text", "") or "").strip()
        if goods_out and anchor_out:
            has_yc_json = False
            if goods_out.startswith("{"):
                try:
                    _d = json.loads(goods_out)
                    if isinstance(_d, dict) and (
                        _d.get("cart_short_name") or _d.get("yellow_cart_short_name") or ""
                    ).strip():
                        has_yc_json = True
                except (json.JSONDecodeError, TypeError):
                    pass
            if has_yc_json:
                anchor_out = ""
            else:
                goods_out = ""

        return {
            "user_id": self.user_id,
            "title": title_text,
            "description": desc_text,
            "tags_str": tags_str,
            "cover_path": cover,
            "poi_info": loc_part["poi_info"],
            "wechat_empty_location_open_picker": loc_part["wechat_empty_location_open_picker"],
            "micro_app_info": "",
            "cart_info": goods_out,
            "anchor_info": anchor_out,
            "music_info": (getattr(self, "music_info", "") or "").strip()
            if self._media_type == "image" else "",
            "privacy_settings": privacy_settings,
        }

    # ==================================================================
    # 发布逻辑
    # ==================================================================

    @asyncSlot()
    async def _on_batch_publish(self):
        if not self._current_user_svc.is_logged_in():
            try:
                from src.ui.dialogs.login_dialog import LoginDialog
                from src.ui.utils.async_helper import await_qdialog_finished
                dialog = LoginDialog(self)
                dialog.login_success.connect(self._refresh_user_id)
                code = await await_qdialog_finished(dialog)  # type: ignore
                if code != int(QDialog.DialogCode.Accepted):
                    InfoBar.warning("请先登录", "发布前需要登录",
                                    parent=self, position=InfoBarPosition.TOP)
                    return
                self._refresh_user_id()
            except Exception:
                InfoBar.warning("请先登录", "发布前需要登录",
                                parent=self, position=InfoBarPosition.TOP)
                return

        if not self.selected_accounts:
            InfoBar.warning("提示", "请先选择发布账号", parent=self, position=InfoBarPosition.TOP)
            return
        if not self.video_list:
            InfoBar.warning("提示", f"请先导入{self._media_label}文件", parent=self, position=InfoBarPosition.TOP)
            return
        if not self.time_slots:
            InfoBar.warning(
                "提示",
                "请先配置发布时间",
                parent=self,
                position=InfoBarPosition.TOP,
            )
            return

        # 视频号图文发布必须填写作品标题
        if self._media_type == "image" and self._selected_targets_include_wechat_video():
            wechat_tasks_missing_title = False
            if getattr(self, "_preview_tasks", None):
                for idx, pt in enumerate(self._preview_tasks):
                    if hasattr(self, "_preview_exclusion") and self._preview_exclusion.is_task_excluded(pt):
                        continue
                    if pt.get("platform") == "wechat_video" and not (pt.get("title") or "").strip():
                        wechat_tasks_missing_title = True
                        break
            else:
                if not (self.same_title_text or "").strip():
                    wechat_tasks_missing_title = True

            if wechat_tasks_missing_title:
                InfoBar.warning(
                    "作品标题必填",
                    "所选发布目标包含视频号账号，图文发布必须包含「作品标题」。\n"
                    "请在「批量发布设置」中检查描述来源，或在「作品描述」中填写标题后再添加到发布列表。",
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=6000,
                )
                return

        self.btn_publish.setEnabled(False)
        try:
            from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
            from src.ui.utils.fluent_dialogs import show_warning

            repo = PublishRecordRepositoryAsync()
            common = self._collect_common_fields()

            br = await build_publish_tasks_for_batch(
                self.selected_accounts,
                self.video_list,
                self.time_slots,
                common,
                False,
                self._preview_exclusion,
                user_id=self.user_id,
                group_service=self.group_service,
                publish_record_repo=repo,
                file_type=self._file_type,
                schedule_mode=getattr(self, "schedule_mode", "reuse"),
            )

            for gname in br.empty_group_names:
                InfoBar.warning(
                    "账号组为空",
                    f"账号组「{gname}」内没有任何账号，已跳过",
                    parent=self, position=InfoBarPosition.TOP, duration=4000,
                )

            if br.validation_error:
                InfoBar.error(
                    "发布失败", br.validation_error,
                    parent=self, position=InfoBarPosition.TOP, duration=5000,
                )
                return

            if br.skip_dup_lines:
                show_warning(
                    self,
                    "部分任务未添加",
                    f"以下 {len(br.skip_dup_lines)} 条与发布列表中已有任务重复"
                    f"（相同{self._task_label}素材、同平台同账号、且为待发布或进行中），已跳过：\n\n"
                    + "\n".join(br.skip_dup_lines[:25])
                    + ("\n…" if len(br.skip_dup_lines) > 25 else ""),
                )

            if not br.tasks:
                msg = "未生成任何任务，请检查配置"
                if br.skip_dup_lines:
                    msg = f"所选任务均在发布列表中已存在相同{self._task_label}，未写入。"
                InfoBar.warning("提示", msg, parent=self, position=InfoBarPosition.TOP, duration=5000)
                return

            count = await batch_create_publish_records(br.tasks, repo)

            skipped_n = len(br.skip_dup_lines)
            extra_skip = f"，已跳过 {skipped_n} 条重复任务" if skipped_n else ""
            InfoBar.success(
                "批量添加成功",
                f"已成功添加 {count} 条发布任务到发布列表{extra_skip}",
                parent=self, position=InfoBarPosition.TOP, duration=4000,
            )
            self._reset_all()

            main_window = self.window()
            if hasattr(main_window, '_get_or_create_page'):
                list_page = main_window._get_or_create_page("publish_list_page")
                if list_page and hasattr(list_page, 'mark_data_stale'):
                    list_page.mark_data_stale()

            if hasattr(main_window, '_jump_to_feature'):
                main_window._jump_to_feature("publish_list_page")
            elif hasattr(main_window, 'navigate_to'):
                main_window.navigate_to("publish_list_page")

        except Exception as e:
            logger.error("批量写入发布记录失败: %s", e, exc_info=True)
            InfoBar.error("写入失败", str(e),
                          parent=self, position=InfoBarPosition.TOP, duration=5000)
        finally:
            self.btn_publish.setEnabled(True)

    def _refresh_user_id(self):
        self.user_id = self._current_user_svc.get_user_id_or_default(1)

    # ==================================================================
    # 发布成功后整页重置（内部用，与「删除全部预览任务」不同）
    # ==================================================================

    def _reset_all(self):
        from src.ui.publish.work_description import (
            load_persisted_declare_original,
            load_persisted_work_declaration,
            clear_publish_description_dialog_session,
        )

        self.declare_original_checked = load_persisted_declare_original()
        _wdecl = load_persisted_work_declaration()
        self.douyin_work_declaration = normalize_douyin_value(_wdecl.get(KEY_DOUYIN))
        self.kuaishou_work_declaration = normalize_kuaishou_value(_wdecl.get(KEY_KUAISHOU))
        self.douyin_work_declaration_auto = bool(_wdecl.get(KEY_DOUYIN_AUTO, False))
        self.kuaishou_work_declaration_auto = bool(_wdecl.get(KEY_KUAISHOU_AUTO, False))
        self.xiaohongshu_is_original = bool(_wdecl.get(KEY_XHS_ORIGINAL, False))
        self.xiaohongshu_content_attribute = normalize_xhs_content_attr(
            _wdecl.get(KEY_XHS_CONTENT_ATTR)
        )
        self.xiaohongshu_content_attribute_auto = bool(
            _wdecl.get(KEY_XHS_CONTENT_ATTR_AUTO, False)
        )
        self.selected_accounts.clear()
        self.video_list.clear()
        self.time_slots.clear()
        self._preview_exclusion.clear()
        self._get_video_auto_matcher().reset()
        # 仅清空本次批次的标题/简介文案；保留「描述配置 / 文案库自动匹配」等用户偏好（原先用
        # reset_persisted_publish_description_prefs 会连带把勾选偏好清掉，导致再次打开「配置描述」全未勾选）。
        self.same_title_text = ""
        self.same_desc_text = ""
        clear_publish_description_dialog_session()
        save_persisted_publish_description_prefs(
            {
                "title": "",
                "desc": "",
                "apply_to_all_tasks": self.apply_description_to_all_tasks,
                "use_library_title": self.use_library_title,
                "use_library_desc": self.use_library_desc,
                "manual_title_backup": "",
                "manual_desc_backup": "",
            }
        )
        self.location_text = ""
        self._batch_wechat_empty_location_open_picker = False
        save_batch_location_prefs("", False)
        self.goods_text = ""
        self.anchor_text = ""
        self.music_info = ""
        self.cover_type = "first_frame"
        self.cover_path = ""



        if hasattr(self, 'location_edit'):
            self.location_edit.clear()
        if hasattr(self, 'goods_edit'):
            self.goods_edit.clear()
        if hasattr(self, "_material_stats_rows_layout"):
            self._refresh_task_status_reminder()
        if hasattr(self, 'title_edit'):
            self.title_edit.clear()
        if hasattr(self, 'desc_edit'):
            self.desc_edit.clear()
        if hasattr(self, 'privacy_combo'):
            self.privacy_combo.setCurrentIndex(0)
        if hasattr(self, 'allow_download_check'):
            self.allow_download_check.setChecked(True)
        if hasattr(self, 'is_original_check'):
            self.is_original_check.setChecked(False)

        if hasattr(self, "_sync_batch_publish_settings_ui"):
            self._sync_batch_publish_settings_ui()
        self._sync_music_settings_button_state()
        self._refresh_preview()
