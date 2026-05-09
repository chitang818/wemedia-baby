"""
文案库页面
文件路径：src/ui/pages/material/copywriting_library_page.py
功能：展示和管理本地数据库中的文案数据，支持新增、编辑、删除、Excel 导入（覆盖模式），以及飞书云文档预留入口。
表格使用 Fluent TableWidget，含序号列，与视频库风格一致。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
)

from qfluentwidgets import (
    CardWidget,
    PrimaryPushButton,
    PushButton,
    InfoBar,
    InfoBarPosition,
)

from src.ui.pages.base_page import BasePage
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.ui.components.rubber_band_row_table import RubberBandRowSelectTable
from src.infrastructure.storage.repositories.copywriting_repository import (
    CopywritingRepository,
)
from src.ui.pages.material.copywriting_edit_dialog import CopywritingEditDialog

logger = logging.getLogger(__name__)

# 列索引常量（含序号列）
_COL_NO          = 0
_COL_WORK_ID     = 1
_COL_SHORT_TITLE = 2
_COL_DESCRIPTION = 3
_COL_CONTENT     = 4
_HEADERS = ["序号", "作品编号", "作品标题", "作品描述", "文案内容"]


class CopywritingLibraryPage(BasePage):
    """文案库页面：基于 SQLite + Tortoise 的文案管理界面。"""

    _lazy_content = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("标准文案库", parent)
        self._table: Optional[TableWidget] = None

    def _setup_content(self):
        """构建页面内容。"""
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        # 顶部工具栏卡片
        toolbar_card = CardWidget(self)
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        toolbar_layout.setSpacing(12)

        self.btn_new = PrimaryPushButton("新建文案", toolbar_card)
        self.btn_new.clicked.connect(self._on_new_clicked)

        self.btn_edit = PushButton("编辑选中", toolbar_card)
        self.btn_edit.clicked.connect(self._on_edit_clicked)

        self.btn_import = PushButton("导入 Excel", toolbar_card)
        self.btn_import.clicked.connect(self._on_import_clicked)

        self.btn_delete = PushButton("删除选中", toolbar_card)
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        self.btn_reload = PushButton("刷新列表", toolbar_card)
        self.btn_reload.clicked.connect(self._on_reload_clicked)

        # 飞书云文档预留入口（置灰，功能待开发）
        self.btn_feishu = PushButton("提取飞书云文档", toolbar_card)
        self.btn_feishu.setEnabled(False)
        _feishu_row = QWidget(toolbar_card)
        _fr = QHBoxLayout(_feishu_row)
        _fr.setContentsMargins(0, 0, 0, 0)
        _fr.setSpacing(4)
        _fr.addWidget(self.btn_feishu)
        apply_instructional_tooltip(
            "飞书集成功能开发中，敬请期待",
            self.btn_feishu,
            position=ToolTipPosition.BOTTOM,
        )

        toolbar_layout.addWidget(self.btn_new)
        toolbar_layout.addWidget(self.btn_edit)
        toolbar_layout.addWidget(self.btn_import)
        toolbar_layout.addWidget(self.btn_delete)
        toolbar_layout.addWidget(self.btn_reload)
        toolbar_layout.addWidget(_feishu_row)
        toolbar_layout.addStretch()

        # 表格卡片（Fluent TableWidget，与视频库风格一致）
        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self._table = RubberBandRowSelectTable(table_card)
        self._setup_table_style(self._table)
        # RubberBandRowSelectTable.__init__ 已内置 2px padding，此处只需设 objectName
        self._table.setObjectName("CopywritingLibraryTable")
        # RubberBandRowSelectTable 自带 NoDragDrop；显式设置选择模式
        self._table.setSelectionBehavior(self._table.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(self._table.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(self._table.EditTrigger.NoEditTriggers)

        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.verticalHeader().setVisible(False)
        # 双击行触发编辑
        self._table.doubleClicked.connect(self._on_table_double_clicked)

        # 列宽：序号列固定，其余列 Interactive 可拖拽调整
        header = self._table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_NO, QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(52)
        self._table.setColumnWidth(_COL_NO,          52)
        self._table.setColumnWidth(_COL_WORK_ID,    120)
        self._table.setColumnWidth(_COL_SHORT_TITLE, 150)
        self._table.setColumnWidth(_COL_DESCRIPTION, 200)
        self._table.setColumnWidth(_COL_CONTENT,     300)

        table_layout.addWidget(self._table)

        root_layout.addWidget(toolbar_card)
        root_layout.addWidget(table_card)
        self.content_layout.addLayout(root_layout)

        asyncio.create_task(self._reload())

    # ---------- 表格填充 ----------

    def _populate_table(self, rows: List[Dict[str, Any]]) -> None:
        """将数据库查询结果渲染到 TableWidget。"""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))

        for row_idx, item in enumerate(rows):
            # 序号列：存储完整数据字典，供编辑/删除时取用
            no_cell = QTableWidgetItem(str(row_idx + 1))
            no_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            no_cell.setData(Qt.ItemDataRole.UserRole, item)
            self._table.setItem(row_idx, _COL_NO, no_cell)

            work_id_cell = QTableWidgetItem(item.get("work_id") or "")
            work_id_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_idx, _COL_WORK_ID, work_id_cell)

            short_title_cell = QTableWidgetItem(item.get("short_title") or "")
            short_title_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_idx, _COL_SHORT_TITLE, short_title_cell)

            desc_cell = QTableWidgetItem(item.get("description") or "")
            desc_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_idx, _COL_DESCRIPTION, desc_cell)

            content_cell = QTableWidgetItem(item.get("content") or "")
            content_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self._table.setItem(row_idx, _COL_CONTENT, content_cell)

        self._table.setSortingEnabled(True)

    def _get_selected_items(self) -> List[Dict[str, Any]]:
        """从选中行取出数据字典列表（用于批量删除等）。"""
        if not self._table:
            return []
        seen: set = set()
        result: List[Dict[str, Any]] = []
        for sel in self._table.selectedItems():
            r = sel.row()
            if r in seen:
                continue
            seen.add(r)
            no_cell = self._table.item(r, _COL_NO)
            if no_cell:
                data = no_cell.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    result.append(data)
        return result

    def _get_single_selected_item(self) -> Optional[Dict[str, Any]]:
        """仅当精确选中单行时返回数据；多选或未选返回 None。"""
        items = self._get_selected_items()
        return items[0] if len(items) == 1 else None

    # ---------- 加载 ----------

    def _on_reload_clicked(self):
        asyncio.create_task(self._reload())

    async def _reload(self):
        """从数据库异步加载文案列表并刷新表格。"""
        try:
            rows = await CopywritingRepository.list_items(page=1, page_size=500)
            if self._table:
                self._populate_table(rows)
        except Exception as e:
            logger.error("加载文案库列表失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content="加载文案库列表时发生异常，请稍后重试。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    # ---------- 新建 ----------

    def _on_new_clicked(self):
        """弹出新建文案表单，用户填写后写入数据库。"""
        dialog = CopywritingEditDialog(self, item_data=None)
        if not dialog.exec():
            return
        data = dialog.get_form_data()
        asyncio.create_task(self._save_copywriting(data, is_edit=False))

    # ---------- 编辑 ----------

    def _on_edit_clicked(self):
        """编辑选中的单条文案记录。"""
        item = self._get_single_selected_item()
        if item is None:
            InfoBar.info(
                title="提示",
                content="请先在列表中选择一条文案记录再点击编辑。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        self._open_edit_dialog(item)

    def _on_table_double_clicked(self, index):
        """双击表格行时打开编辑弹窗。"""
        if not index.isValid():
            return
        no_cell = self._table.item(index.row(), _COL_NO)
        if no_cell:
            data = no_cell.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                self._open_edit_dialog(data)

    def _open_edit_dialog(self, item: Dict[str, Any]):
        """打开编辑弹窗并保存修改结果。"""
        dialog = CopywritingEditDialog(self, item_data=item)
        if not dialog.exec():
            return
        data = dialog.get_form_data()
        # 编辑模式下保留原始主键，供仓库层精准更新
        data["id"] = item.get("id")
        asyncio.create_task(self._save_copywriting(data, is_edit=True))

    # ---------- 保存（新建/编辑共用）----------

    async def _save_copywriting(self, data: Dict[str, Any], is_edit: bool):
        """将表单数据写入数据库（按 work_id 新建或覆盖更新）。"""
        try:
            result = await CopywritingRepository.create_or_update_by_work_id(data)
            action = "已更新" if is_edit else "已创建"
            InfoBar.success(
                title=action,
                content=f"{action}文案，作品编号：{result.get('work_id')}",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            await self._reload()
        except Exception as e:
            logger.error("保存文案失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content=f"保存文案时发生异常：{e}",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    # ---------- 删除 ----------

    def _on_delete_clicked(self):
        """删除选中的一条或多条文案记录。"""
        selected = self._get_selected_items()
        if not selected:
            InfoBar.info(
                title="提示",
                content="请先选择要删除的文案记录。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        ids = [int(it["id"]) for it in selected if it.get("id")]
        if not ids:
            return

        from src.ui.utils.fluent_dialogs import show_confirm

        if not show_confirm(self, "确认删除", f"确定要删除选中的 {len(ids)} 条文案记录吗？此操作不可撤销。"):
            return

        asyncio.create_task(self._delete_items(ids))

    async def _delete_items(self, ids: List[int]):
        try:
            deleted = await CopywritingRepository.delete_items(ids)
            if deleted > 0:
                InfoBar.success(
                    title="已删除",
                    content=f"成功删除 {deleted} 条文案记录。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=4000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                await self._reload()
            else:
                InfoBar.info(
                    title="提示",
                    content="未删除任何记录，请稍后重试。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=4000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("删除文案记录失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content=f"删除文案记录时发生异常：{e}",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    # ---------- Excel 导入（覆盖模式：同作品编号则更新）----------

    def _on_import_clicked(self):
        """从 Excel 批量导入文案；同作品编号的记录会被覆盖更新。"""
        from PySide6.QtWidgets import QFileDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择文案库 Excel 文件",
            "",
            "Excel 文件 (*.xlsx);;所有文件 (*.*)",
        )
        if not file_path:
            return

        asyncio.create_task(self._import_excel(file_path))

    async def _import_excel(self, file_path: str):
        """异步解析并导入 Excel 文案数据。"""
        try:
            from src.infrastructure.common.excel_copywriting_importer import (
                parse_excel,
            )
        except ImportError as e:
            logger.warning("文案库 Excel 导入依赖缺失: %s", e)
            InfoBar.error(
                title="无法导入 Excel",
                content="当前环境未安装 openpyxl。请在项目目录执行：pip install openpyxl",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=8000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        try:
            # parse_excel 是同步函数，在事件循环线程中直接调用（文件读取速度快）
            result = await asyncio.get_event_loop().run_in_executor(
                None, parse_excel, file_path
            )
        except Exception as e:
            logger.error("解析文案 Excel 失败: %s", e, exc_info=True)
            InfoBar.error(
                title="导入失败",
                content=f"解析 Excel 文件失败，请确认文件是否为标准模板。错误：{e}",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=7000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        items = result.get("items") or []
        base_total = result.get("total", 0)
        base_errors: List[str] = result.get("errors") or []

        if not items:
            msg = "未解析到任何有效文案，请检查 Excel 是否符合模板格式。"
            if base_errors:
                msg += "\n" + "\n".join(base_errors[:5])
            InfoBar.warning(
                title="导入失败",
                content=msg,
                orient=Qt.Horizontal,
                isClosable=True,
                duration=7000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        try:
            # overwrite_by_work_id=True：同作品编号的记录将被覆盖更新
            stats = await CopywritingRepository.bulk_import(items, overwrite_by_work_id=True)
        except Exception as e:
            logger.error("批量导入文案失败: %s", e, exc_info=True)
            InfoBar.error(
                title="导入失败",
                content="写入数据库时发生错误，请稍后重试。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=6000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        success = stats.get("success", 0)
        failed = stats.get("failed", 0)
        errs: List[str] = stats.get("errors") or []

        # 明确提示覆盖规则：同作品编号则更新，新编号则新增
        summary = (
            f"导入完成：共 {base_total} 行（有效 {len(items)} 行），"
            f"成功 {success} 行，失败 {failed} 行。\n"
            f"（同作品编号的记录已覆盖更新，新编号已新增）"
        )
        if base_errors or errs:
            detail_lines = base_errors + errs
            preview = "\n".join(detail_lines[:5])
            if len(detail_lines) > 5:
                preview += "\n……"
            summary += "\n部分错误：\n" + preview

        InfoBar.success(
            title="导入完成",
            content=summary,
            orient=Qt.Horizontal,
            isClosable=True,
            duration=8000,
            position=InfoBarPosition.TOP,
            parent=self,
        )
        await self._reload()
