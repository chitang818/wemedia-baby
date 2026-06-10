"""
发布列表页面
文件路径：src/ui/pages/publish/publish_list_page.py
功能：显示待发布任务列表（复用发布记录页面布局）。

说明：单条/批量任务创建页只负责把任务写入列表；本页是用户触发「发布」后
      实际执行各平台上传与发布管道的入口。
"""

from typing import Optional, List, Dict, Any, FrozenSet
import logging
from PySide6.QtWidgets import (
    QWidget,
    QTextEdit,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QAbstractItemView,
    QDialog,
)
from PySide6.QtCore import Qt, QObject, Signal, Slot, QTimer, QUrl

logger = logging.getLogger(__name__)
from PySide6.QtGui import QFont, QShowEvent, QDesktopServices
import asyncio
from qasync import asyncSlot

from .publish_records_page import (
    PublishRecordsPage,
    notify_publish_records_history_tab_refresh,
    open_record_media_folder,
    open_record_primary_media_file,
)
from .list_settings_dialog import (
    ListSettingsDialog,
    get_display_mode,
    get_speed_rate,
    get_speed_index,
    SPEED_OPTIONS,
    get_first_platform,
    get_effective_publish_interval_seconds,
    get_post_publish_action,
    get_publish_show_browser,
    get_precheck_account_online_enabled,
    clear_publish_after_shutdown_one_shot,
    is_publish_after_shutdown_one_shot_armed,
    sample_publish_interval_delay_seconds,
    set_post_publish_action,
    MODE_ORDER,
    MODE_PLATFORM,
    MODE_ACCOUNT,
)
from src.infrastructure.browser.browser_launch_policy import should_stop_on_risk_prompt
from src.plugins.core.publish_failure_kind import (
    classify_publish_failure,
    is_blocking_failure_kind,
    PublishFailureKind,
)
from src.infrastructure.common.publish_material_path_policy import (
    desired_persisted_post_publish_action,
    message_for_auto_post_publish_change,
    resolve_effective_post_publish_action_for_queue,
)
from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.ui.components.log_display_widget import LogDisplayWidget


_RISK_PROMPT_KEYWORDS = (
    "操作频繁",
    "风控",
    "异常验证",
    "安全验证",
    "验证失败",
    "环境异常",
    "账号异常",
    "强制登录",
    "扫码登录",
    "重新登录",
    "登录已过期",
    "稍后重试",
    "脚本",
    "自动化",
    "自动化软件",
    "AI自动化",
    "AI 自动化",
    "人工智能",
    "验证码",
)


def _looks_like_platform_risk_prompt(message: str) -> bool:
    text = str(message or "")
    return any(k in text for k in _RISK_PROMPT_KEYWORDS)


from src.ui.components.task_overview_card import TaskOverviewCard
from src.ui.components.task_description_card import TaskDescriptionCard
from src.ui.components.publish_settings_card import PublishSettingsCard
from src.ui.utils.fluent_tooltips import apply_instructional_tooltip, ToolTipPosition
from src.utils.platform_names import get_platform_display_name
from qfluentwidgets import InfoBar, FluentIcon, PushButton
from src.ui.pages.publish.publish_validators import (
    wechat_video_short_title_validation_error,
    publish_file_missing_error,
)
import os


def _get_process_memory_mb() -> float:
    """获取当前进程的 RSS 内存（MB），失败返回 0。"""
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return 0.0


class PublishListPage(PublishRecordsPage):
    """发布列表页面 - 复用发布记录页面的设计"""

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化"""
        super().__init__(
            parent,
            title="待发布",
            target_statuses=["pending", "failed"],
        )
        # 筛选栏显示「任务类型」下拉（全部/视频/图文），在 _setup_content 中创建
        self._enable_task_type_filter = True
        # 筛选栏显示「发布方式」：全部 / 定时发布 / 立即发布
        self._enable_publish_timing_filter = True
        self._task_description_wired = False
        # 发布中队列仅在表格上标「发布中」，库表仍为 pending；选中行刷新说明时需与此对齐
        self._ui_active_publishing_task_id: Optional[int] = None

        self.current_task = None
        self.publish_pause_event = asyncio.Event()
        self.publish_pause_event.set()
        # 手动点「停止」后置 True，防止队列 finally 刷新列表时触发自动发布重启；_check_auto_start 读后清除
        self._manual_stop_requested: bool = False
        
        self.log_widget = None
        self._session_evicted_subscribed = False
        self._subscribe_session_evicted()
        # 发布列表表右键（与记录页分开缓存，项不同）
        self._list_table_ctx_menu = None
        self._list_table_ctx_view = None
        self._list_table_ctx_open_file = None
        self._list_table_ctx_open_folder = None
        self._list_table_ctx_retry = None
        self._list_table_ctx_delete = None
        self._list_ctx_failed_records: List[Dict[str, Any]] = []
        self._list_table_ctx_selected_rows: List[int] = []
        self._shown_diagnostic_paths: set[str] = set()
        # 发布队列本轮仅处理点击「发布」时表格筛选内的待发布任务（ID 快照）
        self._publish_queue_scoped_ids: Optional[FrozenSet[int]] = None
        # 媒体库规则自动改写发布后文件处理后，待弹窗展示的说明（进入待发布页或本页刷新后弹出）
        self._pending_publish_policy_modal_hint: Optional[str] = None
        # 发布失败提示（诊断弹窗 + InfoBar），页面不可见时挂起至 showEvent
        self._pending_publish_failure_notice: Optional[Dict[str, Any]] = None

    def _use_pending_table_column_order(self) -> bool:
        return True

    def _get_record_by_id(self, task_id: Any) -> Optional[Dict[str, Any]]:
        try:
            tid_int = int(task_id)
        except (TypeError, ValueError):
            return None
        return (getattr(self, "_records_by_id", {}) or {}).get(tid_int)

    def _update_task_status_in_memory(self, task_id: int, new_status: str, error_message: str = "") -> None:
        """在内存缓存中更新任务状态。

        发布循环期间（_is_publishing_loop_active=True）使用增量更新：
        - success/cancelled 状态：直接从表格行移除（该任务不再属于 pending/failed 范围）
        - failed/pending 状态：只更新状态列文本，保留在表格中
        发布循环结束后的整表刷新由 _load_publish_records() 负责。
        """
        rec = self._get_record_by_id(task_id)
        if rec is not None:
            rec["status"] = new_status
            if error_message:
                rec["error_message"] = error_message
            try:
                self._record_filter_meta_by_id[int(task_id)] = self._build_record_filter_meta(rec)
            except (TypeError, ValueError):
                pass
            self._records_version += 1
            self._last_filter_render_state = None
        # 同步更新 _filtered_records 缓存中的状态
        filtered = getattr(self, "_filtered_records", None) or []
        for rec in filtered:
            if rec.get("id") == task_id:
                rec["status"] = new_status
                if error_message:
                    rec["error_message"] = error_message
                break

        if getattr(self, "_is_publishing_loop_active", False):
            # 成功或取消的任务不属于 target_statuses=[pending,failed]，直接从表格行移除
            if new_status in ("success", "cancelled"):
                self._remove_row_from_table(task_id)
            else:
                # failed/pending：只更新状态列文本，保留在表格中
                self._update_single_row_status(task_id, new_status, error_message=error_message)
        else:
            self._schedule_table_refresh()

    def _remove_row_from_table(self, task_id: int) -> None:
        """发布循环期间将指定任务行从表格中移除，同时从 _filtered_records 中删除。"""
        table = getattr(self, "records_table", None)
        if table is None:
            return
        try:
            tid_int = int(task_id)
        except (TypeError, ValueError):
            return

        # 从 _filtered_records 中移除
        filtered = getattr(self, "_filtered_records", None)
        if filtered is not None:
            self._filtered_records = [r for r in filtered if r.get("id") != tid_int]

        # 从 publish_records（内存总缓存）中也移除，避免后续计算残留
        if hasattr(self, "publish_records"):
            self.publish_records = [r for r in self.publish_records if r.get("id") != tid_int]
            self._account_filter_options_cache = None
            self._records_version += 1
            self._last_filter_render_state = None
        try:
            self._records_by_id.pop(tid_int, None)
        except Exception:
            pass
        try:
            self._record_filter_meta_by_id.pop(tid_int, None)
        except Exception:
            pass

        found_row = self._find_record_row(tid_int)

        if found_row >= 0:
            table.blockSignals(True)
            try:
                table.removeRow(found_row)
                # 删除一行后仅后续视觉行号左移 1，无需重扫整张表。
                self._highlighted_task_row = -1
                self._shift_record_row_index_after_remove(tid_int, found_row)
            finally:
                table.blockSignals(False)

    def _find_record_row(self, task_id: int) -> int:
        """按记录 id 查找当前表格行，优先使用 row index，失败再扫描兜底。"""
        table = getattr(self, "records_table", None)
        if table is None:
            return -1
        try:
            tid_int = int(task_id)
        except (TypeError, ValueError):
            return -1

        for candidate in (
            getattr(self, "_highlighted_task_row", -1),
            (getattr(self, "_row_by_record_id", {}) or {}).get(tid_int, -1),
        ):
            try:
                row = int(candidate)
            except (TypeError, ValueError):
                continue
            if row < 0 or row >= table.rowCount():
                continue
            it = table.item(row, 0)
            if it is None:
                continue
            try:
                if int(it.data(Qt.UserRole)) == tid_int:
                    return row
            except (TypeError, ValueError):
                continue

        for row in range(table.rowCount()):
            it = table.item(row, 0)
            if it is None:
                continue
            try:
                if int(it.data(Qt.UserRole)) == tid_int:
                    try:
                        self._row_by_record_id[tid_int] = row
                    except Exception:
                        pass
                    return row
            except (TypeError, ValueError):
                continue
        return -1

    def _rebuild_record_row_index(self) -> None:
        table = getattr(self, "records_table", None)
        if table is None:
            return
        row_by_id: Dict[int, int] = {}
        for row in range(table.rowCount()):
            it = table.item(row, 0)
            if it is None:
                continue
            try:
                row_by_id[int(it.data(Qt.UserRole))] = row
            except (TypeError, ValueError):
                continue
        self._row_by_record_id = row_by_id

    def _shift_record_row_index_after_remove(self, removed_id: int, removed_row: int) -> None:
        """表格删除一行后增量维护 id->row 索引，避免发布循环中每次成功都全表扫描。"""
        current = getattr(self, "_row_by_record_id", None)
        if not current:
            return
        updated: Dict[int, int] = {}
        for rid, row in current.items():
            try:
                rid_int = int(rid)
                row_int = int(row)
            except (TypeError, ValueError):
                continue
            if rid_int == removed_id or row_int == removed_row:
                continue
            updated[rid_int] = row_int - 1 if row_int > removed_row else row_int
        self._row_by_record_id = updated

    def _update_single_row_status(self, task_id: int, new_status: str, error_message: str = "") -> None:
        """发布循环期间的增量状态列更新：仅改变目标行的状态列文本，不重建整张表。"""
        table = getattr(self, "records_table", None)
        if table is None:
            return
        status_text_map = {
            "success": "✅ 成功",
            "failed": "❌ 失败",
            "cancelled": "🚫 已取消",
            "pending": "⏳ 待发布",
        }
        display_text = status_text_map.get(new_status, new_status)
        from PySide6.QtWidgets import QTableWidgetItem
        try:
            tid_int = int(task_id)
        except (TypeError, ValueError):
            return

        row = self._find_record_row(tid_int)
        if row < 0:
            return
        item = QTableWidgetItem(display_text)
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )
        table.blockSignals(True)
        try:
            table.setItem(row, self.COL_STATUS, item)
        finally:
            table.blockSignals(False)

    def _schedule_table_refresh(self) -> None:
        """通过防抖定时器延迟刷新表格，将短时间内多次更新合并为一次 DOM 操作。"""
        if not hasattr(self, "_table_refresh_timer"):
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(150)
            timer.timeout.connect(self._do_deferred_table_refresh)
            self._table_refresh_timer = timer
        self._table_refresh_timer.start()

    def _do_deferred_table_refresh(self) -> None:
        """执行延迟的表格刷新（由防抖定时器触发）。
        
        发布循环中仅更新任务状态，账号下拉内容不变，跳过重建以减少主线程开销。
        """
        if hasattr(self, "records_table"):
            self._apply_filters(skip_account_rebuild=True)

    def _on_view_detail(self, record):  # type: ignore[override]
        """待发布列表进入编辑：返回时回到待发布页。"""
        super()._on_view_detail(record, edit_return_route="publish_list_page")

    def showEvent(self, event: QShowEvent) -> None:
        """进入待发布页时尝试弹出「发布后文件处理」说明弹窗（若有挂起提示）。"""
        super().showEvent(event)
        self._schedule_base_page_timer(
            "publish_policy_modal",
            0,
            self._flush_pending_publish_policy_modal,
        )
        self._schedule_base_page_timer(
            "publish_failure_notice",
            0,
            self._flush_pending_publish_failure_notice,
        )

    def _flush_pending_publish_policy_modal(self) -> None:
        """消费挂起的说明并用 Fluent 单按钮弹窗展示；页面不可见时保留待下次显示。"""
        hint = self._pending_publish_policy_modal_hint
        if not hint:
            return
        if not self.isVisible():
            return
        self._pending_publish_policy_modal_hint = None
        try:
            from src.ui.utils.fluent_dialogs import show_info

            show_info(
                self.window() or self,
                "发布后文件处理已自动调整",
                hint,
            )
            # 弹窗关闭后再刷一次，避免极端时序下卡片仍显示旧值
            if hasattr(self, "publish_settings_card"):
                self.publish_settings_card.refresh()
        except Exception as e:
            logger.warning("发布后文件策略弹窗失败: %s", e, exc_info=True)

    def _schedule_publish_policy_modal_if_pending(self) -> None:
        """当前页可见且有待展示说明时，下一事件循环弹出（避免与布局/拉库同一帧冲突）。"""
        if self._pending_publish_policy_modal_hint and self.isVisible():
            self._schedule_base_page_timer(
                "publish_policy_modal",
                0,
                self._flush_pending_publish_policy_modal,
            )

    def _publish_queue_scoped_pending_ids(self) -> FrozenSet[int]:
        """当前表格筛选结果（_filtered_records）中 status=pending 的任务 ID 集合。"""
        filtered = getattr(self, "_filtered_records", None) or []
        ids: List[int] = []
        for r in filtered:
            if r.get("status") != "pending":
                continue
            rid = r.get("id")
            if rid is None:
                continue
            try:
                ids.append(int(rid))
            except (TypeError, ValueError):
                continue
        return frozenset(ids)

    def _setup_content(self):
        """先构建父类内容（筛选栏 + 表格），再追加日志控件到底部"""
        super()._setup_content()

        if hasattr(self, 'status_filter'):
            self.status_filter.setCurrentText("全部")

        btn_clear_filters = PushButton("清除筛选", self.filter_card)
        btn_clear_filters.clicked.connect(self._on_clear_filters)
        if getattr(self, "_filter_widgets_order", None) is not None:
            self._filter_widgets_order.append(btn_clear_filters)

        if hasattr(self, "auto_publish_check") and hasattr(
            self, "_hint_icon_auto_publish"
        ):
            apply_instructional_tooltip(
                "勾选后，只要当前表格筛选结果里存在待发布任务，就会自动开始发布（范围与点「发布」一致）",
                self.auto_publish_check,
                self._hint_icon_auto_publish,
                position=ToolTipPosition.BOTTOM,
            )

        self._setup_log_window()

    def _on_clear_filters(self) -> None:
        """清除所有筛选项与表头排序，刷新表格为默认列表顺序。"""
        combos = []
        tt = getattr(self, "task_type_filter", None)
        if tt is not None:
            combos.append(tt)
        pt = getattr(self, "publish_timing_filter", None)
        if pt is not None:
            combos.append(pt)
        if getattr(self, "platform_filter", None) is not None:
            combos.append(self.platform_filter)
        if getattr(self, "account_filter", None) is not None:
            combos.append(self.account_filter)
        if getattr(self, "status_filter", None) is not None:
            combos.append(self.status_filter)

        for c in combos:
            c.blockSignals(True)
        try:
            if tt is not None:
                tt.setCurrentText("全部")
            if pt is not None:
                pt.setCurrentText("全部")
            if getattr(self, "platform_filter", None) is not None:
                self.platform_filter.setCurrentText("全部")
            if getattr(self, "account_filter", None) is not None:
                self.account_filter.setCurrentIndex(0)
            if getattr(self, "status_filter", None) is not None:
                self.status_filter.setCurrentText("全部")
        finally:
            for c in combos:
                c.blockSignals(False)

        table = getattr(self, "records_table", None)
        if table is not None:
            table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)

        self._apply_filters()

    def _setup_log_window(self):
        """底部四卡片：发布设置(2) | 任务统计(1) | 发布日志(2) | 任务说明(2)；垂直约 5:2 表格与底栏均衡"""
        self.publish_settings_card = PublishSettingsCard(self)
        self.task_overview_card = TaskOverviewCard(self)
        self.task_description_card = TaskDescriptionCard(self)
        self.log_widget = LogDisplayWidget("发布日志", self)

        # 点击发布设置卡片的「⚙」按钮 → 打开设置弹窗
        self.publish_settings_card.open_settings_clicked.connect(self._on_publish_settings_clicked)

        bottom_row = QWidget(self)
        bottom_layout = QHBoxLayout(bottom_row)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        self.publish_settings_card.setMinimumWidth(10)
        self.publish_settings_card.setMaximumWidth(220)
        self.publish_settings_card.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.task_overview_card.setMinimumWidth(10)
        self.task_overview_card.setMaximumWidth(160)
        self.task_overview_card.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )

        for card in (self.log_widget, self.task_description_card):
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 水平 2:1:2:2 — 加宽发布设置，收窄日志与任务说明
        bottom_layout.addWidget(self.publish_settings_card, 2)
        bottom_layout.addWidget(self.task_overview_card, 1)
        bottom_layout.addWidget(self.log_widget, 2)
        bottom_layout.addWidget(self.task_description_card, 2)

        self.content_layout.addWidget(bottom_row, 2)
        self.content_layout.setStretch(0, 5)   # 上方表格
        self.content_layout.setStretch(1, 2)   # 下方一行

        target_loggers = ["publish.user_log"]
        self.log_widget.start_logging(target_loggers)
        
        # 3. 自动发布监听
        if hasattr(self, 'auto_publish_check'):
            self.auto_publish_check.stateChanged.connect(self._check_auto_start)

        # 任务说明：默认提示；选中任务时刷新
        self._wire_task_description()

    def _wire_task_description(self):
        if not hasattr(self, "records_table") or not hasattr(self, "task_description_card"):
            return
        if getattr(self, "_task_description_wired", False):
            return
        try:
            self.records_table.itemSelectionChanged.connect(self._on_task_selection_changed)
            self.records_table.cellClicked.connect(lambda r, _c: self._on_task_row_clicked(r))
            self._task_description_wired = True
        except Exception:
            pass

    def _on_task_row_clicked(self, row: int):
        rec = self._get_record_by_row(row)
        if hasattr(self, "task_description_card"):
            self.task_description_card.set_task(self._record_with_ui_publish_status(rec))

    def _on_task_selection_changed(self):
        rows = list(getattr(self, "_selected_rows_cache", None) or [])
        if not rows:
            try:
                rows = [idx.row() for idx in self.records_table.selectionModel().selectedRows()]
            except Exception:
                rows = []
        if not rows:
            if hasattr(self, "task_description_card"):
                self.task_description_card.clear()
            return
        self._on_task_row_clicked(rows[0])

    def _get_record_by_row(self, row: int):
        """按表格当前视觉行解析记录。表头排序后行序与 _filtered_records 下标不一致，必须用首列 UserRole 的 id 查找。"""
        table = getattr(self, "records_table", None)
        if table is not None and 0 <= row < table.rowCount():
            rid_item = table.item(row, 0)
            if rid_item is not None:
                rid = rid_item.data(Qt.UserRole)
                if rid is not None:
                    try:
                        rid_int = int(rid)
                    except (TypeError, ValueError):
                        rid_int = None
                    if rid_int is not None:
                        rec = (getattr(self, "_records_by_id", {}) or {}).get(rid_int)
                        if rec is not None:
                            return rec
        records = getattr(self, "_filtered_records", None) or []
        if 0 <= row < len(records):
            return records[row]
        all_records = getattr(self, "publish_records", None) or []
        if 0 <= row < len(all_records):
            return all_records[row]
        return None
            
    def _subscribe_session_evicted(self) -> None:
        """订阅媒小宝账号被顶下线事件，触发时自动停止发布队列。"""
        if self._session_evicted_subscribed:
            return
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.infrastructure.common.event.event_bus import EventBus
            sl = ServiceLocator()
            if sl.is_registered(EventBus):
                event_bus = sl.get(EventBus)
                event_bus.subscribe("SessionEvictedEvent", self._on_session_evicted_stop_queue)
                self._session_evicted_subscribed = True
        except Exception as e:
            logger.warning("订阅 SessionEvictedEvent 失败: %s", e)

    def _on_session_evicted_stop_queue(self, event) -> None:
        """账号被顶下线：立即停止发布队列，并在 UI 线程弹出醒目提示。"""
        reason = getattr(event, "reason", "您的媒小宝账号已在其他设备登录，当前会话已失效。")
        from PySide6.QtCore import QMetaObject, Q_ARG, Qt
        QMetaObject.invokeMethod(
            self, "_stop_queue_on_session_evicted", Qt.QueuedConnection, Q_ARG(str, reason)
        )

    @Slot(str)
    def _stop_queue_on_session_evicted(self, reason: str) -> None:
        """UI 主线程：停止队列 + 弹出持久错误提示（需用户手动关闭）。"""
        is_active = getattr(self, "_is_publishing_loop_active", False)
        ct = getattr(self, "current_task", None)
        has_running = ct is not None and not ct.done()

        if is_active or has_running:
            # 置停止标志、唤醒 Event、取消当前 Task；被顶下线属系统行为，不设 _manual_stop_requested
            self._do_stop_publish_queue(manual=False)
            if self.log_widget:
                self.log_widget.append_warning(
                    f"🔐 媒小宝账号已在其他设备登录，发布队列已自动停止。请重新登录后再继续发布。"
                )

        try:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(
                title="账号已在其他设备登录，发布已停止",
                content=f"{reason}\n\n请重新登录媒小宝账号后，再重新启动发布。",
                parent=self.window() or self,
                position=InfoBarPosition.TOP,
                duration=-1,
            )
        except Exception:
            pass

    def closeEvent(self, event):
        """关闭时移除 Handler"""
        ct = getattr(self, "current_task", None)
        if ct is not None and not ct.done():
            ct.cancel()
        timer = getattr(self, "_table_refresh_timer", None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
            self._table_refresh_timer = None
        if self.log_widget:
            self.log_widget.stop_logging()
        super().closeEvent(event)

    def _get_extra_filter_widgets(self):
        return []

    def _on_publish_settings_clicked(self):
        """打开发布设置弹窗，确认后刷新列表与发布设置卡片。"""
        try:
            parent = self.window() or self

            def _on_saved():
                self._apply_filters()
                if hasattr(self, "publish_settings_card"):
                    self.publish_settings_card.refresh()

            policy_recs = [
                r
                for r in self.publish_records
                if r.get("status") in ("pending", "failed")
            ]
            dialog = ListSettingsDialog(
                parent, on_saved=_on_saved, pending_policy_records=policy_recs
            )
            dialog.exec()
        except Exception as e:
            logger.error("打开发布设置弹窗失败: %s", e, exc_info=True)
            InfoBar.error("错误", f"打开发布设置失败：{e}", parent=self.window() or self)

    def _apply_filters(self, *, skip_account_rebuild: bool = False):
        """应用筛选后刷新任务统计卡片，并按记录 id 恢复选中行与任务说明（避免列表重载后说明滞后或错位）。"""
        preserved_ids: List[int] = []
        if hasattr(self, "records_table"):
            rows = list(getattr(self, "_selected_rows_cache", None) or [])
            if not rows:
                sm = self.records_table.selectionModel()
                if sm is not None:
                    rows = [idx.row() for idx in sm.selectedRows()]
            for row in rows:
                rid_item = self.records_table.item(row, 0)
                if rid_item is None:
                    continue
                rid = rid_item.data(Qt.UserRole)
                if rid is None:
                    continue
                try:
                    preserved_ids.append(int(rid))
                except (TypeError, ValueError):
                    pass

        super()._apply_filters(skip_account_rebuild=skip_account_rebuild)
        self._sync_post_publish_action_from_material_rules()
        self._refresh_task_overview_from_list()
        self._schedule_publish_policy_modal_if_pending()

        if not hasattr(self, "task_description_card"):
            return

        if preserved_ids:
            target_id = preserved_ids[0]
            rec = (getattr(self, "_records_by_id", {}) or {}).get(target_id)
            if rec is None:
                self.task_description_card.clear()
                return
            found_row = self._find_record_row(target_id)
            if found_row >= 0:
                self.records_table.blockSignals(True)
                try:
                    self.records_table.selectRow(found_row)
                finally:
                    self.records_table.blockSignals(False)
                self.task_description_card.set_task(self._record_with_ui_publish_status(rec))
            else:
                self.task_description_card.clear()
        else:
            self.task_description_card.clear()

    def _record_with_ui_publish_status(
        self, rec: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """任务说明用数据：若该行正是当前队列正在执行的任务，合并 status=running（与表格状态列一致）。"""
        if not rec:
            return None
        active = getattr(self, "_ui_active_publishing_task_id", None)
        if active is None:
            return rec
        rid = rec.get("id")
        if rid is None:
            return rec
        try:
            if int(rid) != int(active):
                return rec
        except (TypeError, ValueError):
            return rec
        merged = dict(rec)
        merged["status"] = "running"
        return merged

    def _sync_post_publish_action_from_material_rules(self) -> None:
        """待发布/失败任务命中媒体库规则时，自动把配置中的发布后文件处理改为「移动」。"""
        recs = [
            r
            for r in getattr(self, "publish_records", None) or []
            if r.get("status") in ("pending", "failed")
        ]
        cur = get_post_publish_action()
        new_a = desired_persisted_post_publish_action(recs, cur)
        if new_a is None:
            return
        hint = message_for_auto_post_publish_change(recs, cur)
        set_post_publish_action(new_a)
        if hasattr(self, "publish_settings_card"):
            self.publish_settings_card.refresh()
        self._pending_publish_policy_modal_hint = (
            hint
            or "待发布列表命中媒体库规则，已将「发布后文件处理」自动调整为「移动至媒体库已发布目录」。"
        )

    def _refresh_task_overview_from_list(self):
        """根据当前任务列表（筛选后）实时更新任务统计卡片。
        
        发布循环进行中时跳过，避免用待发布列表（不含已完成任务）覆盖掉正确的队列统计数字。
        """
        if not hasattr(self, "task_overview_card"):
            return
        # 发布循环运行期间由队列自身维护 task_overview_card，此处不介入
        if getattr(self, "_is_publishing_loop_active", False):
            return
        records = getattr(self, "_filtered_records", None) or []
        task_items = []
        for r in records:
            task_items.append({
                "task_id": r.get("id"),
                "platform": r.get("platform", ""),
                "account": r.get("platform_username", ""),
                "file_basename": os.path.basename(str(r.get("file_path") or "")),
                "status": r.get("status", "pending"),
            })
        total = len(task_items)
        remaining = sum(1 for t in task_items if t.get("status") == "pending")
        self.task_overview_card.set_task_overview(total, remaining, 0, task_items)

    def _set_publish_queue_ui_executing_count(self, n: int) -> None:
        """同步全局「发布中」条数（供工作台统计），并广播事件以便首页立即刷新。"""
        from src.services.publish.publish_queue_ui_state import set_publish_queue_executing_count
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.infrastructure.common.event.event_bus import EventBus
        from src.infrastructure.common.event.events import PublishQueueExecutingCountChangedEvent

        set_publish_queue_executing_count(n)
        try:
            bus = ServiceLocator().get(EventBus)
            bus.publish_sync(PublishQueueExecutingCountChangedEvent(executing_count=n))
        except Exception:
            pass

    def _sync_publish_queue_ui_executing_from_active_id(self) -> None:
        """根据 _ui_active_publishing_task_id 更新全局执行中条数（0 或 1）。"""
        active = getattr(self, "_ui_active_publishing_task_id", None)
        self._set_publish_queue_ui_executing_count(1 if active is not None else 0)

    def _highlight_current_publishing_task(self, task: Dict[str, Any]) -> None:
        """队列执行到某条任务时：表格选中该行、滚到可视区，任务说明显示为「发布中」（库表仍为 pending，仅界面同步）。"""
        try:
            if not hasattr(self, "task_description_card"):
                return
            tid = task.get("id")
            try:
                self._ui_active_publishing_task_id = int(tid) if tid is not None else None
            except (TypeError, ValueError):
                self._ui_active_publishing_task_id = None
            rec = dict(task)
            rec["status"] = "running"
            self.task_description_card.set_task(rec)

            table = getattr(self, "records_table", None)
            if table is None or tid is None:
                return
            try:
                tid_int = int(tid)
            except (TypeError, ValueError):
                return

            found_row = self._find_record_row(tid_int)

            if found_row < 0:
                self._highlighted_task_row = -1
                return

            # 写入缓存，供 _update_single_row_status 使用
            self._highlighted_task_row = found_row
            table.blockSignals(True)
            try:
                table.selectRow(found_row)
                idx = table.model().index(found_row, 0)
                table.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
                # 在状态列实时显示「发布中」，库表仍为 pending，仅界面同步
                from PySide6.QtWidgets import QTableWidgetItem
                status_item = QTableWidgetItem("🔄 发布中")
                status_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
                )
                table.setItem(found_row, self.COL_STATUS, status_item)
            finally:
                table.blockSignals(False)
        finally:
            self._sync_publish_queue_ui_executing_from_active_id()

    def _sort_key_for_record(self, r, mode: str):
        """与列表显示模式一致的排序键，用于排序和发布队列取序。"""
        created = r.get("created_at") or ""
        rid = r.get("id") or 0
        if mode == MODE_PLATFORM:
            platform = r.get("platform") or ""
            first = get_first_platform()
            # 若设置了「排在第一的平台」，该平台键优先（0），其余为 1，再按 platform、created、rid
            prefix = 0 if (first and platform == first) else 1
            return (prefix, platform, created, rid)
        if mode == MODE_ACCOUNT:
            return (r.get("platform") or "", r.get("platform_username") or "", created, rid)
        return (created, rid)

    def _sort_filtered(self, filtered):
        """按当前列表显示模式排序（与发布队列取任务顺序一致）。"""
        mode = get_display_mode()
        return sorted(filtered, key=lambda r: self._sort_key_for_record(r, mode))

    def _refresh_user_id(self):
        """媒小宝账号登录成功后刷新 user_id（发布队列与账号加载依赖此项）。"""
        self.user_id = self._current_user_svc.get_user_id_or_default(1)

    @asyncSlot()
    async def _on_start_publish(self):
        """开始发布任务（需先登录媒小宝软件账号；与抖音/快手等平台侧账号无关）"""
        from qfluentwidgets import InfoBar
        if not self._current_user_svc.is_logged_in():
            try:
                from src.ui.dialogs.login_dialog import LoginDialog
                from src.ui.utils.async_helper import await_qdialog_finished
                parent = self.window() or self
                dialog = LoginDialog(parent)
                dialog.login_success.connect(self._refresh_user_id)
                code = await await_qdialog_finished(dialog)
                if code != int(QDialog.DialogCode.Accepted):
                    InfoBar.warning(
                        "已取消登录",
                        "批量发布需先登录媒小宝软件账号；各平台发布账号请在账号库中登录维护。",
                        parent=self,
                    )
                    return
                self._refresh_user_id()
            except Exception as e:
                logger.error("打开发布前媒小宝登录弹窗失败: %s", e, exc_info=True)
                InfoBar.warning(
                    "无法打开登录窗口",
                    "请通过侧边栏「个人中心」登录媒小宝账号后再试发布。",
                    parent=self,
                )
                return
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.services.publish.publish_service import PublishService
        from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
        from src.domain.repositories.account_repository_async import AccountRepositoryAsync
        from src.domain.repositories.account_group_repository_async import AccountGroupRepositoryAsync
        from src.services.account.account_manager_async import AccountManagerAsync
        from src.infrastructure.common.event.event_bus import EventBus
        
        # 防止重复启动
        if getattr(self, '_is_publishing_loop_active', False):
             InfoBar.warning("运行中", "自动发布队列已在运行中", parent=self)
             return
             
        # 设置状态标识
        self._ui_active_publishing_task_id = None
        self._sync_publish_queue_ui_executing_from_active_id()
        self._is_publishing_loop_active = True
        try:
            # 预先获取依赖
            service_locator = ServiceLocator()
            publish_service = service_locator.get(PublishService)
            # 用作状态依赖注入
            try:
                db_publish = service_locator.get(PublishRecordRepositoryAsync)
            except Exception:
                db_publish = None
                logger.warning("无法获取 PublishRecordRepositoryAsync 实例")

            # 准备账号检测依赖（发布页使用 LoginStatusVerifier 单次校验，需 account_manager 加载 Cookie）
            account_repo = AccountRepositoryAsync()
            group_repo = AccountGroupRepositoryAsync()
            event_bus = service_locator.get(EventBus)
            account_manager = AccountManagerAsync(user_id=self.user_id, event_bus=event_bus)
            await self._run_publish_loop(
                db_publish=db_publish,
                account_repo=account_repo,
                group_repo=group_repo,
                account_manager=account_manager,
                publish_service=publish_service,
            )
        except Exception:
            # _run_publish_loop 内部有自己的 finally 复位逻辑；
            # 这里仅在 _run_publish_loop 之前（依赖组装阶段）异常时做保底复位，
            # 防止 _is_publishing_loop_active 永远卡在 True
            if getattr(self, '_is_publishing_loop_active', False):
                self._is_publishing_loop_active = False
                self._ui_active_publishing_task_id = None
                self._sync_publish_queue_ui_executing_from_active_id()
                logger.warning("发布启动阶段异常，已重置发布状态标志", exc_info=True)

    async def _mark_task_failed_in_loop(
        self,
        task_id,
        error_message: str,
        *,
        db_publish,
        post_publish_action: str,
        file_groups: dict,
        run_task_items: list,
        run_total: int,
        pending_count: int,
        failure_kind: Optional[str] = None,
    ) -> None:
        """发布循环内的统一失败标记：更新 DB、总览卡片、内存状态、文件分组。"""
        from src.infrastructure.common.post_publish_file_handler import PostPublishFileHandler
        self.log_widget.start_current_task()
        self.log_widget.append_error(f"任务 {task_id} 发布失败：{error_message}")
        if db_publish:
            await db_publish.update_status(
                task_id,
                'failed',
                error_message=error_message,
                failure_kind=failure_kind or classify_publish_failure(error_message),
            )
        if post_publish_action != "none":
            PostPublishFileHandler.on_task_failed(task_id, file_groups)
        for item in run_task_items:
            if item.get("task_id") == task_id:
                item["status"] = "failed"
                break
        remaining = pending_count - 1
        completed = run_total - remaining
        self.task_overview_card.set_task_overview(run_total, remaining, completed, run_task_items)
        self._update_task_status_in_memory(task_id, "failed", error_message=error_message)
        await self._interruptible_sleep_for_publish_queue(1.0)

    def _do_stop_publish_queue(self, *, manual: bool = True) -> None:
        """公共停止原语：置停止标志、唤醒暂停 Event、取消当前发布 Task。

        由 _on_stop_publish（手动停止）和 _stop_queue_on_session_evicted（被顶下线）共同调用，
        避免两处各自维护相同的三步操作（置标志→set event→cancel task）出现遗漏。

        Args:
            manual: True 表示用户主动点「停止」，会同步设置 _manual_stop_requested 防止自动重启。
        """
        self._is_publishing_loop_active = False
        self._ui_active_publishing_task_id = None
        self._sync_publish_queue_ui_executing_from_active_id()
        if manual:
            self._manual_stop_requested = True
        if hasattr(self, "publish_pause_event"):
            self.publish_pause_event.set()
        ct = getattr(self, "current_task", None)
        if ct is not None and not ct.done():
            try:
                ct.cancel()
            except Exception as e:
                logger.warning("取消当前发布任务时异常（可忽略）: %s", e)

    async def _publish_queue_checkpoint(self) -> None:
        """队列协作点：响应「停止」与「暂停」。停止则抛 CancelledError；暂停则阻塞直至点「继续」或停止。

        说明：停止时必须配合 `_on_stop_publish` 里对 `publish_pause_event.set()`，
        否则协程可能永久卡在 `Event.wait()`（此前为典型「点了停止没反应」原因之一）。"""
        if not getattr(self, "_is_publishing_loop_active", False):
            raise asyncio.CancelledError()
        await self.publish_pause_event.wait()
        if not getattr(self, "_is_publishing_loop_active", False):
            raise asyncio.CancelledError()

    async def _interruptible_sleep_for_publish_queue(self, total_seconds: float) -> None:
        """可打断等待：期间反复检查停止/暂停，避免长 sleep 内无法响应按钮。"""
        if total_seconds <= 0:
            await self._publish_queue_checkpoint()
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + float(total_seconds)
        while True:
            await self._publish_queue_checkpoint()
            now = loop.time()
            if now >= deadline:
                return
            chunk = min(0.25, deadline - now)
            await asyncio.sleep(chunk)

    async def _await_with_publish_stop_cancel(self, awaitable):
        """对账号检测等长 IO 轮询「停止」：无原生取消点时，停止后取消子协程并尽快退出队列。"""
        task = asyncio.ensure_future(awaitable)
        if hasattr(task, "set_name"):
            task.set_name("publish.await_with_stop_cancel")
        if isinstance(task, asyncio.Task):
            get_async_task_registry().register(
                task,
                group="publish",
                log_exceptions=False,
            )
        try:
            while not task.done():
                if not getattr(self, "_is_publishing_loop_active", False):
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        raise asyncio.CancelledError()
                await asyncio.sleep(0.2)
            exc = task.exception()
            if exc is not None:
                raise exc
            return task.result()
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            raise

    async def _sleep_between_publish_tasks(
        self, had_more_pending: bool, next_same_platform: bool,
        *, prev_task_failed: bool = False,
    ) -> None:
        """单次 publish_single 结束后：队列为空则短结束喘息；否则仅当下一任务与当前同平台时按设置随机间隔，跨平台不等待该间隔。
        prev_task_failed=True 时强制至少等 3 秒，让浏览器页面状态稳定。"""
        _MIN_FAIL_RECOVERY = 3.0
        if not self._is_publishing_loop_active:
            await asyncio.sleep(0)
            return
        if not had_more_pending:
            await self._interruptible_sleep_for_publish_queue(0.6)
            return
        if not next_same_platform:
            user_log = logging.getLogger("publish.user_log")
            user_log.info("[间隔] 下一任务为其他平台，跳过任务间隔，短暂衔接后继续")
            await self._interruptible_sleep_for_publish_queue(0.5)
            return
        current_platform = str(getattr(self, "_current_publish_platform", "") or "")
        base = get_effective_publish_interval_seconds(current_platform)
        if base > 0:
            delay = sample_publish_interval_delay_seconds(base)
        else:
            delay = 0.5
        if prev_task_failed:
            delay = max(delay, _MIN_FAIL_RECOVERY)
        logging.getLogger("publish.user_log").info(
            f"[间隔] 同平台下一任务：等待 {delay:.1f} 秒后继续"
        )
        await self._interruptible_sleep_for_publish_queue(delay)

    async def _precheck_accounts_online_before_publish(self, pending_records, account_repo, account_manager) -> bool:
        """发布前批量检测账号在线状态。返回 True 表示继续发布，False 表示终止。"""
        if not get_precheck_account_online_enabled():
            return True
        if not pending_records:
            return True
        user_log = logging.getLogger("publish.user_log")
        user_log.info("[检测] 发布前账号在线检测：开始批量检查")
        self._publish_verified_accounts = set()

        def _normalize_offline_reason(reason: str) -> str:
            """将底层英文/技术错误原因转换为用户可读中文。"""
            r = (reason or "").strip()
            if not r:
                return "未登录"
            low = r.lower()
            if "request failed" in low:
                return "请求失败"
            if "timeout" in low or "timed out" in low:
                return "请求超时"
            if "forbidden" in low or "403" in low:
                return "无权限（403）"
            if "unauthorized" in low or "401" in low:
                return "未授权（401）"
            return r

        def _format_offline_account_item(raw_item: str, idx: int) -> str:
            """将 platform:account（原因） 格式化成更易读的列表项。"""
            item = (raw_item or "").strip()
            platform = ""
            account = item
            reason = ""

            if "（" in item and item.endswith("）"):
                try:
                    before, after = item.rsplit("（", 1)
                    item = before.strip()
                    reason = after[:-1].strip()
                except Exception:
                    reason = ""

            if ":" in item:
                try:
                    platform, account = item.split(":", 1)
                    platform = (platform or "").strip()
                    account = (account or "").strip()
                except Exception:
                    platform, account = "", item

            platform_cn = get_platform_display_name(platform) if platform else platform
            reason_cn = _normalize_offline_reason(reason)
            if platform_cn:
                return f"{idx}. {platform_cn}：{account}（{reason_cn}）"
            return f"{idx}. {account}（{reason_cn}）"

        def _build_offline_accounts_block(accounts: list, *, max_items: int = 8) -> str:
            show = accounts[:max_items]
            lines = [_format_offline_account_item(a, i + 1) for i, a in enumerate(show)]
            extra = ""
            if len(accounts) > max_items:
                extra = f"\n… 还有 {len(accounts) - max_items} 个账号未展开"
            return "\n".join(lines) + extra
        account_map = {}
        for rec in pending_records:
            key = ((rec.get("platform") or "").strip(), (rec.get("platform_username") or "").strip())
            if key[0] and key[1]:
                account_map[key] = rec
        offline_accounts = []
        for platform, account_name in account_map.keys():
            platform_accounts = await self._await_with_publish_stop_cancel(
                account_repo.find_all(user_id=None, platform=platform)
            )
            matched_acc = next(
                (a for a in (platform_accounts or []) if (a.get("platform_username") or "").strip() == account_name),
                None,
            )
            if not matched_acc:
                offline_accounts.append(f"{platform}:{account_name}（账号库未匹配）")
                continue
            if matched_acc.get("publish_risk_state") == "quarantined":
                reason = matched_acc.get("publish_risk_reason") or "发布风险隔离"
                offline_accounts.append(f"{platform}:{account_name}（风险隔离：{reason}）")
                continue
            acc_id = matched_acc.get("id")
            cookie_dict = await self._await_with_publish_stop_cancel(
                account_manager.load_account_cookie(acc_id, merge_storage_state=True)
            )
            if not cookie_dict or not isinstance(cookie_dict, dict):
                offline_accounts.append(f"{platform}:{account_name}（Cookie缺失）")
                continue
            from src.services.account.login_status_verifier import verify_login_status
            res_info = await self._await_with_publish_stop_cancel(
                verify_login_status(
                    platform=platform,
                    cookies=cookie_dict,
                    account_id=acc_id,
                    account_name=account_name,
                    user_agent=matched_acc.get("user_agent"),
                    http_session=None,
                    timeout=15,
                )
            )
            if not res_info.get("is_logged_in"):
                reason = res_info.get("error", "未登录")
                offline_accounts.append(f"{platform}:{account_name}（{reason}）")
                try:
                    await account_manager.update_account_login_status(acc_id, "offline")
                except Exception:
                    pass
            else:
                self._publish_verified_accounts.add((platform, account_name))
        if not offline_accounts:
            user_log.info("[检测] 发布前账号在线检测：全部在线，继续发布")
            return True
        from src.ui.utils.fluent_dialogs import show_three_choice_async

        offline_block = _build_offline_accounts_block(offline_accounts, max_items=8)

        # 全部掉线：只允许去账号管理或取消
        if len(offline_accounts) == len(account_map):
            content = (
                f"本轮任务涉及账号已全部离线（{len(offline_accounts)}/{len(account_map)}）。\n\n"
                f"离线账号如下：\n{offline_block}\n\n"
                "建议先去「账号管理」重新登录，再回来发布。"
            )
            choice = await show_three_choice_async(
                self.window() or self,
                "账号全部掉线",
                content,
                yes_text="去账号管理",
                no_text="取消发布",
                cancel_text="关闭",
            )
            if choice == "yes" and self.window() and callable(getattr(self.window(), "navigate_to", None)):
                self.window().navigate_to("account_page")
            return False

        # 部分掉线：允许「跳过掉线账号继续发布」或「去账号管理」或「取消」
        content = (
            f"检测到部分账号离线（{len(offline_accounts)}/{len(account_map)}）。\n\n"
            f"离线账号如下：\n{offline_block}\n\n"
            "你可以选择跳过离线账号继续发布其余任务，或先去「账号管理」重新登录。"
        )
        choice = await show_three_choice_async(
            self.window() or self,
            "部分账号掉线",
            content,
            yes_text="继续发布其余任务",
            no_text="去账号管理",
            cancel_text="取消发布",
        )
        if choice == "no" and self.window() and callable(getattr(self.window(), "navigate_to", None)):
            self.window().navigate_to("account_page")
            return False
        return choice == "yes"

    async def _run_publish_loop(self, db_publish, account_repo, group_repo, account_manager, publish_service):
        """执行发布循环"""
        from src.infrastructure.common.post_publish_file_handler import PostPublishFileHandler

        # 提前检测是否有待发布任务，避免先禁用按钮再立即复位导致闪烁
        scoped_ids = self._publish_queue_scoped_pending_ids()
        if not scoped_ids:
            self.log_widget.append_text(
                "⚠️ 当前筛选结果中没有待发布任务，未启动队列。"
            )
            InfoBar.warning(
                "无任务",
                "当前表格筛选结果内没有待发布任务，可调整筛选或状态后再试",
                parent=self,
            )
            # 提前返回时必须复位，防止标志永久卡在 True 导致按钮无法再次点击
            self._is_publishing_loop_active = False
            return

        self.log_widget.append_text("======== 🚀 启动自动发布队列 ========")
        
        # 更新按钮状态
        if hasattr(self, 'btn_start_publish'):
            self.btn_start_publish.setEnabled(False)
        if hasattr(self, 'btn_stop_publish'):
            self.btn_stop_publish.setEnabled(True)
        
        # 重置暂停事件
        self.publish_pause_event.set()
        if hasattr(self, 'btn_pause_publish'):
            self.btn_pause_publish.setEnabled(True)
            self.btn_pause_publish.setText("暂停")
            try:
                from qfluentwidgets import FluentIcon
                self.btn_pause_publish.setIcon(FluentIcon.GAME)
            except Exception as e:
                logger.warning("设置暂停按钮图标失败: %s", e)

        run_task_items = None  # 本轮发布的任务列表快照（用于左侧总览）
        run_total = 0
        # 发布后文件操作：队列启动时按配置 + 媒体库规则解析一次，整个会话保持不变
        post_publish_action = "none"
        file_groups: dict = {}

        self._publish_queue_natural_complete = False
        self._publish_one_shot_shutdown_this_run = False
        try:
            self._publish_queue_scoped_ids = scoped_ids
            pending_for_policy = [
                r
                for r in self.publish_records
                if r.get("status") == "pending"
                and r.get("id") is not None
                and int(r["id"]) in scoped_ids
            ]
            post_publish_action = resolve_effective_post_publish_action_for_queue(
                pending_for_policy,
                get_post_publish_action(),
            )
            self.log_widget.append_text(
                f"📋 本轮仅发布当前表格中的任务，待发布 {len(scoped_ids)} 条（已按筛选范围锁定）。"
            )

            # 队列启动时按平台预热账号缓存，避免每条任务重复全平台查库
            # 结构：{platform: [account_dict, ...]}
            _platform_accounts_cache: dict = {}
            _scoped_platforms = {
                r.get("platform") for r in pending_for_policy if r.get("platform")
            }
            for _plat in _scoped_platforms:
                try:
                    _plat_accounts = await self._await_with_publish_stop_cancel(
                        account_repo.find_all(user_id=None, platform=_plat)
                    )
                    _platform_accounts_cache[_plat] = _plat_accounts or []
                except Exception as _cache_e:
                    logger.warning("预热账号缓存失败（平台=%s）: %s", _plat, _cache_e)
                    _platform_accounts_cache[_plat] = []

            # 构建有序发布队列快照（deque），避免每轮从全量 publish_records 重新筛选
            from collections import deque as _deque
            scope = self._publish_queue_scoped_ids or frozenset()
            _initial_pending = [
                r for r in self.publish_records
                if r.get("status") == "pending"
                and r.get("id") is not None
                and int(r["id"]) in scope
            ]
            should_continue = await self._precheck_accounts_online_before_publish(
                _initial_pending, account_repo, account_manager
            )
            if not should_continue:
                self.log_widget.append_warning("⚠️ 发布前账号在线检测未通过，本轮发布已终止。")
                self._publish_queue_natural_complete = False
                return
            mode = get_display_mode()
            _initial_pending.sort(key=lambda r: self._sort_key_for_record(r, mode))
            _pending_deque: _deque = _deque(_initial_pending)

            # 队列启动瞬间快照：发布后关机为一次性选项，跑完本轮（任意结束方式）后清除
            self._publish_one_shot_shutdown_this_run = (
                is_publish_after_shutdown_one_shot_armed()
            )

            _current_retry_count = 0
            _risk_blocked_accounts: set[tuple[str, str]] = set()
            _platform_risk_accounts: dict[str, set[str]] = {}
            _risk_blocked_platforms: set[str] = set()
            self._publish_verified_accounts = getattr(self, "_publish_verified_accounts", set())

            while self._is_publishing_loop_active:
                await self._publish_queue_checkpoint()
                # 跳过已不是 pending 的任务（可能在循环中被标记为 failed/success）
                while _pending_deque:
                    _head = _pending_deque[0]
                    _head_id = _head.get("id")
                    _live = self._get_record_by_id(_head_id)
                    if _live and _live.get("status") == "pending":
                        break
                    _pending_deque.popleft()
                pending_records = list(_pending_deque)
                if not pending_records:
                    import src.ui.pages.publish.list_settings_dialog as lsd
                    max_retry = getattr(lsd, 'get_publish_queue_retry_count', lambda: 0)()
                    if _current_retry_count < max_retry:
                        failed_in_scope = [
                            r
                            for r in (
                                self._get_record_by_id(rid)
                                for rid in (self._publish_queue_scoped_ids or ())
                            )
                            if r and r.get("status") == "failed"
                            and (r.get("platform") or "") not in _risk_blocked_platforms
                            and (
                                (r.get("platform") or ""),
                                (r.get("platform_username") or "").strip(),
                            ) not in _risk_blocked_accounts
                        ]
                        if failed_in_scope:
                            _current_retry_count += 1
                            self.log_widget.append_text(
                                f"⏳ 当前队列已执行完毕。发现 {len(failed_in_scope)} 个失败任务，准备执行第 {_current_retry_count} 次发布队列重试..."
                            )
                            for f_rec in failed_in_scope:
                                tid = f_rec.get("id")
                                if db_publish:
                                    await db_publish.update_status(tid, 'pending', error_message="")
                                if post_publish_action != "none":
                                    PostPublishFileHandler.on_task_reset_to_pending(tid, file_groups)
                                self._update_task_status_in_memory(tid, "pending", error_message="")
                                if run_task_items is not None:
                                    for item in run_task_items:
                                        if item.get("task_id") == tid:
                                            item["status"] = "pending"
                                            break
                                _pending_deque.append(f_rec)
                            
                            self.log_widget.append_text("✅ 已成功将失败任务复位为待发布，即将重新进入发布队列。")
                            continue

                    self.log_widget.append_text(
                        "✅ 当前筛选范围内的待发布任务已处理完毕，队列结束。"
                    )
                    InfoBar.success(
                        "队列结束",
                        "当前表格筛选范围内的待办任务均已处理完毕！",
                        parent=self,
                    )
                    self._publish_queue_natural_complete = True
                    break

                # 首次进入循环时初始化任务总览快照（以当前表格视图为底本，避免总计数字跳变）
                if run_task_items is None:
                    records_snapshot = getattr(self, "_filtered_records", None) or []
                    run_total = len(records_snapshot)
                    run_task_items = []
                    for r in records_snapshot:
                        platform = r.get("platform") or ""
                        account = (r.get("platform_username") or "").strip()
                        fp = r.get("file_path") or ""
                        paths = [p.strip().lower() for p in fp.split(",")] if fp else []
                        is_image = any(p.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")) for p in paths)
                        type_zh = "图文" if is_image else "视频"
                        basename = os.path.basename(paths[0].strip()) if paths else ""
                        run_task_items.append({
                            "task_id": r.get("id"),
                            "platform": platform,
                            "account": account,
                            "type_zh": type_zh,
                            "file_basename": basename,
                            "status": r.get("status", "pending"),
                        })
                    
                    initial_remaining = sum(1 for item in run_task_items if item["status"] == "pending")
                    self.task_overview_card.set_task_overview(run_total, initial_remaining, 0, run_task_items)
                    # 构建文件引用分组表（仅在队列首次启动时执行一次）
                    if post_publish_action != "none":
                        try:
                            file_groups = await PostPublishFileHandler.build_file_groups(
                                pending_records, account_repo, group_repo
                            )
                        except Exception as _fg_e:
                            logger.warning("构建文件分组表失败（不影响发布）: %s", _fg_e)

                task = pending_records[0]
                had_more_pending = len(pending_records) > 1
                next_task = pending_records[1] if had_more_pending else None
                same_account_next = (
                    next_task
                    and task.get("platform") == next_task.get("platform")
                    and task.get("platform_username") == next_task.get("platform_username")
                )
                # 任务间隔仅在同平台连续任务之间生效（与发布设置说明一致）
                same_platform_next = bool(
                    next_task
                    and (task.get("platform") or "") == (next_task.get("platform") or "")
                )
                close_browser_after = not same_account_next
                task_id = task.get('id')
                
                account_name = (task.get('platform_username') or '').strip()
                platform = task.get('platform')
                file_path = task.get('file_path')
                self._current_publish_platform = platform or ""
                if (platform or "") in _risk_blocked_platforms:
                    skip_msg = "同平台已有多个账号在本轮发布中触发验证、频繁操作或账号异常提示，已停止该平台后续任务，请人工检查后再继续。"
                    self.log_widget.append_warning(f"⚠️ {skip_msg}")
                    if db_publish:
                        await db_publish.update_status(
                            task_id,
                            'failed',
                            error_message=skip_msg,
                            failure_kind=PublishFailureKind.RISK_CHALLENGE.value,
                        )
                    if post_publish_action != "none":
                        PostPublishFileHandler.on_task_failed(task_id, file_groups)
                    if run_task_items:
                        for item in run_task_items:
                            if item.get("task_id") == task_id:
                                item["status"] = "failed"
                                break
                    self._update_task_status_in_memory(task_id, "failed", error_message=skip_msg)
                    if _pending_deque and _pending_deque[0].get("id") == task_id:
                        _pending_deque.popleft()
                    continue
                if (platform or "", account_name) in _risk_blocked_accounts:
                    skip_msg = "检测到该账号/平台本轮已有异常验证或操作频繁提示，已停止后续任务，请人工检查后再继续。"
                    self.log_widget.append_warning(f"⚠️ {skip_msg}")
                    if db_publish:
                        await db_publish.update_status(
                            task_id,
                            'failed',
                            error_message=skip_msg,
                            failure_kind=PublishFailureKind.RISK_CHALLENGE.value,
                        )
                    if post_publish_action != "none":
                        PostPublishFileHandler.on_task_failed(task_id, file_groups)
                    if run_task_items:
                        for item in run_task_items:
                            if item.get("task_id") == task_id:
                                item["status"] = "failed"
                                break
                    self._update_task_status_in_memory(task_id, "failed", error_message=skip_msg)
                    if _pending_deque and _pending_deque[0].get("id") == task_id:
                        _pending_deque.popleft()
                    continue
                
                # 识别当前发布类型
                publish_type = "video"
                if file_path:
                    # 分辨单个或多个文件，只要存在图片拓展即认为是图文发布（过滤文件夹标记条目）
                    _folder_pfx = "__FOLDER__:"
                    paths = [
                        p.strip().lower() for p in file_path.split(',')
                        if p.strip() and not p.strip().startswith(_folder_pfx)
                    ]
                    if any(p.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')) for p in paths):
                        publish_type = "image"
                        
                pub_type_zh = "图文" if publish_type == "image" else "视频"
                
                # 显式输出终端日志
                logger.info(f"判断发布类型为: {pub_type_zh}发布 (publish_type={publish_type}), 解析文件: {file_path}")

                title = task.get('title') or ""
                desc = task.get('description') or ""
                tags_str = task.get('tags') or ""
                tags = [t.strip() for t in tags_str.split(',') if t.strip()] if tags_str else []
                
                if not account_name or not platform or not file_path:
                    await self._mark_task_failed_in_loop(
                        task_id, "任务信息不完整",
                        db_publish=db_publish, post_publish_action=post_publish_action,
                        file_groups=file_groups, run_task_items=run_task_items,
                        run_total=run_total, pending_count=len(pending_records),
                    )
                    continue

                file_err = publish_file_missing_error(file_path)
                if file_err:
                    await self._mark_task_failed_in_loop(
                        task_id, file_err,
                        db_publish=db_publish, post_publish_action=post_publish_action,
                        file_groups=file_groups, run_task_items=run_task_items,
                        run_total=run_total, pending_count=len(pending_records),
                    )
                    continue

                wt_err = wechat_video_short_title_validation_error(platform, title)
                if wt_err:
                    await self._mark_task_failed_in_loop(
                        task_id, wt_err,
                        db_publish=db_publish, post_publish_action=post_publish_action,
                        file_groups=file_groups, run_task_items=run_task_items,
                        run_total=run_total, pending_count=len(pending_records),
                    )
                    continue

                # 检测定时发布时间：定时发布必须晚于当前时间 2 小时 10 分钟
                scheduled_time_str = task.get("scheduled_publish_time")
                if scheduled_time_str:
                    from datetime import datetime, timedelta
                    _fail_kwargs = dict(
                        db_publish=db_publish, post_publish_action=post_publish_action,
                        file_groups=file_groups, run_task_items=run_task_items,
                        run_total=run_total, pending_count=len(pending_records),
                    )
                    try:
                        scheduled_dt = datetime.strptime(scheduled_time_str, "%Y-%m-%d %H:%M")
                        now = datetime.now()
                        min_schedule_time = now + timedelta(hours=2, minutes=10)
                        if scheduled_dt <= min_schedule_time:
                            await self._mark_task_failed_in_loop(
                                task_id,
                                f"定时发布时间太近（{scheduled_time_str}），请修改后再发布",
                                **_fail_kwargs,
                            )
                            continue
                    except ValueError as e:
                        logger.warning(f"解析定时发布时间失败: {scheduled_time_str}, 错误: {e}")
                        await self._mark_task_failed_in_loop(
                            task_id,
                            f"定时发布时间格式错误（{scheduled_time_str}），请修正后再发布",
                            **_fail_kwargs,
                        )
                        continue

                # 长耗时步骤前再检查一次，避免「点停止后仍卡在账号检测」
                await self._publish_queue_checkpoint()

                # 用户可见日志（发布日志框只监听 publish.user_log）；「发布中」UI 在账号检测通过后再切换
                user_log = logging.getLogger("publish.user_log")
                _fp_parts = [
                    p.strip() for p in str(file_path).split(",")
                    if p.strip() and not p.strip().startswith("__FOLDER__:")
                ] if file_path else []
                basename = os.path.basename(_fp_parts[0]) if _fp_parts else ""
                platform_cn = get_platform_display_name((platform or "").strip())
                user_log.info(f"[准备] 平台={platform_cn} 账号={account_name} 类型={pub_type_zh} 任务ID={task_id}")
                user_log.info(f"[准备] 文件={basename} 路径={file_path}")

                # ==== 1. 严格的前置状态校验 ====
                user_log.info("[检测] 账号在线检测：开始")
                try:
                    # 优先从队列启动时预热的缓存中取账号列表，避免每条任务重复查库；
                    # 若缓存中无该平台（可能是循环中途新增），回退到实时查询
                    platform_accounts = _platform_accounts_cache.get(platform)
                    if platform_accounts is None:
                        platform_accounts = await self._await_with_publish_stop_cancel(
                            account_repo.find_all(user_id=None, platform=platform)
                        )
                        _platform_accounts_cache[platform] = platform_accounts or []
                    matched_acc = next(
                        (a for a in platform_accounts
                         if (a.get('platform_username') or '').strip() == account_name),
                        None
                    )
                    
                    if not matched_acc:
                         raise ValueError(f"系统账号库中未匹配到该账号 '{account_name}'")
                    
                    # 与账号库刷新一致：合并 storage_state，避免仅 cookies.json 子集导致误判掉线
                    if matched_acc.get("publish_risk_state") == "quarantined":
                        reason = matched_acc.get("publish_risk_reason") or "发布风险隔离"
                        await self._mark_task_failed_in_loop(
                            task_id,
                            f"账号已处于发布风险隔离状态，请在账号管理页人工确认后解除：{reason}",
                            db_publish=db_publish,
                            post_publish_action=post_publish_action,
                            file_groups=file_groups,
                            run_task_items=run_task_items,
                            run_total=run_total,
                            pending_count=len(pending_records),
                            failure_kind=PublishFailureKind.RISK_CHALLENGE.value,
                        )
                        continue
                    acc_id = matched_acc.get('id')
                    platform_username = matched_acc.get('platform_username') or matched_acc.get('account_name', '')
                    plat = matched_acc.get('platform', '')
                    cookie_dict = await self._await_with_publish_stop_cancel(
                        account_manager.load_account_cookie(
                            acc_id, merge_storage_state=True
                        )
                    )
                    if not cookie_dict or not isinstance(cookie_dict, dict):
                        raise ValueError("Cookie 文件不存在或格式错误")
                    verified_key = ((plat or "").strip(), (platform_username or "").strip())
                    if verified_key in getattr(self, "_publish_verified_accounts", set()):
                        res_info = {"is_logged_in": True}
                    else:
                        from src.services.account.login_status_verifier import verify_login_status
                        res_info = await self._await_with_publish_stop_cancel(
                            verify_login_status(
                                platform=plat,
                                cookies=cookie_dict,
                                account_id=acc_id,
                                account_name=platform_username,
                                user_agent=matched_acc.get('user_agent'),
                                http_session=None,
                                timeout=15,
                            )
                        )
                        if res_info.get("is_logged_in"):
                            self._publish_verified_accounts.add(verified_key)
                    
                    _fail_kw = dict(
                        db_publish=db_publish, post_publish_action=post_publish_action,
                        file_groups=file_groups, run_task_items=run_task_items,
                        run_total=run_total, pending_count=len(pending_records),
                    )
                    if not res_info.get('is_logged_in'):
                         error_reason = res_info.get('error', 'Cookie失效或未登录')
                         user_log.warning(f"[检测] 账号在线检测：掉线（{error_reason}）")
                         try:
                             await account_manager.update_account_login_status(acc_id, "offline")
                             user_log.info("[检测] 已将账号库中该账号登录状态同步为「离线」")
                         except Exception as sync_e:
                             logger.warning("同步账号库登录状态为离线失败: %s", sync_e)
                         await self._mark_task_failed_in_loop(
                             task_id, f"账号已掉线：{error_reason}", **_fail_kw,
                         )
                         continue
                    else:
                         user_log.info("[检测] 账号在线检测：在线")
                except asyncio.CancelledError:
                    raise
                except Exception as check_e:
                    user_log.warning(f"[检测] 账号在线检测：异常（{str(check_e)}）")
                    await self._mark_task_failed_in_loop(
                        task_id, f"账号检测异常: {str(check_e)}",
                        db_publish=db_publish, post_publish_action=post_publish_action,
                        file_groups=file_groups, run_task_items=run_task_items,
                        run_total=run_total, pending_count=len(pending_records),
                    )
                    continue

                # 账号检测通过后再标「发布中」，避免检测阶段点停止时表格仍显示发布中
                self.log_widget.start_current_task()
                current_index = run_total - len(pending_records) + 1
                for item in run_task_items:
                    if item.get("task_id") == task_id:
                        item["status"] = "running"
                        break
                self.task_overview_card.set_task_overview(run_total, len(pending_records), current_index, run_task_items)
                self._highlight_current_publishing_task(task)

                # ==== 2. 检查暂停状态 / 执行发布业务 ====
                result = None  # 提前初始化，防止 finally 中因任务取消路径未赋值触发 UnboundLocalError
                try:
                    await self._publish_queue_checkpoint()
                    
                    # 获取配置参数（显示浏览器在「发布设置」中配置）
                    is_headful = get_publish_show_browser()
                    speed_rate = get_speed_rate()
                    speed_label = SPEED_OPTIONS[get_speed_index()][0]
                    user_log.info(f"[启动] 开始启动发布流程（速度：{speed_label}）")
                    # 让出一帧给 Qt 事件循环处理 UI 更新（日志显示、按钮状态等），避免界面卡顿
                    await asyncio.sleep(0)
                             
                    # 开始包装一层单独的任务执行供中途可取消操作
                    self.current_task = get_async_task_registry().create_task(publish_service.publish_single(
                        user_id=self.user_id,
                        publish_record_id=task_id,
                        account_name=account_name,
                        platform=platform,
                        file_path=file_path,
                        publish_type=publish_type,
                        title=title,
                        description=desc,
                        tags=tags,
                        headless=not is_headful,
                        speed_rate=speed_rate,
                        pause_event=self.publish_pause_event,
                        cover_type=task.get("cover_type") or ("custom" if task.get("cover_path") else "first_frame"),
                        cover_path=task.get("cover_path"),
                        scheduled_publish_time=task.get("scheduled_publish_time"),
                        privacy_settings=task.get("privacy_settings"),
                        close_browser_after=close_browser_after,
                        poi_info=task.get("poi_info"),
                        wechat_empty_location_open_picker=task.get(
                            "wechat_empty_location_open_picker"
                        ),
                        cart_info=task.get("cart_info"),
                        anchor_info=task.get("anchor_info"),
                        micro_app_info=task.get("micro_app_info"),
                        music_info=task.get("music_info"),
                    ), name=f"publish.single.{task_id}", group="publish", log_exceptions=False)
                    
                    _SINGLE_TASK_TIMEOUT = 600  # 单任务最大执行时间 10 分钟
                    try:
                        result = await asyncio.wait_for(
                            asyncio.shield(self.current_task),
                            timeout=_SINGLE_TASK_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        self.current_task.cancel()
                        try:
                            await self.current_task
                        except (asyncio.CancelledError, Exception):
                            pass
                        result = None
                        _timeout_msg = f"任务执行超时（已超过 {_SINGLE_TASK_TIMEOUT // 60} 分钟），已强制终止"
                        self.log_widget.append_error(f"⏰ {_timeout_msg}")
                        if db_publish:
                            await db_publish.update_status(
                                task_id,
                                'failed',
                                error_message=_timeout_msg,
                                failure_kind=PublishFailureKind.NETWORK_ERROR.value,
                            )
                        if post_publish_action != "none":
                            PostPublishFileHandler.on_task_failed(task_id, file_groups)
                        for item in run_task_items:
                            if item.get("task_id") == task_id:
                                item["status"] = "failed"
                                break
                        self._update_task_status_in_memory(task_id, "failed", error_message=_timeout_msg)
                        remaining_after = len(pending_records) - 1
                        self.task_overview_card.set_task_overview(run_total, remaining_after, run_total - remaining_after, run_task_items)
                        continue
                    
                    if result and result.success:
                         self.log_widget.append_success(
                             f"🎉 任务发布成功！URL: {result.publish_url}\n"
                             "（已写入数据库，可在「发布记录」页查看本条历史）"
                         )
                         if db_publish:
                             await db_publish.update_status(
                                 task_id,
                                 'success',
                                 publish_url=result.publish_url,
                                 diagnostic_path=getattr(result, "diagnostic_path", None),
                             )
                         if post_publish_action != "none":
                             await PostPublishFileHandler.on_task_success(
                                 task_id, task, file_groups, post_publish_action, user_log,
                                 publish_repo=db_publish,
                             )
                         for item in run_task_items:
                             if item.get("task_id") == task_id:
                                 item["status"] = "success"
                                 break
                         self._update_task_status_in_memory(task_id, "success")
                    else:
                         msg = result.error_message if result else "未知错误"
                         failure_kind = (
                             getattr(result, "failure_kind", None)
                             if result
                             else classify_publish_failure(msg)
                         )
                         failure_kind = failure_kind or classify_publish_failure(msg)
                         self.log_widget.append_error(f"❌ 任务发布失败: {msg}")
                         blocking_failure = is_blocking_failure_kind(failure_kind)
                         if should_stop_on_risk_prompt() and (blocking_failure or _looks_like_platform_risk_prompt(msg)):
                             _risk_blocked_accounts.add((platform or "", account_name))
                             account_set = _platform_risk_accounts.setdefault(platform or "", set())
                             if account_name:
                                 account_set.add(account_name)
                             if len(account_set) >= 2:
                                 _risk_blocked_platforms.add(platform or "")
                                 user_log.warning(
                                     "[风险控制] 同平台已有多个账号触发风险，停止本轮该平台后续任务: 平台=%s 账号数=%s",
                                     platform,
                                     len(account_set),
                                 )
                             try:
                                 acc_id_to_quarantine = matched_acc.get("id") if isinstance(matched_acc, dict) else None
                                 if acc_id_to_quarantine:
                                     await account_repo.mark_publish_quarantined(
                                         int(acc_id_to_quarantine),
                                         str(msg or "发布触发平台风险提示"),
                                     )
                                     if isinstance(matched_acc, dict):
                                         matched_acc["publish_risk_state"] = "quarantined"
                                         matched_acc["publish_risk_reason"] = str(msg or "")
                             except Exception as risk_e:
                                 logger.warning("持久化账号发布风险隔离失败: %s", risk_e)
                             user_log.warning(
                                 "[风险控制] 检测到平台异常提示，停止本轮该账号后续任务: 平台=%s 账号=%s",
                                 platform,
                                 account_name,
                             )
                         diagnostic_path = getattr(result, "diagnostic_path", None) if result else None
                         if not diagnostic_path and msg and "SubmitStep" in msg:
                             logger.warning(
                                 "发布失败但未回传 diagnostic_path: task_id=%s msg=%s",
                                 task_id,
                                 msg[:120],
                             )
                         self._enqueue_publish_failure_notice(
                             error_message=msg,
                             diagnostic_path=diagnostic_path,
                             task_id=task_id,
                             platform=task.get("platform") or "",
                         )
                         if db_publish:
                             await db_publish.update_status(
                                 task_id,
                                 'failed',
                                 error_message=msg,
                                 diagnostic_path=diagnostic_path,
                                  failure_kind=failure_kind,
                             )
                         if post_publish_action != "none":
                             PostPublishFileHandler.on_task_failed(task_id, file_groups)
                         for item in run_task_items:
                             if item.get("task_id") == task_id:
                                 item["status"] = "failed"
                                 break
                         self._update_task_status_in_memory(task_id, "failed", error_message=msg)
                    remaining_after = len(pending_records) - 1
                    self.task_overview_card.set_task_overview(run_total, remaining_after, run_total - remaining_after, run_task_items)
                             
                except asyncio.CancelledError:
                    self.log_widget.append_warning("⚠️ 当前发布任务被停止，已恢复为「待发布」，下次继续。")
                    # 停止时任务未完成发布，应恢复为 pending（而非 cancelled），
                    # 否则 target_statuses=["pending","failed"] 过滤后该任务从列表消失
                    if db_publish and task_id:
                        await db_publish.update_status(task_id, 'pending', error_message='')
                    for item in run_task_items:
                        if item.get("task_id") == task_id:
                            item["status"] = "pending"
                            break
                    self._update_task_status_in_memory(task_id, "pending")
                    self.task_overview_card.set_task_overview(run_total, len(pending_records), run_total - len(pending_records), run_task_items)
                    raise  # 抛到外层终止循环
                except Exception as e:
                    error_msg = str(e)
                    self.log_widget.append_error(f"🔥 处理队列发生业务崩溃: {error_msg}")
                    if db_publish:
                        await db_publish.update_status(
                            task_id,
                            'failed',
                            error_message=error_msg,
                            failure_kind=classify_publish_failure(error_msg),
                        )
                    if post_publish_action != "none":
                        PostPublishFileHandler.on_task_failed(task_id, file_groups)
                    for item in run_task_items:
                        if item.get("task_id") == task_id:
                            item["status"] = "failed"
                            break
                    self._update_task_status_in_memory(task_id, "failed", error_message=error_msg)
                    self.task_overview_card.set_task_overview(run_total, len(pending_records) - 1, run_total - len(pending_records) + 1, run_task_items)
                finally:
                    _task_failed = (result is None or not result.success) if result is not None else True
                    self.current_task = None
                    self._ui_active_publishing_task_id = None
                    self._sync_publish_queue_ui_executing_from_active_id()
                    self._highlighted_task_row = -1
                    # 从快照队列中弹出已处理的任务
                    if _pending_deque and _pending_deque[0].get("id") == task_id:
                        _pending_deque.popleft()
                    # 发布循环期间状态已由 _update_single_row_status 增量更新；
                    # 此处不再触发整表重建，等发布循环结束后由 _load_publish_records() 统一完整刷新
                    await self._sleep_between_publish_tasks(
                        had_more_pending, same_platform_next,
                        prev_task_failed=_task_failed,
                    )

        except asyncio.CancelledError:
            # 停止时的 InfoBar 已在点击「停止」时提示，此处只写日志避免重复弹条
            self.log_widget.append_warning("🛑 发布队列已结束（手动停止）。")
        except Exception as queue_e:
            self.log_widget.append_error(f"🤯 队列保护系统捕获致命异常: {str(queue_e)}")
            InfoBar.error("组件错误", f"队列异常断开：{str(queue_e)}", parent=self)
        finally:
            self._publish_queue_scoped_ids = None
            self._publish_verified_accounts = set()
            self._ui_active_publishing_task_id = None
            self._sync_publish_queue_ui_executing_from_active_id()
            self._is_publishing_loop_active = False
            self._highlighted_task_row = -1
            self.current_task = None
            if hasattr(self, 'btn_start_publish'):
                self.btn_start_publish.setEnabled(True)
            if hasattr(self, 'btn_stop_publish'):
                self.btn_stop_publish.setEnabled(False)
            if hasattr(self, 'btn_pause_publish'):
                self.btn_pause_publish.setEnabled(False)
                self.btn_pause_publish.setText("暂停")
            # 队列结束后做一次完整的数据库刷新，确保状态与数据库同步
            self._load_publish_records()
            # 队列全部结束后做一次残留浏览器进程清理（此时无活跃发布，安全）
            try:
                from src.infrastructure.browser.browser_manager import UndetectedBrowserManager
                await asyncio.to_thread(UndetectedBrowserManager.cleanup_all_processes)
                _mem_mb = _get_process_memory_mb()
                if _mem_mb > 0:
                    logging.getLogger("publish.user_log").info(
                        f"[维护] 队列结束，已执行残留进程清理，当前进程内存: {_mem_mb:.0f} MB"
                    )
            except Exception:
                pass

            armed_this_run = getattr(self, "_publish_one_shot_shutdown_this_run", False)
            natural = getattr(self, "_publish_queue_natural_complete", False)
            self._publish_queue_natural_complete = False
            self._publish_one_shot_shutdown_this_run = False

            if armed_this_run:
                clear_publish_after_shutdown_one_shot()

            if natural and armed_this_run:

                def _open_shutdown_dialog() -> None:
                    try:
                        from src.ui.dialogs.post_publish_shutdown_dialog import (
                            PostPublishShutdownDialog,
                        )

                        dlg = PostPublishShutdownDialog(self.window() or self)
                        dlg.exec()
                    except Exception as dlg_e:
                        logger.error(
                            "打开发布完成自动关机提示失败: %s", dlg_e, exc_info=True
                        )

                self._schedule_base_page_timer(
                    "post_publish_shutdown_dialog",
                    0,
                    _open_shutdown_dialog,
                )

    def _enqueue_publish_failure_notice(
        self,
        *,
        error_message: Optional[str],
        diagnostic_path: Optional[str],
        task_id: Optional[int],
        platform: str = "",
    ) -> None:
        """将失败提示投递到 UI 主线程；页面不可见时挂起至 showEvent。"""
        self._pending_publish_failure_notice = {
            "error_message": (error_message or "").strip() or "未知错误",
            "diagnostic_path": (diagnostic_path or "").strip(),
            "task_id": task_id,
            "platform": (platform or "").strip(),
        }
        if self.isVisible():
            self._schedule_base_page_timer(
                "publish_failure_notice",
                0,
                self._flush_pending_publish_failure_notice,
            )

    def _flush_pending_publish_failure_notice(self) -> None:
        """在 UI 主线程展示挂起的发布失败提示。"""
        pending = getattr(self, "_pending_publish_failure_notice", None)
        if not pending or not self.isVisible():
            return
        self._pending_publish_failure_notice = None
        self._present_publish_failure_notice(
            pending.get("error_message") or "未知错误",
            pending.get("diagnostic_path") or "",
            pending.get("task_id"),
            pending.get("platform") or "",
        )

    @Slot(str, str, object)
    def _present_publish_failure_notice(
        self,
        error_message: str,
        diagnostic_path: str,
        task_id: object = None,
        platform: str = "",
    ) -> None:
        """发布失败：InfoBar 提示和日志记录。"""
        from PySide6.QtWidgets import QApplication

        parent = QApplication.activeWindow() or self.window() or self
        short_msg = (error_message or "未知错误").strip()
        if len(short_msg) > 120:
            short_msg = short_msg[:117] + "…"
        title = "发布失败"
        if task_id is not None:
            try:
                title = f"发布失败（任务 {int(task_id)}）"
            except (TypeError, ValueError):
                pass
        try:
            InfoBar.error(
                title,
                short_msg,
                parent=parent,
                duration=8000,
            )
        except Exception as e:
            logger.warning("发布失败 InfoBar 展示失败: %s", e)

        path = (diagnostic_path or "").strip()
        if path:
            self._handle_publish_diagnostic_ready(
                path,
                error_message=error_message,
                platform=platform,
            )
        else:
            if getattr(self, "log_widget", None) is not None:
                self.log_widget.append_warning(
                    f"❌ {title}: {error_message or '未知错误'}\n（未生成诊断包，请查看发布日志）"
                )

    def _handle_publish_diagnostic_ready(
        self,
        diagnostic_path: str,
        *,
        error_message: Optional[str] = None,
        platform: str = "",
    ) -> None:
        """记录失败诊断结果已生成。"""
        path = (diagnostic_path or "").strip()
        if not path:
            return
        shown = getattr(self, "_shown_diagnostic_paths", None)
        if shown is None:
            shown = set()
            self._shown_diagnostic_paths = shown
        if path in shown:
            return
        shown.add(path)

        if getattr(self, "log_widget", None) is not None:
            self.log_widget.append_warning(
                f"🧩 发布失败（{platform}）：{error_message or '未知错误'}\n已保存诊断包至: {path}"
            )

    def _on_stop_publish(self):
        """停止发布：必须唤醒可能卡在暂停 wait 上的协程，否则界面会像「点了没反应」。"""
        had_queue = getattr(self, "_is_publishing_loop_active", False)
        ct = getattr(self, "current_task", None)
        had_publish_coro = ct is not None and not ct.done()
        if not had_queue and not had_publish_coro:
            InfoBar.info(
                "提示",
                "当前没有正在运行的发布队列。",
                parent=self.window() or self,
            )
            return

        # 置停止标志、唤醒 Event、取消当前 Task（manual=True 同时设 _manual_stop_requested）
        self._do_stop_publish_queue(manual=True)

        self.log_widget.append_warning("🛑 已请求停止：队列将尽快结束（浏览器内步骤可能仍需数秒收尾）。")
        InfoBar.warning(
            "已请求停止",
            "发布队列正在结束；若正在上传或填表，平台页面可能还会跑一会儿。",
            parent=self.window() or self,
            duration=3500,
        )
        # 已清空「发布中」覆盖，刷新任务说明避免徽章仍停在「发布中」
        if hasattr(self, "task_description_card") and hasattr(self, "records_table"):
            sel_rows = list(getattr(self, "_selected_rows_cache", None) or [])
            if not sel_rows:
                try:
                    sel_rows = [
                        idx.row()
                        for idx in self.records_table.selectionModel().selectedRows()
                    ]
                except Exception:
                    sel_rows = []
            if sel_rows:
                rec = self._get_record_by_row(sel_rows[0])
                self.task_description_card.set_task(
                    self._record_with_ui_publish_status(rec)
                )

    def _on_pause_publish(self):
        """暂停/继续发布"""
        if not hasattr(self, "publish_pause_event"):
            return
        if not getattr(self, "_is_publishing_loop_active", False):
            InfoBar.info(
                "提示",
                "请先点击「发布」启动队列后再使用暂停。",
                parent=self.window() or self,
            )
            return

        parent_win = self.window() or self
        if self.publish_pause_event.is_set():
            self.publish_pause_event.clear()
            self.log_widget.append_text("⏸️ 已暂停：将在当前步骤结束后停在「下一条任务」之前。")
            if hasattr(self, "btn_pause_publish"):
                self.btn_pause_publish.setText("继续")
                try:
                    self.btn_pause_publish.setIcon(FluentIcon.PLAY)
                except Exception as e:
                    logger.warning("设置继续按钮图标失败: %s", e)
            InfoBar.info(
                "已暂停",
                "队列将在当前浏览器步骤完成后停住；点「继续」再往下执行。",
                parent=parent_win,
                duration=3000,
            )
        else:
            self.publish_pause_event.set()
            self.log_widget.append_text("▶️ 已恢复发布…")
            if hasattr(self, "btn_pause_publish"):
                self.btn_pause_publish.setText("暂停")
                try:
                    self.btn_pause_publish.setIcon(FluentIcon.GAME)
                except Exception as e:
                    logger.warning("设置暂停按钮图标失败: %s", e)
            InfoBar.success("已继续", "发布队列已恢复执行。", parent=parent_win, duration=2000)

    def _on_records_loaded(self, records):
        """重写父类方法，当记录加载完成后检查是否需要自动发布"""
        super()._on_records_loaded(records)
        # 列表与记录页各自缓存：发布结果写入 DB 后同步让「发布记录」页失效或立即刷新
        notify_publish_records_history_tab_refresh(self)
        self._check_auto_start()
        # 数据就绪后预创建待发布页专属右键菜单，消除首次右键的一次性延迟
        self._schedule_base_page_timer(
            "list_prepare_context_menu",
            250,
            self._ensure_list_table_round_menu,
        )

    def _check_auto_start(self):
        """检查并触发自动发布"""
        # 1. 检查开关
        if not hasattr(self, 'auto_publish_check') or not self.auto_publish_check.isChecked():
            return
            
        # 2. 队列已启动时勿重复拉起（含账号检测等「尚未创建 current_task」的阶段）
        if getattr(self, "_is_publishing_loop_active", False):
            return

        # 3. 用户手动点「停止」后，本轮列表刷新不触发自动重启；清除标志供下次正常检测
        if getattr(self, "_manual_stop_requested", False):
            self._manual_stop_requested = False
            return
            
        # 4. 检查当前表格筛选结果内是否有待发布任务（与手动点「发布」范围一致）
        if not self._publish_queue_scoped_pending_ids():
            return
            
        self.log_widget.append_text("⏳ 检测到自动发布开启与待办任务，准备启动...")
        # asyncSlot 调用时可能返回 Task，用 ensure_future 兼容协程与 Task
        task = asyncio.ensure_future(self._on_start_publish())
        if hasattr(task, "set_name"):
            task.set_name("publish.auto_start")
        if isinstance(task, asyncio.Task):
            get_async_task_registry().register(
                task,
                group="publish",
                log_exceptions=False,
            )
        task.add_done_callback(
            lambda t: logger.error("自动发布任务异常: %s", t.exception()) if not t.cancelled() and t.exception() else None
        )

    def _ensure_list_table_round_menu(self) -> bool:
        try:
            from qfluentwidgets import RoundMenu, Action, FluentIcon as _FI
        except ImportError:
            return False
        from src.ui.components.fluent_context_menu import (
            install_round_menu_close_on_app_inactive,
            is_round_menu_alive,
            round_menu_parent,
        )

        if self._list_table_ctx_menu is not None and is_round_menu_alive(self._list_table_ctx_menu):
            return True
        parent = round_menu_parent(self)
        if parent is None:
            return False
        self._list_table_ctx_menu = RoundMenu(parent=parent)
        self._list_table_ctx_view = Action(_FI.EDIT, "编辑任务", parent)
        self._list_table_ctx_open_file = Action(_FI.DOCUMENT, "打开文件", parent)
        self._list_table_ctx_open_folder = Action(_FI.FOLDER, "打开所在文件夹", parent)
        self._list_table_ctx_retry = Action(_FI.SYNC, "重新发布", parent)
        self._list_table_ctx_delete = Action(_FI.DELETE, "删除此记录", parent)
        self._list_table_ctx_view.triggered.connect(self._on_list_table_ctx_view_clicked)
        self._list_table_ctx_open_file.triggered.connect(
            self._on_list_table_ctx_open_file_clicked
        )
        self._list_table_ctx_open_folder.triggered.connect(
            self._on_list_table_ctx_open_folder_clicked
        )
        self._list_table_ctx_retry.triggered.connect(self._on_list_table_ctx_retry_clicked)
        self._list_table_ctx_delete.triggered.connect(self._on_list_table_ctx_delete_clicked)
        self._list_table_ctx_menu.addAction(self._list_table_ctx_view)
        self._list_table_ctx_menu.addAction(self._list_table_ctx_open_file)
        self._list_table_ctx_menu.addAction(self._list_table_ctx_open_folder)
        self._list_table_ctx_menu.addSeparator()
        self._list_table_ctx_menu.addAction(self._list_table_ctx_retry)
        self._list_table_ctx_menu.addSeparator()
        self._list_table_ctx_menu.addAction(self._list_table_ctx_delete)
        install_round_menu_close_on_app_inactive(self._list_table_ctx_menu)
        return True

    def _on_list_table_ctx_view_clicked(self) -> None:
        rows = getattr(self, "_list_ctx_selected_rows", None) or []
        if len(rows) != 1:
            return
        rec = self._get_record_by_row(rows[0])
        if rec:
            self._on_view_detail(rec)

    def _on_list_table_ctx_open_folder_clicked(self) -> None:
        rows = getattr(self, "_list_ctx_selected_rows", None) or []
        if len(rows) != 1:
            return
        rec = self._get_record_by_row(rows[0])
        if rec:
            open_record_media_folder(self, rec)

    def _on_list_table_ctx_open_file_clicked(self) -> None:
        rows = getattr(self, "_list_ctx_selected_rows", None) or []
        if len(rows) != 1:
            return
        rec = self._get_record_by_row(rows[0])
        if rec:
            open_record_primary_media_file(self, rec)

    def _on_list_table_ctx_retry_clicked(self):
        recs = getattr(self, "_list_ctx_failed_records", None) or []
        if recs:
            self._handle_retry_publish(recs)

    def _on_list_table_ctx_delete_clicked(self):
        self._on_delete_records()

    def _on_context_menu(self, pos):
        """发布列表页右键菜单：失败任务可「重新发布」改为待发布，支持多选"""
        table = self.records_table
        selected_rows = list(getattr(self, "_selected_rows_cache", None) or [])
        if not selected_rows:
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
        else:
            selected_rows = sorted(set(selected_rows))

        failed_records: List[dict] = []
        # 使用 id 索引字典（O(1) 查找），兜底走线性查找
        records_by_id = getattr(self, "_records_by_id", {})
        for row in selected_rows:
            rid_item = table.item(row, 0)
            if not rid_item:
                continue
            try:
                rid = int(rid_item.data(Qt.UserRole))
                rec = records_by_id.get(rid)
                if rec and rec.get('status') == 'failed':
                    failed_records.append(rec)
            except (ValueError, TypeError):
                pass

        self._list_ctx_failed_records = failed_records
        self._list_ctx_selected_rows = selected_rows
        n_fail = len(failed_records)
        n_sel = len(selected_rows)
        single = n_sel == 1
        retry_text = "重新发布" if n_fail <= 1 else f"重新发布（{n_fail} 条失败任务）"
        del_text = "删除此记录" if n_sel <= 1 else f"删除选中记录（{n_sel} 条）"

        if self._ensure_list_table_round_menu():
            tip_single = "" if single else "请只选择一条任务时使用"
            self._list_table_ctx_view.setEnabled(single)
            self._list_table_ctx_view.setToolTip(tip_single)
            self._list_table_ctx_open_file.setEnabled(single)
            self._list_table_ctx_open_file.setToolTip(
                "使用系统默认程序打开；视频用默认播放器播放，图片用默认看图软件"
                if single
                else "请只选择一条任务时使用"
            )
            self._list_table_ctx_open_folder.setEnabled(single)
            self._list_table_ctx_open_folder.setToolTip(tip_single)
            # 固定两项+分隔线，避免隐藏首项时出现多余分隔线；无失败任务时置灰并提示
            self._list_table_ctx_retry.setText(retry_text)
            self._list_table_ctx_retry.setEnabled(n_fail > 0)
            self._list_table_ctx_retry.setToolTip(
                "" if n_fail > 0 else "仅当选中包含「失败」状态的任务时可重新发布"
            )
            self._list_table_ctx_delete.setText(del_text)
            self._list_table_ctx_menu.exec(table.viewport().mapToGlobal(pos))
            return

        menu = QMenu(self)
        action_view = None
        action_open_file = None
        action_open_folder = None
        if single:
            action_view = menu.addAction("编辑任务")
            try:
                action_view.setIcon(FluentIcon.EDIT.icon())
            except Exception:
                pass
            action_open_file = menu.addAction("打开文件")
            try:
                action_open_file.setIcon(FluentIcon.DOCUMENT.icon())
            except Exception:
                pass
            action_open_folder = menu.addAction("打开所在文件夹")
            try:
                action_open_folder.setIcon(FluentIcon.FOLDER.icon())
            except Exception:
                pass
            menu.addSeparator()
        action_retry = None
        if failed_records:
            action_retry = menu.addAction(retry_text)
            try:
                action_retry.setIcon(FluentIcon.SYNC.icon())
            except Exception:
                pass
        action_delete = menu.addAction(del_text)
        try:
            action_delete.setIcon(FluentIcon.DELETE.icon())
        except Exception:
            pass
        action = menu.exec(table.viewport().mapToGlobal(pos))
        if action_view is not None and action == action_view:
            self._on_list_table_ctx_view_clicked()
        elif action_open_file is not None and action == action_open_file:
            self._on_list_table_ctx_open_file_clicked()
        elif action_open_folder is not None and action == action_open_folder:
            self._on_list_table_ctx_open_folder_clicked()
        elif action == action_retry and failed_records:
            self._handle_retry_publish(failed_records)
        elif action == action_delete:
            self._on_delete_records()

    def _handle_retry_publish(self, records: List[dict]):
        """将选中的失败任务状态改为待发布"""
        from src.infrastructure.common.di.service_locator import ServiceLocator
        from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync
        from src.ui.utils.async_helper import run_async_task

        repo = ServiceLocator().get(PublishRecordRepositoryAsync)

        async def update_to_pending():
            for rec in records:
                rid = rec.get('id')
                if rid:
                    await repo.update_status(rid, 'pending', error_message='')

        def on_done(t):
            try:
                t.result()
                count = len(records)
                InfoBar.success("重新发布", f"已将 {count} 个失败任务改为待发布", parent=self)
                self._load_publish_records()
            except Exception as e:
                InfoBar.error("操作失败", f"更新状态失败: {e}", parent=self)

        task = run_async_task(update_to_pending)
        task.add_done_callback(on_done)
