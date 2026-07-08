"""
文案库页面
文件路径：src/ui/pages/material/copywriting_library_page.py
功能：展示和管理本地数据库中的文案数据，支持新增、编辑、删除、Excel 导入（覆盖模式），以及飞书云文档预留入口。
支持多分类（Sheet）的 TabBar 标签页展示。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QStackedWidget,
    QSizePolicy,
)

from qfluentwidgets import (
    CardWidget,
    PrimaryPushButton,
    PushButton,
    InfoBar,
    InfoBarPosition,
    CaptionLabel,
    BodyLabel,
    TabBar,
    TabCloseButtonDisplayMode,
    DropDownPushButton,
    TransparentToolButton,
    RoundMenu,
    Action,
    FluentIcon,
)

from src.ui.pages.base_page import BasePage
from src.ui.utils.task_tracking import TrackedTaskMixin
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
_HEADERS = ["序号", "作品编号", "作品标题", "作品描述", "作品文案"]


class CopywritingLibraryPage(TrackedTaskMixin, BasePage):
    """文案库页面：以选项卡（按分类）形式展示媒体文案。"""

    _lazy_content = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("标准文案库", parent)
        self.setObjectName("CopywritingLibraryPage")
        
        self._category_names: List[str] = []
        self._tables: Dict[str, RubberBandRowSelectTable] = {}

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

        self.btn_edit = PushButton("编辑选中", toolbar_card)
        self.btn_edit.clicked.connect(self._on_edit_clicked)

        self.btn_delete = PushButton("删除选中", toolbar_card)
        self.btn_delete.clicked.connect(self._on_delete_clicked)

        self.btn_reload = PushButton("刷新列表", toolbar_card)
        self.btn_reload.clicked.connect(self._on_reload_clicked)

        # 状态切换容器
        self.btn_bind_source = DropDownPushButton("关联数据源", toolbar_card, FluentIcon.LINK)
        menu = RoundMenu(parent=self.btn_bind_source)
        action_excel = Action(FluentIcon.DOCUMENT, '导入本地 Excel', self)
        action_excel.triggered.connect(self._on_bind_excel_clicked)
        action_feishu = Action(FluentIcon.CLOUD, '绑定飞书云文档', self)
        action_feishu.triggered.connect(self._on_bind_feishu_clicked)
        menu.addAction(action_excel)
        menu.addAction(action_feishu)
        self.btn_bind_source.setMenu(menu)
        
        self.btn_sync_active = PrimaryPushButton("同步最新数据", toolbar_card, FluentIcon.SYNC)
        self.btn_sync_active.clicked.connect(self._on_sync_active_clicked)
        
        self.btn_unbind = PushButton("解除绑定", toolbar_card, FluentIcon.CLOSE)
        self.btn_unbind.clicked.connect(self._on_unbind_clicked)

        toolbar_layout.addWidget(self.btn_edit)
        toolbar_layout.addWidget(self.btn_delete)
        toolbar_layout.addWidget(self.btn_reload)
        toolbar_layout.addWidget(self.btn_bind_source)
        toolbar_layout.addWidget(self.btn_sync_active)
        toolbar_layout.addWidget(self.btn_unbind)
        toolbar_layout.addStretch()

        self.lbl_sync_path = CaptionLabel(toolbar_card)
        
        def _on_lbl_click(event):
            CaptionLabel.mousePressEvent(self.lbl_sync_path, event)
            self._open_sync_file_folder()
            
        self.lbl_sync_path.mousePressEvent = _on_lbl_click

        toolbar_layout.addWidget(self.lbl_sync_path)
        self._update_sync_path_label()

        # 表格和标签主容器（统一卡片背景）
        main_card = CardWidget(self)
        main_layout = QVBoxLayout(main_card)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 多表格容器（上半部分）
        self.stacked_widget = QStackedWidget(main_card)

        # 底部标签栏容器（下半部分）
        tab_container = QWidget(main_card)
        tab_layout = QHBoxLayout(tab_container)
        tab_container.setMinimumHeight(48)
        tab_layout.setContentsMargins(8, 6, 8, 6)
        tab_layout.setSpacing(0)
        
        # 多标签页导航（使用带圆角背景的 TabBar）
        self.tab_bar = TabBar(self)
        self.tab_bar.setScrollable(True)
        self.tab_bar.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
        
        # 直接占用所有空间（TabBar自带滚动和左对齐防拉伸机制）
        tab_layout.addWidget(self.tab_bar, 1)

        main_layout.addWidget(self.stacked_widget, 1)
        
        # 分割线
        from PySide6.QtWidgets import QFrame
        line = QFrame(main_card)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet("color: #e5e5e5; border-bottom: 1px solid #e5e5e5;")
        line.setFixedHeight(1)
        
        main_layout.addWidget(line)
        main_layout.addWidget(tab_container)

        root_layout.addWidget(toolbar_card)
        root_layout.addWidget(main_card, 1)
        self.content_layout.addLayout(root_layout)

        # 绑定标签切换
        self.tab_bar.currentChanged.connect(self._on_tab_changed)

        self._create_tracked_task(self._reload_all(), name="copywriting_library.initial_reload")


    def _open_sync_file_folder(self):
        import subprocess
        feishu_cfg = self._get_feishu_sync_config()
        if feishu_cfg and feishu_cfg.spreadsheet_token:
            return

        path = QSettings("WeMediaBaby", "媒小宝").value("app/copywriting_last_import_path")
        if path and os.path.exists(str(path)):
            try:
                subprocess.run(['explorer', '/select,', os.path.normpath(str(path))])
            except Exception as e:
                logger.error("打开文件夹失败: %s", e, exc_info=True)

    def _update_sync_path_label(self):
        source = QSettings("WeMediaBaby", "媒小宝").value("app/copywriting_active_source", "none")
        
        if source == "feishu":
            self.btn_bind_source.hide()
            self.btn_sync_active.show()
            self.btn_unbind.show()
            
            feishu_cfg = self._get_feishu_sync_config()
            if feishu_cfg and feishu_cfg.spreadsheet_token:
                name = feishu_cfg.spreadsheet_name or "飞书表格"
                self.lbl_sync_path.setText(f"<span style='color: #00b42a; font-size: 14px;'>●</span> 数据源：飞书文档 - {name}")
                tip = f"飞书表格：{name}\\n自动同步所有可见子表"
                if feishu_cfg.last_sync_time:
                    tip += f"\\n上次同步：{feishu_cfg.last_sync_time}"
                self.lbl_sync_path.setToolTip(tip)
                self.lbl_sync_path.setStyleSheet("")
                self.lbl_sync_path.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.lbl_sync_path.setText("<span style='color: #f53f3f; font-size: 14px;'>●</span> 数据源：飞书文档 (配置已丢失或异常)")
                self.lbl_sync_path.setToolTip("无法读取飞书绑定信息，请尝试解除绑定后重新关联。")
                self.lbl_sync_path.setStyleSheet("")
                self.lbl_sync_path.setCursor(Qt.CursorShape.PointingHandCursor)
            return
            
        elif source == "excel":
            self.btn_bind_source.hide()
            self.btn_sync_active.show()
            self.btn_unbind.show()
            
            path = QSettings("WeMediaBaby", "媒小宝").value("app/copywriting_last_import_path")
            if path and os.path.exists(str(path)):
                self.lbl_sync_path.setText(f"<span style='color: #00b42a; font-size: 14px;'>●</span> 数据源：本地 Excel - {os.path.basename(str(path))}")
                self.lbl_sync_path.setToolTip(str(path))
                self.lbl_sync_path.setStyleSheet("")
                self.lbl_sync_path.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                name = os.path.basename(str(path)) if path else "未知文件"
                self.lbl_sync_path.setText(f"<span style='color: #f53f3f; font-size: 14px;'>●</span> 数据源：本地 Excel - {name} (文件不存在)")
                self.lbl_sync_path.setToolTip("绑定的本地文件已被移动或删除，请重新绑定或找回文件。")
                self.lbl_sync_path.setStyleSheet("")
                self.lbl_sync_path.setCursor(Qt.CursorShape.PointingHandCursor)
            return
                
        # None 或失效情况
        self.btn_bind_source.show()
        self.btn_sync_active.hide()
        self.btn_unbind.hide()
        self.lbl_sync_path.setText("未关联数据源")
        self.lbl_sync_path.setToolTip("请先点击“关联数据源”选择数据维护通道")
        self.lbl_sync_path.setStyleSheet("color: #888888;")
        self.lbl_sync_path.setCursor(Qt.CursorShape.ArrowCursor)

    def _on_unbind_clicked(self):
        from src.ui.utils.fluent_dialogs import show_confirm
        if show_confirm(self, "确认解除绑定", "解除绑定不会删除本地已有的文案，但之后您需要重新绑定数据源才能同步更新。\\n确认解除吗？"):
            QSettings("WeMediaBaby", "媒小宝").setValue("app/copywriting_active_source", "none")
            self._update_sync_path_label()

    # ---------- 多标签页与表格管理 ----------

    def _get_active_table(self) -> Optional[RubberBandRowSelectTable]:
        cat = self._get_active_category()
        if not cat:
            return None
        return self._tables.get(cat)

    def _get_active_category(self) -> str:
        idx = self.tab_bar.currentIndex()
        if 0 <= idx < len(self._category_names):
            return self._category_names[idx]
        return "全部"

    def _setup_table_style(self, table: RubberBandRowSelectTable):
        table.setObjectName("CopywritingLibraryTable")
        table.setSelectionBehavior(table.SelectionBehavior.SelectRows)
        table.setSelectionMode(table.SelectionMode.ExtendedSelection)
        table.setEditTriggers(table.EditTrigger.NoEditTriggers)

        table.setColumnCount(len(_HEADERS))
        table.setHorizontalHeaderLabels(_HEADERS)
        table.verticalHeader().setVisible(False)
        table.doubleClicked.connect(lambda idx, t=table: self._on_table_double_clicked(idx, t))

        header = table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_NO, QHeaderView.ResizeMode.Fixed)
        header.setStretchLastSection(True)
        header.setMinimumSectionSize(52)
        table.setColumnWidth(_COL_NO,          52)
        table.setColumnWidth(_COL_WORK_ID,    120)
        table.setColumnWidth(_COL_SHORT_TITLE, 150)
        table.setColumnWidth(_COL_DESCRIPTION, 200)
        table.setColumnWidth(_COL_CONTENT,     300)

    def _populate_table(self, table: RubberBandRowSelectTable, rows: List[Dict[str, Any]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(0)
        table.setRowCount(len(rows))

        for row_idx, item in enumerate(rows):
            no_cell = QTableWidgetItem(str(row_idx + 1))
            no_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            no_cell.setData(Qt.ItemDataRole.UserRole, item)
            table.setItem(row_idx, _COL_NO, no_cell)

            work_id_cell = QTableWidgetItem(item.get("work_id") or "")
            work_id_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, _COL_WORK_ID, work_id_cell)

            short_title_cell = QTableWidgetItem(item.get("short_title") or "")
            short_title_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, _COL_SHORT_TITLE, short_title_cell)

            desc_cell = QTableWidgetItem(item.get("description") or "")
            desc_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, _COL_DESCRIPTION, desc_cell)

            content_cell = QTableWidgetItem(item.get("content") or "")
            content_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row_idx, _COL_CONTENT, content_cell)

        table.setSortingEnabled(True)

    def _get_selected_items(self) -> List[Dict[str, Any]]:
        table = self._get_active_table()
        if not table:
            return []
        seen: set = set()
        result: List[Dict[str, Any]] = []
        for sel in table.selectedItems():
            r = sel.row()
            if r in seen:
                continue
            seen.add(r)
            no_cell = table.item(r, _COL_NO)
            if no_cell:
                data = no_cell.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    result.append(data)
        return result

    def _get_single_selected_item(self) -> Optional[Dict[str, Any]]:
        items = self._get_selected_items()
        return items[0] if len(items) == 1 else None

    # ---------- 加载 ----------

    def _on_reload_clicked(self):
        self._create_tracked_task(self._reload_all(), name="copywriting_library.reload")

    async def _reload_all(self) -> None:
        """重载所有分类标签，并触发当前激活标签页的数据加载。"""
        try:
            # 1. 尝试获取所有分类
            categories = await CopywritingRepository.get_all_categories()
            if not categories:
                categories = ["全部"]

            # 2. 记住当前选中的分类，以便重建后恢复
            current_cat = self._get_active_category()

            # 3. 清理现有的 Tab 和 Table
            self.tab_bar.clear()
            while self.stacked_widget.count() > 0:
                w = self.stacked_widget.widget(0)
                self.stacked_widget.removeWidget(w)
                w.deleteLater()

            self._category_names = []
            self._tables = {}

            # 4. 为每个分类创建 Tab 和空的表格框架
            for cat in categories:
                self._category_names.append(cat)
                
                table = RubberBandRowSelectTable(self.stacked_widget)
                # 隐藏表格的默认圆角和外边框，以融入外层的 main_card
                table.setStyleSheet("QTableWidget { border: none; border-radius: 0px; }")
                self._setup_table_style(table)
                
                self.tab_bar.addTab(routeKey=cat, text=cat)
                self.stacked_widget.addWidget(table)
                self._tables[cat] = table

            # 5. 恢复选中状态，触发加载
            if current_cat in self._category_names:
                idx = self._category_names.index(current_cat)
                self.tab_bar.setCurrentIndex(idx)
            elif self._category_names:
                self.tab_bar.setCurrentIndex(0)
                
            # 强制触发一次数据加载，避免 currentIndex 未改变导致未发射 currentChanged 信号
            current_idx = self.tab_bar.currentIndex()
            if current_idx >= 0:
                self._on_tab_changed(current_idx)

        except Exception as e:
            logger.error("加载文案库列表失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content="加载文案库列表时发生异常，请稍后重试。",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    def _on_tab_changed(self, index: int):
        """选项卡切换时，重置页码并加载该选项卡的数据。"""
        if index < 0 or index >= len(self._category_names):
            return
        self.stacked_widget.setCurrentIndex(index)
        self._create_tracked_task(self._load_current_page_data(), name="load_page_data")

    async def _load_current_page_data(self):
        """根据当前分类加载所有数据并渲染到当前激活的表格。"""
        cat = self._get_active_category()
        table = self._get_active_table()
        if not table:
            return

        try:
            # 取消分页，一次性加载当前分类的所有记录
            rows = await CopywritingRepository.list_items(
                category=cat if cat != "全部" else None,
                paginate=False
            )
            
            self._populate_table(table, rows)
        except Exception as e:
            logger.error("加载文案数据失败: %s", e, exc_info=True)



    # ---------- 编辑 ----------

    def _on_edit_clicked(self):
        item = self._get_single_selected_item()
        if item is None:
            InfoBar.info(
                title="提示",
                content="请先在当前列表中选择一条文案记录再点击编辑。",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=3000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
        self._open_edit_dialog(item)

    def _on_table_double_clicked(self, index, table: RubberBandRowSelectTable):
        if not index.isValid():
            return
        no_cell = table.item(index.row(), _COL_NO)
        if no_cell:
            data = no_cell.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                self._open_edit_dialog(data)

    def _open_edit_dialog(self, item: Dict[str, Any]):
        dialog = CopywritingEditDialog(self, item_data=item)
        if not dialog.exec():
            return
        data = dialog.get_form_data()
        data["id"] = item.get("id")
        data["category"] = item.get("category") or self._get_active_category()
        self._create_tracked_task(
            self._save_copywriting(data, is_edit=True),
            name="copywriting_library.save_edit",
        )

    # ---------- 保存（新建/编辑共用）----------

    async def _save_copywriting(self, data: Dict[str, Any], is_edit: bool):
        try:
            result = await CopywritingRepository.create_or_update_by_work_id(data)
            action = "已更新" if is_edit else "已创建"
            InfoBar.success(
                title=action,
                content=f"{action}文案，作品编号：{result.get('work_id')}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=4000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            await self._reload_all()
        except Exception as e:
            logger.error("保存文案失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content=f"保存文案时发生异常：{e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    # ---------- 删除 ----------

    def _on_delete_clicked(self):
        selected = self._get_selected_items()
        if not selected:
            InfoBar.info(
                title="提示",
                content="请先选择要删除的文案记录。",
                orient=Qt.Orientation.Horizontal,
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

        self._create_tracked_task(self._delete_items(ids), name="copywriting_library.delete")

    async def _delete_items(self, ids: List[int]):
        try:
            deleted = await CopywritingRepository.delete_items(ids)
            if deleted > 0:
                InfoBar.success(
                    title="已删除",
                    content=f"成功删除 {deleted} 条文案记录。",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    duration=4000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                await self._reload_all()
            else:
                InfoBar.info(
                    title="提示",
                    content="未删除任何记录，请稍后重试。",
                    orient=Qt.Orientation.Horizontal,
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
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    # ---------- Excel 导入 ----------

    def _export_template_excel(self, save_path: str) -> bool:
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            assert ws is not None
            ws.title = "标准文案库模板"
            headers = ["作品编号", "作品标题", "作品描述", "文案内容"]
            ws.append(headers)
            example1 = [
                "A0001", "示例短标题A", "这是一个关于自媒体自动发布工具的介绍视频 #自媒体运营 #WeMediaBaby",
                "大家好，今天给大家推荐 WeMediaBaby，这是一个超好用的自媒体自动发布工具！"
            ]
            example2 = [
                "A0002", "示例短标题B", "自媒体运营干货分享 #运营干货 #工具推荐",
                "哈罗大家下午好！今天又是阳光明媚的一天，给大家分享一下我的自媒体运营日常..."
            ]
            ws.append(example1)
            ws.append(example2)
            ws.column_dimensions['A'].width = 15
            ws.column_dimensions['B'].width = 25
            ws.column_dimensions['C'].width = 50
            ws.column_dimensions['D'].width = 60
            wb.save(save_path)
            return True
        except Exception as e:
            logger.error("生成 Excel 模板失败: %s", e, exc_info=True)
            return False

    def _on_bind_excel_clicked(self):
        from src.ui.components.base_dialog import AppMessageBoxBase
        from qfluentwidgets import BodyLabel, PushButton, FluentIcon
        from PySide6.QtWidgets import QFileDialog

        dlg = AppMessageBoxBase(self, header_title="导入标准文案")
        desc = BodyLabel(
            "您可以从 Excel 模板批量导入标准文案，相同作品编号的记录将被自动覆盖更新。\\n\\n"
            "支持多 Sheet 导入，不同 Sheet 的文案将会在此页面自动按不同标签页分类展示。\\n\\n"
            "如果您是首次使用，建议先下载并填写我们的标准 Excel 模板，然后再执行导入操作。", 
            dlg
        )
        desc.setWordWrap(True)
        dlg.viewLayout.addWidget(desc)

        btn_download = PushButton("下载标准文案库模板", dlg, FluentIcon.DOWNLOAD)
        
        def _download_template():
            try:
                import openpyxl
            except ImportError:
                InfoBar.error(
                    title="环境依赖缺失",
                    content="当前环境未安装 openpyxl。请在项目目录执行：pip install openpyxl",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    duration=8000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                return

            import os
            desktop_dir = os.path.join(os.path.expanduser("~"), "Desktop")
            default_path = os.path.join(desktop_dir, "标准文案库模板.xlsx") if os.path.exists(desktop_dir) else "标准文案库模板.xlsx"

            save_path, _ = QFileDialog.getSaveFileName(self, "保存标准文案库模板", default_path, "Excel 文件 (*.xlsx)")
            if save_path:
                if self._export_template_excel(save_path):
                    InfoBar.success(
                        title="下载成功",
                        content=f"已成功保存标准文案库模板至：{save_path}",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        duration=5000,
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )
                else:
                    InfoBar.error(
                        title="下载失败",
                        content="保存模板文件时发生错误，请检查是否有权限写入该目录。",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        duration=5000,
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )

        btn_download.clicked.connect(_download_template)
        dlg.viewLayout.addWidget(btn_download)

        dlg.yesButton.setText("选择文件导入")
        dlg.cancelButton.setText("取消")

        if not dlg.exec():
            return

        file_path, _ = QFileDialog.getOpenFileName(self, "选择文案库 Excel 文件", "", "Excel 文件 (*.xlsx);;所有文件 (*.*)")
        if not file_path:
            return

        QSettings("WeMediaBaby", "媒小宝").setValue("app/copywriting_last_import_path", file_path)
        QSettings("WeMediaBaby", "媒小宝").setValue("app/copywriting_active_source", "excel")
        self._update_sync_path_label()
        self._create_tracked_task(self._import_excel(file_path), name="copywriting_library.import_excel")

    def _on_sync_active_clicked(self):
        source = QSettings("WeMediaBaby", "媒小宝").value("app/copywriting_active_source", "none")
        if source == "feishu":
            feishu_cfg = self._get_feishu_sync_config()
            if feishu_cfg and feishu_cfg.spreadsheet_token:
                name = feishu_cfg.spreadsheet_name or feishu_cfg.sheet_name or "飞书表格"
                InfoBar.info(
                    title="开始同步",
                    content=f"正在从飞书同步文案库...\\n表格：{name}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    duration=3000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                self._create_tracked_task(self._sync_from_feishu(feishu_cfg), name="copywriting_library.feishu_sync")
            else:
                InfoBar.warning(title="同步失败", content="未找到飞书配置，请重新绑定", parent=self)
        elif source == "excel":
            path = QSettings("WeMediaBaby", "媒小宝").value("app/copywriting_last_import_path")
            if path and os.path.exists(str(path)):
                InfoBar.info(
                    title="开始同步",
                    content=f"正在同步文案库...\\n文件：{os.path.basename(str(path))}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    duration=3000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                self._create_tracked_task(self._import_excel(str(path)), name="copywriting_library.import_excel_sync")
            else:
                InfoBar.warning(title="同步失败", content="未找到本地 Excel 文件，请重新关联", parent=self)

    async def _import_excel(self, file_path: str):
        try:
            from src.infrastructure.common.excel_copywriting_importer import parse_excel
        except ImportError as e:
            logger.warning("文案库 Excel 导入依赖缺失: %s", e)
            InfoBar.error(
                title="无法导入 Excel",
                content="当前环境未安装 openpyxl。",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=8000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return
            
        try:
            result = await asyncio.to_thread(parse_excel, file_path)
        except Exception as e:
            logger.error("解析文案 Excel 失败: %s", e, exc_info=True)
            InfoBar.error(
                title="导入失败",
                content=f"{e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=7000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        items = result.get("items", [])
        base_total = result.get("total", 0)
        base_errors = result.get("errors", [])
        total_sheets = result.get("total_sheets", 0)
        valid_sheets = result.get("valid_sheets", 0)

        if not items:
            msg = "导入失败：未在文件中找到任何符合规范（含“作品编号”和“作品描述”）的文案数据，请检查 Excel 是否符合模板格式。"
            if base_errors:
                msg += "\\n" + "\\n".join(base_errors[:5])
            InfoBar.warning(
                title="导入失败",
                content=msg,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=7000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        try:
            stats = await CopywritingRepository.bulk_import(items, overwrite_by_work_id=True, clear_first=True)
        except Exception as e:
            logger.error("批量导入文案失败: %s", e, exc_info=True)
            InfoBar.error(
                title="导入失败",
                content="写入数据库时发生错误，请稍后重试。",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=6000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
            return

        success = stats.get("success", 0)
        failed = stats.get("failed", 0)
        errs: List[str] = stats.get("errors") or []

        detail_lines = base_errors + errs
        
        if detail_lines or failed > 0:
            summary = (
                f"导入完成！检测到 {total_sheets} 个表格，其中 {valid_sheets} 个包含有效数据。\n"
                f"共读取 {base_total} 行，成功提取并入库 {success} 条文案，失败 {failed} 条。\n"
                f"（已开启全量镜像模式：本地旧文案已清空，多 Sheet 已自动分类）\n"
            )
            if detail_lines:
                summary += "\n【异常或跳过详情】\n"
                summary += "\n".join(detail_lines[:10])
                if len(detail_lines) > 10:
                    summary += f"\n...（还有 {len(detail_lines) - 10} 条异常详情被省略）"
            
            from src.ui.utils.fluent_dialogs import show_info
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: show_info(self, "导入完成（含异常数据）", summary))
            InfoBar.success(
                title="导入完成",
                content=f"检测到 {total_sheets} 个表格，其中 {valid_sheets} 个包含有效数据。\n已成功入库 {success} 条新数据！\n（已开启全量镜像模式：本地旧文案已清空）",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=6000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
        await self._reload_all()

    # ---------- 飞书集成 ----------

    def _get_feishu_sync_config(self):
        try:
            from src.proprietary.services.feishu.feishu_config import FeishuConfig
            return FeishuConfig.get_sync_config()
        except Exception:
            return None

    def _on_bind_feishu_clicked(self):
        from src.ui.utils.async_helper import run_async_from_ui

        async def _check_and_open():
            try:
                from src.proprietary.services.feishu.feishu_auth_service import FeishuAuthService
                auth = FeishuAuthService.get_instance()
                if not auth.is_app_configured():
                    InfoBar.warning(
                        title="飞书未配置",
                        content="请先在 config/feishu_config.json 中配置飞书应用凭证。",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        duration=5000,
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )
                    return

                if not await auth.is_authorized(verify=False):
                    await self._open_feishu_auth_dialog()
                else:
                    await self._open_feishu_sheet_picker()
            except Exception as e:
                logger.error("检查飞书授权状态失败: %s", e, exc_info=True)
                InfoBar.error(
                    title="错误",
                    content=f"检查飞书授权状态失败：{e}",
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    duration=5000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        run_async_from_ui(_check_and_open)

    async def _open_feishu_auth_dialog(self):
        try:
            from .feishu_auth_dialog import FeishuAuthDialog
            from src.ui.utils.async_helper import await_qdialog_finished

            dlg = FeishuAuthDialog(self)
            def _on_auth_success():
                dlg.accept()
                from src.ui.utils.async_helper import run_async_from_ui
                run_async_from_ui(self._open_feishu_sheet_picker)
                
            try:
                dlg.auth_success.connect(_on_auth_success)
            except Exception:
                pass

            await await_qdialog_finished(dlg)
        except Exception as e:
            logger.error("打开飞书授权对话框失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content=f"打开授权对话框失败：{e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    async def _open_feishu_sheet_picker(self):
        try:
            from .feishu_sheet_picker_dialog import FeishuSheetPickerDialog
            from src.ui.utils.async_helper import await_qdialog_finished

            dlg = FeishuSheetPickerDialog(self)
            code = await await_qdialog_finished(dlg)
            from PySide6.QtWidgets import QDialog
            if code != QDialog.DialogCode.Accepted and code != 1:
                return

            result = dlg.get_result()
            self._create_tracked_task(
                self._do_feishu_sync_with_result(result),
                name="copywriting_library.feishu_initial_sync",
            )
        except Exception as e:
            logger.error("打开飞书表格选择对话框失败: %s", e, exc_info=True)
            InfoBar.error(
                title="错误",
                content=f"打开表格选择对话框失败：{e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=5000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    async def _do_feishu_sync_with_result(self, result: dict):
        from datetime import datetime
        try:
            from src.proprietary.services.feishu.feishu_copywriting_sync import FeishuCopywritingSyncService
            from src.proprietary.services.feishu.feishu_config import FeishuConfig, FeishuCopywritingSyncConfig

            spreadsheet_token = result.get("spreadsheet_token", "")
            spreadsheet_name = result.get("spreadsheet_name", "")

            if not spreadsheet_token:
                return

            sync_service = FeishuCopywritingSyncService()
            sync_result = await sync_service.sync_from_feishu(
                spreadsheet_token=spreadsheet_token,
            )

            if sync_result.success:
                cfg = FeishuCopywritingSyncConfig(
                    spreadsheet_token=spreadsheet_token,
                    spreadsheet_name=spreadsheet_name,
                    sheet_id="",
                    sheet_name="",
                    field_mapping={},
                    last_sync_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    auto_sync_on_startup=False,
                )
                await FeishuConfig.save_sync_config(cfg)
                QSettings("WeMediaBaby", "媒小宝").setValue("app/copywriting_active_source", "feishu")
                self._update_sync_path_label()

                summary = (
                    f"同步完成！检测到 {sync_result.total_sheets} 个表格，其中 {sync_result.valid_sheets} 个包含有效数据。\n"
                    f"共读取 {sync_result.total_rows} 行，成功入库 {sync_result.inserted + sync_result.updated} 条，"
                    f"失败 {sync_result.failed} 条。\n"
                    f"（已开启全量镜像模式：本地旧文案已清空）\n"
                )
                if sync_result.errors:
                    summary += f"\n（注：有 {len(sync_result.errors)} 条异常数据已跳过，详情请见日志）"

                InfoBar.success(
                    title="飞书同步成功",
                    content=summary,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    duration=8000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
                await self._reload_all()
            else:
                InfoBar.error(
                    title="飞书同步失败",
                    content=sync_result.message,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    duration=7000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("飞书同步异常: %s", e, exc_info=True)
            InfoBar.error(
                title="同步出错",
                content=f"飞书同步过程中发生错误：{e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=7000,
                position=InfoBarPosition.TOP,
                parent=self,
            )

    async def _sync_from_feishu(self, feishu_cfg):
        from datetime import datetime
        try:
            from src.proprietary.services.feishu.feishu_copywriting_sync import FeishuCopywritingSyncService
            from src.proprietary.services.feishu.feishu_config import FeishuConfig
            
            sync_service = FeishuCopywritingSyncService()
            sync_result = await sync_service.sync_from_feishu(
                spreadsheet_token=feishu_cfg.spreadsheet_token,
            )

            if sync_result.success:
                feishu_cfg.last_sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await FeishuConfig.save_sync_config(feishu_cfg)
                self._update_sync_path_label()

                # 如果存在跳过或失败，升级为模态弹窗，强制让用户确认详情
                if sync_result.errors or sync_result.failed > 0:
                    summary = (
                        f"同步完成！检测到 {sync_result.total_sheets} 个表格，其中 {sync_result.valid_sheets} 个包含有效数据。\n"
                        f"共读取 {sync_result.total_rows} 行，提取有效数据 {sync_result.valid_rows} 行。\n"
                        f"成功入库 {sync_result.inserted + sync_result.updated} 条，"
                        f"失败 {sync_result.failed} 条。\n"
                        f"（已开启全量镜像模式：本地旧文案已清空）\n"
                    )
                    if sync_result.errors:
                        summary += f"\n【异常或跳过详情】\n"
                        summary += "\n".join(sync_result.errors[:10])
                        if len(sync_result.errors) > 10:
                            summary += f"\n...（还有 {len(sync_result.errors) - 10} 条异常详情被省略）"
                    
                    from src.ui.utils.fluent_dialogs import show_info
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: show_info(self, "同步完成（含异常数据）", summary))
                else:
                    # 如果 0 错误 0 跳过，极其丝滑，仅用轻量消息条
                    InfoBar.success(
                        title="同步完成",
                        content=f"检测到 {sync_result.total_sheets} 个表格，其中 {sync_result.valid_sheets} 个包含有效数据。\n已成功导入 {sync_result.inserted + sync_result.updated} 条新数据！",
                        orient=Qt.Orientation.Horizontal,
                        isClosable=True,
                        duration=6000,
                        position=InfoBarPosition.TOP,
                        parent=self,
                    )
                await self._reload_all()
            else:
                InfoBar.error(
                    title="同步失败",
                    content=sync_result.message,
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    duration=7000,
                    position=InfoBarPosition.TOP,
                    parent=self,
                )
        except Exception as e:
            logger.error("飞书同步异常: %s", e, exc_info=True)
            InfoBar.error(
                title="同步出错",
                content=f"同步过程中发生错误：{e}",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=7000,
                position=InfoBarPosition.TOP,
                parent=self,
            )
