"""
账号选择弹窗
文件路径：src/ui/dialogs/account_selection_dialog.py
"""
import asyncio
from typing import Any, Optional, Set
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QStackedWidget, QAbstractItemView, QApplication, QTableWidgetItem, QHeaderView, QGridLayout,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QBrush, QColor
from qfluentwidgets import (
    BodyLabel, IconWidget, FluentIcon, ComboBox,
    InfoBadge, CheckBox, TableWidget, FlowLayout, PushButton, TogglePushButton,
    SegmentedWidget
)

from src.ui.components.base_dialog import AppMessageBoxBase
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.services.material.media_library_stats_cache import get_media_library_stats_cache
from src.services.material.media_library_stats_service import get_media_library_stats_service

class AccountSelectionDialog(AppMessageBoxBase):
    """账号选择弹窗 (双列布局 - 账号/分组 模式)

    header_title：各业务场景自定义顶栏标题（如「选择发布对象」「选择分配对象」）。
    parent：可传任意控件；AppMessageBoxBase 会挂到顶层窗口，遮罩覆盖整块主窗口（含左侧导航）。
    """

    def __init__(self, parent=None, header_title: str = "选择发布对象"):
        super().__init__(parent, header_title=header_title)

        # 账号表格列索引（随是否多选而变化，运行时赋值）
        self._col_check = 3
        self._col_tags = 3
        self._col_video_count = 3
        self._col_image_count = 4
        # 不在弹窗内重复统计素材数量：统一复用全局统计缓存（总/占用/未占用）
        self._media_stats_cache = get_media_library_stats_cache()
        self._account_tags_cache = {}  # account_id -> "标签1、标签2"
        # 左侧标签按钮引用：用于稳定同步选中态（避免布局遍历找不到控件）
        self._tag_buttons = {}  # tag_id -> TogglePushButton
        self._active_tag_id = None  # 单选高亮：记录最近一次点击的标签 id
        try:
            self._media_stats_cache.statsUpdated.connect(self._on_media_stats_updated)
        except Exception:
            pass

        # 多选辅助（红框工具条）：全选 + 平台筛选 + 已选数量
        self._enable_ctrl_multi_select = False
        self._account_checked_ids = set()
        self._filtered_accounts = []

        # 底部筛选条：外层不画边框，避免和表格边框“叠边”显脏
        self._toolbar = QWidget(self)
        tb = QHBoxLayout(self._toolbar)
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setSpacing(12)
        self._toolbar.setStyleSheet("QWidget { background: transparent; border: none; }")
        self._toolbar.setFixedHeight(52)

        self._select_all_accounts = CheckBox("全选", self._toolbar)
        # 仅两态：选中/未选中（不显示“半选 -”）
        self._select_all_accounts.setTristate(False)
        apply_instructional_tooltip(
            "全选当前筛选结果",
            self._select_all_accounts,
            position=ToolTipPosition.BOTTOM,
        )
        self._select_all_accounts.setVisible(False)
        self._select_all_accounts.stateChanged.connect(self._on_toggle_select_all_accounts)

        # 账号组页的“全选”（与账号页分离，避免逻辑互相影响）
        self._select_all_groups = CheckBox("全选", self._toolbar)
        self._select_all_groups.setTristate(False)
        self._select_all_groups.setVisible(False)
        self._select_all_groups.stateChanged.connect(self._on_toggle_select_all_groups)

        self._platform_filter = ComboBox(self._toolbar)
        self._platform_filter.setFixedWidth(140)
        self._platform_filter.setVisible(False)
        self._platform_filter.currentTextChanged.connect(self._on_platform_filter_changed)

        # 顶部切换标签（替代左侧导航栏，释放空间）
        self._pivot = SegmentedWidget(self)
        self._pivot.setObjectName("AccountSelectionPivot")
        self._apply_pivot_style()
        try:
            self._pivot.currentItemChanged.connect(self._sync_pivot_selection)
        except Exception:
            pass

        # 左侧筛选控件：放入“筛选胶囊”内，视觉更统一
        self._filter_box = QWidget(self._toolbar)
        self._filter_box.setStyleSheet("""
            QWidget {
                background: rgba(255, 255, 255, 0.92);
                border: none;
                border-radius: 12px;
            }
            /* 胶囊内部控件不再单独画边框，避免出现“多层边框” */
            QCheckBox, CheckBox {
                background: transparent;
                border: none;
                padding: 0px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid rgba(0, 0, 0, 0.22);
                background: rgba(255, 255, 255, 0.90);
            }
            QCheckBox::indicator:hover {
                border: 1px solid rgba(0, 120, 212, 0.40);
                background: rgba(0, 120, 212, 0.06);
            }
            QCheckBox::indicator:checked {
                border: 1px solid rgba(0, 120, 212, 0.55);
                background: rgba(0, 120, 212, 0.18);
            }
            QComboBox, ComboBox {
                background: transparent;
                border: none;
                padding: 2px 18px 2px 6px; /* 给右侧箭头留空间 */
                min-height: 22px;
            }
            QComboBox::drop-down {
                border: none;
                background: transparent;
                width: 18px;
            }
            QComboBox::down-arrow {
                background: transparent;
            }
            QComboBox:hover {
                background: rgba(0, 0, 0, 0.03);
                border-radius: 8px;
            }
            QComboBox:focus {
                background: rgba(0, 120, 212, 0.06);
                border-radius: 8px;
            }
        """)
        fl = QHBoxLayout(self._filter_box)
        fl.setContentsMargins(12, 8, 12, 8)
        fl.setSpacing(10)

        self._center_controls = QWidget(self._filter_box)
        center = QHBoxLayout(self._center_controls)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(10)
        center.addWidget(self._select_all_accounts)
        center.addWidget(self._select_all_groups)

        sep = QWidget(self._center_controls)
        sep.setFixedSize(1, 18)
        # 分隔线更轻，避免与外框叠加显脏
        sep.setStyleSheet("background: rgba(0,0,0,0.08);")
        center.addWidget(sep)

        label = BodyLabel("平台", self._toolbar)
        label.setStyleSheet("color: rgba(0,0,0,0.55); font-weight: 600;")
        center.addWidget(label)
        center.addWidget(self._platform_filter)

        fl.addWidget(self._center_controls, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # --- 右侧内容区域 (StackedWidget) ---
        self.content_stack = QStackedWidget(self)
        self.content_stack.setStyleSheet("""
             QStackedWidget {
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 6px;
                background-color: rgba(255, 255, 255, 0.5);
            }
        """)
        
        # 页面1: 账号列表（表格样式，支持排序）
        self.account_table = TableWidget(self)
        self._multi_select = False  # 是否多选模式（添加到账号组时使用）
        self.content_stack.addWidget(self.account_table)
        
        # 页面2: 账号组列表（表格，信息密度更高）
        self.group_table = TableWidget(self)
        self.content_stack.addWidget(self.group_table)

        # 工具条放在红框区域（表格下方、按钮上方）
        self._multi_select_hint = QLabel("")
        self._multi_select_hint.setStyleSheet("""
            QLabel {
                color: #0B4A7A;
                background-color: #D6ECFF;
                border-radius: 14px;
                padding: 6px 12px;
                font-size: 12px;
                font-weight: 650;
            }
        """)
        tb.addWidget(self._filter_box, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        tb.addStretch(1)
        tb.addWidget(self._multi_select_hint, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        # ---------------- 主体布局：左侧账号标签 | 右侧账号列表/账号组 ----------------
        self.viewLayout.setSpacing(6)

        body = QWidget(self)
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(12)

        # 左侧：账号标签面板（可滚动）
        self._tags_panel = QFrame(body)
        self._tags_panel.setObjectName("AccountTagsPanel")
        # 左侧面板保留足够宽度，避免标签按钮右侧边框被裁切。
        self._tags_panel.setFixedWidth(170)
        self._tags_panel.setStyleSheet("""
            QFrame#AccountTagsPanel {
                border: 1px solid rgba(0, 0, 0, 0.10);
                border-radius: 8px;
                background-color: rgba(255, 255, 255, 0.55);
            }
            /* 胶囊标签（左侧单列） */
            TogglePushButton#AccountTagPill {
                border: 1px solid rgba(0, 0, 0, 0.12);
                border-radius: 8px;
                padding: 7px 10px;
                background: rgba(255, 255, 255, 0.85);
                color: #333;
                font-weight: 600;
                text-align: left;
            }
            /* 账号标签 / 账号组标签：轻量区分（不额外占文案空间） */
            TogglePushButton#AccountTagPill[tagKind="account"] {
                border: 1px solid rgba(0, 120, 212, 0.22);
            }
            TogglePushButton#AccountTagPill[tagKind="group"] {
                border: 1px solid rgba(107, 97, 214, 0.22);
            }
            TogglePushButton#AccountTagPill:hover {
                background: rgba(0, 120, 212, 0.08);
                border: 1px solid rgba(0, 120, 212, 0.28);
            }
            TogglePushButton#AccountTagPill:checked {
                background: rgba(0, 120, 212, 0.14);
                border: 1px solid rgba(0, 120, 212, 0.38);
                color: #0B4A7A;
            }
            TogglePushButton#AccountTagPill[tagKind="group"]:checked {
                background: rgba(107, 97, 214, 0.14);
                border: 1px solid rgba(107, 97, 214, 0.38);
                color: #3D36A8;
            }
        """)
        tags_outer = QVBoxLayout(self._tags_panel)
        tags_outer.setContentsMargins(10, 10, 10, 10)
        tags_outer.setSpacing(10)
        tags_title = BodyLabel("标签（账号/账号组）", self._tags_panel)
        tags_title.setStyleSheet("font-weight: 650; color: #333; font-size: 13px;")
        tags_outer.addWidget(tags_title)

        self._tags_scroll = QScrollArea(self._tags_panel)
        self._tags_scroll.setWidgetResizable(True)
        self._tags_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # 让滚动区背景与卡片一致，视觉更干净
        try:
            self._tags_scroll.viewport().setStyleSheet("background: transparent;")
        except Exception:
            pass

        # 快捷标签流式容器（放到左侧滚动区内）
        self._tags_widget = QWidget(self._tags_panel)
        # 单列纵向：用 QVBoxLayout，选中态更稳定、点击区域更大
        self._tags_layout = QVBoxLayout(self._tags_widget)
        self._tags_layout.setContentsMargins(0, 0, 0, 0)
        self._tags_layout.setSpacing(10)
        self._tags_scroll.setWidget(self._tags_widget)
        tags_outer.addWidget(self._tags_scroll, 1)

        # 右侧：账号列表/账号组 + 工具条
        right = QWidget(body)
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        # 表格与底部工具条之间留出更舒服的层级间距
        right_lay.setSpacing(10)
        right_lay.addWidget(self._pivot)
        right_lay.addWidget(self.content_stack, 1)
        right_lay.addWidget(self._toolbar)

        body_lay.addWidget(self._tags_panel, 0)
        body_lay.addWidget(right, 1)

        self.viewLayout.addWidget(body, 1)

        self._all_tags = []
        
        # 调整弹窗大小
        # 账号表格新增「账号标签/视频库/图片库」后，原 720 宽度会挤压「平台昵称」列导致遮挡
        # 统计列从“单数字”升级为“总/占用/未占用”后，需要给「平台昵称」留出更多空间
        self.widget.setMinimumWidth(1010)
        self.widget.setMinimumHeight(600)
        
        # 数据
        self.all_accounts = []
        self.groups = []
        
        # 选中结果 {'type': 'account'|'group', 'data': ...}
        self.selection_result = None
        self._selected_accounts = []
        self._selected_groups = []

        # 单任务等场景：左侧标签仅筛选，不写入多选集合、不点亮确认
        self._tags_filter_only = False
        self._tag_filter_account_ids: Optional[Set[Any]] = None
        self._tag_filter_group_ids: Optional[Set[Any]] = None
        self._accounts_after_platform: list = []
        
        # 记录最后显示的提示条，防止重复弹出
        self._last_info_bar = None
        
        # 信号连接
        self.account_table.cellClicked.connect(self._on_account_cell_clicked)
        self.account_table.cellDoubleClicked.connect(self._on_account_cell_double_clicked)
        # 表头排序指示
        header = self.account_table.horizontalHeader()
        header.setSortIndicatorShown(True)
        
        self.group_table.cellClicked.connect(self._on_group_cell_clicked)
        self.group_table.cellDoubleClicked.connect(self._on_group_cell_double_clicked)
        
        # 按钮中文且调换位置：取消在左，确认在右
        self.yesButton.setText("确认")
        self.cancelButton.setText("取消")
        lay = getattr(self, "buttonLayout", None)
        if lay is not None and lay.indexOf(self.yesButton) >= 0 and lay.indexOf(self.cancelButton) >= 0:
            lay.removeWidget(self.cancelButton)
            lay.removeWidget(self.yesButton)
            lay.addWidget(self.cancelButton)
            lay.addWidget(self.yesButton)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    @staticmethod
    def _norm_int_id(v):
        """将 dict 中可能为 str/int 的 id 统一为 int；失败返回 None。"""
        try:
            if v is None:
                return None
            return int(v)
        except Exception:
            return None
        
    def _set_list_style(self, list_widget):
        list_widget.setStyleSheet("""
            QListWidget {
                border: none;
                background-color: transparent;
                outline: none;
            }
            QListWidget::item {
                height: 36px;
                padding: 2px 8px;
                border-bottom: 1px solid rgba(0,0,0,0.05);
            }
            QListWidget::item:selected {
                background-color: rgba(0, 120, 212, 0.1);
                border-radius: 4px;
                border-bottom: none;
            }
            QListWidget::item:hover {
                background-color: rgba(0, 0, 0, 0.03);
                border-radius: 4px;
                border-bottom: none;
            }
        """)

    def _apply_pivot_style(self) -> None:
        """顶部 Tab 样式（与项目排期弹窗同类风格）。"""
        # 轻量样式：不依赖主题管理器，暗色主题下也可读
        bg_hover = "rgba(0,0,0,0.06)"
        border = "rgba(0,0,0,0.12)"
        tp = "#1A1A1A"
        ts = "#666666"
        bg_card = "rgba(255,255,255,0.85)"
        self._pivot.setStyleSheet(f"""
            #AccountSelectionPivot {{
                background-color: {bg_hover};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px;
                min-height: 36px;
            }}
            #AccountSelectionPivot SegmentedItem {{
                border: none;
                border-radius: 6px;
                padding: 6px 20px;
                font-size: 13px;
                color: {ts};
                background: transparent;
            }}
            #AccountSelectionPivot SegmentedItem:hover {{
                color: {tp};
                background: rgba(128,128,128,0.15);
            }}
            #AccountSelectionPivot SegmentedItem[isSelected="true"],
            #AccountSelectionPivot SegmentedItem[isSelected="1"] {{
                color: {tp};
                font-weight: 600;
                background-color: {bg_card};
            }}
        """)

    def _sync_pivot_selection(self) -> None:
        """同步 SegmentedItem 的 isSelected 属性，确保样式正确刷新。"""
        try:
            get_current = getattr(self._pivot, "currentRouteKey", None)
            current_key = get_current() if callable(get_current) else "accounts"
        except Exception:
            current_key = "accounts"
        for child in self._pivot.findChildren(QWidget):
            if type(child).__name__ == "SegmentedItem":
                key = child.property("routeKey") or ""
                child.setProperty("isSelected", key == current_key)
                child.style().unpolish(child)
                child.style().polish(child)

    def set_data(
        self,
        accounts,
        groups=None,
        show_group_nav=True,
        multi_select=False,
        ctrl_multi_select=False,
        initial_account_ids=None,
        initial_group_ids=None,
        tags_filter_only: bool = False,
    ):
        """设置数据并初始化
        
        Args:
            accounts: 账号列表
            groups: 分组列表（可选）
            show_group_nav: 是否显示左侧分组导航
            multi_select: 是否多选模式（如添加到账号组时一次选多个）
            ctrl_multi_select: 非 multi_select 时，是否允许 Ctrl+鼠标点击多选账号
            initial_account_ids: 初始勾选的账号 ID 列表
            initial_group_ids: 初始勾选的账号组 ID 列表
            tags_filter_only: 为 True 且非多选时，左侧标签只筛选列表，须点右侧行才能确认
        """
        self.all_accounts = accounts
        self.groups = groups or []
        self._multi_select = multi_select
        self._enable_ctrl_multi_select = bool(ctrl_multi_select)
        self._account_checked_ids = set(initial_account_ids or [])
        self._group_checked_ids = set(initial_group_ids or [])
        self._filtered_accounts = list(accounts or [])
        self._tags_filter_only = bool(tags_filter_only) and (not multi_select)
        self._tag_filter_account_ids = None
        self._tag_filter_group_ids = None
        
        # 账号列表选择模式：多选时用 NoSelection + 行内复选框；否则支持单选或 Ctrl 多选
        if multi_select:
            self.account_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            self.account_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
            self.group_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        else:
            if self._enable_ctrl_multi_select:
                self.account_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
                self.account_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            else:
                self.account_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
                self.account_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.group_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        
        # 初始化顶部 Tab
        self._reset_pivot_items(show_group_tab=bool(show_group_nav))

        # 账号列表
        self._pivot.addItem(
            routeKey="accounts",
            text="账号列表",
            onClick=lambda: self._set_current_page(0, True),
        )
        # 账号组（可选）
        if bool(show_group_nav):
            self._pivot.addItem(
                routeKey="groups",
                text="账号组",
                onClick=lambda: self._set_current_page(1, True),
            )
        
        # 渲染内容
        self._setup_platform_filter_options()
        self._apply_account_filter()
        if show_group_nav:
            self._render_groups()

        # 多选模式：初始化确定按钮与已选数量提示
        if multi_select:
            # 只有 groups 而没有 accounts 时，自动跳到账号组标签（索引1）
            # 这还会避免 _on_multi_select_changed 切页时被“账号页”逻辑自动 clear
            target_page = 0
            if show_group_nav and self._group_checked_ids and not self._account_checked_ids:
                target_page = 1
            self._set_current_page(target_page)
            self._on_multi_select_changed()
        else:
            self._set_current_page(0)
            self._multi_select_hint.setVisible(False)
            self.yesButton.setEnabled(False)
            self._select_all_accounts.setVisible(False)
            self._platform_filter.setVisible(True)

        # 异步拉取所有标签数据供快捷选择
        self._load_tags_async()

    def _reset_pivot_items(self, show_group_tab: bool) -> None:
        """清空并重建顶部 Tab，兼容不同版本的 qfluentwidgets SegmentedWidget API。"""
        pivot = getattr(self, "_pivot", None)
        if pivot is None:
            return

        # 优先使用库自带 clear()
        clear_fn = getattr(pivot, "clear", None)
        if callable(clear_fn):
            try:
                clear_fn()
                return
            except Exception:
                pass

        # 若无 clear() 或 clear() 失败，则安全重建 pivot，避免重复 addItem 造成标签堆叠
        try:
            idx = self.viewLayout.indexOf(pivot)
        except Exception:
            idx = -1

        new_pivot = SegmentedWidget(self)
        new_pivot.setObjectName("AccountSelectionPivot")
        # 替换引用并重新挂到布局
        try:
            if idx >= 0:
                self.viewLayout.removeWidget(pivot)
                self.viewLayout.insertWidget(idx, new_pivot)
            else:
                self.viewLayout.insertWidget(0, new_pivot)
        except Exception:
            # 兜底：直接 add 到最上方（不会影响功能，只是顺序可能略有差异）
            self.viewLayout.insertWidget(0, new_pivot)

        try:
            pivot.setParent(None)
            pivot.deleteLater()
        except Exception:
            pass

        self._pivot = new_pivot
        self._apply_pivot_style()
        try:
            self._pivot.currentItemChanged.connect(self._sync_pivot_selection)
        except Exception:
            pass

    def _set_current_page(self, page_index: int, clear_tag_filter_on_pivot: bool = True) -> None:
        """切换账号列表/账号组页面（由顶部 Tab 或标签逻辑触发）。"""
        try:
            prev_idx = int(self.content_stack.currentIndex())
        except Exception:
            prev_idx = 0
        # 防御：未启用账号组时不允许切到 index=1
        if page_index not in (0, 1):
            page_index = 0
        if page_index == 1 and self.content_stack.count() < 2:
            page_index = 0

        if (
            getattr(self, "_tags_filter_only", False)
            and clear_tag_filter_on_pivot
            and prev_idx != page_index
        ):
            self._tag_filter_account_ids = None
            self._tag_filter_group_ids = None
            self._active_tag_id = None
            self._clear_tags_highlight()

        self.content_stack.setCurrentIndex(page_index)
        # 以实际切页结果为准（部分环境下 setCurrentIndex 可能被防御逻辑回退）
        try:
            actual_index = int(self.content_stack.currentIndex())
        except Exception:
            actual_index = page_index
        # 同步 Tab 选中项（避免外部直接 setCurrentIndex 导致样式不刷新）
        try:
            if actual_index == 0:
                self._pivot.setCurrentItem("accounts")
            else:
                self._pivot.setCurrentItem("groups")
        except Exception:
            pass
        self._sync_pivot_selection()
        self._on_page_changed(actual_index)
        if getattr(self, "_tags_filter_only", False):
            self._recompute_filtered_accounts()
            self._render_accounts()
            self._render_groups()

    def _recompute_filtered_accounts(self) -> None:
        """在平台筛选结果上叠加「标签筛选」（仅 tags_filter_only 时生效）。"""
        base = getattr(self, "_accounts_after_platform", None)
        if base is None:
            base = list(self.all_accounts or [])
            self._accounts_after_platform = base
        tids = getattr(self, "_tag_filter_account_ids", None)
        if getattr(self, "_tags_filter_only", False) and tids is not None:
            self._filtered_accounts = [a for a in base if a.get("id") in tids]
        else:
            self._filtered_accounts = list(base)

    def _groups_for_table(self) -> list:
        """账号组表格数据源（可叠加标签筛选）。"""
        base = list(self.groups or [])
        if not getattr(self, "_tags_filter_only", False):
            return base
        gids = getattr(self, "_tag_filter_group_ids", None)
        if gids is None:
            return base
        return [g for g in base if g.get("id") in gids]

    def _load_tags_async(self):
        try:
            from src.services.account.account_tag_service import AccountTagService
            import asyncio
            tag_service = AccountTagService()
            
            async def get_tags():
                try:
                    tags = await tag_service.get_tags()
                    self._all_tags = tags
                    self._render_tags()
                    self._rebuild_account_tags_cache()
                    self._refresh_account_tags_column()
                except Exception as e:
                    pass
                
            task = get_async_task_registry().create_task(
                get_tags(),
                name="ui.account_selection.load_tags",
                group="ui",
            )
            if not hasattr(self, '_bg_tasks'):
                self._bg_tasks = set()
            self._bg_tasks.add(task)
            task.add_done_callback(self._bg_tasks.discard)
        except Exception as e:
            pass

    def closeEvent(self, event):
        for task in list(getattr(self, "_bg_tasks", set())):
            if not task.done():
                task.cancel()
        getattr(self, "_bg_tasks", set()).clear()
        super().closeEvent(event)

    def _setup_platform_filter_options(self):
        """初始化平台筛选下拉框（基于账号列表动态生成）"""
        if not hasattr(self, "_platform_filter"):
            return
        from src.utils.platform_names import PLATFORM_ID_TO_NAME as platform_name_map
        plats = []
        for a in self.all_accounts or []:
            pid = a.get("platform", "")
            if pid and pid not in plats:
                plats.append(pid)
        items = ["全部"] + [platform_name_map.get(p, p) for p in plats]
        self._platform_filter.blockSignals(True)
        self._platform_filter.clear()
        self._platform_filter.addItems(items)
        self._platform_filter.setCurrentText("全部")
        self._platform_filter.blockSignals(False)

    def _on_platform_filter_changed(self, text: str):
        if getattr(self, "_tags_filter_only", False):
            self._tag_filter_account_ids = None
            self._tag_filter_group_ids = None
            self._active_tag_id = None
            self._clear_tags_highlight()
        self._apply_account_filter()

    def _apply_account_filter(self):
        """根据平台筛选重渲染账号表格（并可叠加标签筛选）"""
        from src.utils.platform_names import PLATFORM_ID_TO_NAME as platform_name_map
        wanted = self._platform_filter.currentText() if hasattr(self, "_platform_filter") else "全部"
        if wanted == "全部":
            self._accounts_after_platform = list(self.all_accounts or [])
        else:
            # wanted 为中文名，反查 platform_id
            pid = next((k for k, v in platform_name_map.items() if v == wanted), wanted)
            self._accounts_after_platform = [a for a in (self.all_accounts or []) if a.get("platform") == pid]
        self._recompute_filtered_accounts()
        self._render_accounts()
        self._update_select_all_state()
        self._render_tags()
        self._refresh_account_tags_column()
        self._refresh_media_stats_from_cache()
        if getattr(self, "_tags_filter_only", False):
            self._render_groups()

    def _update_select_all_state(self):
        """根据当前筛选结果更新全选状态（两态）"""
        if not self._multi_select:
            return
        visible = self._filtered_accounts or []
        total = len(visible)
        checked = 0
        for a in visible:
            aid = a.get("id")
            if aid is None:
                continue
            if aid in self._account_checked_ids:
                checked += 1
        self._select_all_accounts.blockSignals(True)
        # 两态：只有“当前筛选结果全部选中”才显示勾选，否则为空
        self._select_all_accounts.setChecked(bool(total > 0 and checked >= total))
        self._select_all_accounts.blockSignals(False)

    def _update_select_all_groups_state(self):
        """账号组页：根据当前勾选更新全选状态（两态）"""
        if not self._multi_select:
            return
        groups = self.groups or []
        total = len(groups)
        checked = 0
        for g in groups:
            gid = g.get("id")
            if gid is None:
                continue
            if gid in getattr(self, "_group_checked_ids", set()):
                checked += 1
        self._select_all_groups.blockSignals(True)
        self._select_all_groups.setChecked(bool(total > 0 and checked >= total))
        self._select_all_groups.blockSignals(False)
            
    def set_accounts(self, accounts):
        """兼容旧接口"""
        self.set_data(accounts, show_group_nav=False)
        
    def _render_accounts(self):
        """渲染账号列表"""
        self.account_table.setUpdatesEnabled(False)
        self.account_table.setSortingEnabled(False)
        self.account_table.clear()
        self.account_table.setRowCount(0)
        # 列：序号 / 平台 / 平台昵称 / 账号组 / 账号标签 / 视频库 / 图片库 / 勾选
        self.account_table.setColumnCount(8)
        self.account_table.setHorizontalHeaderLabels(["序号", "平台", "平台昵称", "账号组", "账号标签", "视频库", "图片库", ""])

        header = self.account_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # 平台昵称
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        self.account_table.setColumnWidth(0, 52)   # 序号
        self.account_table.setColumnWidth(1, 96)   # 平台（略收窄，给昵称列让空间）
        # 固定列尽量紧凑，把空间留给「平台昵称」（Stretch）
        self.account_table.setColumnWidth(3, 80)   # 账号组（收窄）
        self.account_table.setColumnWidth(4, 110)  # 账号标签（收窄）
        # 统计列显示“总/占用/未占用”，64 会被省略成 0/...，因此加宽
        self.account_table.setColumnWidth(5, 90)   # 视频库
        self.account_table.setColumnWidth(6, 90)   # 图片库
        self.account_table.setColumnWidth(7, 40)   # 勾选框
        self.account_table.verticalHeader().setVisible(False)
        self.account_table.setWordWrap(False)
        self.account_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.account_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.account_table.setSortingEnabled(True)
        self._col_tags = 4
        self._col_video_count = 5
        self._col_image_count = 6
        self._col_check = 7

        platform_icon_map = {
            'douyin': FluentIcon.VIDEO,
            'kuaishou': FluentIcon.VIDEO,
            'xiaohongshu': FluentIcon.BOOK_SHELF,
            'bilibili': FluentIcon.VIDEO,
            'wechat_video': FluentIcon.CHAT
        }
        
        from src.utils.platform_names import PLATFORM_ID_TO_NAME as platform_name_map
        
        accounts = self._filtered_accounts if getattr(self, "_filtered_accounts", None) is not None else (self.all_accounts or [])
        self.account_table.setRowCount(len(accounts))
        for row, account in enumerate(accounts):
            platform = account.get('platform', '')
            platform_cn = platform_name_map.get(platform, platform)
            _ = platform_icon_map.get(platform, FluentIcon.PEOPLE)  # 预留：后续可放图标
            
            username = account.get('platform_username') or account.get('account_name', '未命名')
            acc_id = self._norm_int_id(account.get("id"))
            g_name = ""
            if account.get('group_id'):
                g_name = next((g['group_name'] for g in self.groups if g['id'] == account['group_id']), "")
            
            display_group = g_name if g_name and g_name != "未分类" else ""

            # 序号
            item_idx = QTableWidgetItem(str(row + 1))
            item_idx.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            # 排序按数字
            try:
                item_idx.setData(Qt.UserRole, row + 1)
            except Exception:
                pass
            self.account_table.setItem(row, 0, item_idx)

            item_platform = QTableWidgetItem(platform_cn)
            item_platform.setData(Qt.UserRole, account)
            item_platform.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.account_table.setItem(row, 1, item_platform)

            item_name = QTableWidgetItem(username)
            item_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.account_table.setItem(row, 2, item_name)

            item_group = QTableWidgetItem(display_group)
            item_group.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if not display_group:
                item_group.setText("-")
                item_group.setForeground(QBrush(QColor("#CCCCCC")))
            self.account_table.setItem(row, 3, item_group)

            # 账号标签
            tag_text = ""
            if acc_id is not None:
                tag_text = self._account_tags_cache.get(acc_id, "") or ""
            tag_cell = QTableWidgetItem(tag_text if tag_text else "-")
            tag_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if not tag_text:
                tag_cell.setForeground(QBrush(QColor("#CCCCCC")))
            else:
                tag_cell.setToolTip(tag_text)
            self.account_table.setItem(row, self._col_tags, tag_cell)

            # 媒体库统计：总/占用/未占用（格式：总/占用/未占用）
            v_text = "—"
            i_text = "—"
            v_tip = "视频库：—"
            i_tip = "图片库：—"
            try:
                stats = self._media_stats_cache.get()
                if acc_id is not None and stats is not None:
                    vc = (stats.video.by_account_id or {}).get(int(acc_id))
                    ic = (stats.image.by_account_id or {}).get(int(acc_id))
                    if vc is not None:
                        v_text = f"{vc.total}/{vc.used}/{vc.unused}"
                        v_tip = f"视频库：总 {vc.total}，已占用 {vc.used}，未占用 {vc.unused}\n显示格式：总/占用/未占用"
                    if ic is not None:
                        i_text = f"{ic.total}/{ic.used}/{ic.unused}"
                        i_tip = f"图片库：总 {ic.total}，已占用 {ic.used}，未占用 {ic.unused}\n显示格式：总/占用/未占用"
            except Exception:
                pass
            item_v = QTableWidgetItem(v_text)
            item_v.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            item_v.setToolTip(v_tip)
            self.account_table.setItem(row, self._col_video_count, item_v)
            item_i = QTableWidgetItem(i_text)
            item_i.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            item_i.setToolTip(i_tip)
            self.account_table.setItem(row, self._col_image_count, item_i)

            if self._multi_select:
                cb = CheckBox("")
                cb.setFixedSize(20, 20)
                if acc_id is not None and acc_id in self._account_checked_ids:
                    cb.setChecked(True)

                def _on_cb_changed(state, _acc_id=acc_id, _cb=cb):
                    if _acc_id is None:
                        return
                    # PySide6 下 state 可能是 int 或 Qt.CheckState
                    try:
                        state_val = int(state)
                    except Exception:
                        try:
                            state_val = int(getattr(state, "value", 0))
                        except Exception:
                            state_val = 0
                            
                    if state_val == int(Qt.CheckState.Checked.value):
                        # 互斥逻辑升级：如果有账号组被选中，自动清除账号组并保留当前账号选择
                        if getattr(self, '_group_checked_ids', set()):
                            from qfluentwidgets import InfoBar, InfoBarPosition
                            self._clear_group_checks()
                            # 提示防抖：隐藏旧的，显示新的
                            if self._last_info_bar:
                                self._last_info_bar.close()
                            self._last_info_bar = InfoBar.info("自动切换", "已为您自动取消已选的账号组，改为按个人账号选择。", parent=self, position=InfoBarPosition.TOP, duration=2500)
                            
                        self._account_checked_ids.add(_acc_id)
                    else:
                        if _acc_id in self._account_checked_ids:
                            self._account_checked_ids.remove(_acc_id)
                    self._on_multi_select_changed()

                cb.stateChanged.connect(_on_cb_changed)
                w = QWidget(self.account_table)
                lay = QHBoxLayout(w)
                lay.setContentsMargins(0, 0, 0, 0)
                lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.addWidget(cb, 0, Qt.AlignmentFlag.AlignCenter)
                w._account_checkbox = cb
                self.account_table.setCellWidget(row, self._col_check, w)
            else:
                _empty = QTableWidgetItem("")
                _empty.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                self.account_table.setItem(row, self._col_check, _empty)

        self.account_table.setUpdatesEnabled(True)
        self.account_table.setSortingEnabled(True)
        self._refresh_account_tags_column()
        self._refresh_media_stats_from_cache()
        self._refresh_media_stats_async()

    def _rebuild_account_tags_cache(self) -> None:
        """根据 _all_tags 重建 account_id -> 标签文案 的缓存。"""
        cache = {}
        tags = getattr(self, "_all_tags", None) or []
        for tag in tags:
            name = (tag.get("name") or "").strip()
            if not name:
                continue
            for acc in (tag.get("accounts") or []):
                if not isinstance(acc, dict):
                    continue
                aid = acc.get("id")
                if aid is None:
                    continue
                cache.setdefault(aid, [])
                cache[aid].append(name)
        out = {}
        for aid, names in cache.items():
            uniq = []
            seen = set()
            for n in names:
                if n in seen:
                    continue
                seen.add(n)
                uniq.append(n)
            out[aid] = "、".join(uniq)
        self._account_tags_cache = out

    def _refresh_account_tags_column(self) -> None:
        """不重建表格，原地刷新「账号标签」列。"""
        if not hasattr(self, "account_table") or self.account_table is None:
            return
        if getattr(self, "content_stack", None) is not None and self.content_stack.currentIndex() != 0:
            return
        try:
            rc = self.account_table.rowCount()
        except Exception:
            return
        col = getattr(self, "_col_tags", 3)
        for row in range(rc):
            it0 = self.account_table.item(row, 1)
            acc = it0.data(Qt.UserRole) if it0 else None
            aid = acc.get("id") if isinstance(acc, dict) else None
            tag_text = self._account_tags_cache.get(aid, "") if aid is not None else ""
            cell = self.account_table.item(row, col)
            if cell is None:
                continue
            if tag_text:
                cell.setText(tag_text)
                cell.setToolTip(tag_text)
                cell.setForeground(QBrush())  # 恢复默认
            else:
                cell.setText("-")
                cell.setToolTip("")
                cell.setForeground(QBrush(QColor("#CCCCCC")))

    def _refresh_media_stats_async(self) -> None:
        """触发统计刷新（异步，避免阻塞弹窗）。"""
        try:
            get_async_task_registry().create_task(
                get_media_library_stats_service().refresh(),
                name="ui.account_selection.media_stats_refresh",
                group="ui",
            )
        except Exception:
            return

    def _refresh_media_stats_from_cache(self) -> None:
        """从全局统计缓存刷新当前表格显示（不做任何磁盘统计）。"""
        if getattr(self, "content_stack", None) is not None and self.content_stack.currentIndex() != 0:
            return
        try:
            rc = self.account_table.rowCount()
        except Exception:
            return
        stats = self._media_stats_cache.get()
        if stats is None:
            return
        for row in range(rc):
            it0 = self.account_table.item(row, 1)
            acc = it0.data(Qt.UserRole) if it0 else None
            aid = self._norm_int_id(acc.get("id")) if isinstance(acc, dict) else None
            if aid is None:
                continue
            vc = (stats.video.by_account_id or {}).get(aid)
            ic = (stats.image.by_account_id or {}).get(aid)
            itv = self.account_table.item(row, self._col_video_count)
            iti = self.account_table.item(row, self._col_image_count)
            if itv is not None and vc is not None:
                itv.setText(f"{vc.total}/{vc.used}/{vc.unused}")
                itv.setToolTip(f"视频库：总 {vc.total}，已占用 {vc.used}，未占用 {vc.unused}\n显示格式：总/占用/未占用")
            if iti is not None and ic is not None:
                iti.setText(f"{ic.total}/{ic.used}/{ic.unused}")
                iti.setToolTip(f"图片库：总 {ic.total}，已占用 {ic.used}，未占用 {ic.unused}\n显示格式：总/占用/未占用")

    def _on_media_stats_updated(self, _stats: object) -> None:
        """统计更新后，弹窗表格同步刷新账号/账号组数量列。"""
        self._refresh_media_stats_from_cache()
        try:
            self._refresh_group_media_stats_from_cache()
        except Exception:
            pass

    def _refresh_group_media_stats_from_cache(self) -> None:
        """账号组表格：从全局统计缓存刷新「视频库/图片库」汇总显示。"""
        if getattr(self, "content_stack", None) is not None and self.content_stack.currentIndex() != 1:
            return
        if not hasattr(self, "group_table") or self.group_table is None:
            return

        stats = self._media_stats_cache.get()
        if stats is None:
            return
        try:
            rc = self.group_table.rowCount()
        except Exception:
            return

        col_v = getattr(self, "_col_group_video_count", None)
        col_i = getattr(self, "_col_group_image_count", None)
        if col_v is None or col_i is None:
            return

        for row in range(rc):
            it_name = self.group_table.item(row, 1)
            g = it_name.data(Qt.UserRole) if it_name else None
            if not isinstance(g, dict):
                continue
            gid = g.get("id")
            try:
                gid_int = int(gid) if gid is not None else None
            except Exception:
                gid_int = None
            if gid_int is None:
                continue
            vc = (stats.video.by_group_id or {}).get(gid_int)
            ic = (stats.image.by_group_id or {}).get(gid_int)

            itv = self.group_table.item(row, col_v)
            iti = self.group_table.item(row, col_i)
            if itv is not None and vc is not None:
                itv.setText(f"{vc.total}/{vc.used}/{vc.unused}")
                itv.setToolTip(f"视频库：总 {vc.total}，已占用 {vc.used}，未占用 {vc.unused}\n显示格式：总/占用/未占用")
            if iti is not None and ic is not None:
                iti.setText(f"{ic.total}/{ic.used}/{ic.unused}")
                iti.setToolTip(f"图片库：总 {ic.total}，已占用 {ic.used}，未占用 {ic.unused}\n显示格式：总/占用/未占用")
            
    def _render_groups(self):
        """渲染账号组表格（信息密度更高）"""
        if not hasattr(self, "group_table") or self.group_table is None:
            return

        t = self.group_table
        t.setUpdatesEnabled(False)
        t.setSortingEnabled(False)
        t.clear()
        t.setRowCount(0)

        # 列：序号 / 账号组 / 平台 / 账号数 / 视频库 / 图片库 / 勾选
        t.setColumnCount(7)
        t.setHorizontalHeaderLabels(["序号", "账号组", "平台", "账号数", "视频库", "图片库", ""])

        header = t.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # 账号组名
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        # 列宽：整体更紧凑，且数字列统一
        t.setColumnWidth(0, 52)   # 序号
        t.setColumnWidth(2, 170)  # 平台
        t.setColumnWidth(3, 70)   # 账号数
        # 统计列显示“总/占用/未占用”，64 会被省略成 0/...，因此加宽
        t.setColumnWidth(4, 96)   # 视频库
        t.setColumnWidth(5, 96)   # 图片库
        t.setColumnWidth(6, 44)   # 勾选
        t.verticalHeader().setVisible(False)
        t.setWordWrap(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSortingEnabled(True)

        # 记录列索引，供其它逻辑使用
        self._col_group_video_count = 4
        self._col_group_image_count = 5
        self._col_group_check = 6

        from src.utils.platform_names import get_platform_display_name

        groups = self._groups_for_table()
        t.setRowCount(len(groups))
        for row, group in enumerate(groups):
            # 序号
            it_idx = QTableWidgetItem(str(row + 1))
            it_idx.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(row, 0, it_idx)

            # 账号组名（绑定 group 数据）
            gname = group.get("group_name", "未命名")
            it_name = QTableWidgetItem(str(gname))
            it_name.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            it_name.setData(Qt.UserRole, group)
            t.setItem(row, 1, it_name)

            # 平台（中文展示）
            plats = group.get("platforms", []) or []
            plats_cn = [get_platform_display_name(p) for p in plats] if plats else []
            it_plat = QTableWidgetItem("，".join(plats_cn) if plats_cn else "-")
            it_plat.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            if not plats_cn:
                it_plat.setForeground(QBrush(QColor("#CCCCCC")))
            t.setItem(row, 2, it_plat)

            # 账号数：优先 accounts 长度，其次 account_count
            accs = group.get("accounts")
            if isinstance(accs, list):
                cnt = len(accs)
            else:
                cnt = group.get("account_count", 0) or 0
            it_cnt = QTableWidgetItem(str(cnt))
            it_cnt.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(row, 3, it_cnt)

            # 视频库 / 图片库：先占位，随后从全局缓存汇总刷新
            it_v = QTableWidgetItem("—")
            it_v.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(row, self._col_group_video_count, it_v)
            it_i = QTableWidgetItem("—")
            it_i.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            t.setItem(row, self._col_group_image_count, it_i)

            # 勾选框
            if self._multi_select:
                cb = CheckBox("")
                cb.setFixedSize(20, 20)
                gid = group.get("id")
                if gid is not None and gid in getattr(self, "_group_checked_ids", set()):
                    cb.setChecked(True)

                def _on_cb_changed(state, _gid=gid):
                    try:
                        state_val = int(state)
                    except Exception:
                        try:
                            state_val = int(getattr(state, "value", 0))
                        except Exception:
                            state_val = 0
                    if state_val == int(Qt.CheckState.Checked.value):
                        # 互斥：选账号组时清空账号
                        if getattr(self, "_account_checked_ids", set()):
                            from qfluentwidgets import InfoBar, InfoBarPosition
                            self._clear_account_checks()
                            if self._last_info_bar:
                                self._last_info_bar.close()
                            self._last_info_bar = InfoBar.info(
                                "自动切换",
                                "已为您自动取消已选的个人账号，改为按账号组选择。",
                                parent=self,
                                position=InfoBarPosition.TOP,
                                duration=2500,
                            )
                        if _gid is not None:
                            self._group_checked_ids.add(_gid)
                    else:
                        if _gid is not None:
                            self._group_checked_ids.discard(_gid)
                    self._on_multi_select_changed()

                cb.stateChanged.connect(_on_cb_changed)
                w = QWidget(t)
                lay = QHBoxLayout(w)
                lay.setContentsMargins(0, 0, 0, 0)
                lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lay.addWidget(cb, 0, Qt.AlignmentFlag.AlignCenter)
                w._group_checkbox = cb
                t.setCellWidget(row, self._col_group_check, w)
            else:
                _empty = QTableWidgetItem("")
                _empty.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                t.setItem(row, self._col_group_check, _empty)

        t.setUpdatesEnabled(True)
        t.setSortingEnabled(True)
        # 渲染完成后，立即尝试从缓存刷新汇总媒体库数量
        try:
            self._refresh_group_media_stats_from_cache()
        except Exception:
            pass
            
    def _on_page_changed(self, page_index: int):
        """切换右侧视图后更新工具条/选择状态。"""
        self.yesButton.setEnabled(False)
        self.account_table.clearSelection()
        try:
            self.group_table.clearSelection()
        except Exception:
            pass
        self.selection_result = None
        if self._multi_select:
            self._on_multi_select_changed()
        # 底部工具条：多选时账号/账号组两页都显示；单选时仅在「账号列表」页显示（含平台筛选）
        if self._multi_select:
            self._toolbar.setVisible(page_index in (0, 1))
        else:
            self._toolbar.setVisible(page_index == 0)

        is_accounts_page = bool(page_index == 0)
        is_groups_page = bool(page_index == 1)

        self._select_all_accounts.setVisible(bool(self._multi_select and is_accounts_page))
        self._select_all_groups.setVisible(bool(self._multi_select and is_groups_page))
        self._platform_filter.setVisible(bool(is_accounts_page))

        if is_accounts_page:
            self._update_select_all_state()
        if is_groups_page:
            self._update_select_all_groups_state()
            try:
                self._refresh_group_media_stats_from_cache()
            except Exception:
                pass
        self._render_tags()

    def _on_toggle_select_all_groups(self, state: int):
        """账号组列表：全选/取消全选"""
        if not self._multi_select:
            return
        if self.content_stack.currentIndex() != 1:
            return
        try:
            state_val = int(state)
        except Exception:
            state_val = int(getattr(state, "value", 0) or 0)
        target = state_val == int(Qt.CheckState.Checked.value)

        # 互斥：选择账号组时清空账号选择
        if target and getattr(self, "_account_checked_ids", set()):
            from qfluentwidgets import InfoBar, InfoBarPosition
            self._clear_account_checks()
            if self._last_info_bar:
                self._last_info_bar.close()
            self._last_info_bar = InfoBar.info("自动切换", "已为您自动取消已选的个人账号，改为按账号组全选。", parent=self, position=InfoBarPosition.TOP, duration=2500)

        if not hasattr(self, "_group_checked_ids") or self._group_checked_ids is None:
            self._group_checked_ids = set()
        groups = self.groups or []
        visible_ids = [g.get("id") for g in groups if g.get("id") is not None]
        if target:
            for gid in visible_ids:
                self._group_checked_ids.add(gid)
        else:
            for gid in visible_ids:
                self._group_checked_ids.discard(gid)

        # 同步 UI 勾选框（账号组表格）
        try:
            rc = self.group_table.rowCount()
        except Exception:
            rc = 0
        for row in range(rc):
            w = self.group_table.cellWidget(row, getattr(self, "_col_group_check", 4))
            cb = getattr(w, "_group_checkbox", None) if w else None
            if not cb:
                continue
            it_name = self.group_table.item(row, 1)
            g = it_name.data(Qt.UserRole) if it_name else None
            gid = g.get("id") if isinstance(g, dict) else None
            should = bool(gid is not None and gid in self._group_checked_ids)
            if cb.isChecked() != should:
                cb.blockSignals(True)
                cb.setChecked(should)
                cb.blockSignals(False)

        self._on_multi_select_changed()
        
    def _on_account_cell_clicked(self, row: int, col: int):
        # 清除分组选区
        try:
            self.group_table.blockSignals(True)
            self.group_table.clearSelection()
            self.group_table.blockSignals(False)
        except Exception:
            pass

        if self._multi_select:
            w = self.account_table.cellWidget(row, getattr(self, "_col_check", 5))
            cb = getattr(w, "_account_checkbox", None) if w else None
            if cb:
                cb.setChecked(not cb.isChecked())
            return

        if self._enable_ctrl_multi_select:
            selected = []
            for idx in self.account_table.selectionModel().selectedRows():
                it0 = self.account_table.item(idx.row(), 1)
                acc = it0.data(Qt.UserRole) if it0 else None
                if acc:
                    selected.append(acc)
            if selected:
                self.selection_result = {'type': 'account', 'data': selected}
                self.yesButton.setEnabled(True)
            else:
                self.selection_result = None
                self.yesButton.setEnabled(False)
            return

        it0 = self.account_table.item(row, 1)
        acc = it0.data(Qt.UserRole) if it0 else None
        if acc:
            self.selection_result = {'type': 'account', 'data': acc}
            self.yesButton.setEnabled(True)
        
    def _on_account_cell_double_clicked(self, row: int, col: int):
        if self._multi_select or self._enable_ctrl_multi_select:
            return
        self._on_account_cell_clicked(row, col)
        self.accept()
    
    def _on_multi_select_changed(self):
        """多选模式下复选框或点击行变更时：更新选中结果、确定按钮、已选数量提示"""
        accounts = self._update_multi_account_selection()
        groups = self._update_multi_group_selection()

        self._selected_accounts = accounts
        self._selected_groups = groups

        if groups:
            self.selection_result = {'type': 'group', 'data': groups}
            hint = f"已选 {len(groups)} 个账号组"
        elif accounts:
            self.selection_result = {'type': 'account', 'data': accounts}
            hint = f"已选 {len(accounts)} 个账号"
        else:
            self.selection_result = None
            hint = ""

        self.yesButton.setEnabled(bool(self.selection_result))
        self._multi_select_hint.setText(hint)
        self._multi_select_hint.setVisible(bool(hint))

        # 同步“全选账号”复选框状态（仅账号页，由 _update_select_all_state 统一管理两态）
        if self._multi_select and (self.content_stack.currentIndex() == 0):
            self._update_select_all_state()
            
        self._update_tags_ui()

    # 旧：表头内全选复选框已移除，改为红框工具条展示

    def _on_toggle_select_all_accounts(self, state: int):
        """账号列表：全选/取消全选"""
        if not self._multi_select:
            return
        if self.content_stack.currentIndex() != 0:
            return
        # 两态：0=未选，2=全选（Qt.Checked 的 value）
        try:
            state_val = int(state)
        except Exception:
            state_val = int(getattr(state, "value", 0) or 0)
        target = state_val == int(Qt.CheckState.Checked.value)
        
        # 互斥逻辑升级：如果在全选时发现已经有账号组被选中
        if target and getattr(self, '_group_checked_ids', set()):
            from qfluentwidgets import InfoBar, InfoBarPosition
            self._clear_group_checks()
            # 提示防抖
            if self._last_info_bar:
                self._last_info_bar.close()
            self._last_info_bar = InfoBar.info("自动切换", "已为您自动取消已选的账号组，改为按个人账号全选。", parent=self, position=InfoBarPosition.TOP, duration=2500)
            
        visible = self._filtered_accounts or []
        visible_ids = [a.get("id") for a in visible if a.get("id") is not None]
        if target:
            for aid in visible_ids:
                self._account_checked_ids.add(aid)
        else:
            for aid in visible_ids:
                if aid in self._account_checked_ids:
                    self._account_checked_ids.remove(aid)

        # 只更新可见行的复选框显示
        for row in range(self.account_table.rowCount()):
            w = self.account_table.cellWidget(row, getattr(self, "_col_check", 5))
            cb = getattr(w, "_account_checkbox", None) if w else None
            if not cb:
                continue
            # 账号数据绑定在「平台」列（新增序号列后索引为 1）
            it0 = self.account_table.item(row, 1)
            acc = it0.data(Qt.UserRole) if it0 else None
            aid = acc.get("id") if isinstance(acc, dict) else None
            should = bool(aid is not None and aid in self._account_checked_ids)
            if cb.isChecked() != should:
                cb.blockSignals(True)
                cb.setChecked(should)
                cb.blockSignals(False)

        self._on_multi_select_changed()
        
        # 独立化：全选操作不应影响/联动下方的标签按钮高亮状态
        # 强制将所有标签按钮设为未选中（除非它们是手动触发的）
        self._clear_tags_highlight()
    
    def _update_multi_account_selection(self):
        """多选模式：按行内复选框收集选中账号列表"""
        selected = []
        for a in (self.all_accounts or []):
            aid = a.get("id")
            if aid is not None and aid in self._account_checked_ids:
                selected.append(a)
        return selected

    def _update_multi_group_selection(self):
        """多选模式：按已勾选集合收集选中账号组列表"""
        selected = []
        checked_ids = getattr(self, "_group_checked_ids", set()) or set()
        for g in (self.groups or []):
            gid = g.get("id")
            if gid is not None and gid in checked_ids:
                selected.append(g)
        return selected

    def _clear_account_checks(self):
        self._account_checked_ids.clear()
        for row in range(self.account_table.rowCount()):
            w = self.account_table.cellWidget(row, getattr(self, "_col_check", 5))
            cb = getattr(w, "_account_checkbox", None) if w else None
            if cb and cb.isChecked():
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)

    def _clear_group_checks(self):
        # 同步清空内存集合，避免“界面已清空但仍被判定为按账号组选择”导致标签不高亮
        try:
            self._group_checked_ids.clear()
        except Exception:
            self._group_checked_ids = set()
        # 同步更新表格上的复选框
        try:
            rc = self.group_table.rowCount() if hasattr(self, "group_table") else 0
        except Exception:
            rc = 0
        for row in range(rc):
            w = self.group_table.cellWidget(row, getattr(self, "_col_group_check", 4)) if rc else None
            cb = getattr(w, "_group_checkbox", None) if w else None
            if cb and cb.isChecked():
                cb.blockSignals(True)
                cb.setChecked(False)
                cb.blockSignals(False)

    def _update_ui_checkboxes(self):
        """同步更新UI复选框状态"""
        for row in range(self.account_table.rowCount()):
            w = self.account_table.cellWidget(row, getattr(self, "_col_check", 5))
            cb = getattr(w, "_account_checkbox", None) if w else None
            if cb:
                # 账号数据绑定在「平台」列（新增序号列后索引为 1）
                it0 = self.account_table.item(row, 1)
                acc = it0.data(Qt.UserRole) if it0 else None
                aid = acc.get("id") if isinstance(acc, dict) else None
                should = bool(aid is not None and aid in self._account_checked_ids)
                if cb.isChecked() != should:
                    cb.blockSignals(True)
                    cb.setChecked(should)
                    cb.blockSignals(False)
                    
        # 账号组表格复选框
        try:
            rcg = self.group_table.rowCount() if hasattr(self, "group_table") else 0
        except Exception:
            rcg = 0
        for row in range(rcg):
            w = self.group_table.cellWidget(row, getattr(self, "_col_group_check", 4))
            cb = getattr(w, "_group_checkbox", None) if w else None
            if not cb:
                continue
            it_name = self.group_table.item(row, 1)
            g = it_name.data(Qt.UserRole) if it_name else None
            gid = g.get("id") if isinstance(g, dict) else None
            should = bool(gid is not None and gid in getattr(self, "_group_checked_ids", set()))
            if cb.isChecked() != should:
                cb.blockSignals(True)
                cb.setChecked(should)
                cb.blockSignals(False)

    def _render_tags(self):
        """根据当前筛选的账号和组，渲染快捷标签按钮"""
        # 左侧标签面板：账号列表与账号组页都显示（提高空间利用与一致性）
        if hasattr(self, "_tags_panel") and self._tags_panel is not None:
            self._tags_panel.setVisible(True)

        plat_acc = getattr(self, "_accounts_after_platform", None)
        if plat_acc is None:
            plat_acc = self._filtered_accounts or []
        visible_acc_ids = {a.get("id") for a in plat_acc if a.get("id") is not None}
        visible_grp_ids = {g.get("id") for g in (self.groups or []) if g.get("id") is not None}
        
        # 清空旧按钮
        while self._tags_layout.count():
            item = self._tags_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        self._tag_buttons = {}
                
        has_tags = False
        for tag in self._all_tags:
            tag_acc_ids = {a.get('id') for a in tag.get('accounts', [])}
            tag_grp_ids = {g.get('id') for g in tag.get('groups', [])}
            
            acc_intersect = visible_acc_ids & tag_acc_ids
            grp_intersect = visible_grp_ids & tag_grp_ids
            
            if acc_intersect or grp_intersect:
                has_tags = True
                tname = str(tag.get('name') or '').strip()
                btn = TogglePushButton(tname, self._tags_widget)
                btn.setObjectName("AccountTagPill")
                btn.setProperty('tag_data', tag)
                btn.setCheckable(True)
                btn.setFixedHeight(34)
                btn.setMinimumWidth(136)
                # 图标 + 悬停解释，帮助区分「账号标签」与「账号组标签」
                tag_type = (tag or {}).get("tag_type")
                if tag_type not in ("account", "group"):
                    # 兼容旧数据：按已关联对象推断；都没有则默认账号标签
                    is_group_tag = bool(tag.get("groups")) and not bool(tag.get("accounts"))
                else:
                    is_group_tag = bool(tag_type == "group")
                btn.setProperty("tagKind", "group" if is_group_tag else "account")

                try:
                    # 与账号标签卡片保持一致：账号=人物，账号组=库/文件夹
                    icon_account = getattr(FluentIcon, "PEOPLE", FluentIcon.CERTIFICATE)
                    icon_group = getattr(FluentIcon, "LIBRARY", getattr(FluentIcon, "FOLDER", FluentIcon.CERTIFICATE))
                    btn.setIcon((icon_group if is_group_tag else icon_account).icon())
                    btn.setIconSize(QSize(14, 14))
                except Exception:
                    # 兼容：部分版本 TogglePushButton 可能不支持 setIcon()
                    pass

                # 用 Fluent 自绘提示替代原生黑底 ToolTip（Windows 下更一致）
                tip = (
                    f"{tname}\n账号组标签：用于给账号组做归类"
                    if is_group_tag
                    else f"{tname}\n账号标签：用于给账号做归类"
                )
                apply_instructional_tooltip(
                    tip,
                    btn,
                    show_delay_ms=250,
                    position=ToolTipPosition.RIGHT,
                )

                # 绑定 tag_id，避免闭包变量在循环中被覆盖导致“点A亮B”
                try:
                    tid = int(tag.get("id")) if tag.get("id") is not None else None
                except Exception:
                    tid = None

                def _on_clicked(checked: bool, t=tag, b=btn, _tid=tid):
                    # 单选：选中一个就取消其它；取消则清空选择
                    if checked:
                        # 记录当前激活标签（用于强一致的单选高亮）
                        self._active_tag_id = _tid
                        for other in self._tag_buttons.values():
                            if other is b:
                                continue
                            if other.isChecked():
                                other.blockSignals(True)
                                other.setChecked(False)
                                other.blockSignals(False)
                    else:
                        if self._active_tag_id == _tid:
                            self._active_tag_id = None
                    self._on_tag_quick_select(t, checked)

                btn.clicked.connect(_on_clicked)
                self._tags_layout.addWidget(btn, 0)
                if tid is not None:
                    self._tag_buttons[tid] = btn
                
        # 底部撑开，避免按钮堆在中间
        self._tags_layout.addStretch(1)
        self._update_tags_ui()

    def _clear_tags_highlight(self):
        """强制清空所有快捷标签的高亮选中状态"""
        for i in range(self._tags_layout.count()):
            item = self._tags_layout.itemAt(i)
            if item and hasattr(item, 'widget'):
                btn = item.widget()
                if isinstance(btn, TogglePushButton):
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)

    def _update_tags_ui(self):
        """根据当前的选中集合，更新快捷标签的高亮状态"""
        plat_acc = getattr(self, "_accounts_after_platform", None)
        if plat_acc is None:
            plat_acc = self._filtered_accounts or []
        visible_acc_ids = {a.get("id") for a in plat_acc if a.get("id") is not None}
        visible_grp_ids = {g.get("id") for g in (self.groups or []) if g.get("id") is not None}

        # 若用户是通过“点击某个标签”进入的单选状态，则优先只高亮该标签，避免多个标签同时点亮造成困扰
        active_id = getattr(self, "_active_tag_id", None)
        if active_id is not None and active_id in getattr(self, "_tag_buttons", {}):
            for tid, btn in list(self._tag_buttons.items()):
                should = tid == active_id
                if btn.isChecked() != should:
                    btn.blockSignals(True)
                    btn.setChecked(should)
                    btn.blockSignals(False)
            return

        if getattr(self, "_tags_filter_only", False):
            for btn in list(getattr(self, "_tag_buttons", {}).values()):
                if not isinstance(btn, TogglePushButton):
                    continue
                if btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
            return

        # 仅同步真实标签按钮（跳过底部 stretch）
        for btn in list(getattr(self, "_tag_buttons", {}).values()):
            if not isinstance(btn, TogglePushButton):
                continue
            tag = btn.property('tag_data')
            if not tag:
                continue
            tag_acc_ids = {a.get('id') for a in tag.get('accounts', [])}
            tag_grp_ids = {g.get('id') for g in tag.get('groups', [])}
            
            valid_accs = tag_acc_ids & visible_acc_ids
            valid_grps = tag_grp_ids & visible_grp_ids
            
            # 规则：一个标签只能包含账号或账号组其中一种
            is_active = False
            if valid_grps:
                is_active = bool(valid_grps <= self._group_checked_ids)
            elif valid_accs:
                is_active = bool(valid_accs <= self._account_checked_ids)
            
            if btn.isChecked() != is_active:
                btn.blockSignals(True)
                btn.setChecked(is_active)
                btn.blockSignals(False)

    def _on_tag_quick_select(self, tag, checked=True):
        """点击标签，快捷选中或取消包含的对象"""
        tag_acc_ids = {a.get('id') for a in tag.get('accounts', [])}
        tag_grp_ids = {g.get('id') for g in tag.get('groups', [])}

        plat_acc = getattr(self, "_accounts_after_platform", None)
        if plat_acc is None:
            plat_acc = self._filtered_accounts or []
        visible_acc_ids = {a.get("id") for a in plat_acc if a.get("id") is not None}
        visible_grp_ids = {g.get("id") for g in (self.groups or []) if g.get("id") is not None}

        valid_accs = tag_acc_ids & visible_acc_ids
        valid_grps = tag_grp_ids & visible_grp_ids

        if getattr(self, "_tags_filter_only", False):
            self.selection_result = None
            self.yesButton.setEnabled(False)
            if not checked:
                self._tag_filter_account_ids = None
                self._tag_filter_group_ids = None
                self._active_tag_id = None
                self._clear_tags_highlight()
                self._recompute_filtered_accounts()
                self._render_accounts()
                self._render_groups()
                self._render_tags()
                self.account_table.scrollToTop()
                return
            if valid_grps:
                self._tag_filter_account_ids = None
                self._tag_filter_group_ids = set(valid_grps)
                self._set_current_page(1, False)
            elif valid_accs:
                self._tag_filter_account_ids = set(valid_accs)
                self._tag_filter_group_ids = None
                self._set_current_page(0, False)
            else:
                return
            if self.content_stack.currentIndex() == 0:
                self.account_table.scrollToTop()
            else:
                self.group_table.scrollToTop()
            return

        if checked:
            # 体验优化：在「账号组」页点击标签但实际命中的是账号时，自动切回账号列表页；
            # 命中账号组时则切到账号组页，避免用户感觉“点击没反应”。
            try:
                # 标签只允许绑定一种类型：优先按命中类型切页
                if valid_grps:
                    self._set_current_page(1)
                else:
                    self._set_current_page(0)
            except Exception:
                pass
            # 单选模式：点击新标签时，彻底清空之前所有的选择状态（内存+UI）并恢复原始排序
            self._clear_account_checks()
            self._clear_group_checks()
            self._apply_account_filter() # 恢复原始顺序
            
            if valid_grps:
                for gid in valid_grps:
                    self._group_checked_ids.add(gid)
            else:
                for aid in valid_accs:
                    self._account_checked_ids.add(aid)
                
                # 置顶显示选中的账号：对 visible 列表重新排序，将已选中的排在前面
                if valid_accs and hasattr(self, "_filtered_accounts"):
                    # 稳定排序：已选在前，未选在后
                    self._filtered_accounts.sort(key=lambda a: a.get("id") not in self._account_checked_ids)
                    # 重新渲染表格
                    self._render_accounts()
                    # 滚动到顶部
                    self.account_table.scrollToTop()
        else:
            if valid_grps:
                for gid in valid_grps:
                    self._group_checked_ids.discard(gid)
            if valid_accs:
                for aid in valid_accs:
                    self._account_checked_ids.discard(aid)
                
                # 取消选择标签时，恢复账号列表的原始排序（重新触发筛选过滤即可）
                self._apply_account_filter()
                self.account_table.scrollToTop()
                
        self._update_ui_checkboxes()
        self._on_multi_select_changed()
    
    def _has_valid_selection(self):
        """是否有有效选择"""
        if self._multi_select:
            return bool(self.selection_result and len(self.selection_result.get('data', [])) > 0)
        return self.selection_result is not None
        
    # 旧的 QListWidget 账号组点击处理已替换为表格版本：_on_group_cell_clicked / _on_group_cell_double_clicked

    def _on_group_cell_clicked(self, row: int, col: int):
        """账号组表格点击"""
        # 清除账号选区
        try:
            self.account_table.blockSignals(True)
            self.account_table.clearSelection()
            self.account_table.blockSignals(False)
        except Exception:
            pass

        if self._multi_select:
            w = self.group_table.cellWidget(row, getattr(self, "_col_group_check", 4))
            cb = getattr(w, "_group_checkbox", None) if w else None
            if cb:
                cb.setChecked(not cb.isChecked())
            return

        it = self.group_table.item(row, 1)
        g = it.data(Qt.UserRole) if it else None
        if g:
            self.selection_result = {"type": "group", "data": g}
            self.yesButton.setEnabled(True)

    def _on_group_cell_double_clicked(self, row: int, col: int):
        if self._multi_select:
            return
        self._on_group_cell_clicked(row, col)
        self.accept()

    def get_selected_result(self):
        """获取选择结果 {'type': 'account'|'group', 'data': ...}"""
        if self._multi_select:
            self._on_multi_select_changed()
        return self.selection_result
    
    def get_selected_account(self):
        """兼容旧接口：单选时返回单个 account，多选时返回 account 列表"""
        if self.selection_result and self.selection_result['type'] == 'account':
            data = self.selection_result['data']
            if self._multi_select and isinstance(data, list):
                return data  # 多选：返回列表
            return data if not isinstance(data, list) else (data[0] if data else None)
        return None
    
    def get_selected_accounts(self):
        """多选时返回选中的账号列表，单选时返回单元素列表或空列表"""
        acc = self.get_selected_account()
        if acc is None:
            return []
        return acc if isinstance(acc, list) else [acc]
