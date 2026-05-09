"""
视频库页面
文件路径：src/ui/pages/material/video_library_page.py
功能：展示媒小宝媒体库下视频（含已分配到「账号库」下各账号/账号组「视频/未发布」的视频），支持分配、工具栏打开视频库目录、表格右键打开当前行视频文件或所在文件夹；
     顶部提供「分配筛选」（全部/未分配/已分配）与「账号筛选」（按视频归属列）组合过滤；支持将选中视频移入系统回收站。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

from qasync import asyncSlot
from PySide6.QtCore import Qt, QUrl, QTimer, QPoint
from PySide6.QtGui import QDesktopServices, QAction
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QHeaderView,
    QFileDialog,
    QButtonGroup,
    QTableWidgetItem,
    QMenu,
)

from qfluentwidgets import (
    CardWidget,
    PrimaryPushButton,
    PushButton,
    ComboBox,
    InfoBar,
    InfoBarPosition,
    BodyLabel,
    RadioButton,
    TransparentToolButton,
    FluentIcon,
)

from src.ui.pages.base_page import BasePage
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.ui.components.base_dialog import AppMessageBoxBase
from src.ui.components.rubber_band_row_table import RubberBandRowSelectTable
from src.ui.utils.async_helper import AsyncWorker
from src.infrastructure.common.material_library_manager import MaterialLibraryManager
from src.infrastructure.common.media_library_assign import (
    AssignTargetType,
    resolve_assign_target,
    move_sources_to_assign_target,
    scan_video_library_entries,
)
from src.infrastructure.common.media_assign_strategy import (
    AssignStrategy,
    STRATEGY_DISPLAY_NAMES,
    strategy_from_display_name,
    load_assign_strategy,
    save_assign_strategy,
    distribute_files_to_targets_grouped,
)
from src.ui.utils.fluent_dialogs import show_warning, show_confirm
from src.utils.video_metadata import (
    ensure_ffmpeg_on_path,
    format_duration,
    get_video_metadata,
)
from src.services.material.media_library_stats_cache import get_media_library_stats_cache
from src.services.material.media_library_stats_service import get_media_library_stats_service

logger = logging.getLogger(__name__)


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv"}

# 列索引常量（含序号列）
_COL_NO       = 0
_COL_NAME     = 1
_COL_SIZE     = 2
_COL_DURATION = 3
_COL_RESOLUTION = 4
_COL_ORIENT   = 5
_COL_OWNER    = 6
_COL_USAGE    = 7
_HEADERS = ["序号", "文件名称", "文件大小", "时长", "分辨率", "方向", "视频归属", "使用统计"]

_CACHE_DIR_NAME = ".cache"
_VIDEO_META_CACHE_FILE = "video_metadata.json"


class _VideoMetadataCache:
    """ffprobe 结果的磁盘缓存，通过 (路径+mtime+大小) 校验有效性。"""

    def __init__(self) -> None:
        self._data: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._dirty = False
        self._cache_path: Optional[Path] = None

    def load(self, root: Path) -> None:
        cache_dir = root / _CACHE_DIR_NAME
        self._cache_path = cache_dir / _VIDEO_META_CACHE_FILE
        try:
            if self._cache_path.exists():
                raw = self._cache_path.read_text(encoding="utf-8")
                self._data = json.loads(raw)
        except Exception:
            self._data = {}
        self._dirty = False

    def get(self, file_path: str, mtime: float, size: int) -> Optional[dict]:
        key = os.path.normcase(os.path.normpath(file_path))
        with self._lock:
            entry = self._data.get(key)
        if not entry:
            return None
        if entry.get("size") == size and abs(entry.get("mtime", 0) - mtime) < 0.01:
            return entry
        return None

    def put(self, file_path: str, mtime: float, size: int,
            duration: str, resolution: str, orientation: str) -> None:
        key = os.path.normcase(os.path.normpath(file_path))
        with self._lock:
            self._data[key] = {
                "mtime": mtime, "size": size,
                "duration": duration, "resolution": resolution,
                "orientation": orientation,
            }
            self._dirty = True

    def save(self) -> None:
        if not self._dirty or not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                snapshot = dict(self._data)
                self._dirty = False
            with open(self._cache_path, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, ensure_ascii=False)
        except Exception as exc:
            logger.debug("保存视频元数据缓存失败: %s", exc)


class _ImportModeDialog(AppMessageBoxBase):
    """符合 Fluent 规范的导入方式选择弹窗（复制 / 剪切）。"""

    MODE_COPY = "copy"
    MODE_MOVE = "move"

    def __init__(self, parent: Optional[QWidget] = None, file_count: int = 1):
        super().__init__(parent, header_title="选择导入方式")
        self.widget.setMinimumWidth(420)

        self.viewLayout.addSpacing(4)

        desc = BodyLabel(f"已选择 {file_count} 个视频文件，请选择导入到媒体库的方式：", self.widget)
        desc.setWordWrap(True)
        self.viewLayout.addWidget(desc)
        self.viewLayout.addSpacing(12)

        self._btn_group = QButtonGroup(self.widget)
        self._radio_copy = RadioButton("复制到媒体库（保留源文件不变）", self.widget)
        self._radio_move = RadioButton("剪切到媒体库（源文件将被删除）", self.widget)
        self._radio_copy.setChecked(True)
        self._btn_group.addButton(self._radio_copy, 0)
        self._btn_group.addButton(self._radio_move, 1)
        self.viewLayout.addWidget(self._radio_copy)
        self.viewLayout.addWidget(self._radio_move)

        self.cancelButton.setText("取消")
        self.yesButton.setText("确定")
        self._reorder_buttons()

    def _reorder_buttons(self):
        btn_layout = self.buttonGroup.layout()
        if btn_layout:
            btn_layout.removeWidget(self.yesButton)
            btn_layout.removeWidget(self.cancelButton)
            btn_layout.addWidget(self.cancelButton)
            btn_layout.addWidget(self.yesButton)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def get_mode(self) -> str:
        return self.MODE_MOVE if self._radio_move.isChecked() else self.MODE_COPY


class _VideoItem:
    """视频条目数据结构。"""

    __slots__ = (
        "path", "name", "size_mb", "size_bytes", "mtime",
        "duration", "resolution", "orientation", "owner", "_meta_cached",
        "in_use",
    )

    def __init__(self, path: Path):
        self.path: Path = path
        self.name: str = path.name
        self.size_mb: float = 0.0
        self.size_bytes: int = 0
        self.mtime: float = 0.0
        self.duration: str = "-"
        self.resolution: str = "-"
        self.orientation: str = "-"
        self.owner: str = "未分配"
        self._meta_cached: bool = False
        self.in_use: bool = False


class VideoLibraryPage(BasePage):
    """视频库页面：展示媒体库视频并支持分配到账号未发布目录。"""

    _lazy_content = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("视频库", parent)
        self._table: Optional[RubberBandRowSelectTable] = None
        self._all_items: List[_VideoItem] = []
        self._video_refresh_gen: int = 0
        self._video_table_ctx_menu = None
        self._video_table_ctx_action_open_file = None
        self._video_table_ctx_action_open = None
        self._table_ctx_target_video: Optional[_VideoItem] = None
        self._assign_strategy: AssignStrategy = load_assign_strategy("library")
        self._meta_cache = _VideoMetadataCache()
        self._usage_refresh_gen: int = 0
        self._stats_cache = get_media_library_stats_cache()
        self._stats_label = None
        try:
            self._stats_cache.statsUpdated.connect(self._on_stats_updated)
        except Exception:
            pass

    def _setup_content(self):
        """构建页面内容（首次显示时调用）。"""
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        # 顶部工具栏卡片
        toolbar_card = CardWidget(self)
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        toolbar_layout.setSpacing(12)

        self.btn_refresh = PrimaryPushButton("刷新目录", toolbar_card)
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)

        self.btn_add = PushButton("添加视频", toolbar_card)
        self.btn_add.clicked.connect(self._on_add_video_clicked)

        self.btn_open_folder = PushButton("打开本地文件夹", toolbar_card)
        self.btn_open_folder.clicked.connect(self._on_open_video_folder_clicked)

        self.btn_assign = PushButton("分配到账号", toolbar_card)
        self.btn_assign.clicked.connect(self._on_assign_clicked)

        self.btn_assign_strategy = TransparentToolButton(FluentIcon.SETTING, toolbar_card)
        self.btn_assign_strategy.setFixedSize(28, 28)
        _tip_as = f"分配策略：{self._assign_strategy.display_name()}"
        apply_instructional_tooltip(
            _tip_as,
            self.btn_assign_strategy,
            position=ToolTipPosition.BOTTOM,
        )
        self.btn_assign_strategy.clicked.connect(self._on_assign_strategy_btn_clicked)

        self.owner_status_filter = ComboBox(toolbar_card)
        self.owner_status_filter.addItems(["全部", "未分配", "已分配"])
        self.owner_status_filter.setCurrentText("全部")
        self.owner_status_filter.setMinimumWidth(110)
        self.owner_status_filter.currentTextChanged.connect(self._apply_filters)

        self.owner_filter = ComboBox(toolbar_card)
        self.owner_filter.addItems(["全部账号"])
        self.owner_filter.setCurrentText("全部账号")
        self.owner_filter.setMinimumWidth(180)
        self.owner_filter.currentTextChanged.connect(self._apply_filters)

        self.btn_delete = PushButton(FluentIcon.DELETE, "删除", toolbar_card)
        apply_instructional_tooltip(
            "将选中视频移入系统回收站（非彻底删除，可从回收站恢复）",
            self.btn_delete,
            position=ToolTipPosition.BOTTOM,
        )
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        toolbar_layout.addWidget(self.btn_refresh)
        toolbar_layout.addWidget(self.btn_add)
        toolbar_layout.addWidget(self.btn_open_folder)
        toolbar_layout.addWidget(self.btn_assign)
        toolbar_layout.addWidget(self.btn_assign_strategy)
        toolbar_layout.addWidget(BodyLabel("分配筛选", toolbar_card))
        toolbar_layout.addWidget(self.owner_status_filter)
        toolbar_layout.addWidget(BodyLabel("账号筛选", toolbar_card))
        toolbar_layout.addWidget(self.owner_filter)
        toolbar_layout.addWidget(self.btn_delete)
        self._stats_label = BodyLabel("", toolbar_card)
        self._stats_label.setToolTip("统计口径：被待发布任务引用即视为“已占用”（pending/failed/running）")
        toolbar_layout.addWidget(self._stats_label)
        toolbar_layout.addStretch()

        # 表格卡片（Fluent TableWidget 替换原 QTableView）
        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self._table = RubberBandRowSelectTable(table_card)
        self._setup_table_style(self._table)
        # RubberBandRowSelectTable.__init__ 已内置 2px padding，此处只需设 objectName
        self._table.setObjectName("VideoLibraryTable")
        # RubberBandRowSelectTable 自带 NoDragDrop；显式设置选择模式
        self._table.setSelectionBehavior(self._table.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(self._table.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(self._table.EditTrigger.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.verticalHeader().setVisible(False)

        # 列宽：序号固定，文件名可拉伸，其余 Interactive 可拖拽调整
        header = self._table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_NO,   QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(52)
        self._table.setColumnWidth(_COL_NO,         52)
        self._table.setColumnWidth(_COL_SIZE,       100)
        self._table.setColumnWidth(_COL_DURATION,   80)
        self._table.setColumnWidth(_COL_RESOLUTION, 110)
        self._table.setColumnWidth(_COL_ORIENT,     70)
        self._table.setColumnWidth(_COL_OWNER,      100)
        self._table.setColumnWidth(_COL_USAGE,      80)

        table_layout.addWidget(self._table)

        root_layout.addWidget(toolbar_card)
        root_layout.addWidget(table_card)
        self.content_layout.addLayout(root_layout)

        self._refresh_async()
        self._refresh_stats_async()

    def _refresh_stats_async(self) -> None:
        """触发全局媒体库统计刷新（异步，避免阻塞 UI）。"""
        try:
            import asyncio

            asyncio.ensure_future(get_media_library_stats_service().refresh())
        except Exception:
            return

    def _format_stats_text(self, stats) -> str:
        try:
            all_counts = getattr(stats, "all_media", None)
            if all_counts is None:
                return "素材统计：—"
            total = int(getattr(all_counts, "total", 0) or 0)
            used = int(getattr(all_counts, "used", 0) or 0)
            unused = int(getattr(all_counts, "unused", 0) or 0)
            return f"素材统计：总 {total}｜已占用 {used}｜未占用 {unused}"
        except Exception:
            return "素材统计：—"

    def _on_stats_updated(self, stats) -> None:
        if not getattr(self, "_stats_label", None):
            return
        try:
            self._stats_label.setText(self._format_stats_text(stats))
            err = str(getattr(stats, "error", "") or "").strip()
            if err:
                self._stats_label.setToolTip(f"{self._stats_label.toolTip()}\n\n注意：{err}")
        except Exception:
            return

    # ---------- 表格填充 ----------

    def _populate_table(self, items: List[_VideoItem]) -> None:
        """将扫描到的视频条目渲染到 TableWidget。"""
        self._table.setSortingEnabled(False)
        self._table.setUpdatesEnabled(False)
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        self._table.setRowCount(len(items))

        for row, item in enumerate(items):
            # 序号（居中，不可排序干扰）
            no_cell = QTableWidgetItem(str(row + 1))
            no_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            no_cell.setData(Qt.ItemDataRole.UserRole, item)  # 存储 _VideoItem 供取行用
            self._table.setItem(row, _COL_NO, no_cell)

            name_cell = QTableWidgetItem(item.name)
            name_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_NAME, name_cell)

            size_cell = QTableWidgetItem(
                f"{item.size_mb:.2f} MB" if item.size_mb > 0 else "-"
            )
            size_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_SIZE, size_cell)

            dur_cell = QTableWidgetItem(item.duration)
            dur_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_DURATION, dur_cell)

            res_cell = QTableWidgetItem(item.resolution)
            res_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_RESOLUTION, res_cell)

            orient_cell = QTableWidgetItem(item.orientation)
            orient_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_ORIENT, orient_cell)

            owner_cell = QTableWidgetItem(item.owner)
            owner_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_OWNER, owner_cell)

            usage_cell = QTableWidgetItem("已占用" if getattr(item, "in_use", False) else "")
            usage_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row, _COL_USAGE, usage_cell)

        self._table.blockSignals(False)
        self._table.setUpdatesEnabled(True)
        self._table.setSortingEnabled(True)

    def _schedule_refresh_usage_marks(self, gen: int) -> None:
        """异步查询待发布任务占用情况，并为 _all_items 打上 in_use 标记。"""
        try:
            import asyncio
            from src.services.material.media_usage_service import (
                get_pending_media_usage,
                is_video_used,
            )
        except Exception:
            return

        async def _run() -> None:
            usage = await get_pending_media_usage()
            if gen != self._usage_refresh_gen:
                return
            for it in self._all_items:
                try:
                    it.in_use = bool(is_video_used(usage, it.path))
                except Exception:
                    it.in_use = False
            # 仅原地更新“使用统计”列，避免重建表格导致“进入后自动刷新/闪一下”
            self._update_usage_column_in_place()

        try:
            asyncio.ensure_future(_run())
        except Exception:
            return

    def _update_usage_column_in_place(self) -> None:
        """原地刷新表格中的“使用统计”列，不重建行也不重跑筛选。

        进入页面后会先快速扫描目录，再异步查询占用情况；若占用结果回来时重建表格，
        用户会感知到一次“自动刷新”（并可能丢失选中行/滚动位置），因此这里改为原地更新。
        """
        if not self._table:
            return
        try:
            self._table.setUpdatesEnabled(False)
            for row in range(self._table.rowCount()):
                no_cell = self._table.item(row, _COL_NO)
                if not no_cell:
                    continue
                item = no_cell.data(Qt.ItemDataRole.UserRole)
                if not isinstance(item, _VideoItem):
                    continue
                usage_cell = self._table.item(row, _COL_USAGE)
                if usage_cell:
                    usage_cell.setText("已占用" if getattr(item, "in_use", False) else "")
        finally:
            self._table.setUpdatesEnabled(True)

    def _get_selected_items(self) -> List[_VideoItem]:
        """从表格选中行中取出 _VideoItem 列表。"""
        if not self._table:
            return []
        seen_rows = set()
        items: List[_VideoItem] = []
        for sel_item in self._table.selectedItems():
            row = sel_item.row()
            if row in seen_rows:
                continue
            seen_rows.add(row)
            no_cell = self._table.item(row, _COL_NO)
            if no_cell:
                video_item = no_cell.data(Qt.ItemDataRole.UserRole)
                if isinstance(video_item, _VideoItem):
                    items.append(video_item)
        return items

    def _remove_nonexistent_rows(self) -> None:
        """即时移除已不存在的文件行，提升分配后的列表刷新感知。"""
        if not self._table:
            return
        for row in range(self._table.rowCount() - 1, -1, -1):
            no_cell = self._table.item(row, _COL_NO)
            if not no_cell:
                continue
            video_item = no_cell.data(Qt.ItemDataRole.UserRole)
            if isinstance(video_item, _VideoItem) and not video_item.path.exists():
                self._table.removeRow(row)

    def _refresh_owner_filter_options(self) -> None:
        """基于当前数据刷新“账号筛选”下拉项，并尽量保留用户当前选择。"""
        current_text = self.owner_filter.currentText() if hasattr(self, "owner_filter") else "全部账号"
        owners = sorted({item.owner for item in self._all_items if item.owner != "未分配"})
        options = ["全部账号"] + owners
        self.owner_filter.blockSignals(True)
        self.owner_filter.clear()
        self.owner_filter.addItems(options)
        self.owner_filter.setCurrentText(current_text if current_text in options else "全部账号")
        self.owner_filter.blockSignals(False)

    def _apply_filters(self) -> None:
        """按分配状态与账号归属组合筛选并渲染列表。"""
        if not self._table:
            return
        status = self.owner_status_filter.currentText() if hasattr(self, "owner_status_filter") else "全部"
        owner = self.owner_filter.currentText() if hasattr(self, "owner_filter") else "全部账号"

        # 未分配素材没有「账号归属」，此时禁用账号下拉避免误选导致空列表
        if hasattr(self, "owner_filter") and hasattr(self, "owner_status_filter"):
            if status == "未分配":
                self.owner_filter.blockSignals(True)
                self.owner_filter.setCurrentText("全部账号")
                self.owner_filter.blockSignals(False)
                self.owner_filter.setEnabled(False)
            else:
                self.owner_filter.setEnabled(True)

        items = list(self._all_items)
        if status == "未分配":
            items = [item for item in items if item.owner == "未分配"]
        elif status == "已分配":
            items = [item for item in items if item.owner != "未分配"]

        if owner != "全部账号" and status != "未分配":
            items = [item for item in items if item.owner == owner]

        self._populate_table(items)

    def _update_metadata_columns(self) -> None:
        """原地刷新表格中的时长/分辨率/方向列，不重建行。"""
        if not self._table:
            return
        self._table.setUpdatesEnabled(False)
        for row in range(self._table.rowCount()):
            no_cell = self._table.item(row, _COL_NO)
            if not no_cell:
                continue
            item = no_cell.data(Qt.ItemDataRole.UserRole)
            if not isinstance(item, _VideoItem):
                continue
            dur_cell = self._table.item(row, _COL_DURATION)
            if dur_cell:
                dur_cell.setText(item.duration)
            res_cell = self._table.item(row, _COL_RESOLUTION)
            if res_cell:
                res_cell.setText(item.resolution)
            orient_cell = self._table.item(row, _COL_ORIENT)
            if orient_cell:
                orient_cell.setText(item.orientation)
        self._table.setUpdatesEnabled(True)

    # ---------- 添加视频 ----------

    def _on_add_video_clicked(self):
        """从任意位置选择视频文件，复制或剪切到媒体库视频目录。"""
        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            InfoBar.warning(
                title="提示",
                content="未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        ext_filter = "视频文件 (*.mp4 *.mov *.avi *.mkv *.flv *.wmv);;所有文件 (*.*)"
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择要添加到媒体库的视频文件", "", ext_filter
        )
        if not file_paths:
            return

        mode_dialog = _ImportModeDialog(self, file_count=len(file_paths))
        if not mode_dialog.exec():
            return

        use_move = mode_dialog.get_mode() == _ImportModeDialog.MODE_MOVE
        video_dir = root / MaterialLibraryManager.VIDEO_FOLDER_NAME

        def import_sync() -> tuple:
            success_count = 0
            failed_names: List[str] = []
            for fp in file_paths:
                src = Path(fp)
                if not src.exists():
                    failed_names.append(src.name)
                    continue
                dst = video_dir / src.name
                if dst.exists():
                    stem = dst.stem
                    suffix = dst.suffix
                    idx = 1
                    while True:
                        candidate = video_dir / f"{stem} ({idx}){suffix}"
                        if not candidate.exists():
                            dst = candidate
                            break
                        idx += 1
                try:
                    if use_move:
                        shutil.move(str(src), str(dst))
                    else:
                        shutil.copy2(str(src), str(dst))
                    success_count += 1
                except Exception as err:
                    logger.warning("添加视频文件失败: %s -> %s (%s)", src, dst, err)
                    failed_names.append(src.name)
            return success_count, failed_names

        worker = AsyncWorker(import_sync)
        worker.setParent(self)
        action_label = "剪切" if use_move else "复制"

        def on_finished(result: tuple):
            success_count, failed_names = result
            if success_count > 0:
                content = f"成功{action_label} {success_count} 个视频到媒体库。"
                if failed_names:
                    content += f"\n以下文件失败：{', '.join(failed_names[:3])}"
                    if len(failed_names) > 3:
                        content += "……"
                InfoBar.success(
                    title="添加完成",
                    content=content,
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=5000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                self._refresh_async()
            else:
                InfoBar.warning(
                    title="添加失败",
                    content="未能添加任何视频，请检查文件是否存在或磁盘权限。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=5000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )

        def on_error(e: Exception):
            logger.error("添加视频到媒体库失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content="添加视频时发生异常，请稍后重试。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    def _on_open_video_folder_clicked(self):
        """打开本地视频库目录。"""
        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            InfoBar.warning(
                title="提示",
                content="未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        video_dir = root / MaterialLibraryManager.VIDEO_FOLDER_NAME
        if not video_dir.exists():
            InfoBar.warning(
                title="提示",
                content="未找到视频库目录，请先在设置中确认媒体库路径。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(video_dir))):
            InfoBar.error(
                title="错误",
                content="打开本地视频库目录失败，请检查系统默认文件管理器设置。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _ensure_video_table_round_menu(self) -> bool:
        try:
            from qfluentwidgets import RoundMenu, Action, FluentIcon as _FI
        except ImportError:
            return False
        from src.ui.components.fluent_context_menu import (
            install_round_menu_close_on_app_inactive,
            is_round_menu_alive,
            round_menu_parent,
        )

        if self._video_table_ctx_menu is not None and is_round_menu_alive(self._video_table_ctx_menu):
            return True
        parent = round_menu_parent(self)
        if parent is None:
            return False
        self._video_table_ctx_menu = RoundMenu(parent=parent)
        self._video_table_ctx_action_open_file = Action(_FI.DOCUMENT, "打开文件", parent)
        self._video_table_ctx_action_open_file.setToolTip(
            "使用系统默认程序打开；视频一般由已安装的播放器播放"
        )
        self._video_table_ctx_action_open_file.triggered.connect(
            self._on_video_table_ctx_open_file_clicked
        )
        self._video_table_ctx_action_open = Action(_FI.FOLDER, "打开所在文件夹", parent)
        self._video_table_ctx_action_open.triggered.connect(self._on_video_table_ctx_open_folder_clicked)
        self._video_table_ctx_menu.addAction(self._video_table_ctx_action_open_file)
        self._video_table_ctx_menu.addAction(self._video_table_ctx_action_open)
        install_round_menu_close_on_app_inactive(self._video_table_ctx_menu)
        return True

    def _on_video_table_ctx_open_file_clicked(self) -> None:
        video_item = self._table_ctx_target_video
        self._table_ctx_target_video = None
        if not isinstance(video_item, _VideoItem):
            return
        try:
            path = video_item.path.resolve()
        except OSError:
            path = video_item.path
        fp = os.fspath(path)
        if not os.path.isfile(fp):
            InfoBar.warning(
                title="提示",
                content="该视频文件已不存在，可能已被移动或删除。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(fp)):
            InfoBar.error(
                title="打开失败",
                content="系统未能用默认程序打开该文件，请检查是否已安装播放器并在系统中关联该视频格式。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_video_table_ctx_open_folder_clicked(self) -> None:
        video_item = self._table_ctx_target_video
        self._table_ctx_target_video = None
        if not isinstance(video_item, _VideoItem):
            return
        try:
            folder = video_item.path.resolve().parent
        except OSError:
            folder = video_item.path.parent
        if not folder.exists():
            InfoBar.warning(
                title="提示",
                content="该视频所在文件夹已不存在，可能已被移动或删除。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            InfoBar.error(
                title="错误",
                content="打开文件夹失败，请检查系统默认文件管理器设置。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_table_context_menu(self, pos: QPoint) -> None:
        """表格右键：打开当前行视频文件或所在文件夹（与批量预览表选择逻辑一致）。"""
        if not self._table:
            return
        cell = self._table.itemAt(pos)
        if cell is None:
            return
        sm = self._table.selectionModel()
        if sm is None:
            return
        clicked_row = cell.row()
        selected_rows = {idx.row() for idx in sm.selectedRows()}
        need_single = (not selected_rows) or (clicked_row not in selected_rows)
        if need_single:
            sm.blockSignals(True)
            try:
                self._table.selectRow(clicked_row)
            finally:
                sm.blockSignals(False)
        no_cell = self._table.item(clicked_row, _COL_NO)
        if not no_cell:
            return
        video_item = no_cell.data(Qt.ItemDataRole.UserRole)
        if not isinstance(video_item, _VideoItem):
            return
        self._table_ctx_target_video = video_item
        global_pos = self._table.viewport().mapToGlobal(pos)
        if self._ensure_video_table_round_menu():
            self._video_table_ctx_menu.exec(global_pos)
            return
        menu = QMenu(self._table)
        act_open_file = menu.addAction("打开文件")
        try:
            act_open_file.setIcon(FluentIcon.DOCUMENT.icon())
        except Exception:
            pass
        act_open = menu.addAction("打开所在文件夹")
        try:
            act_open.setIcon(FluentIcon.FOLDER.icon())
        except Exception:
            pass
        chosen = menu.exec(global_pos)
        if chosen == act_open_file:
            self._on_video_table_ctx_open_file_clicked()
        elif chosen == act_open:
            self._on_video_table_ctx_open_folder_clicked()

    # ---------- 删除到回收站 ----------

    def _on_delete_clicked(self) -> None:
        """将选中视频移入系统回收站（二次确认后在后台线程执行）。"""
        selected = self._get_selected_items()
        if not selected:
            InfoBar.info(
                title="提示",
                content="请先在列表中选择要删除的视频。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            InfoBar.warning(
                title="提示",
                content="未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        n = len(selected)
        confirmed = show_confirm(
            self,
            "确认删除",
            f"将把选中的 {n} 个视频移入 Windows 系统回收站。\n\n"
            "文件不会被彻底删除，可随时打开回收站手动恢复。\n"
            "（注意：网络盘或 UNC 路径上的文件可能无法进入回收站。）\n\n"
            "确认继续？",
        )
        if not confirmed:
            return

        try:
            root_resolved = root.resolve()
        except OSError:
            root_resolved = root

        def delete_sync() -> tuple:
            try:
                import send2trash
            except ImportError:
                return 0, [], "send2trash 未安装，无法使用回收站删除功能。"

            success_count = 0
            failed_names: List[str] = []

            for item in selected:
                path = item.path
                try:
                    resolved = path.resolve()
                except OSError:
                    resolved = path

                # 安全约束：只允许删除媒体库根目录下的文件
                try:
                    resolved.relative_to(root_resolved)
                except ValueError:
                    logger.warning("拒绝删除媒体库范围外的文件: %s", path)
                    failed_names.append(item.name)
                    continue

                if not path.exists():
                    failed_names.append(item.name)
                    continue

                try:
                    send2trash.send2trash(os.fspath(path))
                    success_count += 1
                except Exception as err:
                    logger.warning("移入回收站失败: %s (%s)", path, err)
                    failed_names.append(item.name)

            return success_count, failed_names, None

        worker = AsyncWorker(delete_sync)
        worker.setParent(self)

        def on_finished(result: tuple):
            success_count, failed_names, import_err = result
            if import_err:
                InfoBar.error(
                    title="错误",
                    content=import_err,
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=6000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return
            if success_count > 0:
                content = f"已将 {success_count} 个视频移入系统回收站，可从回收站恢复。"
                if failed_names:
                    preview = "、".join(failed_names[:3])
                    if len(failed_names) > 3:
                        preview += f" 等 {len(failed_names)} 个"
                    content += f"\n以下文件操作失败：{preview}"
                InfoBar.success(
                    title="已移入回收站",
                    content=content,
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=5000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                self._refresh_async()
            else:
                InfoBar.warning(
                    title="未能删除",
                    content="未能将任何视频移入回收站，请检查文件是否存在或路径权限。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=5000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )

        def on_error(e: Exception):
            logger.error("移入回收站操作失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content="删除操作时发生异常，请稍后重试。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    # ---------- 刷新目录 ----------

    def _clear_filters(self) -> None:
        """将分配筛选、账号筛选恢复为默认（刷新目录时一并清空筛选条件）。"""
        if not hasattr(self, "owner_status_filter") or not hasattr(self, "owner_filter"):
            return
        self.owner_status_filter.blockSignals(True)
        self.owner_filter.blockSignals(True)
        self.owner_status_filter.setCurrentText("全部")
        self.owner_filter.setCurrentText("全部账号")
        self.owner_filter.setEnabled(True)
        self.owner_status_filter.blockSignals(False)
        self.owner_filter.blockSignals(False)

    def _on_refresh_clicked(self):
        self._clear_filters()
        # 在异步扫描返回前，先用当前缓存数据按「无筛选」重绘，避免仍显示旧筛选结果
        if self._table and self._all_items:
            self._apply_filters()
        self._refresh_async()
        self._refresh_stats_async()

    def _apply_video_metadata_to_item(self, item: _VideoItem, file_path: str) -> None:
        """对单个条目写入时长/分辨率（ffprobe）；失败时保持占位符。"""
        try:
            meta = get_video_metadata(file_path)
            item.duration = format_duration(meta.get("duration"))
            width = meta.get("width")
            height = meta.get("height")
            if width and height:
                item.resolution = f"{width}x{height}"
                item.orientation = "竖屏" if height > width else "横屏"
        except Exception as meta_err:
            logger.debug("解析视频元数据失败（%s）: %s", item.name, meta_err)

    def _scan_video_items_fast(self) -> Tuple[List[_VideoItem], Optional[str]]:
        """枚举路径与文件大小，并用缓存命中的元数据直接填充，避免冗余 ffprobe。"""
        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            return [], "未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。"
        self._meta_cache.load(root)
        scanned, err = scan_video_library_entries(root, VIDEO_EXTENSIONS)
        if err:
            return [], err
        items: List[_VideoItem] = []
        for entry in scanned:
            item = _VideoItem(entry.path)
            item.size_mb = entry.size_bytes / (1024 * 1024)
            item.size_bytes = entry.size_bytes
            item.mtime = entry.mtime
            item.owner = entry.owner_label
            cached = self._meta_cache.get(str(entry.path), entry.mtime, entry.size_bytes)
            if cached:
                item.duration = cached.get("duration", "-")
                item.resolution = cached.get("resolution", "-")
                item.orientation = cached.get("orientation", "-")
                item._meta_cached = True
            items.append(item)
        return items, None

    def _enrich_video_metadata_worker(self, items: List[_VideoItem], gen: int) -> None:
        """后台线程：并行 ffprobe 补全时长与分辨率（跳过已缓存的条目）。"""
        if gen != self._video_refresh_gen or not items:
            return
        need_enrich = [it for it in items if not it._meta_cached]
        if not need_enrich:
            return
        ensure_ffmpeg_on_path()

        def enrich_one(it: _VideoItem) -> None:
            if gen != self._video_refresh_gen:
                return
            self._apply_video_metadata_to_item(it, str(it.path))
            self._meta_cache.put(
                str(it.path), it.mtime, it.size_bytes,
                it.duration, it.resolution, it.orientation,
            )

        max_workers = min(8, max(1, len(need_enrich)))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            pool.map(enrich_one, need_enrich)
        self._meta_cache.save()

    def _refresh_async(self):
        """异步扫描媒体库视频目录：先快速列出文件，再在后台补全元数据。"""
        root_base = MaterialLibraryManager.get_root_base_dir()
        if root_base is None:
            parent_win = self.window()
            should_go_settings = show_confirm(
                parent_win if isinstance(parent_win, QWidget) else self,
                "提示",
                "未检测到有效的媒体库路径，是否现在前往设置中心配置媒体库存储位置？",
            )
            if should_go_settings and parent_win is not None and hasattr(parent_win, "navigate_to"):
                try:
                    parent_win.navigate_to("settings_page")
                except Exception as e:
                    logger.warning("跳转到设置页面失败: %s", e, exc_info=True)
            return

        self._video_refresh_gen += 1
        gen = self._video_refresh_gen
        self._usage_refresh_gen += 1
        ugen = self._usage_refresh_gen

        def scan_sync() -> Tuple[List[_VideoItem], Optional[str]]:
            try:
                return self._scan_video_items_fast()
            except Exception as e:
                logger.error("扫描媒体库视频目录失败: %s", e, exc_info=True)
                return [], "扫描媒体库视频目录时发生错误，请稍后重试。"

        worker = AsyncWorker(scan_sync)
        worker.setParent(self)

        def on_fast_finished(result: Tuple[List[_VideoItem], Optional[str]]):
            items, error = result
            if gen != self._video_refresh_gen:
                return
            if error:
                InfoBar.warning(
                    title="提示",
                    content=error,
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=5000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
            self._all_items = items
            self._refresh_owner_filter_options()
            self._apply_filters()
            # 使用统计（占用标记）：异步查库后回填到表格
            self._schedule_refresh_usage_marks(ugen)
            # 数据就绪后预创建右键菜单，消除首次右键的一次性延迟
            QTimer.singleShot(200, self._ensure_video_table_round_menu)

            if not items:
                return

            if all(it._meta_cached for it in items):
                return

            enrich_worker = AsyncWorker(lambda: self._enrich_video_metadata_worker(items, gen))
            enrich_worker.setParent(self)

            def on_enrich_done(_: object) -> None:
                if gen != self._video_refresh_gen:
                    return
                self._update_metadata_columns()

            def on_enrich_error(e: Exception) -> None:
                logger.error("补全视频元数据失败: %s", e, exc_info=True)

            enrich_worker.finished.connect(on_enrich_done)
            enrich_worker.error.connect(on_enrich_error)
            enrich_worker.start()

        def on_error(e: Exception):
            logger.error("刷新视频库列表失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content="刷新视频库列表时发生异常，请稍后重试。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

        worker.finished.connect(on_fast_finished)
        worker.error.connect(on_error)
        worker.start()

    # ---------- 分配策略 ----------

    def _on_assign_strategy_btn_clicked(self) -> None:
        """点击⚙按钮弹出策略选择菜单。"""
        menu = QMenu(self)
        for s in AssignStrategy:
            action = QAction(s.display_name(), menu)
            action.setCheckable(True)
            action.setChecked(s == self._assign_strategy)
            action.setData(s)
            menu.addAction(action)

        btn = self.btn_assign_strategy
        pos = btn.mapToGlobal(btn.rect().bottomLeft())
        chosen = menu.exec(pos)
        if chosen is not None:
            strategy: AssignStrategy = chosen.data()
            self._assign_strategy = strategy
            save_assign_strategy(strategy, "library")
            _t_as = f"分配策略：{strategy.display_name()}"
            apply_instructional_tooltip(
                _t_as,
                self.btn_assign_strategy,
                position=ToolTipPosition.BOTTOM,
            )

    # ---------- 分配逻辑 ----------

    @asyncSlot()
    async def _on_assign_clicked(self):
        """将选中视频按当前策略分配到一个或多个账号/账号组的「未发布」目录。"""
        selected = self._get_selected_items()
        if not selected:
            InfoBar.info(
                title="提示",
                content="请先在列表中选择要分配的视频。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        targets_result = await self._choose_targets_dialog()
        if not targets_result:
            return

        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            InfoBar.error(
                title="错误",
                content="未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        from src.infrastructure.common.media_library_assign import AssignTarget
        assign_targets: List[AssignTarget] = []
        for item in targets_result:
            t_type = item.get("type")
            t_data = item.get("data")
            if not isinstance(t_data, dict):
                continue
            tt: AssignTargetType = "group" if t_type == "group" else "account"
            assign_targets.append(resolve_assign_target(root, media_kind="video", target_type=tt, target_data=t_data))

        if not assign_targets:
            show_warning(self, "提示", "请选择有效的账号或账号组。")
            return

        file_paths = [v.path for v in selected]
        distribution = distribute_files_to_targets_grouped(file_paths, assign_targets, self._assign_strategy)

        for at in assign_targets:
            try:
                at.directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error("创建素材分配目标目录失败: %s", e, exc_info=True)
                InfoBar.error(
                    title="错误",
                    content=f"无法创建{at.label}的素材目录，请检查磁盘权限。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=5000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return

        strategy = self._assign_strategy
        n_targets = len(assign_targets)

        def move_sync() -> int:
            total = 0
            for at, paths in distribution.items():
                total += move_sources_to_assign_target(paths, at.directory, skip_if_already_in_target=True)
            return total

        worker = AsyncWorker(move_sync)
        worker.setParent(self)

        def on_finished(moved: int):
            if moved > 0:
                self._remove_nonexistent_rows()
                target_desc = "、".join(at.label for at in assign_targets[:3])
                if n_targets > 3:
                    target_desc += f" 等 {n_targets} 个目标"
                InfoBar.success(
                    title="已分配",
                    content=f"按{strategy.display_name()}策略成功分配 {moved} 个视频到{target_desc}的未发布目录。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=4000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                self._refresh_async()
            else:
                InfoBar.info(
                    title="提示",
                    content="未能分配任何视频，请检查文件是否仍存在。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=4000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )

        def on_error(e: Exception):
            logger.error("分配视频素材失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content="分配视频素材时发生错误，请稍后重试。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    # ---------- 账号选择 ----------

    async def _choose_targets_dialog(self) -> Optional[List[Dict[str, Any]]]:
        """选择分配对象（支持多选账号或多选账号组），返回 [{'type':..., 'data':...}] 列表。"""
        from src.domain.repositories.account_repository_async import AccountRepositoryAsync
        from src.services.account.account_group_service import AccountGroupService

        async def _load_accounts():
            repo = AccountRepositoryAsync()
            return await repo.find_all(user_id=None, platform=None)

        async def _load_groups():
            service = AccountGroupService()
            return await service.get_groups(user_id=None)

        try:
            accounts, groups = await asyncio.gather(_load_accounts(), _load_groups())
            accounts = accounts or []
            groups = groups or []
        except Exception as e:
            logger.error("加载可分配对象失败: %s", e, exc_info=True)
            accounts = []
            groups = []

        if not accounts and not groups:
            show_warning(self, "提示", "当前没有可分配的账号或账号组，请先在账号库/账号组中创建。")
            return None

        if len(accounts) == 1 and not groups:
            return [{"type": "account", "data": accounts[0]}]

        from src.ui.dialogs.account_selection_dialog import AccountSelectionDialog

        dialog = AccountSelectionDialog(self, header_title="选择分配对象")
        dialog.set_data(accounts, groups=groups, show_group_nav=True, multi_select=True)
        if not dialog.exec():
            return None

        result = dialog.get_selected_result()
        if not isinstance(result, dict):
            return None

        r_type = result.get("type")
        r_data = result.get("data")

        if r_type == "account":
            data_list = r_data if isinstance(r_data, list) else ([r_data] if r_data else [])
            return [{"type": "account", "data": d} for d in data_list if isinstance(d, dict)]

        if r_type == "group":
            data_list = r_data if isinstance(r_data, list) else ([r_data] if r_data else [])
            return [{"type": "group", "data": d} for d in data_list if isinstance(d, dict)]

        return None
