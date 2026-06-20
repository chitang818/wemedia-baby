"""
位置推广页面
功能：管理位置推广配置，支持新增、编辑、删除、Excel 导入（覆盖模式）和刷新。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt
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
from src.ui.utils.task_tracking import TrackedTaskMixin
from src.ui.components.rubber_band_row_table import RubberBandRowSelectTable
from src.infrastructure.storage.repositories.location_promotion_repository import (
    LocationPromotionRepository,
)
from src.proprietary.ui.pages.material.location_promotion_edit_dialog import (
    LocationPromotionEditDialog,
)

logger = logging.getLogger(__name__)

_COL_NO = 0
_COL_SHORT_NAME = 1
_COL_DOUYIN = 2
_COL_KUAISHOU = 3
_COL_CHANNELS = 4
_COL_XIAOHONGSHU = 5
_HEADERS = [
    "序号",
    "位置简称",
    "抖音位置",
    "快手位置",
    "视频号位置",
    "小红书位置",
]


class LocationPromotionPage(TrackedTaskMixin, BasePage):
    """位置推广页面：基于 SQLite + Tortoise 的位置配置管理界面。"""

    _lazy_content = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("位置推广", parent)
        self._table: Optional[RubberBandRowSelectTable] = None

    def _setup_content(self):
        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(12)

        toolbar_card = CardWidget(self)
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        toolbar_layout.setSpacing(12)

        self.btn_new = PrimaryPushButton("新建位置", toolbar_card)
        self.btn_new.clicked.connect(self._on_new_clicked)
        self.btn_edit = PushButton("编辑选中", toolbar_card)
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        self.btn_import = PushButton("导入 Excel", toolbar_card)
        self.btn_import.clicked.connect(self._on_import_clicked)
        self.btn_delete = PushButton("删除选中", toolbar_card)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        self.btn_reload = PushButton("刷新列表", toolbar_card)
        self.btn_reload.clicked.connect(self._on_reload_clicked)

        toolbar_layout.addWidget(self.btn_new)
        toolbar_layout.addWidget(self.btn_edit)
        toolbar_layout.addWidget(self.btn_import)
        toolbar_layout.addWidget(self.btn_delete)
        toolbar_layout.addWidget(self.btn_reload)
        toolbar_layout.addStretch()

        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self._table = RubberBandRowSelectTable(table_card)
        self._setup_table_style(self._table)
        self._table.setObjectName("LocationPromotionTable")
        self._table.setSelectionBehavior(self._table.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(self._table.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(self._table.EditTrigger.NoEditTriggers)
        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._on_table_double_clicked)

        header = self._table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_NO, QHeaderView.ResizeMode.Fixed)
        header.setMinimumSectionSize(52)
        self._table.setColumnWidth(_COL_NO, 52)
        self._table.setColumnWidth(_COL_SHORT_NAME, 140)
        self._table.setColumnWidth(_COL_DOUYIN, 220)
        self._table.setColumnWidth(_COL_KUAISHOU, 220)
        self._table.setColumnWidth(_COL_CHANNELS, 220)
        self._table.setColumnWidth(_COL_XIAOHONGSHU, 220)

        table_layout.addWidget(self._table)
        root_layout.addWidget(toolbar_card)
        root_layout.addWidget(table_card)
        self.content_layout.addLayout(root_layout)

        self._create_tracked_task(self._reload(), name="location_promotion.initial_reload")

    def _populate_table(self, rows: List[Dict[str, Any]]) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))

        for row_idx, item in enumerate(rows):

            def _cell(val: str) -> QTableWidgetItem:
                c = QTableWidgetItem(val)
                c.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                return c

            no_cell = QTableWidgetItem(str(row_idx + 1))
            no_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            no_cell.setData(Qt.ItemDataRole.UserRole, item)
            self._table.setItem(row_idx, _COL_NO, no_cell)
            self._table.setItem(row_idx, _COL_SHORT_NAME, _cell(item.get("short_name") or ""))
            self._table.setItem(row_idx, _COL_DOUYIN, _cell(item.get("douyin_location") or ""))
            self._table.setItem(row_idx, _COL_KUAISHOU, _cell(item.get("kuaishou_location") or ""))
            self._table.setItem(row_idx, _COL_CHANNELS, _cell(item.get("channels_location") or ""))
            self._table.setItem(
                row_idx, _COL_XIAOHONGSHU, _cell(item.get("xiaohongshu_location") or "")
            )

        self._table.setSortingEnabled(True)

    def _get_selected_items(self) -> List[Dict[str, Any]]:
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
        items = self._get_selected_items()
        return items[0] if len(items) == 1 else None

    def _on_reload_clicked(self):
        self._create_tracked_task(self._reload(), name="location_promotion.reload")

    async def _reload(self):
        try:
            rows = await LocationPromotionRepository.list_all()
            if self._table:
                self._populate_table(rows)
        except Exception as e:
            logger.error("加载位置推广列表失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content="加载位置列表时发生异常，请稍后重试。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_new_clicked(self):
        dialog = LocationPromotionEditDialog(self, item_data=None)
        if not dialog.exec():
            return
        self._create_tracked_task(
            self._save_item(dialog.get_form_data(), is_edit=False),
            name="location_promotion.save_new",
        )

    def _on_edit_clicked(self):
        item = self._get_single_selected_item()
        if item is None:
            InfoBar.info(
                title="提示",
                content="请先在列表中选择一条位置记录再点击编辑。",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        self._open_edit_dialog(item)

    def _on_table_double_clicked(self, index):
        if not index.isValid():
            return
        no_cell = self._table.item(index.row(), _COL_NO)
        if no_cell:
            data = no_cell.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                self._open_edit_dialog(data)

    def _open_edit_dialog(self, item: Dict[str, Any]):
        dialog = LocationPromotionEditDialog(self, item_data=item)
        if not dialog.exec():
            return
        data = dialog.get_form_data()
        data["id"] = item.get("id")
        self._create_tracked_task(
            self._save_item(data, is_edit=True),
            name="location_promotion.save_edit",
        )

    async def _save_item(self, data: Dict[str, Any], is_edit: bool):
        try:
            result = await LocationPromotionRepository.create_or_update_by_short_name(data)
            action = "已更新" if is_edit else "已创建"
            InfoBar.success(
                title=action,
                content=f"{action}位置配置：{result.get('short_name')}",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            await self._reload()
        except Exception as e:
            logger.error("保存位置配置失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content=f"保存位置配置时发生异常：{e}",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_delete_clicked(self):
        selected = self._get_selected_items()
        if not selected:
            InfoBar.info(
                title="提示",
                content="请先选择要删除的位置记录。",
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

        names = "、".join(it.get("short_name", "") for it in selected[:3])
        if len(selected) > 3:
            names += " 等"
        if not show_confirm(
            self, "确认删除", f"确定要删除选中的 {len(ids)} 条位置配置（{names}）吗？此操作不可撤销。"
        ):
            return
        self._create_tracked_task(self._delete_items(ids), name="location_promotion.delete")

    async def _delete_items(self, ids: List[int]):
        try:
            deleted = await LocationPromotionRepository.delete_by_ids(ids)
            if deleted > 0:
                InfoBar.success(
                    title="已删除",
                    content=f"成功删除 {deleted} 条位置配置。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=4000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                await self._reload()
        except Exception as e:
            logger.error("删除位置配置失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content=f"删除位置配置时发生异常：{e}",
                orient=Qt.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _export_template_excel(self, save_path: str) -> bool:
        """生成位置推广 Excel 模板文件并保存。"""
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "位置推广模板"

            # 写入表头
            headers = [
                "位置简称",
                "抖音位置",
                "快手位置",
                "视频号位置",
                "小红书位置"
            ]
            ws.append(headers)

            # 写入示例行
            example1 = [
                "南山科技园",
                "深圳市南山区南山科技园",
                "深圳南山科技园",
                "深圳市腾讯大厦",
                "深圳湾万象城"
            ]
            example2 = [
                "北京路",
                "广州市越秀区北京路",
                "广州北京路步行街",
                "广州北京路",
                "广州天河城"
            ]
            ws.append(example1)
            ws.append(example2)

            # 稍微调整一下列宽
            ws.column_dimensions['A'].width = 15
            ws.column_dimensions['B'].width = 30
            ws.column_dimensions['C'].width = 30
            ws.column_dimensions['D'].width = 30
            ws.column_dimensions['E'].width = 30

            wb.save(save_path)
            return True
        except Exception as e:
            logger.error("生成 Excel 模板失败: %s", e, exc_info=True)
            return False

    def _on_import_clicked(self):
        """弹出导入与模板下载的选择窗口。"""
        from src.ui.components.base_dialog import AppMessageBoxBase
        from qfluentwidgets import BodyLabel, PushButton, FluentIcon
        from PySide6.QtWidgets import QFileDialog

        dlg = AppMessageBoxBase(self, header_title="导入位置推广")
        
        # 说明正文
        desc = BodyLabel(
            "您可以从 Excel 模板批量导入位置推广库，相同位置简称的记录将被覆盖更新。\n\n"
            "如果您是首次使用，建议先下载并填写我们的位置推广模板，然后再执行导入操作。", 
            dlg
        )
        desc.setWordWrap(True)
        dlg.viewLayout.addWidget(desc)

        # 模板下载按钮
        btn_download = PushButton("下载位置推广模板", dlg, FluentIcon.DOWNLOAD)
        
        def _download_template():
            try:
                import openpyxl
            except ImportError:
                from qfluentwidgets import InfoBar, InfoBarPosition
                InfoBar.error(
                    title="环境依赖缺失",
                    content="当前环境未安装 openpyxl。请在项目目录执行：pip install openpyxl",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    duration=8000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return

            import os
            desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
            default_path = os.path.join(desktop_dir, "位置推广模板.xlsx") if os.path.exists(desktop_dir) else "位置推广模板.xlsx"

            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "保存位置推广模板",
                default_path,
                "Excel 文件 (*.xlsx)"
            )
            if save_path:
                success = self._export_template_excel(save_path)
                if success:
                    from qfluentwidgets import InfoBar, InfoBarPosition
                    InfoBar.success(
                        title="下载成功",
                        content=f"已成功保存位置推广模板至：{save_path}",
                        orient=Qt.Horizontal,
                        isClosable=True,
                        duration=5000,
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )
                else:
                    from qfluentwidgets import InfoBar, InfoBarPosition
                    InfoBar.error(
                        title="下载失败",
                        content="保存模板文件时发生错误，请检查是否有权限写入该目录。",
                        orient=Qt.Horizontal,
                        isClosable=True,
                        duration=5000,
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )

        btn_download.clicked.connect(_download_template)
        dlg.viewLayout.addWidget(btn_download)

        dlg.yesButton.setText("选择文件导入")
        dlg.cancelButton.setText("取消")

        # 弹窗交互
        if not dlg.exec():
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择位置推广 Excel 文件",
            "",
            "Excel 文件 (*.xlsx);;所有文件 (*.*)",
        )
        if not file_path:
            return
        self._create_tracked_task(
            self._import_excel(file_path),
            name="location_promotion.import_excel",
        )

    async def _import_excel(self, file_path: str):
        try:
            from src.infrastructure.common.excel_location_importer import parse_excel
        except ImportError as e:
            logger.warning("位置 Excel 导入依赖缺失: %s", e)
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
            result = await asyncio.get_event_loop().run_in_executor(
                None, parse_excel, file_path
            )
        except Exception as e:
            logger.error("解析位置 Excel 失败: %s", e, exc_info=True)
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
            msg = "未解析到任何有效位置配置，请检查 Excel 是否符合模板格式。"
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
            stats = await LocationPromotionRepository.bulk_import(items, overwrite=True)
        except Exception as e:
            logger.error("批量导入位置配置失败: %s", e, exc_info=True)
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
        summary = (
            f"导入完成：共 {base_total} 行（有效 {len(items)} 行），"
            f"成功 {success} 行，失败 {failed} 行。\n"
            f"（同位置简称的记录已覆盖更新，新位置已新增）"
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
