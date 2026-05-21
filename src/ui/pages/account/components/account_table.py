# -*- coding: utf-8 -*-
"""
账号表格组件
文件路径：src/ui/pages/account/components/account_table.py
功能：独立的账号列表表格组件，负责账号的显示和基本交互
"""

from datetime import datetime
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

from PySide6.QtWidgets import (
    QWidget, QTableWidget, QTableWidgetItem, QHBoxLayout, QVBoxLayout,
    QLabel,
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QFont, QColor, QPalette, QBrush
import logging
import os


try:
    from qfluentwidgets import (
        FluentIcon, BodyLabel, IconWidget,
        TransparentToolButton, InfoBadge,
    )
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False

from src.ui.components.rubber_band_row_table import RubberBandRowSelectTable
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.ui.utils.async_helper import AsyncWorker
from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.services.material.media_library_stats_cache import get_media_library_stats_cache
from src.services.material.media_library_stats_service import get_media_library_stats_service

logger = logging.getLogger(__name__)

_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_LATEST_PUBLISH_TIME_FMT = "%Y-%m-%d %H:%M"
_LATEST_PUBLISH_PAST_RED = QColor("#E81123")


class AccountTableWidget(QWidget):
    """账号表格组件
    
    负责显示账号列表，处理选择、筛选等基本交互。
    通过信号与外部通信，保持组件的独立性。
    """
    
    # 信号定义
    account_double_clicked = Signal(int)  # 账号ID
    account_selected = Signal(list)       # 选中的账号ID列表
    switch_account_requested = Signal(int) # 账号ID
    context_menu_requested = Signal(dict, object)  # account_data, pos
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.table = None
        self._stats_cache = get_media_library_stats_cache()
        self._render_batch_timers: List[QTimer] = []
        try:
            self._stats_cache.statsUpdated.connect(self._on_media_stats_updated)
        except Exception:
            pass
        self._fit_columns_timer = QTimer(self)
        self._fit_columns_timer.setSingleShot(True)
        self._fit_columns_timer.setInterval(0)
        self._fit_columns_timer.timeout.connect(self._apply_column_layout)
        self._latest_publish_style_timer = QTimer(self)
        self._latest_publish_style_timer.setInterval(60_000)
        self._latest_publish_style_timer.timeout.connect(self._refresh_latest_publish_time_column_styles)
        self._setup_ui()

    def closeEvent(self, event):
        self._cancel_render_batch_timers()
        super().closeEvent(event)

    def _schedule_render_batch(self, callback) -> None:
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
        for timer in list(self._render_batch_timers):
            timer.stop()
            timer.deleteLater()
        self._render_batch_timers = []

    @staticmethod
    def _fmt_counts(total: int, used: int, unused: int) -> str:
        try:
            return f"{int(total)}/{int(used)}/{int(unused)}"
        except Exception:
            return "—"

    @staticmethod
    def _counts_tooltip(kind: str, total: int, used: int, unused: int) -> str:
        return f"{kind}：总 {total}，已占用 {used}，未占用 {unused}\n显示格式：总/占用/未占用"

    @staticmethod
    def _latest_publish_cell_should_be_red(display_text: str) -> bool:
        """展示串为 YYYY-MM-DD HH:mm 且严格早于当前北京时间则 True（标红）。"""
        s = (display_text or "").strip()
        if not s or s in ("-", "—"):
            return False
        if len(s) < 16:
            return False
        try:
            naive = datetime.strptime(s[:16], _LATEST_PUBLISH_TIME_FMT)
        except ValueError:
            return False
        cell = naive.replace(tzinfo=_SHANGHAI_TZ)
        now = datetime.now(_SHANGHAI_TZ)
        return cell < now

    def _apply_latest_publish_time_cell_style(self, item: QTableWidgetItem, display_text: str) -> None:
        if self._latest_publish_cell_should_be_red(display_text):
            item.setForeground(QBrush(_LATEST_PUBLISH_PAST_RED))
        else:
            item.setData(Qt.ItemDataRole.ForegroundRole, None)

    def _refresh_latest_publish_time_column_styles(self) -> None:
        if not self.table:
            return
        try:
            rc = self.table.rowCount()
        except Exception:
            return
        for row in range(rc):
            it = self.table.item(row, 7)
            if it is None:
                continue
            self._apply_latest_publish_time_cell_style(it, it.text())

    def _sync_latest_publish_style_timer(self) -> None:
        t = getattr(self, "_latest_publish_style_timer", None)
        if t is None or not self.table:
            return
        try:
            if self.table.rowCount() > 0:
                if not t.isActive():
                    t.start()
            else:
                t.stop()
        except Exception:
            pass

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建表格（统一使用 RubberBandRowSelectTable 支持橡皮筋框选）
        if FLUENT_WIDGETS_AVAILABLE:
            self.table = RubberBandRowSelectTable(self)
            self._setup_table_style(self.table)
            # RubberBandRowSelectTable.__init__ 已内置 2px padding；不调用 setBorderRadius
            # 等 Fluent 样式 API，避免触发 CustomStyleSheetWatcher 递归崩溃。
            self.table.setObjectName("AccountTable")
            palette = self.table.palette()
            palette.setColor(QPalette.Highlight, QColor(0, 120, 212, 15))
            palette.setColor(QPalette.HighlightedText, QColor("black"))
            self.table.setPalette(palette)
        else:
            self.table = QTableWidget(self)

        # 设置列
        # 平台 / 昵称 / 状态 / 账号组 / 标签 / 视频库 / 图文库 / 已发布最晚时间 / 操作
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "平台", "平台昵称", "登录状态", "账号组", "账号标签", "视频库", "图文库", "已发布最晚时间", "操作"
        ])

        # 设置表头居中
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter | Qt.AlignVCenter)

        # ResizeMode：昵称（1）、账号组（2）、标签（3）Interactive；平台（0）、状态（4）、操作（6）Fixed
        from PySide6.QtWidgets import QHeaderView as _QHV
        _h = self.table.horizontalHeader()
        _h.setSectionResizeMode(_QHV.ResizeMode.Fixed)
        _h.setSectionResizeMode(1, _QHV.ResizeMode.Interactive)
        _h.setSectionResizeMode(2, _QHV.ResizeMode.Fixed)        # 登录状态 Fixed
        _h.setSectionResizeMode(3, _QHV.ResizeMode.Interactive)  # 账号组 Interactive
        _h.setSectionResizeMode(4, _QHV.ResizeMode.Interactive)  # 账号标签 Interactive
        _h.setSectionResizeMode(5, _QHV.ResizeMode.Fixed)        # 视频库 Fixed
        _h.setSectionResizeMode(6, _QHV.ResizeMode.Fixed)        # 图文库 Fixed
        _h.setSectionResizeMode(7, _QHV.ResizeMode.Interactive)  # 已发布最晚时间 Interactive
        _h.setMinimumSectionSize(52)

        # 设置列宽
        # 说明：旧版宽度总和偏大，窗口还原时容易出现横向滚动条。
        # 新策略：关键固定列瘦身 + 其余列按可用宽度动态分配，尽量不需要横向滚动。
        self._apply_column_layout()

        # RubberBandRowSelectTable 自带 NoDragDrop；显式设置选择模式
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        
        # 连接信号
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        
        layout.addWidget(self.table)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # resize 过程中 table/viewport 宽度可能尚未稳定，延后到下一轮事件循环再计算更稳
        try:
            self._fit_columns_timer.start()
        except Exception:
            pass

    def _apply_column_layout(self) -> None:
        """根据当前表格可用宽度动态分配列宽，尽量避免出现横向滚动条。"""
        if not getattr(self, "table", None):
            return

        table = self.table
        try:
            viewport_w = int(table.viewport().width())
        except Exception:
            return
        if viewport_w <= 0:
            return

        # 固定列：平台、登录状态、视频库、图文库、操作（内容短且可压缩）
        fixed = {
            0: 112,  # 平台（图标+平台名）
            2: 86,   # 登录状态（在线/离线徽章）
            5: 64,   # 视频库
            6: 64,   # 图文库
            8: 92,   # 操作（单个按钮）
        }

        # 弹性列：昵称 / 账号组 / 标签 / 已发布最晚时间
        flex_min = {
            1: 120,  # 平台昵称
            3: 90,   # 账号组
            4: 120,  # 账号标签
            7: 136,  # 已发布最晚时间
        }
        flex_pref = {
            1: 160,
            3: 100,
            4: 140,
            7: 150,
        }

        total_fixed = sum(fixed.values())
        total_flex_min = sum(flex_min.values())

        # 预留一点安全边距（避免样式边框/滚动条占位导致刚好溢出）
        safety = 10
        available = max(0, viewport_w - safety)

        # 先把固定列设置到位
        for col, w in fixed.items():
            try:
                table.setColumnWidth(col, int(w))
            except Exception:
                pass

        # 宽度不足：至少保证各列最小可读性，必要时允许出现横向滚动条
        if available < (total_fixed + total_flex_min):
            for col, w in flex_min.items():
                try:
                    table.setColumnWidth(col, int(w))
                except Exception:
                    pass
            return

        remaining = available - total_fixed

        # 按偏好宽度分配剩余空间，若有富余则按比例扩展
        pref_sum = sum(flex_pref.values())
        if pref_sum <= 0:
            pref_sum = 1

        widths: Dict[int, int] = {}
        for col, pref in flex_pref.items():
            share = int(remaining * (pref / pref_sum))
            widths[col] = max(int(flex_min[col]), share)

        # 修正因取整导致的误差：把差值补到昵称列（更常需要空间）
        used = sum(widths.values())
        diff = remaining - used
        if diff != 0:
            widths[1] = max(widths[1] + diff, int(flex_min[1]))

        for col, w in widths.items():
            try:
                table.setColumnWidth(col, int(w))
            except Exception:
                pass
    
    def _setup_table_style(self, table):
        """设置表格非样式属性（Fluent UI）。

        不调用 setBorderVisible/setBorderRadius，避免触发 CustomStyleSheetWatcher 递归崩溃。
        边框样式由 Fluent TableWidget 默认值决定。
        """
        if not FLUENT_WIDGETS_AVAILABLE:
            return
        table.setWordWrap(False)
        # 设置行号（垂直表头）居中
        table.verticalHeader().setDefaultAlignment(Qt.AlignCenter)
        table.verticalHeader().setMinimumSectionSize(52) # 保持行高一致
    
    def load_accounts(self, accounts: List[Dict]):
        """加载账号列表
        
        Args:
            accounts: 账号列表，每个账号是一个字典
        """
        table = self.table
        table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        table.blockSignals(True)
        # 预先获取主题，避免每行重复调用 isDarkTheme()
        from qfluentwidgets import isDarkTheme as _isDarkTheme
        self._cached_is_dark = _isDarkTheme()

        table.setRowCount(0)
        n = len(accounts)
        table.setRowCount(n)

        _BATCH = 100
        self._cancel_render_batch_timers()
        self._load_render_gen = getattr(self, "_load_render_gen", 0) + 1
        render_gen = self._load_render_gen

        def _render_batch(start: int) -> None:
            if render_gen != self._load_render_gen:
                return
            end = min(start + _BATCH, n)
            table.blockSignals(True)
            for row in range(start, end):
                self._add_account_row(accounts[row], row)
            table.blockSignals(False)
            if end < n:
                self._schedule_render_batch(lambda end=end: _render_batch(end))
            else:
                table.setSortingEnabled(True)
                table.setUpdatesEnabled(True)
                logger.info("账号表格加载完成，共 %s 个账号", n)
                self._refresh_media_stats_async()
                self._sync_latest_publish_style_timer()

        if n <= _BATCH:
            for row in range(n):
                self._add_account_row(accounts[row], row)
            table.blockSignals(False)
            table.setSortingEnabled(True)
            table.setUpdatesEnabled(True)
            logger.info("账号表格加载完成，共 %s 个账号", n)
            self._refresh_media_stats_async()
            self._sync_latest_publish_style_timer()
        else:
            table.blockSignals(False)
            _render_batch(0)

    def _refresh_media_stats_async(self) -> None:
        """触发媒体库统计刷新（异步，结果通过 statsUpdated 推送）。"""
        try:
            get_async_task_registry().create_task(
                get_media_library_stats_service().refresh(),
                name="ui.account_table.media_stats_refresh",
                group="ui",
            )
        except Exception:
            return
    
    def _add_account_row(self, account: Dict, row: int):
        """在指定行写入账号数据（行已由 setRowCount 预分配）。"""
        self.table.setRowHeight(row, 52)
        
        # 1. 平台列（带图标）
        platform = account.get('platform', '')
        platform_name = self._get_platform_name(platform)
        
        platform_container = QWidget()
        platform_layout = QHBoxLayout(platform_container)
        platform_layout.setContentsMargins(12, 0, 8, 0)
        platform_layout.setSpacing(8)
        platform_layout.setAlignment(Qt.AlignCenter)
        
        icon_label = IconWidget(self._get_platform_icon(platform), platform_container)
        icon_label.setFixedSize(24, 24)
        
        name_label = BodyLabel(platform_name, platform_container)
        is_dark = getattr(self, '_cached_is_dark', None)
        if is_dark is None:
            from qfluentwidgets import isDarkTheme
            is_dark = isDarkTheme()
        text_color = "#EEEEEE" if is_dark else "#333333"
        name_label.setStyleSheet(f"font-weight: bold; color: {text_color}; font-size: 13px;")
        
        platform_layout.addWidget(icon_label)
        platform_layout.addWidget(name_label)
        
        self.table.setCellWidget(row, 0, platform_container)
        
        # 隐藏的文本项（用于排序和搜索）
        hidden_item = QTableWidgetItem("")
        hidden_item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        hidden_item.setData(Qt.ItemDataRole.UserRole, platform)
        self.table.setItem(row, 0, hidden_item)
        
        # 2. 昵称列
        platform_username = account.get('platform_username') or account.get('account_name', '未命名')
        item_name = QTableWidgetItem(platform_username)
        item_name.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        item_name.setData(Qt.ItemDataRole.UserRole, account.get('id'))
        item_name.setData(Qt.ItemDataRole.UserRole + 1, platform_username)
        item_name.setData(Qt.ItemDataRole.UserRole + 2, account.get('profile_folder_name'))
        self.table.setItem(row, 1, item_name)
        
        # 3. 登录状态（移到昵称后面）
        login_status = account.get('login_status', 'offline')
        status_widget = self._create_status_widget(login_status)
        self.table.setCellWidget(row, 2, status_widget)
        
        # 4. 账号组列
        group_name = account.get('group_name')
        display_group = group_name if group_name and group_name != '未分类' else ""
        item_group = QTableWidgetItem(display_group)
        item_group.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        if not display_group:
            # 如果没有分组，显示一个浅色的占位横线，或者留空
            item_group.setText("-")
            item_group.setForeground(QBrush(QColor("#CCCCCC")))
        self.table.setItem(row, 3, item_group)
        self.table.removeCellWidget(row, 3)
        
        # 5. 账号标签（彩色气泡优化）
        tags = account.get('tags', [])
        self.table.removeCellWidget(row, 4) # 先清理旧组件
        if tags:
            tag_container = QWidget()
            tag_layout = QHBoxLayout(tag_container)
            tag_layout.setContentsMargins(4, 0, 4, 0)
            tag_layout.setSpacing(6)
            tag_layout.setAlignment(Qt.AlignCenter)
            
            tag_qss = """
                QLabel {
                    background-color: #E1F5FE;
                    color: #01579B;
                    border: 1px solid #B3E5FC;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                    font-weight: bold;
                }
            """
            for t_name in tags:
                lbl = QLabel(t_name)
                lbl.setStyleSheet(tag_qss)
                tag_layout.addWidget(lbl)
            
            self.table.setCellWidget(row, 4, tag_container)
            # 同时设置隐藏文本项（设为空字符串，避免文字和气泡重叠，但保持 Data 供搜索）
            hidden_tag = QTableWidgetItem("")
            hidden_tag.setData(Qt.ItemDataRole.DisplayRole, "")
            hidden_tag.setData(Qt.ItemDataRole.UserRole, ", ".join(tags))
            self.table.setItem(row, 4, hidden_tag)
        else:
            item_no_tag = QTableWidgetItem("-")
            item_no_tag.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            item_no_tag.setForeground(QBrush(QColor("#CCCCCC")))
            self.table.setItem(row, 4, item_no_tag)
            self.table.removeCellWidget(row, 4)

        # 6. 视频库 / 7. 图文库（显示：总/占用/未占用；数据来自全局统计缓存）
        acc_id = account.get("id")
        v_text = "—"
        i_text = "—"
        v_tip = "视频库：—"
        i_tip = "图文库：—"
        try:
            aid = int(acc_id) if acc_id is not None else None
        except Exception:
            aid = None
        try:
            stats = self._stats_cache.get()
            if aid is not None and stats is not None:
                vc = (stats.video.by_account_id or {}).get(aid)
                ic = (stats.image.by_account_id or {}).get(aid)
                if vc is not None:
                    v_text = self._fmt_counts(vc.total, vc.used, vc.unused)
                    v_tip = self._counts_tooltip("视频库", vc.total, vc.used, vc.unused)
                if ic is not None:
                    i_text = self._fmt_counts(ic.total, ic.used, ic.unused)
                    i_tip = self._counts_tooltip("图文库", ic.total, ic.used, ic.unused)
        except Exception:
            pass

        item_video = QTableWidgetItem(v_text)
        item_video.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        item_video.setToolTip(v_tip)
        self.table.setItem(row, 5, item_video)
        item_image = QTableWidgetItem(i_text)
        item_image.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        item_image.setToolTip(i_tip)
        self.table.setItem(row, 6, item_image)

        # 8. 已发布最晚时间
        latest_publish_time = str(account.get("latest_publish_time") or "-")
        item_latest = QTableWidgetItem(latest_publish_time)
        item_latest.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        self.table.setItem(row, 7, item_latest)
        self._apply_latest_publish_time_cell_style(item_latest, latest_publish_time)

        # 9. 操作列
        actions_widget = self._create_actions_widget(account)
        self.table.setCellWidget(row, 8, actions_widget)

    def _on_media_stats_updated(self, stats: object) -> None:
        """统计刷新后原地更新「视频库/图文库」两列（不重建表格）。"""
        if not self.table:
            return
        if stats is None:
            return
        try:
            rc = self.table.rowCount()
        except Exception:
            return

        for row in range(rc):
            id_item = self.table.item(row, 1)
            if id_item is None:
                continue
            aid = id_item.data(Qt.ItemDataRole.UserRole)
            try:
                aid_int = int(aid)
            except Exception:
                continue

            vc = getattr(getattr(stats, "video", None), "by_account_id", {}).get(aid_int)
            ic = getattr(getattr(stats, "image", None), "by_account_id", {}).get(aid_int)

            itv = self.table.item(row, 5)
            iti = self.table.item(row, 6)
            if itv is not None and vc is not None:
                itv.setText(self._fmt_counts(vc.total, vc.used, vc.unused))
                itv.setToolTip(self._counts_tooltip("视频库", vc.total, vc.used, vc.unused))
            if iti is not None and ic is not None:
                iti.setText(self._fmt_counts(ic.total, ic.used, ic.unused))
                iti.setToolTip(self._counts_tooltip("图文库", ic.total, ic.used, ic.unused))

    def closeEvent(self, event) -> None:
        """组件关闭时无需停止统计线程（已改为全局服务 + 缓存推送）。"""
        try:
            self._latest_publish_style_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)
    
    def _create_status_widget(self, login_status: str, tooltip: str = "") -> QWidget:
        """创建状态显示组件
        
        Args:
            login_status: 登录状态 ('online' / 'offline')
            tooltip: 离线原因悬浮提示（仅离线时有效）
        """
        # 使用固定高度的容器来确保垂直居中
        status_widget = QWidget()
        status_widget.setFixedHeight(50)  # 匹配行高 52px
        
        # 离线时，在整个状态单元格容器上设置悬浮提示
        if login_status != 'online' and tooltip:
            status_widget.setToolTip(f"离线原因：{tooltip}")
        
        # 使用 QVBoxLayout + QHBoxLayout 实现双向居中
        main_layout = QVBoxLayout(status_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        main_layout.addStretch(1)
        
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(0)
        
        try:
            if FLUENT_WIDGETS_AVAILABLE:
                badge = InfoBadge.success("在线") if login_status == 'online' else InfoBadge.error("离线")
                h_layout.addStretch()
                h_layout.addWidget(badge)
                h_layout.addStretch()
        except Exception:
            status_color = "#107C10" if login_status == 'online' else "#E81123"
            lbl = QLabel("●")
            lbl.setStyleSheet(f"color: {status_color}; font-weight: bold; font-size: 10px;")
            h_layout.addStretch()
            h_layout.addWidget(lbl)
            h_layout.addStretch()
        
        main_layout.addLayout(h_layout)
        main_layout.addStretch(1)
        
        return status_widget
    
    def update_account_status(self, account_id: int, new_status: str, error_msg: str = ""):
        """实时更新指定账号的状态列（逐条刷新，无需重载整个表格）
        
        Args:
            account_id: 账号ID
            new_status: 新状态 ('online' / 'offline')
            error_msg: 离线原因（用于悬浮提示）
        """
        for row in range(self.table.rowCount()):
            username_item = self.table.item(row, 1)
            if username_item and username_item.data(Qt.ItemDataRole.UserRole) == account_id:
                status_widget = self._create_status_widget(new_status, error_msg)
                self.table.setCellWidget(row, 2, status_widget)
                logger.debug(f"实时更新账号 {account_id} 状态为 {new_status}")
                break
    
    def _create_actions_widget(self, account: Dict) -> QWidget:
        """创建操作按钮组件"""
        widget_actions = QWidget()
        layout_actions = QHBoxLayout(widget_actions)
        layout_actions.setContentsMargins(2, 0, 2, 0)
        layout_actions.setSpacing(4)
        layout_actions.setAlignment(Qt.AlignCenter)
        
        btn_switch = TransparentToolButton(FluentIcon.GLOBE, widget_actions)
        btn_switch.setFixedSize(32, 32)
        btn_switch.setIconSize(QSize(16, 16))
        apply_instructional_tooltip(
            "打开账号浏览器",
            btn_switch,
            position=ToolTipPosition.BOTTOM,
        )

        account_id = account.get('id')
        if account_id:
            btn_switch.clicked.connect(lambda: self.switch_account_requested.emit(account_id))

        layout_actions.addWidget(btn_switch)
        
        return widget_actions
    
    def _get_platform_icon(self, platform: str):
        """获取平台图标"""
        if platform == 'douyin':
            return FluentIcon.VIDEO
        elif platform == 'kuaishou':
            return FluentIcon.MOVIE
        elif platform == 'wechat_video':
            return FluentIcon.CHAT
        elif platform == 'xiaohongshu':
            return FluentIcon.PHOTO
        return FluentIcon.GLOBE
    
    @staticmethod
    def _get_platform_name(platform: str) -> str:
        """获取平台显示名称"""
        from src.utils.platform_names import get_platform_display_name
        return get_platform_display_name(platform)
    
    def filter_accounts(self, keyword: str = "", platform: str = "all"):
        """筛选账号
        
        Args:
            keyword: 搜索关键词
            platform: 平台筛选（"all" 或 None 表示全部）
        """
        logger.info(f"AccountTableWidget 筛选: keyword='{keyword}', platform='{platform}' (type: {type(platform)})")
        hidden_count = 0
        total_rows = self.table.rowCount()
        keyword_lower = keyword.lower() if keyword else ""
        filter_platform = platform and platform != "all"

        self.table.setUpdatesEnabled(False)
        try:
            for row in range(total_rows):
                show_row = True

                if filter_platform:
                    platform_item = self.table.item(row, 0)
                    if platform_item:
                        row_platform = platform_item.data(Qt.ItemDataRole.UserRole)
                        if row_platform != platform:
                            show_row = False
                    else:
                        logger.warning(f"Row {row} missing platform item")
                        show_row = False

                if keyword_lower and show_row:
                    username_item = self.table.item(row, 1)
                    if username_item:
                        if keyword_lower not in username_item.text().lower():
                            show_row = False

                self.table.setRowHidden(row, not show_row)
                if not show_row:
                    hidden_count += 1
        finally:
            self.table.setUpdatesEnabled(True)

        logger.info(f"筛选完成: 总行数 {total_rows}, 隐藏 {hidden_count}, 显示 {total_rows - hidden_count}")
    
    def get_selected_account_ids(self) -> List[int]:
        """获取选中的账号ID列表"""
        selected_ids = []
        for item in self.table.selectedItems():
            if item.column() == 1:
                account_id = item.data(Qt.ItemDataRole.UserRole)
                if account_id:
                    selected_ids.append(account_id)
        return selected_ids
    
    def _on_selection_changed(self):
        """选择变化时的回调"""
        selected_ids = self.get_selected_account_ids()
        self.account_selected.emit(selected_ids)
    
    def _on_item_double_clicked(self, item):
        """表格项双击事件"""
        if item.column() == 1:
            account_id = item.data(Qt.ItemDataRole.UserRole)
            if account_id:
                logger.info(f"双击账号，ID: {account_id}")
                self.account_double_clicked.emit(account_id)
    
    def _on_context_menu(self, pos):
        """右键菜单请求"""
        item = self.table.itemAt(pos)
        if not item:
            return
        
        row = item.row()
        sm = self.table.selectionModel()
        sm.blockSignals(True)
        try:
            self.table.selectRow(row)
        finally:
            sm.blockSignals(False)

        platform_item = self.table.item(row, 0)
        username_item = self.table.item(row, 1)
        
        if not username_item:
            return
        
        account_id = username_item.data(Qt.ItemDataRole.UserRole)
        platform_username = username_item.data(Qt.ItemDataRole.UserRole + 1)
        platform = platform_item.data(Qt.ItemDataRole.UserRole) if platform_item else ""
        profile_folder_name = username_item.data(Qt.ItemDataRole.UserRole + 2)
        
        account_data = {
            'id': account_id,
            'platform_username': platform_username,
            'platform': platform,
            'profile_folder_name': profile_folder_name
        }
        
        global_pos = self.table.viewport().mapToGlobal(pos)
        self.context_menu_requested.emit(account_data, global_pos)
