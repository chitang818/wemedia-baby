"""
任务回收站页面
文件路径：src/ui/pages/publish/publish_recycle_bin_page.py
功能：展示软删除的发布任务，支持恢复或彻底删除；表格右键可查看、打开文件、打开所在文件夹。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QTableWidgetItem,
    QVBoxLayout,
)

from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    FluentIcon,
    InfoBar,
    PrimaryPushButton,
    PushButton,
)

from ..base_page import BasePage
from src.ui.components.rubber_band_row_table import RubberBandRowSelectTable
from src.utils.date_utils import format_schedule_time_st_str
from src.ui.pages.publish.poi_info_display import format_poi_table_cell_display
from src.ui.pages.publish.task_field_display import (
    TASK_FIELD_EMPTY_DISPLAY,
    format_cart_info_table_cell,
    task_field_str_or_dash,
)

from .publish_records_page import (
    PublishRecordsPage,
    _TableCellCenterHost,
    _record_media_folder_cell,
    _record_task_type_label,
    notify_publish_list_and_records_refresh,
    open_record_media_folder,
    open_record_primary_media_file,
)

logger = logging.getLogger(__name__)

FLUENT_WIDGETS_AVAILABLE = True


def _recycle_source_label(status: str) -> str:
    if status == "deleted_success":
        return "已发布"
    return "待发布"


def _recycle_status_display(status: str) -> str:
    if status == "deleted_pending":
        return "🗑️ 回收（原待发布）"
    if status == "deleted_success":
        return "🗑️ 回收（原已发布）"
    s = (status or "").strip()
    return s if s else TASK_FIELD_EMPTY_DISPLAY


class PublishRecycleBinPage(BasePage):
    """任务回收站：deleted_pending / deleted_success 记录。"""

    _lazy_content = True

    def __init__(self, parent: Optional[Any] = None):
        super().__init__("任务回收站", parent)
        from src.services.auth import CurrentUserService

        self._current_user_svc = CurrentUserService()
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        self.deleted_records: List[Dict[str, Any]] = []
        self._data_stale = True
        self._load_generation = 0
        self._ctx_menu = None
        self._ctx_view = None
        self._ctx_open_file = None
        self._ctx_open_folder = None
        self._ctx_restore = None
        self._ctx_delete = None

    def mark_data_stale(self) -> None:
        self._data_stale = True

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        if self._data_stale and hasattr(self, "records_table"):
            self._load_deleted_records()

    def _ensure_content(self) -> None:
        first_init = not self._content_initialized
        super()._ensure_content()
        if not first_init:
            return
        if hasattr(self, "records_table"):
            if self.deleted_records:
                self._refresh_table()
            elif self._data_stale:
                self._load_deleted_records()

    def _setup_content(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        filter_card = CardWidget(self)
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(10)

        btn_restore = PrimaryPushButton(FluentIcon.SYNC, "恢复", filter_card)
        btn_restore.clicked.connect(self._on_restore_selected)
        filter_layout.addWidget(btn_restore)

        btn_delete = PushButton(FluentIcon.DELETE, "永久删除", filter_card)
        btn_delete.clicked.connect(self._on_permanent_delete_selected)
        filter_layout.addWidget(btn_delete)

        btn_empty = PushButton(FluentIcon.CLEAR_SELECTION, "清空回收站", filter_card)
        btn_empty.clicked.connect(self._on_empty_recycle_bin)
        filter_layout.addWidget(btn_empty)

        filter_layout.addWidget(BodyLabel("提示：Delete 键可永久删除选中项", filter_card))
        filter_layout.addStretch(1)
        layout.addWidget(filter_card)

        table_container = CardWidget(self)
        table_layout = QVBoxLayout(table_container)
        table_layout.setContentsMargins(0, 0, 0, 0)

        self.records_table = RubberBandRowSelectTable(table_container)
        self.records_table.setObjectName("PublishRecycleBinTable")
        self.records_table.setWordWrap(False)
        self.records_table.setSelectionBehavior(
            self.records_table.SelectionBehavior.SelectRows
        )
        self.records_table.setSelectionMode(self.records_table.SelectionMode.ExtendedSelection)
        self.records_table.setEditTriggers(self.records_table.EditTrigger.NoEditTriggers)

        self.records_table.setColumnCount(19)
        self.records_table.setHorizontalHeaderLabels(
            [
                "创建时间",
                "类型",
                "平台",
                "账号组",
                "任务源",
                "平台昵称",
                "文件/文件夹",
                "封面",
                "作品标题",
                "作品描述",
                "发布时间",
                "声明原创",
                "购物车",
                "团购",
                "位置",
                "状态",
                "文件位置",
                "来源",
                "操作",
            ]
        )

        _rh = self.records_table.horizontalHeader()
        for _c in range(19):
            _rh.setSectionResizeMode(_c, QHeaderView.ResizeMode.Interactive)
        _rh.setSectionResizeMode(18, QHeaderView.ResizeMode.Fixed)
        _rh.setMinimumSectionSize(52)
        _rh.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

        self.records_table.setColumnWidth(0, 140)   # 创建时间
        self.records_table.setColumnWidth(1, 52)    # 类型
        self.records_table.setColumnWidth(2, 72)    # 平台
        self.records_table.setColumnWidth(3, 88)    # 账号组
        self.records_table.setColumnWidth(4, 72)    # 任务源
        self.records_table.setColumnWidth(5, 120)   # 平台昵称
        self.records_table.setColumnWidth(6, 140)   # 文件
        self.records_table.setColumnWidth(7, 65)    # 封面
        self.records_table.setColumnWidth(8, 100)   # 作品标题
        self.records_table.setColumnWidth(9, 140)   # 作品描述
        self.records_table.setColumnWidth(10, 120)  # 发布时间
        self.records_table.setColumnWidth(11, 70)   # 声明原创
        self.records_table.setColumnWidth(12, 100)  # 购物车    短标题/✅/—
        self.records_table.setColumnWidth(13, 55)   # 团购      ✅/—
        self.records_table.setColumnWidth(14, 88)   # 位置
        self.records_table.setColumnWidth(15, 120)  # 状态
        self.records_table.setColumnWidth(16, 200)  # 文件位置
        self.records_table.setColumnWidth(17, 72)   # 来源
        self.records_table.setColumnWidth(18, 76)   # 操作
        self.records_table.verticalHeader().setDefaultSectionSize(42)

        self.records_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.records_table.customContextMenuRequested.connect(self._on_context_menu)
        self.records_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.records_table.installEventFilter(self)

        table_layout.addWidget(self.records_table)
        layout.addWidget(table_container)
        self.content_layout.addLayout(layout)

    def eventFilter(self, obj, event) -> bool:
        if (
            obj is getattr(self, "records_table", None)
            and event.type() == QEvent.Type.KeyPress
            and isinstance(event, QKeyEvent)
            and event.key() == Qt.Key.Key_Delete
        ):
            self._on_permanent_delete_selected()
            return True
        return super().eventFilter(obj, event)

    def _load_deleted_records(self) -> None:
        from src.domain.repositories.publish_record_repository_async import (
            PublishRecordRepositoryAsync,
        )
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.ui.utils.async_helper import run_async_task

        sl = ServiceLocator()
        if not sl.is_registered(PublishRecordRepositoryAsync):
            logger.warning("PublishRecordRepositoryAsync 未注册")
            return
        repo = sl.get(PublishRecordRepositoryAsync)
        self._load_generation += 1
        gen = self._load_generation

        async def load_async():
            # 先自动清理超过 30 天的回收站记录
            try:
                purged = await repo.purge_deleted_older_than(days=30)
            except Exception as _pe:
                logger.debug("回收站自动清理异常（不影响加载）: %s", _pe)
                purged = 0
            records = await repo.find_deleted_records(user_id=None, limit=5000)
            return records, purged

        def on_done(task):
            if gen != self._load_generation:
                return
            try:
                records, purged = task.result()
                self._on_deleted_loaded(records)
                if purged > 0:
                    InfoBar.info(
                        "自动清理",
                        f"已自动删除 {purged} 条超过 30 天的回收站记录",
                        parent=self,
                        duration=4000,
                    )
            except Exception as e:
                logger.error("加载回收站失败: %s", e, exc_info=True)
                self._on_deleted_loaded([])

        t = run_async_task(load_async)
        t.add_done_callback(on_done)

    def _on_deleted_loaded(self, records: List[Dict[str, Any]]) -> None:
        self.deleted_records = records or []
        self._data_stale = False
        if len(self.deleted_records) > 1000 and not getattr(self, "_over_limit_warned", False):
            self._over_limit_warned = True
            InfoBar.warning(
                "回收站记录较多",
                f"回收站内有 {len(self.deleted_records)} 条记录，建议点击「清空回收站」释放空间。",
                parent=self,
                duration=6000,
            )
        if hasattr(self, "records_table"):
            self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.records_table
        table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        table.blockSignals(True)
        table.setRowCount(0)
        rows = self.deleted_records
        table.setRowCount(len(rows))

        for row, r in enumerate(rows):
            created_at = r.get("created_at")
            if hasattr(created_at, "strftime"):
                created_time_display = created_at.strftime("%Y-%m-%d %H:%M:%S")
            else:
                created_time_display = (
                    str(created_at).replace("T", " ")[:19] if created_at else "—"
                )
            item_created = QTableWidgetItem(created_time_display)
            item_created.setData(Qt.UserRole, r.get("id"))
            table.setItem(row, 0, item_created)

            table.setItem(row, 1, QTableWidgetItem(_record_task_type_label(r)))

            from src.utils.platform_names import get_platform_display_name

            p_display = task_field_str_or_dash(
                get_platform_display_name(r.get("platform", "") or "")
            )
            table.setItem(row, 2, QTableWidgetItem(p_display))

            grp = (r.get("account_group_name") or "").strip()
            table.setItem(row, 3, QTableWidgetItem(grp or TASK_FIELD_EMPTY_DISPLAY))

            # col 4: 任务源
            _ts = r.get("task_source") or ""
            if _ts == "group":
                _ts_display = "账号组"
            elif _ts == "account":
                _ts_display = "账号"
            else:
                _ts_display = TASK_FIELD_EMPTY_DISPLAY
            table.setItem(row, 4, QTableWidgetItem(_ts_display))

            table.setItem(
                row, 5, QTableWidgetItem(task_field_str_or_dash(r.get("platform_username")))
            )

            _fp_bin = r.get("file_path", "") or ""
            _folder_bin = next(
                (p.strip()[len("__FOLDER__:"):] for p in _fp_bin.split(",")
                 if p.strip().startswith("__FOLDER__:")),
                None,
            )
            if _folder_bin:
                fname = os.path.basename(_folder_bin.rstrip("/\\")) or os.path.basename(_folder_bin)
            else:
                fname = os.path.basename(_fp_bin.split(",")[0].strip()) if _fp_bin else ""
            table.setItem(row, 6, QTableWidgetItem(task_field_str_or_dash(fname)))

            cover_path = r.get("cover_path", "")
            cover_text = "本地封面" if cover_path and os.path.exists(cover_path) else "首帧封面"
            table.setItem(row, 7, QTableWidgetItem(cover_text))

            table.setItem(
                row, 8, QTableWidgetItem(task_field_str_or_dash(r.get("title")))
            )

            table.setItem(
                row, 9, QTableWidgetItem(task_field_str_or_dash(r.get("description")))
            )

            scheduled_time = r.get("scheduled_publish_time")
            time_display = format_schedule_time_st_str(scheduled_time) or "立即发布"
            table.setItem(row, 10, QTableWidgetItem(time_display))

            platform_id = (r.get("platform") or "").strip()
            try:
                import json

                ps_raw = r.get("privacy_settings") or "{}"
                ps = json.loads(ps_raw)
                is_original = (
                    bool(ps.get("is_original", False)) if platform_id == "wechat_video" else False
                )
            except Exception:
                is_original = False
            original_display = "✅ 原创" if is_original else TASK_FIELD_EMPTY_DISPLAY
            table.setItem(row, 11, QTableWidgetItem(original_display))

            cart_info = (r.get("cart_info") or "").strip()
            table.setItem(
                row, 12, QTableWidgetItem(format_cart_info_table_cell(cart_info))
            )

            anchor_info = (r.get("anchor_info") or "").strip()
            table.setItem(
                row, 13, QTableWidgetItem("✅" if anchor_info else TASK_FIELD_EMPTY_DISPLAY)
            )

            poi_display = format_poi_table_cell_display(
                r.get("poi_info"),
                platform=platform_id,
                wechat_empty_location_open_picker=r.get(
                    "wechat_empty_location_open_picker"
                ),
            )
            table.setItem(row, 14, QTableWidgetItem(poi_display))

            st = (r.get("status") or "").strip()
            table.setItem(row, 15, QTableWidgetItem(_recycle_status_display(st)))

            folder_text, folder_tip = _record_media_folder_cell(r)
            item_folder = QTableWidgetItem(folder_text)
            if folder_tip:
                item_folder.setToolTip(folder_tip)
            table.setItem(row, 16, item_folder)

            table.setItem(row, 17, QTableWidgetItem(_recycle_source_label(st)))

            btn_view = PushButton("查看", None)
            btn_view.setFixedSize(56, 30)
            btn_view.clicked.connect(lambda checked, rec=r: self._on_view_detail(rec))
            table.setCellWidget(row, 18, _TableCellCenterHost(btn_view, table, row, 18))

            _cell_center = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            for col in range(19):
                item = table.item(row, col)
                if item:
                    if col == 16:  # 文件位置列左对齐
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                        )
                    else:
                        item.setTextAlignment(_cell_center)

        table.blockSignals(False)
        table.setSortingEnabled(True)
        table.setUpdatesEnabled(True)

    def _selected_record_ids(self) -> List[int]:
        if not hasattr(self, "records_table"):
            return []
        selected_rows = self.records_table.selectionModel().selectedRows()
        ids: List[int] = []
        for index in selected_rows:
            item = self.records_table.item(index.row(), 0)
            if not item:
                continue
            try:
                rid = item.data(Qt.UserRole)
                if rid is not None:
                    ids.append(int(rid))
            except (ValueError, TypeError):
                pass
        return ids

    def _on_restore_selected(self) -> None:
        ids = self._selected_record_ids()
        if not ids:
            InfoBar.warning("未选择", "请先选择要恢复的任务", parent=self)
            return
        from src.ui.utils.fluent_dialogs import show_confirm

        if not show_confirm(
            self.window(),
            "确认恢复",
            f"将选中的 {len(ids)} 条任务恢复到「待发布」或「已发布」列表（按原来源）。",
        ):
            return

        from src.domain.repositories.publish_record_repository_async import (
            PublishRecordRepositoryAsync,
        )
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.ui.utils.async_helper import run_async_task

        repo = ServiceLocator().get(PublishRecordRepositoryAsync)

        async def run_restore():
            return await repo.restore_batch(ids)

        def on_done(t):
            try:
                ok = t.result()
                if ok:
                    InfoBar.success("恢复成功", "任务已恢复到对应列表", parent=self)
                    self._load_deleted_records()
                    notify_publish_list_and_records_refresh(self)
                else:
                    InfoBar.error("恢复失败", "恢复任务时发生错误", parent=self)
            except Exception as e:
                logger.error("恢复失败: %s", e, exc_info=True)
                InfoBar.error("恢复失败", str(e), parent=self)

        task = run_async_task(run_restore)
        task.add_done_callback(on_done)

    def _on_permanent_delete_selected(self) -> None:
        ids = self._selected_record_ids()
        if not ids:
            InfoBar.warning("未选择", "请先选择要永久删除的任务", parent=self)
            return
        from src.ui.utils.fluent_dialogs import show_confirm

        if not show_confirm(
            self.window(),
            "确认永久删除",
            f"将彻底删除选中的 {len(ids)} 条任务，无法恢复。确定吗？",
        ):
            return
        self._run_hard_delete(ids)

    def _run_hard_delete(self, record_ids: List[int]) -> None:
        from src.domain.repositories.publish_record_repository_async import (
            PublishRecordRepositoryAsync,
        )
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.ui.utils.async_helper import run_async_task

        repo = ServiceLocator().get(PublishRecordRepositoryAsync)

        async def run_del():
            return await repo.delete_batch(record_ids)

        def on_done(t):
            try:
                ok = t.result()
                if ok:
                    InfoBar.success("已删除", "选中任务已从数据库永久删除", parent=self)
                    self._load_deleted_records()
                else:
                    InfoBar.error("删除失败", "永久删除时发生错误", parent=self)
            except Exception as e:
                logger.error("永久删除失败: %s", e, exc_info=True)
                InfoBar.error("删除失败", str(e), parent=self)

        task = run_async_task(run_del)
        task.add_done_callback(on_done)

    def _on_empty_recycle_bin(self) -> None:
        if not self.deleted_records:
            InfoBar.info("回收站为空", "没有可清空的内容", parent=self)
            return
        from src.ui.utils.fluent_dialogs import show_confirm

        n = len(self.deleted_records)
        if not show_confirm(
            self.window(),
            "清空回收站",
            f"将永久删除回收站内全部 {n} 条任务，无法恢复。确定吗？",
        ):
            return
        all_ids = [int(r["id"]) for r in self.deleted_records if r.get("id") is not None]
        self._run_hard_delete(all_ids)

    def _ensure_ctx_menu(self) -> bool:
        try:
            from qfluentwidgets import Action, RoundMenu, FluentIcon as _FI
        except ImportError:
            return False
        from src.ui.components.fluent_context_menu import (
            install_round_menu_close_on_app_inactive,
            is_round_menu_alive,
            round_menu_parent,
        )

        if self._ctx_menu is not None and is_round_menu_alive(self._ctx_menu):
            return True
        parent = round_menu_parent(self)
        if parent is None:
            return False
        self._ctx_menu = RoundMenu(parent=parent)
        self._ctx_view = Action(_FI.VIEW, "查看", parent)
        self._ctx_open_file = Action(_FI.DOCUMENT, "打开文件", parent)
        self._ctx_open_folder = Action(_FI.FOLDER, "打开所在文件夹", parent)
        self._ctx_restore = Action(_FI.SYNC, "恢复", parent)
        self._ctx_delete = Action(_FI.DELETE, "永久删除", parent)
        self._ctx_view.triggered.connect(self._on_ctx_view_clicked)
        self._ctx_open_file.triggered.connect(self._on_ctx_open_file_clicked)
        self._ctx_open_folder.triggered.connect(self._on_ctx_open_folder_clicked)
        self._ctx_restore.triggered.connect(self._on_restore_selected)
        self._ctx_delete.triggered.connect(self._on_permanent_delete_selected)
        self._ctx_menu.addAction(self._ctx_view)
        self._ctx_menu.addAction(self._ctx_open_file)
        self._ctx_menu.addAction(self._ctx_open_folder)
        self._ctx_menu.addSeparator()
        self._ctx_menu.addAction(self._ctx_restore)
        self._ctx_menu.addSeparator()
        self._ctx_menu.addAction(self._ctx_delete)
        install_round_menu_close_on_app_inactive(self._ctx_menu)
        return True

    def _on_ctx_view_clicked(self) -> None:
        rows = getattr(self, "_ctx_pending_rows", None) or []
        if len(rows) != 1:
            return
        rid_item = self.records_table.item(rows[0], 0)
        if not rid_item:
            return
        try:
            rid = int(rid_item.data(Qt.UserRole))
        except (ValueError, TypeError):
            return
        rec = next((r for r in self.deleted_records if r.get("id") == rid), None)
        if rec:
            self._on_view_detail(rec)

    def _on_ctx_open_file_clicked(self) -> None:
        rows = getattr(self, "_ctx_pending_rows", None) or []
        if len(rows) != 1:
            return
        rid_item = self.records_table.item(rows[0], 0)
        if not rid_item:
            return
        try:
            rid = int(rid_item.data(Qt.UserRole))
        except (ValueError, TypeError):
            return
        rec = next((r for r in self.deleted_records if r.get("id") == rid), None)
        if rec:
            open_record_primary_media_file(self, rec)

    def _on_ctx_open_folder_clicked(self) -> None:
        rows = getattr(self, "_ctx_pending_rows", None) or []
        if len(rows) != 1:
            return
        rid_item = self.records_table.item(rows[0], 0)
        if not rid_item:
            return
        try:
            rid = int(rid_item.data(Qt.UserRole))
        except (ValueError, TypeError):
            return
        rec = next((r for r in self.deleted_records if r.get("id") == rid), None)
        if rec:
            open_record_media_folder(self, rec)

    def _on_context_menu(self, pos) -> None:
        table = self.records_table
        indexes = table.selectionModel().selectedRows()
        if indexes:
            selected_rows = sorted({idx.row() for idx in indexes})
        else:
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

        n_sel = len(selected_rows)
        self._ctx_pending_rows = selected_rows
        single = n_sel == 1
        restore_lbl = "恢复" if n_sel <= 1 else f"恢复（{n_sel} 条）"
        del_lbl = "永久删除" if n_sel <= 1 else f"永久删除（{n_sel} 条）"

        if self._ensure_ctx_menu():
            tip_single = "" if single else "请只选择一条任务时使用"
            self._ctx_view.setEnabled(single)
            self._ctx_view.setToolTip(tip_single)
            self._ctx_open_file.setEnabled(single)
            self._ctx_open_file.setToolTip(
                "使用系统默认程序打开；视频用默认播放器播放，图片用默认看图软件"
                if single
                else "请只选择一条任务时使用"
            )
            self._ctx_open_folder.setEnabled(single)
            self._ctx_open_folder.setToolTip(tip_single)
            self._ctx_restore.setText(restore_lbl)
            self._ctx_delete.setText(del_lbl)
            self._ctx_menu.exec(table.viewport().mapToGlobal(pos))
            return

        menu = QMenu(self)
        av = None
        afile = None
        aopen = None
        if single:
            av = menu.addAction("查看")
            if FLUENT_WIDGETS_AVAILABLE:
                av.setIcon(FluentIcon.VIEW.icon())
            afile = menu.addAction("打开文件")
            if FLUENT_WIDGETS_AVAILABLE:
                afile.setIcon(FluentIcon.DOCUMENT.icon())
            aopen = menu.addAction("打开所在文件夹")
            if FLUENT_WIDGETS_AVAILABLE:
                aopen.setIcon(FluentIcon.FOLDER.icon())
            menu.addSeparator()
        ar = menu.addAction(restore_lbl)
        ad = menu.addAction(del_lbl)
        if FLUENT_WIDGETS_AVAILABLE:
            ar.setIcon(FluentIcon.SYNC.icon())
            ad.setIcon(FluentIcon.DELETE.icon())
        act = menu.exec(table.viewport().mapToGlobal(pos))
        if av is not None and act == av:
            self._on_ctx_view_clicked()
        elif afile is not None and act == afile:
            self._on_ctx_open_file_clicked()
        elif aopen is not None and act == aopen:
            self._on_ctx_open_folder_clicked()
        elif act == ar:
            self._on_restore_selected()
        elif act == ad:
            self._on_permanent_delete_selected()

    def _on_cell_double_clicked(self, row: int, col: int) -> None:
        rid_item = self.records_table.item(row, 0)
        if not rid_item:
            return
        try:
            rid = int(rid_item.data(Qt.UserRole))
        except (ValueError, TypeError):
            return
        rec = next((r for r in self.deleted_records if r.get("id") == rid), None)
        if rec:
            self._on_view_detail(rec)

    def _on_view_detail(self, record: Dict[str, Any]) -> None:
        """与发布记录页一致：跳转单任务页或弹窗；返回时回到回收站。"""
        PublishRecordsPage._on_view_detail(
            self, record, edit_return_route="publish_recycle_bin_page"
        )  # type: ignore[arg-type]
