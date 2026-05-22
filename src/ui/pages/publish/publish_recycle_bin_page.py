"""
任务回收站页面
文件路径：src/ui/pages/publish/publish_recycle_bin_page.py
功能：展示软删除的发布任务，支持恢复或彻底删除；表格右键可查看、打开文件、打开所在文件夹。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMenu,
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
from src.ui.pages.publish.publish_record_table_view import PublishRecordTableView

from .publish_records_page import (
    PublishRecordsPage,
    notify_publish_list_and_records_refresh,
    open_record_media_folder,
    open_record_primary_media_file,
)

logger = logging.getLogger(__name__)

FLUENT_WIDGETS_AVAILABLE = True

class PublishRecycleBinPage(BasePage):
    """任务回收站：deleted_pending / deleted_success 记录。"""

    _lazy_content = True

    def __init__(self, parent: Optional[Any] = None):
        super().__init__("任务回收站", parent)
        from src.services.auth import CurrentUserService

        self._current_user_svc = CurrentUserService()
        self.user_id = self._current_user_svc.get_user_id_or_default(1)
        self.deleted_records: List[Dict[str, Any]] = []
        self._deleted_records_by_id: Dict[int, Dict[str, Any]] = {}
        self._deleted_load_limit: int = 500
        self._deleted_load_step: int = 500
        self._has_more_deleted_records: bool = False
        self._total_deleted_count: int = 0
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

        self.records_table = PublishRecordTableView(
            table_container,
            recycle_page=True,
            action_text="查看",
        )
        self.records_table.setObjectName("PublishRecycleBinTable")

        self.records_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.records_table.customContextMenuRequested.connect(self._on_context_menu)
        self.records_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.records_table.cellClicked.connect(self._on_cell_clicked)
        self.records_table.installEventFilter(self)

        table_layout.addWidget(self.records_table)
        load_more_bar = QHBoxLayout()
        load_more_bar.setContentsMargins(12, 8, 12, 8)
        self._load_more_label = BodyLabel("", table_container)
        self._load_more_btn = PushButton("加载更多回收站记录…", table_container)
        self._load_more_btn.clicked.connect(self._on_load_more_clicked)
        self._load_more_label.setVisible(False)
        self._load_more_btn.setVisible(False)
        load_more_bar.addWidget(self._load_more_label)
        load_more_bar.addStretch(1)
        load_more_bar.addWidget(self._load_more_btn)
        table_layout.addLayout(load_more_bar)
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
            load_limit = int(getattr(self, "_deleted_load_limit", 500) or 500)
            records = await repo.find_deleted_records(user_id=None, limit=load_limit, offset=0)
            total = await repo.count_records(
                user_id=None,
                status_in=["deleted_pending", "deleted_success"],
            )
            return records, purged, total

        def on_done(task):
            if gen != self._load_generation:
                return
            try:
                records, purged, total = task.result()
                self._on_deleted_loaded(records, total=total)
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

    def _on_deleted_loaded(self, records: List[Dict[str, Any]], *, total: Optional[int] = None) -> None:
        self.deleted_records = records or []
        self._total_deleted_count = int(total if total is not None else len(self.deleted_records))
        self._has_more_deleted_records = len(self.deleted_records) < self._total_deleted_count
        records_by_id: Dict[int, Dict[str, Any]] = {}
        for r in self.deleted_records:
            try:
                records_by_id[int(r["id"])] = r
            except (KeyError, TypeError, ValueError):
                continue
        self._deleted_records_by_id = records_by_id
        self._data_stale = False
        self._update_load_more_bar()
        if self._total_deleted_count > 1000 and not getattr(self, "_over_limit_warned", False):
            self._over_limit_warned = True
            InfoBar.warning(
                "回收站记录较多",
                f"回收站内有 {self._total_deleted_count} 条记录，建议点击「清空回收站」释放空间。",
                parent=self,
                duration=6000,
            )
        if hasattr(self, "records_table"):
            self._refresh_table()

    def _on_load_more_clicked(self) -> None:
        self._load_more_deleted_records()

    def _load_more_deleted_records(self) -> None:
        from src.domain.repositories.publish_record_repository_async import (
            PublishRecordRepositoryAsync,
        )
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.ui.utils.async_helper import run_async_task

        repo = ServiceLocator().get(PublishRecordRepositoryAsync)
        self._load_generation += 1
        gen = self._load_generation
        offset = len(self.deleted_records)
        step = int(getattr(self, "_deleted_load_step", 500) or 500)
        btn = getattr(self, "_load_more_btn", None)
        if btn is not None:
            btn.setEnabled(False)

        async def load_async():
            records = await repo.find_deleted_records(user_id=None, limit=step, offset=offset)
            total = await repo.count_records(
                user_id=None,
                status_in=["deleted_pending", "deleted_success"],
            )
            return records, total

        def on_done(task):
            if btn is not None:
                btn.setEnabled(True)
            if gen != self._load_generation:
                return
            try:
                records, total = task.result()
                self._append_deleted_loaded(records, total=total)
            except Exception as e:
                logger.error("加载更多回收站记录失败: %s", e, exc_info=True)
                InfoBar.error("加载失败", str(e), parent=self)

        t = run_async_task(load_async)
        t.add_done_callback(on_done)

    def _append_deleted_loaded(self, records: List[Dict[str, Any]], *, total: int) -> None:
        new_records = records or []
        if not new_records:
            self._total_deleted_count = int(total or len(self.deleted_records))
            self._has_more_deleted_records = len(self.deleted_records) < self._total_deleted_count
            self._update_load_more_bar()
            return

        start_row = len(self.deleted_records)
        self.deleted_records.extend(new_records)
        for r in new_records:
            try:
                self._deleted_records_by_id[int(r["id"])] = r
            except (KeyError, TypeError, ValueError):
                continue
        self._total_deleted_count = int(total or len(self.deleted_records))
        self._has_more_deleted_records = len(self.deleted_records) < self._total_deleted_count
        if hasattr(self, "records_table"):
            self._append_table_rows(start_row, new_records)
        self._update_load_more_bar()

    def _update_load_more_bar(self) -> None:
        btn = getattr(self, "_load_more_btn", None)
        label = getattr(self, "_load_more_label", None)
        if btn is None:
            return
        has_more = bool(getattr(self, "_has_more_deleted_records", False))
        loaded = len(getattr(self, "deleted_records", []) or [])
        total = int(getattr(self, "_total_deleted_count", 0) or 0)
        btn.setVisible(has_more)
        if label is not None:
            if has_more:
                label.setText(f"当前显示最近 {loaded} 条，共 {total} 条")
                label.setVisible(True)
            else:
                label.setVisible(False)

    def _refresh_table(self) -> None:
        table = self.records_table
        table.setUpdatesEnabled(False)
        table.setSortingEnabled(False)
        table.blockSignals(True)
        try:
            table.set_recycle_page(True)
            table.set_action_text("查看")
            table.set_records(self.deleted_records)
        finally:
            table.blockSignals(False)
            table.setSortingEnabled(True)
            table.setUpdatesEnabled(True)

    def _append_table_rows(self, start_row: int, rows: List[Dict[str, Any]]) -> None:
        if rows and hasattr(self, "records_table"):
            self._refresh_table()

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

        n = int(getattr(self, "_total_deleted_count", 0) or len(self.deleted_records))
        if not show_confirm(
            self.window(),
            "清空回收站",
            f"将永久删除回收站内全部 {n} 条任务，无法恢复。确定吗？",
        ):
            return
        self._run_empty_recycle_bin()

    def _run_empty_recycle_bin(self) -> None:
        from src.domain.repositories.publish_record_repository_async import (
            PublishRecordRepositoryAsync,
        )
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.ui.utils.async_helper import run_async_task

        repo = ServiceLocator().get(PublishRecordRepositoryAsync)

        async def run_empty():
            all_ids = await repo.find_deleted_record_ids(user_id=None)
            if not all_ids:
                return True
            return await repo.delete_batch(all_ids)

        def on_done(t):
            try:
                ok = t.result()
                if ok:
                    InfoBar.success("已清空", "回收站任务已从数据库永久删除", parent=self)
                    self._deleted_load_limit = self._deleted_load_step
                    self._load_deleted_records()
                else:
                    InfoBar.error("清空失败", "清空回收站时发生错误", parent=self)
            except Exception as e:
                logger.error("清空回收站失败: %s", e, exc_info=True)
                InfoBar.error("清空失败", str(e), parent=self)

        task = run_async_task(run_empty)
        task.add_done_callback(on_done)

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
        rec = self._record_by_row(rows[0])
        if rec:
            self._on_view_detail(rec)

    def _on_ctx_open_file_clicked(self) -> None:
        rows = getattr(self, "_ctx_pending_rows", None) or []
        if len(rows) != 1:
            return
        rec = self._record_by_row(rows[0])
        if rec:
            open_record_primary_media_file(self, rec)

    def _on_ctx_open_folder_clicked(self) -> None:
        rows = getattr(self, "_ctx_pending_rows", None) or []
        if len(rows) != 1:
            return
        rec = self._record_by_row(rows[0])
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
        rec = self._record_by_row(row)
        if rec:
            self._on_view_detail(rec)

    def _on_cell_clicked(self, row: int, col: int) -> None:
        if col != 18:
            return
        rec = self._record_by_row(row)
        if rec:
            self._on_view_detail(rec)

    def _record_by_row(self, row: int) -> Optional[Dict[str, Any]]:
        rid_item = self.records_table.item(row, 0)
        if not rid_item:
            return None
        try:
            rid = int(rid_item.data(Qt.UserRole))
        except (ValueError, TypeError):
            return None
        return self._deleted_records_by_id.get(rid)

    def _on_view_detail(self, record: Dict[str, Any]) -> None:
        """与发布记录页一致：跳转单任务页或弹窗；返回时回到回收站。"""
        PublishRecordsPage._on_view_detail(
            self, record, edit_return_route="publish_recycle_bin_page"
        )  # type: ignore[arg-type]
