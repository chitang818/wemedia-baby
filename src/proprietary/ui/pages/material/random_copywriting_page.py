"""
随机文案库页面
文件路径：src/ui/pages/material/random_copywriting_page.py
功能：支持多标签页管理的随机文案库，提供汇总展示及各分类子文案库的管理。
采用 TabBar 组件作为导航。子分类页面采用与标准文案库一致的表格结构。
"""

import asyncio
import logging
import uuid
from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, 
    QVBoxLayout, 
    QStackedWidget, 
    QHBoxLayout, 
    QHeaderView, 
    QTableWidgetItem
)

from qfluentwidgets import (
    TabBar,
    CardWidget,
    FluentIcon,
    PrimaryPushButton,
    PushButton,
    SubtitleLabel,
    BodyLabel,
    FlowLayout,
    InfoBar,
    InfoBarPosition,
    MessageBoxBase,
    LineEdit,
    TransparentToolButton,
    TabCloseButtonDisplayMode,
    IconWidget,
    CaptionLabel,
)

from src.ui.pages.base_page import BasePage
from src.ui.utils.task_tracking import TrackedTaskMixin
from src.ui.components.rubber_band_row_table import RubberBandRowSelectTable
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.infrastructure.storage.repositories.random_copywriting_repository import (
    RandomCopywritingRepository,
)
from src.ui.pages.material.copywriting_edit_dialog import CopywritingEditDialog

logger = logging.getLogger(__name__)

# 列索引常量（与标准文案库保持一致）
_COL_NO          = 0
_COL_WORK_ID     = 1
_COL_SHORT_TITLE = 2
_COL_DESCRIPTION = 3
_COL_CONTENT     = 4
_HEADERS = ["序号", "作品编号", "作品标题", "作品描述", "文案内容"]


class CategoryInputDialog(MessageBoxBase):
    """自定义分类名称输入弹窗"""

    def __init__(self, parent=None, title="创建新分类", initial_text=""):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        
        self.lineEdit = LineEdit(self)
        self.lineEdit.setPlaceholderText("例如：美妆类文案、美食类文案")
        self.lineEdit.setClearButtonEnabled(True)
        if initial_text:
            self.lineEdit.setText(initial_text)

        # 添加到内容布局
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addSpacing(16)
        self.viewLayout.addWidget(self.lineEdit)

        self.widget.setMinimumWidth(360)
        
        # 绑定回车确认
        self.lineEdit.returnPressed.connect(self.yesButton.click)


class RandomCopywritingSummaryWidget(QWidget):
    """随机文案库 - 汇总展示页面"""
    
    # 定义信号：当点击分类卡片时触发，参数为 route_key
    category_clicked = Signal(str)
    # 定义信号：当点击创建按钮时触发
    add_requested = Signal()
    # 定义信号：当点击分类卡片右上角删除按钮时触发
    delete_requested = Signal(str)
    # 定义信号：当点击分类卡片右上角编辑按钮时触发
    edit_requested = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # routeKey -> 条目数 label，用于在子库数据变化后局部刷新数字
        self._count_labels_by_route_key: Dict[str, BodyLabel] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(20)

        # 顶部说明
        header_card = CardWidget(self)
        header_layout = QVBoxLayout(header_card)
        title = SubtitleLabel("随机文案库概览", header_card)
        desc = BodyLabel("在此管理不同分类的随机文案池。任务创建时可选择对应的分类，系统将从中随机抽取文案。", header_card)
        header_layout.addWidget(title)
        header_layout.addWidget(desc)
        layout.addWidget(header_card)

        # 操作栏
        action_layout = QHBoxLayout()
        self.btn_add_group = PrimaryPushButton(FluentIcon.ADD, "创建新分类", self)
        self.btn_add_group.clicked.connect(self.add_requested.emit)
        action_layout.addWidget(self.btn_add_group)
        action_layout.addStretch()
        layout.addLayout(action_layout)

        # 统计卡片区域 (使用容器包裹 FlowLayout)
        self.cards_container = QWidget(self)
        self.cards_layout = FlowLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(16)
        
        # 默认不显示任何示例分类，由父页面动态加载或用户创建
        
        layout.addWidget(self.cards_container)
        layout.addStretch()

    def add_category_card(self, name: str, route_key: str, count: int = 0):
        """添加一个分类统计卡片"""
        card = CardWidget(self)
        card.setMinimumSize(260, 110)
        card.setMaximumWidth(320)
        card.setCursor(Qt.PointingHandCursor)
        
        # 主布局
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 16, 16, 16)
        cl.setSpacing(12)

        # 1. 顶部 Header (图标 + 标签名 + 操作按钮)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        
        # 分类图标
        icon_widget = IconWidget(FluentIcon.FOLDER, card)
        icon_widget.setFixedSize(16, 16)
        header_layout.addWidget(icon_widget)
        
        # 分类名称
        name_lbl = SubtitleLabel(name, card)
        font = name_lbl.font()
        font.setPointSize(12)
        font.setBold(True)
        name_lbl.setFont(font)
        name_lbl.setWordWrap(False)
        header_layout.addWidget(name_lbl)
        header_layout.addStretch(1)
        
        # 操作按钮
        edit_btn = TransparentToolButton(FluentIcon.EDIT, card)
        edit_btn.setToolTip("修改分类名称")
        edit_btn.setFixedSize(28, 28)
        edit_btn.setIconSize(edit_btn.iconSize() * 0.8)
        
        delete_btn = TransparentToolButton(FluentIcon.DELETE, card)
        delete_btn.setToolTip("删除此分类")
        delete_btn.setFixedSize(28, 28)
        delete_btn.setIconSize(delete_btn.iconSize() * 0.8)
        
        header_layout.addWidget(edit_btn)
        header_layout.addWidget(delete_btn)
        cl.addLayout(header_layout)
        
        # 2. 数据统计 / 描述信息
        count_lbl = CaptionLabel(f"当前池中共有 {count} 条文案", card)
        count_lbl.setStyleSheet("color: #666666;")
        cl.addWidget(count_lbl)
        
        # 填充底部空间，使内容靠上对齐
        cl.addStretch(1)

        # 按钮点击时：置位抑制标记，避免 CardWidget 的 clicked 事件再触发打开分类
        card._suppress_open_on_click = False
        def _on_delete_clicked() -> None:
            card._suppress_open_on_click = True
            self.delete_requested.emit(route_key)
            # 下一轮事件循环恢复，确保本次点击不误触发打开
            QTimer.singleShot(0, lambda: setattr(card, "_suppress_open_on_click", False))

        delete_btn.clicked.connect(_on_delete_clicked)

        def _on_edit_clicked() -> None:
            card._suppress_open_on_click = True
            self.edit_requested.emit(route_key, name)
            QTimer.singleShot(0, lambda: setattr(card, "_suppress_open_on_click", False))

        edit_btn.clicked.connect(_on_edit_clicked)

        # 保存引用：用于后续局部更新（避免整页重建 TabBar）
        self._count_labels_by_route_key[route_key] = count_lbl
        
        # 点击卡片跳转到对应标签页（使用 CardWidget 的 clicked 信号更可靠）
        def _on_card_clicked() -> None:
            if getattr(card, "_suppress_open_on_click", False):
                return
            self.category_clicked.emit(route_key)

        card.clicked.connect(_on_card_clicked)
        
        self.cards_layout.addWidget(card)

    def update_category_count(self, route_key: str, count: int) -> None:
        """仅更新指定分类的条目数显示。"""
        lbl = self._count_labels_by_route_key.get(route_key)
        if lbl is None:
            return
        try:
            lbl.setText(f"当前池中共有 {count} 条文案")
        except Exception:
            # QLabel/BodyLabel 可能在某些时序下已被 deleteLater，忽略即可
            pass

    def clear_cards(self):
        """清空所有分类卡片"""
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            # FlowLayout.takeAt 可能返回 QLayoutItem，也可能直接返回 QWidget（不同实现/版本差异）
            widget = None
            try:
                if hasattr(item, "widget"):
                    widget = item.widget()
                else:
                    widget = item
            except Exception:
                widget = None
            if widget is not None:
                widget.deleteLater()
        self._count_labels_by_route_key.clear()


class RandomCopywritingSubLibraryWidget(TrackedTaskMixin, QWidget):
    """随机文案库 - 子分类管理页面 (表格形式)"""

    def __init__(self, category_id: int, category_name: str, parent=None):
        super().__init__(parent)
        self.category_id = category_id
        self.category_name = category_name
        self._table: Optional[RubberBandRowSelectTable] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(12)

        # 顶部工具栏
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

        toolbar_layout.addWidget(self.btn_new)
        toolbar_layout.addWidget(self.btn_edit)
        toolbar_layout.addWidget(self.btn_import)
        toolbar_layout.addWidget(self.btn_delete)
        toolbar_layout.addWidget(self.btn_reload)
        toolbar_layout.addStretch()
        
        layout.addWidget(toolbar_card)

        # 表格卡片
        table_card = CardWidget(self)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self._table = RubberBandRowSelectTable(table_card)
        self._setup_table_style(self._table)
        self._table.setColumnCount(len(_HEADERS))
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.verticalHeader().setVisible(False)

        # 列宽配置
        header = self._table.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_NO, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_NO, 52)
        self._table.setColumnWidth(_COL_WORK_ID, 120)
        self._table.setColumnWidth(_COL_SHORT_TITLE, 150)
        self._table.setColumnWidth(_COL_DESCRIPTION, 200)
        self._table.setColumnWidth(_COL_CONTENT, 300)

        table_layout.addWidget(self._table)
        layout.addWidget(table_card)
        
        # 初始加载
        self._initial_reload_timer = QTimer(self)
        self._initial_reload_timer.setSingleShot(True)
        self._initial_reload_timer.timeout.connect(
            lambda: self._create_tracked_task(
                self._reload(),
                name="random_copywriting.sub_library.initial_reload",
            )
        )
        self._initial_reload_timer.start(100)

    def _setup_table_style(self, table):
        """参考 BasePage 中的表格样式设置"""
        table.setWordWrap(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(RubberBandRowSelectTable.SelectionBehavior.SelectRows)
        table.setEditTriggers(RubberBandRowSelectTable.EditTrigger.NoEditTriggers)
        header = table.horizontalHeader()
        if header:
            header.setStretchLastSection(True)

    async def _reload(self):
        """重新加载当前分类的文案数据"""
        try:
            rows = await RandomCopywritingRepository.list_items_by_category(self.category_id)
            self._populate_table(rows)
        except Exception as e:
            logger.error(f"加载随机文案库分类「{self.category_name}」失败: {e}", exc_info=True)

    async def _notify_summary_count_changed(self) -> None:
        """通知汇总页刷新当前分类的条目数（避免数字长期不更新）。"""
        try:
            p = self.parent()
            while p is not None:
                if hasattr(p, "_refresh_summary_count_for_category"):
                    await p._refresh_summary_count_for_category(self.category_id)
                    return
                p = p.parent()
        except Exception as e:
            logger.debug("刷新汇总页条目数失败: %s", e)

    def _populate_table(self, rows: List[Dict[str, Any]]):
        """渲染表格"""
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._table.setRowCount(len(rows))

        for row_idx, item in enumerate(rows):
            no_cell = QTableWidgetItem(str(row_idx + 1))
            no_cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            no_cell.setData(Qt.ItemDataRole.UserRole, item)
            self._table.setItem(row_idx, _COL_NO, no_cell)

            for col, key in [
                (_COL_WORK_ID, "work_id"),
                (_COL_SHORT_TITLE, "short_title"),
                (_COL_DESCRIPTION, "description"),
                (_COL_CONTENT, "content")
            ]:
                cell = QTableWidgetItem(str(item.get(key) or ""))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                self._table.setItem(row_idx, col, cell)

        self._table.setSortingEnabled(True)

    def _get_selected_items(self) -> List[Dict[str, Any]]:
        seen = set()
        result = []
        for sel in self._table.selectedItems():
            r = sel.row()
            if r in seen: continue
            seen.add(r)
            no_cell = self._table.item(r, _COL_NO)
            if no_cell:
                data = no_cell.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict): result.append(data)
        return result

    def _on_reload_clicked(self):
        self._create_tracked_task(
            self._reload_and_sync_summary(),
            name="random_copywriting.sub_library.reload",
        )

    async def _reload_and_sync_summary(self) -> None:
        """刷新当前表格并同步更新汇总页条目数。"""
        await self._reload()
        await self._notify_summary_count_changed()

    def _on_new_clicked(self):
        dialog = CopywritingEditDialog(self, item_data=None, strict_work_id=False)
        if dialog.exec():
            data = dialog.get_form_data()
            self._create_tracked_task(
                self._save_item(data),
                name="random_copywriting.sub_library.save_new",
            )

    def _on_edit_clicked(self):
        items = self._get_selected_items()
        if len(items) != 1:
            InfoBar.info("提示", "请选择一条记录进行编辑", parent=self.window())
            return
        item = items[0]
        dialog = CopywritingEditDialog(self, item_data=item, strict_work_id=False)
        if dialog.exec():
            data = dialog.get_form_data()
            data["id"] = item["id"]
            self._create_tracked_task(
                self._save_item(data),
                name="random_copywriting.sub_library.save_edit",
            )

    async def _save_item(self, data: Dict[str, Any]):
        try:
            await RandomCopywritingRepository.create_or_update_item(self.category_id, data)
            InfoBar.success("完成", "文案已保存", parent=self.window())
            await self._reload()
            await self._notify_summary_count_changed()
        except Exception as e:
            InfoBar.error("错误", f"保存失败: {e}", parent=self.window())

    def _on_delete_clicked(self):
        items = self._get_selected_items()
        if not items: return
        ids = [it["id"] for it in items]
        
        from src.ui.utils.fluent_dialogs import show_confirm
        if not show_confirm(self.window(), "确认删除", f"确定删除选中的 {len(ids)} 条记录吗？"):
            return
            
        self._create_tracked_task(
            self._delete_items(ids),
            name="random_copywriting.sub_library.delete",
        )

    async def _delete_items(self, ids: List[int]):
        try:
            await RandomCopywritingRepository.delete_items(ids)
            InfoBar.success("已删除", f"成功删除 {len(ids)} 条文案", parent=self.window())
            await self._reload()
            await self._notify_summary_count_changed()
        except Exception as e:
            InfoBar.error("错误", f"删除失败: {e}", parent=self.window())

    def _on_import_clicked(self):
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "选择文案库 Excel", "", "Excel 文件 (*.xlsx)")
        if not file_path: return
        self._create_tracked_task(
            self._import_excel(file_path),
            name="random_copywriting.sub_library.import_excel",
        )

    async def _import_excel(self, file_path: str):
        try:
            from src.infrastructure.common.excel_copywriting_importer import parse_excel
            result = await asyncio.get_event_loop().run_in_executor(None, parse_excel, file_path, False)
            items = result.get("items") or []
            if not items:
                InfoBar.warning("提示", "未解析到有效数据", parent=self.window())
                return
            
            stats = await RandomCopywritingRepository.bulk_import(self.category_id, items)
            InfoBar.success("导入完成", f"成功 {stats['success']} 条，失败 {stats['failed']} 条", parent=self.window())
            await self._reload()
            await self._notify_summary_count_changed()
        except Exception as e:
            InfoBar.error("错误", f"导入失败: {e}", parent=self.window())


class RandomCopywritingPage(TrackedTaskMixin, BasePage):
    """随机文案库主页面：采用 TabBar 导航方式"""

    _lazy_content = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("随机文案库", parent)
        # 记录数据库中已存在的分类名称（用于“创建分类”时去重校验）
        self._category_names = set()
        # route_key -> {cat_id, name}
        self._category_meta_by_route_key: Dict[str, Dict[str, Any]] = {}
        # 记录 route_key 到 QWidget 的映射，避免索引错乱导致切换空白
        self._route_to_widget: Dict[str, QWidget] = {}

    def _setup_content(self):
        """构建页面内容"""
        # 创建 TabBar
        self.tab_bar = TabBar(self)
        self.tab_bar.setMovable(True)
        self.tab_bar.setTabMaximumWidth(200)
        
        # 创建 StackedWidget
        self.stacked_widget = QStackedWidget(self)
        
        # 1. 汇总页面 (固定第一个，不可关闭)
        self.summary_widget = RandomCopywritingSummaryWidget(self)
        self.summary_widget.category_clicked.connect(self._on_summary_category_clicked)
        self.summary_widget.add_requested.connect(self._on_add_new_category_requested)
        self.summary_widget.delete_requested.connect(
            lambda route_key: self._create_tracked_task(
                self._on_category_delete_requested(route_key),
                name="random_copywriting.category_delete",
            )
        )
        self.summary_widget.edit_requested.connect(self._on_category_edit_requested)
        
        self._add_tab(self.summary_widget, "summary", "汇总页", FluentIcon.HOME, can_close=False)
        
        # 默认不初始化示例分类，由汇总页按钮触发添加

        # 布局
        self.content_layout.addWidget(self.tab_bar)
        self.content_layout.addWidget(self.stacked_widget, 1)

        # 默认选中汇总页
        self.tab_bar.setCurrentIndex(0)
        self.stacked_widget.setCurrentIndex(0)
        
        # 信号绑定
        self.tab_bar.currentChanged.connect(self.stacked_widget.setCurrentIndex)
        self.tab_bar.tabCloseRequested.connect(self._on_tab_close_requested)

        # 异步加载所有历史分类
        self._schedule_base_page_timer(
            "random_copywriting.reload_categories",
            100,
            lambda: self._create_tracked_task(
                self._reload_categories(),
                name="random_copywriting.reload_categories",
            ),
        )

    async def _reload_categories(self):
        """从数据库恢复已有的随机库分类"""
        try:
            categories = await RandomCopywritingRepository.list_categories()
            # 懒加载模式：只重建汇总页的分类卡片；把已打开的分类标签页清掉，只保留汇总页
            self.summary_widget.clear_cards()
            self._category_names.clear()
            self._category_meta_by_route_key.clear()

            # 移除除汇总页（index=0）以外的所有分类 Tab（以及对应 stacked widget）
            for i in range(self.tab_bar.count() - 1, 0, -1):
                try:
                    widget = self.stacked_widget.widget(i)
                    self.tab_bar.removeTab(i)
                    if widget is not None:
                        self.stacked_widget.removeWidget(widget)
                        widget.deleteLater()
                except Exception as e:
                    logger.debug("移除分类 Tab 失败: index=%s err=%s", i, e)

            # 清理映射字典，只保留汇总页
            if hasattr(self, 'summary_widget'):
                self._route_to_widget = {"summary": self.summary_widget}

            # 切回汇总页（避免当前 index 指向已被移除的 Tab）
            self.tab_bar.setCurrentIndex(0)
            self.stacked_widget.setCurrentIndex(0)

            # 仅创建汇总卡片（条目数来自库里统计）
            for cat in categories:
                name = cat["name"]
                cat_id = cat["id"]
                route_key = f"cat_{cat_id}"

                self._category_names.add(name)
                self._category_meta_by_route_key[route_key] = {
                    "cat_id": cat_id,
                    "name": name,
                }

                item_count = await RandomCopywritingRepository.count_items(cat_id)
                self.summary_widget.add_category_card(name, route_key, count=item_count)
        except Exception as e:
            logger.error(f"恢复随机文案库分类失败: {e}", exc_info=True)

    async def _refresh_summary_count_for_category(self, category_id: int) -> None:
        """子库数据变化后，局部刷新汇总页对应分类的条目数。"""
        try:
            route_key = f"cat_{category_id}"
            item_count = await RandomCopywritingRepository.count_items(category_id)
            self.summary_widget.update_category_count(route_key, item_count)
        except Exception as e:
            logger.debug("刷新汇总页条目数失败: %s", e)

    def _on_summary_category_clicked(self, route_key: str):
        """点击汇总页卡片：打开/切换到对应分类标签页并聚焦（懒加载）。"""
        logger.info(
            "随机文案库：点击汇总卡片 route_key=%s", route_key
        )
        
        # 判断是否已经创建了对应的 widget
        if route_key in self._route_to_widget:
            # 已打开：通过确定的 widget 对象来切换底层 QStackedWidget
            widget = self._route_to_widget[route_key]
            self.stacked_widget.setCurrentWidget(widget)
            try:
                tab = self.tab_bar.tab(route_key)
                if tab and hasattr(self.tab_bar, 'items'):
                    index = self.tab_bar.items.index(tab)
                    self.tab_bar.setCurrentIndex(index)
            except Exception as e:
                logger.debug("切换 TabBar 焦点失败: %s", e)
            return

        # 未打开：懒加载创建分类 Tab
        meta = self._category_meta_by_route_key.get(route_key)
        logger.info(
            "随机文案库：meta 是否存在 route_key=%s meta=%s",
            route_key,
            bool(meta),
        )
        if not meta:
            return

        cat_id = int(meta["cat_id"])
        name = str(meta["name"])

        # 创建子库管理 Widget并挂载到 TabBar
        sub_lib = RandomCopywritingSubLibraryWidget(cat_id, name, self)
        self._add_tab(sub_lib, route_key, name, FluentIcon.TILES)

        # 强制切换底层 QStackedWidget 以防止空白
        self.stacked_widget.setCurrentWidget(sub_lib)

        # 高亮上方 TabBar 上的对应标签（移除旧的会导致崩溃的 tabItem 代码）
        try:
            tab = self.tab_bar.tab(route_key)
            if tab and hasattr(self.tab_bar, 'items'):
                index = self.tab_bar.items.index(tab)
                self.tab_bar.setCurrentIndex(index)
        except Exception as e:
            logger.debug("聚焦新 TabBar 失败: %s", e)

    def _on_add_new_category_requested(self):
        """处理新建分类请求"""
        dialog = CategoryInputDialog(parent=self.window(), title="创建新分类")
        
        if dialog.exec():
            name = dialog.lineEdit.text().strip()
            if not name:
                return
            
            if name in self._category_names:
                InfoBar.warning(
                    title="名称已存在",
                    content=f"分类「{name}」已存在，请使用其他名称。",
                    parent=self.window(),
                    duration=3000
                )
                return
            
            self._create_tracked_task(
                self._add_category_to_db(name),
                name="random_copywriting.category_add",
            )

    def _on_category_edit_requested(self, route_key: str, old_name: str):
        """处理修改分类名称请求"""
        dialog = CategoryInputDialog(parent=self.window(), title="修改分类名称", initial_text=old_name)
        
        if dialog.exec():
            new_name = dialog.lineEdit.text().strip()
            if not new_name or new_name == old_name:
                return
            
            if new_name in self._category_names:
                InfoBar.warning(
                    title="名称已存在",
                    content=f"分类「{new_name}」已存在，请使用其他名称。",
                    parent=self.window(),
                    duration=3000
                )
                return
            
            self._create_tracked_task(
                self._update_category_name(route_key, old_name, new_name),
                name="random_copywriting.category_rename",
            )

    async def _update_category_name(self, route_key: str, old_name: str, new_name: str):
        """将新分类名称保存到数据库并同步到 UI"""
        meta = self._category_meta_by_route_key.get(route_key)
        if not meta:
            return
            
        cat_id = int(meta["cat_id"])
        try:
            await RandomCopywritingRepository.update_category(cat_id, new_name)
            
            # 更新内存数据
            if old_name in self._category_names:
                self._category_names.remove(old_name)
            self._category_names.add(new_name)
            meta["name"] = new_name
            
            InfoBar.success("修改成功", f"分类名称已更新为「{new_name}」", parent=self.window())
            
            # 刷新汇总页内容
            await self._reload_categories()
            
            # 如果对应 Tab 已打开，同时修改 Tab 名称
            try:
                tab_item = self.tab_bar.tab(route_key)
                if tab_item:
                    tab_item.setText(new_name)
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"修改分类名称失败: {e}", exc_info=True)
            InfoBar.error("错误", f"修改分类名称失败: {e}", parent=self.window())

    async def _on_category_delete_requested(self, route_key: str) -> None:
        """汇总页删除按钮：删除数据库里的分类及其所有条目，然后刷新汇总。"""
        logger.info(
            "随机文案库：点击删除按钮 route_key=%s", route_key
        )
        meta = self._category_meta_by_route_key.get(route_key)
        if not meta:
            return

        from src.ui.utils.fluent_dialogs import show_confirm

        cat_id = int(meta["cat_id"])
        name = str(meta["name"])

        if not show_confirm(
            self.window(),
            "确认删除分类",
            f"确定要删除分类「{name}」吗？这会同步删除该分类下的所有文案条目。",
        ):
            return

        try:
            await RandomCopywritingRepository.delete_category(cat_id)
            InfoBar.success("已删除", f"分类「{name}」及相关文案已清理", parent=self.window())
            await self._reload_categories()
        except Exception as e:
            logger.error(f"删除分类失败: {e}", exc_info=True)
            InfoBar.error("错误", f"删除分类失败: {e}", parent=self.window())

    async def _add_category_to_db(self, name: str):
        """将新分类保存到数据库并同步到 UI"""
        try:
            category = await RandomCopywritingRepository.create_category(name)
            self._create_category_library(name, cat_id=category["id"])
        except Exception as e:
            logger.error(f"创建分类失败: {e}", exc_info=True)
            InfoBar.error("错误", f"创建分类失败: {e}", parent=self.window())

    def _create_category_library(
        self, name: str, cat_id: int, count: int = 0, is_initial: bool = False
    ):
        """执行分类 UI 创建：添加 Tab 和汇总卡片"""
        route_key = f"cat_{cat_id}"
        
        # 1. 创建子库管理 Widget
        sub_lib = RandomCopywritingSubLibraryWidget(cat_id, name, self)
        
        # 2. 添加到 TabBar 和 StackedWidget
        self._add_tab(sub_lib, route_key, name, FluentIcon.TILES)
        
        # 3. 在汇总页添加卡片
        self.summary_widget.add_category_card(name, route_key, count=count)
        self._category_names.add(name)
        
        # 记录分类 meta，确保后续再次点击该卡片时能正确获取其分类信息
        self._category_meta_by_route_key[route_key] = {
            "cat_id": cat_id,
            "name": name,
        }
        
        # 4. 非初始化加载时，自动切换到新创建的页面
        if not is_initial:
            self.stacked_widget.setCurrentWidget(sub_lib)
            try:
                tab = self.tab_bar.tab(route_key)
                if tab and hasattr(self.tab_bar, 'items'):
                    index = self.tab_bar.items.index(tab)
                    self.tab_bar.setCurrentIndex(index)
            except Exception as e:
                logger.debug("聚焦新分类 TabBar 失败: %s", e)
                
            InfoBar.success(
                title="创建成功",
                content=f"已成功创建随机文案库分类：{name}",
                parent=self.window(),
                duration=3000
            )

    def _add_tab(self, widget: QWidget, route_key: str, text: str, icon: FluentIcon, can_close: bool = True):
        """添加标签页"""
        # 记录路由映射
        self._route_to_widget[route_key] = widget
        
        index = self.stacked_widget.addWidget(widget)
        tab_item = self.tab_bar.addTab(
            routeKey=route_key,
            text=text,
            icon=icon,
            onClick=None
        )
        if not can_close and tab_item is not None:
            # 概念：can_close=False 表示此 Tab 不允许关闭
            try:
                tab_item.setCloseButtonDisplayMode(TabCloseButtonDisplayMode.NEVER)
            except Exception:
                pass

    def _on_tab_close_requested(self, index: int):
        if index == 0:
            return

        # 获取对应的 route_key，用于清理映射
        route_key = None
        try:
            # 尝试通过 items 获取 routeKey
            if hasattr(self.tab_bar, 'items') and index < len(self.tab_bar.items):
                route_key = getattr(self.tab_bar.items[index], 'routeKey', lambda: None)()
        except Exception:
            pass

        # 仅关闭 UI 标签页：不删除数据库里的分类与条目
        try:
            widget = self.stacked_widget.widget(index)
        except Exception:
            widget = None
            
        if route_key and route_key in self._route_to_widget:
            del self._route_to_widget[route_key]

        try:
            self.tab_bar.removeTab(index)
        except Exception:
            # tabBar 移除失败时仍尽量移除 stacked widget，避免 UI 残留
            pass

        if widget is not None:
            try:
                self.stacked_widget.removeWidget(widget)
            except Exception:
                pass
            widget.deleteLater()

        # 关闭后聚焦回汇总页
        try:
            if self.tab_bar.count() > 0:
                self.tab_bar.setCurrentIndex(0)
                self.stacked_widget.setCurrentIndex(0)
        except Exception:
            pass

    async def _delete_category_from_db(self, index: int, cat_id: int, name: str):
        try:
            await RandomCopywritingRepository.delete_category(cat_id)
            
            # UI 移除
            widget = self.stacked_widget.widget(index)
            self.tab_bar.removeTab(index)
            self.stacked_widget.removeWidget(widget)
            widget.deleteLater()
            
            route_key = f"cat_{cat_id}"
            if route_key in self._route_to_widget:
                del self._route_to_widget[route_key]
            
            if name in self._category_names:
                self._category_names.remove(name)
            
            # 简单起见，重新刷一下汇总页卡片（最保险）
            await self._reload_categories()
            
            InfoBar.success("已删除", f"分类「{name}」及相关文案已清理", parent=self.window())
        except Exception as e:
            logger.error(f"删除分类失败: {e}", exc_info=True)
            InfoBar.error("错误", f"删除分类失败: {e}", parent=self.window())
