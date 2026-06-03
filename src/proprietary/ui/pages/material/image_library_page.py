"""
图片库页面
文件路径：src/ui/pages/material/image_library_page.py
功能：以图片文件夹为单位展示图片库。每个文件夹对应一个图文任务所需的图片组，
     支持添加图片文件夹、分配到账号、打开本地目录、删除（移入回收站）等操作。
     表格展示文件夹名称、图片数量、总大小、图片归属（账号）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

from qasync import asyncSlot
from PySide6.QtCore import Qt, QUrl, QTimer, QPoint
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QButtonGroup,
    QMenu,
    QDialog,
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
from src.ui.utils.task_tracking import TrackedTaskMixin
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.ui.components.base_dialog import AppMessageBoxBase
from src.ui.pages.material.media_library_page_controller import MediaLibraryPageController
from src.ui.pages.material.media_library_table_model import MediaLibraryTableModel
from src.ui.pages.material.media_library_table_view import MediaLibraryTableView
from src.ui.utils.async_helper import AsyncWorker, await_qdialog_finished
from src.infrastructure.common.material_library_manager import MaterialLibraryManager
from src.infrastructure.common.media_library_assign import (
    AssignTargetType,
    resolve_assign_target,
    move_folder_to_assign_target,
    distribute_folders_to_targets_grouped,
    scan_image_library_entries,
)
from src.infrastructure.common.media_assign_strategy import (
    AssignStrategy,
    load_assign_strategy,
    save_assign_strategy,
)
from src.ui.utils.fluent_dialogs import show_warning, show_confirm

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

_COL_NO = 0
_COL_NAME = 1
_COL_IMAGE_COUNT = 2
_COL_SIZE = 3
_COL_OWNER = 4
_COL_USAGE = 5
_HEADERS = ["序号", "文件夹名称", "图片数量", "总大小", "图片归属", "使用统计"]


class _ImportModeDialog(AppMessageBoxBase):
    """导入方式选择弹窗（复制 / 剪切）。"""

    MODE_COPY = "copy"
    MODE_MOVE = "move"

    def __init__(self, parent: Optional[QWidget] = None, file_count: int = 1):
        super().__init__(parent, header_title="选择导入方式")
        self.widget.setMinimumWidth(420)

        self.viewLayout.addSpacing(4)

        desc = BodyLabel(f"已选择 {file_count} 个图片文件夹，请选择导入到媒体库的方式：", self.widget)
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




class _ImageFolderItem:
    """图片文件夹条目数据结构（每条记录代表一个图片任务文件夹）。"""

    __slots__ = (
        "path", "name", "image_count", "size_mb", "size_bytes", "mtime", "owner",
        "in_use",
    )

    def __init__(self, path: Path):
        self.path: Path = path
        self.name: str = path.name
        self.image_count: int = 0
        self.size_mb: float = 0.0
        self.size_bytes: int = 0
        self.mtime: float = 0.0
        self.owner: str = "未分配"
        self.in_use: bool = False


class ImageLibraryPage(TrackedTaskMixin, BasePage):
    """图片库页面：展示媒体库图片并支持分配到账号未发布目录。"""

    _lazy_content = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("图片库", parent)
        self._table: Optional[MediaLibraryTableView] = None
        self._media_controller = MediaLibraryPageController(self)
        self._all_items: List[_ImageFolderItem] = []
        self._image_refresh_gen: int = 0
        self._table_ctx_menu = None
        self._table_ctx_action_open = None
        self._table_ctx_target_image: Optional[_ImageFolderItem] = None
        self._assign_strategy: AssignStrategy = load_assign_strategy("library")
        self._usage_refresh_gen: int = 0
    # ------------------------------------------------------------------ #
    #                           页面构建                                   #
    # ------------------------------------------------------------------ #

    def _setup_content(self):
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        # ---------- 顶部工具栏 ----------
        toolbar_card = CardWidget(self)
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        toolbar_layout.setSpacing(12)

        self.btn_refresh = PrimaryPushButton("刷新目录", toolbar_card)
        self.btn_refresh.clicked.connect(self._on_refresh_clicked)

        self.btn_add_folder = PushButton("添加图片文件夹", toolbar_card)
        self.btn_add_folder.clicked.connect(self._on_add_image_folder_clicked)

        self.btn_open_folder = PushButton("打开本地文件夹", toolbar_card)
        self.btn_open_folder.clicked.connect(self._on_open_image_folder_clicked)

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
            "将选中图片移入系统回收站（非彻底删除，可从回收站恢复）",
            self.btn_delete,
            position=ToolTipPosition.BOTTOM,
        )
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        toolbar_layout.addWidget(self.btn_refresh)
        toolbar_layout.addWidget(self.btn_add_folder)
        toolbar_layout.addWidget(self.btn_open_folder)
        toolbar_layout.addWidget(self.btn_assign)
        toolbar_layout.addWidget(self.btn_assign_strategy)
        toolbar_layout.addWidget(BodyLabel("分配筛选", toolbar_card))
        toolbar_layout.addWidget(self.owner_status_filter)
        toolbar_layout.addWidget(BodyLabel("账号筛选", toolbar_card))
        toolbar_layout.addWidget(self.owner_filter)
        toolbar_layout.addWidget(self.btn_delete)
        toolbar_layout.addStretch()

        # ---------- 表格 ----------
        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self._table = MediaLibraryTableView(
            table_card,
            kind=MediaLibraryTableModel.KIND_IMAGE_FOLDER,
        )
        self._table.setObjectName("ImageLibraryTable")
        self._table.setSelectionBehavior(self._table.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(self._table.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(self._table.EditTrigger.NoEditTriggers)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

        table_layout.addWidget(self._table)

        root_layout.addWidget(toolbar_card)
        root_layout.addWidget(table_card)
        self.content_layout.addLayout(root_layout)

        self._refresh_async()
    # ------------------------------------------------------------------ #
    #                           表格填充                                   #
    # ------------------------------------------------------------------ #

    def _populate_table(self, items: List[_ImageFolderItem]) -> None:
        """Render image folders through the Model/View table."""
        if not self._table:
            return
        self._table.setSortingEnabled(False)
        self._table.setUpdatesEnabled(False)
        self._table.blockSignals(True)
        try:
            self._table.set_items(items)
        finally:
            self._table.blockSignals(False)
            self._table.setUpdatesEnabled(True)
            self._table.setSortingEnabled(True)

    def _schedule_refresh_usage_marks(self, gen: int) -> None:
        """异步查询待发布任务占用情况，并为 _all_items 打上 in_use 标记。"""
        try:
            from src.services.material.media_usage_service import (
                get_pending_media_usage,
                is_image_folder_used,
            )
        except Exception:
            return

        async def _run() -> None:
            usage = await get_pending_media_usage()
            if gen != self._usage_refresh_gen:
                return
            for it in self._all_items:
                try:
                    it.in_use = bool(is_image_folder_used(usage, it.path))
                except Exception:
                    it.in_use = False
            # 仅原地更新“使用统计”列，避免重建表格导致“进入后自动刷新/闪一下”
            self._update_usage_column_in_place()

        try:
            self._create_tracked_task(_run(), name="image_library.refresh_usage_marks")
        except Exception:
            return

    def _update_usage_column_in_place(self) -> None:
        """Refresh usage column in place without rebuilding rows."""
        if not self._table:
            return
        self._table.notify_columns_changed([_COL_USAGE])

    def _get_selected_items(self) -> List[_ImageFolderItem]:
        if not self._table:
            return []
        seen_rows: set = set()
        items: List[_ImageFolderItem] = []
        for sel_item in self._table.selectedItems():
            row = sel_item.row()
            if row in seen_rows:
                continue
            seen_rows.add(row)
            no_cell = self._table.item(row, _COL_NO)
            if no_cell:
                image_item = no_cell.data(Qt.ItemDataRole.UserRole)
                if isinstance(image_item, _ImageFolderItem):
                    items.append(image_item)
        return items

    def _remove_nonexistent_rows(self) -> None:
        if not self._table:
            return
        for row in range(self._table.rowCount() - 1, -1, -1):
            no_cell = self._table.item(row, _COL_NO)
            if not no_cell:
                continue
            image_item = no_cell.data(Qt.ItemDataRole.UserRole)
            if isinstance(image_item, _ImageFolderItem) and not image_item.path.exists():
                self._table.removeRow(row)

    def _refresh_owner_filter_options(self) -> None:
        current_text = self.owner_filter.currentText() if hasattr(self, "owner_filter") else "全部账号"
        owners = sorted({item.owner for item in self._all_items if item.owner != "未分配"})
        options = ["全部账号"] + owners
        self.owner_filter.blockSignals(True)
        self.owner_filter.clear()
        self.owner_filter.addItems(options)
        self.owner_filter.setCurrentText(current_text if current_text in options else "全部账号")
        self.owner_filter.blockSignals(False)

    def _update_dimension_columns(self) -> None:
        pass

    def _apply_filters(self) -> None:
        if not self._table:
            return
        status = self.owner_status_filter.currentText() if hasattr(self, "owner_status_filter") else "全部"
        owner = self.owner_filter.currentText() if hasattr(self, "owner_filter") else "全部账号"

        if hasattr(self, "owner_filter") and hasattr(self, "owner_status_filter"):
            if status == "未分配":
                self.owner_filter.blockSignals(True)
                self.owner_filter.setCurrentText("全部账号")
                self.owner_filter.blockSignals(False)
                self.owner_filter.setEnabled(False)
            else:
                self.owner_filter.setEnabled(True)

        items = self._media_controller.filter_items(
            self._all_items,
            owner_status=status,
            owner=owner,
        )

        self._populate_table(items)


    # ------------------------------------------------------------------ #
    #                         添加图片文件夹                               #
    # ------------------------------------------------------------------ #

    def _on_add_image_folder_clicked(self):
        """选择文件夹后自动判断：若该文件夹下有子文件夹则导入所有子文件夹，否则导入该文件夹本身。"""
        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            InfoBar.warning(
                title="提示",
                content="未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )
            return

        folder = QFileDialog.getExistingDirectory(self, "选择要添加到图片库的文件夹", "")
        if not folder:
            return

        selected = Path(folder)

        # 检查是否有子文件夹
        try:
            sub_folders = sorted([c for c in selected.iterdir() if c.is_dir()])
        except PermissionError:
            InfoBar.warning(
                title="权限不足",
                content=f"无法读取文件夹「{selected.name}」的内容，请检查文件夹权限。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )
            return

        if sub_folders:
            # 检查子文件夹是否还有下一级子文件夹（不允许超过两层）
            nested = [c for c in sub_folders if any(cc.is_dir() for cc in c.iterdir())]
            if nested:
                names_preview = "、".join(f"「{c.name}」" for c in nested[:3])
                if len(nested) > 3:
                    names_preview += f" 等 {len(nested)} 个"
                InfoBar.warning(
                    title="文件夹层级过深，无法导入",
                    content=(
                        f"以下子文件夹内还包含子文件夹：{names_preview}。\n"
                        "图片库仅支持两层结构（图片库 → 图片文件夹 → 图片），请整理后重试。"
                    ),
                    orient=Qt.Horizontal, isClosable=True, duration=6000,
                    position=InfoBarPosition.TOP, parent=self,
                )
                return

            # 有子文件夹：导入所有子文件夹（过滤掉不含图片的）
            valid_sub: List[Path] = []
            for child in sub_folders:
                has_images = any(
                    os.path.splitext(fn)[1].lower() in IMAGE_EXTENSIONS
                    for fn in os.listdir(str(child))
                    if os.path.isfile(os.path.join(str(child), fn))
                )
                if has_images:
                    valid_sub.append(child)

            if not valid_sub:
                InfoBar.info(
                    title="提示",
                    content=f"文件夹「{selected.name}」的子文件夹中未找到支持的图片文件（jpg/png/gif/webp/bmp）。",
                    orient=Qt.Horizontal, isClosable=True, duration=4000,
                    position=InfoBarPosition.TOP, parent=self,
                )
                return

            self._import_image_folders(valid_sub, root)
        else:
            # 无子文件夹：直接导入该文件夹本身
            has_images = any(
                os.path.splitext(fn)[1].lower() in IMAGE_EXTENSIONS
                for fn in os.listdir(str(selected))
                if os.path.isfile(os.path.join(str(selected), fn))
            )
            if not has_images:
                InfoBar.info(
                    title="提示",
                    content="所选文件夹中未找到支持的图片文件（jpg/png/gif/webp/bmp）。",
                    orient=Qt.Horizontal, isClosable=True, duration=4000,
                    position=InfoBarPosition.TOP, parent=self,
                )
                return

            self._import_image_folders([selected], root)

    def _import_image_folders(self, source_folders: List[Path], root: Path):
        """执行导入：弹出模式选择 → 异步将所有文件夹批量复制/剪切到图片库目录。"""
        n = len(source_folders)
        mode_dialog = _ImportModeDialog(self, file_count=n)
        if not mode_dialog.exec():
            return

        use_move = mode_dialog.get_mode() == _ImportModeDialog.MODE_MOVE
        image_dir = root / MaterialLibraryManager.IMAGE_FOLDER_NAME

        def _resolve_dst(src: Path) -> Path:
            """计算不冲突的目标路径。"""
            dst = image_dir / src.name
            if not dst.exists():
                return dst
            stem = src.name
            idx = 1
            while True:
                candidate = image_dir / f"{stem} ({idx})"
                if not candidate.exists():
                    return candidate
                idx += 1

        def import_sync() -> Tuple[int, List[str]]:
            success_count = 0
            failed_names: List[str] = []
            for src in source_folders:
                dst = _resolve_dst(src)
                try:
                    if use_move:
                        shutil.move(str(src), str(dst))
                    else:
                        shutil.copytree(str(src), str(dst))
                    success_count += 1
                except Exception as err:
                    logger.warning("添加图片文件夹失败: %s -> %s (%s)", src, dst, err)
                    failed_names.append(src.name)
            return success_count, failed_names

        worker = AsyncWorker(import_sync)
        worker.setParent(self)
        action_label = "剪切" if use_move else "复制"

        def on_finished(result: Tuple[int, List[str]]):
            success_count, failed_names = result
            if success_count > 0:
                content = f"已成功{action_label} {success_count} 个图片文件夹到图片库。"
                if failed_names:
                    preview = "、".join(failed_names[:3])
                    if len(failed_names) > 3:
                        preview += f" 等 {len(failed_names)} 个"
                    content += f"\n以下文件夹操作失败：{preview}"
                InfoBar.success(
                    title="添加完成",
                    content=content,
                    orient=Qt.Horizontal, isClosable=True, duration=5000,
                    position=InfoBarPosition.TOP, parent=self,
                )
                self._refresh_async()
            else:
                InfoBar.warning(
                    title="添加失败",
                    content="未能添加任何图片文件夹，请检查磁盘权限或路径是否有效。",
                    orient=Qt.Horizontal, isClosable=True, duration=5000,
                    position=InfoBarPosition.TOP, parent=self,
                )

        def on_error(e: Exception):
            logger.error("添加图片文件夹到媒体库失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误", content="添加图片文件夹时发生异常，请稍后重试。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    # ------------------------------------------------------------------ #
    #                        打开本地文件夹                                 #
    # ------------------------------------------------------------------ #

    def _on_open_image_folder_clicked(self):
        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            InfoBar.warning(
                title="提示",
                content="未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )
            return

        image_dir = root / MaterialLibraryManager.IMAGE_FOLDER_NAME
        if not image_dir.exists():
            InfoBar.warning(
                title="提示", content="未找到图片库目录，请先在设置中确认媒体库路径。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )
            return

        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(image_dir))):
            InfoBar.error(
                title="错误", content="打开本地图片库目录失败，请检查系统默认文件管理器设置。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )

    # ------------------------------------------------------------------ #
    #                            右键菜单                                  #
    # ------------------------------------------------------------------ #

    def _ensure_table_round_menu(self) -> bool:
        try:
            from qfluentwidgets import RoundMenu, Action, FluentIcon as _FI
        except ImportError:
            return False
        from src.ui.components.fluent_context_menu import (
            install_round_menu_close_on_app_inactive,
            is_round_menu_alive,
            round_menu_parent,
        )

        if self._table_ctx_menu is not None and is_round_menu_alive(self._table_ctx_menu):
            return True
        parent = round_menu_parent(self)
        if parent is None:
            return False
        self._table_ctx_menu = RoundMenu(parent=parent)
        self._table_ctx_action_open = Action(_FI.FOLDER, "打开图片文件夹", parent)
        self._table_ctx_action_open.triggered.connect(self._on_ctx_open_folder_clicked)
        self._table_ctx_menu.addAction(self._table_ctx_action_open)
        install_round_menu_close_on_app_inactive(self._table_ctx_menu)
        return True

    def _on_ctx_open_folder_clicked(self) -> None:
        image_item = self._table_ctx_target_image
        self._table_ctx_target_image = None
        if not isinstance(image_item, _ImageFolderItem):
            return
        try:
            folder = image_item.path.resolve()
        except OSError:
            folder = image_item.path
        if not folder.exists():
            InfoBar.warning(
                title="提示", content="该图片文件夹已不存在，可能已被移动或删除。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            InfoBar.error(
                title="错误", content="打开文件夹失败，请检查系统默认文件管理器设置。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )

    def _on_table_context_menu(self, pos: QPoint) -> None:
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
        if (not selected_rows) or (clicked_row not in selected_rows):
            sm.blockSignals(True)
            try:
                self._table.selectRow(clicked_row)
            finally:
                sm.blockSignals(False)
        no_cell = self._table.item(clicked_row, _COL_NO)
        if not no_cell:
            return
        image_item = no_cell.data(Qt.ItemDataRole.UserRole)
        if not isinstance(image_item, _ImageFolderItem):
            return
        self._table_ctx_target_image = image_item
        global_pos = self._table.viewport().mapToGlobal(pos)
        if self._ensure_table_round_menu():
            self._table_ctx_menu.exec(global_pos)
            return
        menu = QMenu(self._table)
        act_open = menu.addAction("打开图片文件夹")
        try:
            act_open.setIcon(FluentIcon.FOLDER.icon())
        except Exception:
            pass
        chosen = menu.exec(global_pos)
        if chosen == act_open:
            self._on_ctx_open_folder_clicked()

    # ------------------------------------------------------------------ #
    #                         删除到回收站                                  #
    # ------------------------------------------------------------------ #

    def _on_delete_clicked(self) -> None:
        selected = self._get_selected_items()
        if not selected:
            InfoBar.info(
                title="提示", content="请先在列表中选择要删除的图片文件夹。",
                orient=Qt.Horizontal, isClosable=True, duration=3000,
                position=InfoBarPosition.TOP, parent=self,
            )
            return

        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            InfoBar.warning(
                title="提示",
                content="未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )
            return

        n = len(selected)
        confirmed = show_confirm(
            self,
            "确认删除",
            f"将把选中的 {n} 个图片文件夹移入 Windows 系统回收站。\n\n"
            "文件夹不会被彻底删除，可随时打开回收站手动恢复。\n"
            "（注意：网络盘或 UNC 路径上的文件夹可能无法进入回收站。）\n\n"
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

                try:
                    resolved.relative_to(root_resolved)
                except ValueError:
                    logger.warning("拒绝删除媒体库范围外的文件夹: %s", path)
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
                    title="错误", content=import_err,
                    orient=Qt.Horizontal, isClosable=True, duration=6000,
                    position=InfoBarPosition.TOP, parent=self,
                )
                return
            if success_count > 0:
                content = f"已将 {success_count} 个图片文件夹移入系统回收站，可从回收站恢复。"
                if failed_names:
                    preview = "、".join(failed_names[:3])
                    if len(failed_names) > 3:
                        preview += f" 等 {len(failed_names)} 个"
                    content += f"\n以下文件夹操作失败：{preview}"
                InfoBar.success(
                    title="已移入回收站", content=content,
                    orient=Qt.Horizontal, isClosable=True, duration=5000,
                    position=InfoBarPosition.TOP, parent=self,
                )
                self._refresh_async()
            else:
                InfoBar.warning(
                    title="未能删除",
                    content="未能将任何图片文件夹移入回收站，请检查路径是否存在或磁盘权限。",
                    orient=Qt.Horizontal, isClosable=True, duration=5000,
                    position=InfoBarPosition.TOP, parent=self,
                )

        def on_error(e: Exception):
            logger.error("移入回收站操作失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误", content="删除操作时发生异常，请稍后重试。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    # ------------------------------------------------------------------ #
    #                           刷新目录                                   #
    # ------------------------------------------------------------------ #

    def _clear_filters(self) -> None:
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
        if self._table and self._all_items:
            self._apply_filters()
        self._refresh_async()
    def _scan_image_items_fast(self) -> Tuple[List[_ImageFolderItem], Optional[str]]:
        """枚举图片库中的文件夹及其图片数量、总大小。"""
        root = MaterialLibraryManager.ensure_initialized()
        if root is None:
            return [], "未检测到有效的媒体库路径，请先在设置中配置媒体库存储位置。"
        scanned, err = scan_image_library_entries(root, IMAGE_EXTENSIONS)
        if err:
            return [], err
        items: List[_ImageFolderItem] = []
        for entry in scanned:
            item = _ImageFolderItem(entry.path)
            item.image_count = entry.image_count
            item.size_mb = entry.size_bytes / (1024 * 1024)
            item.size_bytes = entry.size_bytes
            item.mtime = entry.mtime
            item.owner = entry.owner_label
            items.append(item)
        return items, None

    def _refresh_async(self):
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

        self._image_refresh_gen += 1
        gen = self._image_refresh_gen
        self._usage_refresh_gen += 1
        ugen = self._usage_refresh_gen

        def scan_sync() -> Tuple[List[_ImageFolderItem], Optional[str]]:
            try:
                return self._scan_image_items_fast()
            except Exception as e:
                logger.error("扫描媒体库图片目录失败: %s", e, exc_info=True)
                return [], "扫描媒体库图片目录时发生错误，请稍后重试。"

        worker = AsyncWorker(scan_sync)
        worker.setParent(self)

        def on_fast_finished(result: Tuple[List[_ImageFolderItem], Optional[str]]):
            items, error = result
            if gen != self._image_refresh_gen:
                return
            if error:
                InfoBar.warning(
                    title="提示", content=error,
                    orient=Qt.Horizontal, isClosable=True, duration=5000,
                    position=InfoBarPosition.TOP, parent=self,
                )
            self._all_items = items
            self._refresh_owner_filter_options()
            self._apply_filters()
            # 使用统计（占用标记）：异步查库后回填到表格
            self._schedule_refresh_usage_marks(ugen)
            self._schedule_base_page_timer(
                "image_library.ensure_table_round_menu",
                200,
                self._ensure_table_round_menu,
            )

        def on_error(e: Exception):
            logger.error("刷新图片库列表失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误", content="刷新图片库列表时发生异常，请稍后重试。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )

        worker.finished.connect(on_fast_finished)
        worker.error.connect(on_error)
        worker.start()

    # ------------------------------------------------------------------ #
    #                           分配策略                                   #
    # ------------------------------------------------------------------ #

    def _on_assign_strategy_btn_clicked(self) -> None:
        from PySide6.QtGui import QAction

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

    # ------------------------------------------------------------------ #
    #                           分配逻辑                                   #
    # ------------------------------------------------------------------ #

    @asyncSlot()
    async def _on_assign_clicked(self):
        selected = self._get_selected_items()
        if not selected:
            InfoBar.info(
                title="提示", content="请先在列表中选择要分配的图片文件夹。",
                orient=Qt.Horizontal, isClosable=True, duration=3000,
                position=InfoBarPosition.TOP, parent=self,
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
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
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
            assign_targets.append(resolve_assign_target(root, media_kind="image", target_type=tt, target_data=t_data))

        if not assign_targets:
            show_warning(self, "提示", "请选择有效的账号或账号组。")
            return

        # 过滤出实际存在的文件夹
        valid_folders: List[Path] = [
            fi.path for fi in selected if fi.path.exists() and fi.path.is_dir()
        ]
        if not valid_folders:
            InfoBar.info(
                title="提示", content="所选图片文件夹已不存在，请刷新列表后重试。",
                orient=Qt.Horizontal, isClosable=True, duration=4000,
                position=InfoBarPosition.TOP, parent=self,
            )
            return

        # 以文件夹为粒度，按策略分配到各目标账号
        distribution = distribute_folders_to_targets_grouped(valid_folders, assign_targets, self._assign_strategy)

        # 提前创建所有目标目录
        for at in assign_targets:
            try:
                at.directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error("创建素材分配目标目录失败: %s", e, exc_info=True)
                InfoBar.error(
                    title="错误", content=f"无法创建{at.label}的素材目录，请检查磁盘权限。",
                    orient=Qt.Horizontal, isClosable=True, duration=5000,
                    position=InfoBarPosition.TOP, parent=self,
                )
                return

        strategy = self._assign_strategy
        n_targets = len(assign_targets)

        def move_sync() -> Tuple[int, List[str]]:
            """将每个文件夹整体移入对应账号的「图文/未发布」目录。"""
            moved_count = 0
            failed_names: List[str] = []
            touched_bucket_dirs: set[Path] = set()
            for at, folders in distribution.items():
                for folder in folders:
                    source_parent = folder.parent
                    ok = move_folder_to_assign_target(
                        folder,
                        at.directory,
                        refresh_stats=False,
                    )
                    if ok:
                        moved_count += 1
                        touched_bucket_dirs.add(source_parent)
                        touched_bucket_dirs.add(at.directory)
                    else:
                        failed_names.append(folder.name)
            if moved_count > 0:
                try:
                    from src.services.material.media_library_stats_service import (
                        get_media_library_stats_service,
                    )

                    svc = get_media_library_stats_service()
                    svc.invalidate_bucket_paths(touched_bucket_dirs, kinds=("image",))
                except Exception:
                    logger.debug("批量分配图片文件夹后失效媒体库统计缓存失败", exc_info=True)
            return moved_count, failed_names

        worker = AsyncWorker(move_sync)
        worker.setParent(self)

        def on_finished(result: Tuple[int, List[str]]):
            moved_count, failed_names = result
            if moved_count > 0:
                self._remove_nonexistent_rows()
                target_desc = "、".join(at.label for at in assign_targets[:3])
                if n_targets > 3:
                    target_desc += f" 等 {n_targets} 个目标"
                content = f"按{strategy.display_name()}策略成功分配 {moved_count} 个图片文件夹到{target_desc}的未发布目录。"
                if failed_names:
                    preview = "、".join(failed_names[:3])
                    if len(failed_names) > 3:
                        preview += f" 等 {len(failed_names)} 个"
                    content += f"\n以下文件夹移动失败：{preview}"
                InfoBar.success(
                    title="已分配", content=content,
                    orient=Qt.Horizontal, isClosable=True, duration=5000,
                    position=InfoBarPosition.TOP, parent=self,
                )
                self._refresh_async()
            else:
                InfoBar.info(
                    title="提示", content="未能分配任何图片文件夹，请检查文件夹是否仍存在或磁盘权限。",
                    orient=Qt.Horizontal, isClosable=True, duration=4000,
                    position=InfoBarPosition.TOP, parent=self,
                )

        def on_error(e: Exception):
            logger.error("分配图片文件夹失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误", content="分配图片文件夹时发生错误，请稍后重试。",
                orient=Qt.Horizontal, isClosable=True, duration=5000,
                position=InfoBarPosition.TOP, parent=self,
            )

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        worker.start()

    # ------------------------------------------------------------------ #
    #                          账号选择                                    #
    # ------------------------------------------------------------------ #

    async def _choose_targets_dialog(self) -> Optional[List[Dict[str, Any]]]:
        """选择分配对象（支持多选账号或多选账号组）。"""
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
        code = await await_qdialog_finished(dialog)
        if code != int(QDialog.DialogCode.Accepted):
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
