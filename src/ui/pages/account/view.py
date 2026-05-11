# pyre-ignore-all-errors
"""
账号管理页面
文件路径：src/ui/pages/account/view.py
功能：账号管理页面，包含账号列表、添加、删除、登录等功能
"""
import logging
import asyncio
import time
from typing import List, Optional, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QDialog, QCheckBox, QProgressDialog, QApplication
)
from PySide6.QtCore import Qt, QUrl, QTimer, QEvent, QSize
from PySide6.QtGui import QShowEvent

from qfluentwidgets import (
    FluentIcon, CardWidget, PrimaryPushButton,
    PushButton, BodyLabel, TitleLabel, CaptionLabel, TableWidget,
    SearchLineEdit, ComboBox, IconWidget, InfoBar, InfoBarPosition,
    TransparentToolButton, CheckBox,
)
FLUENT_WIDGETS_AVAILABLE = True # Keep for compatibility if other modules check it, or better remove it? 
# Let's remove the flag usage in this file.

from ..base_page import BasePage
from .components import AccountTableWidget
from .menus import AccountContextMenu
from .dialogs.set_group_dialog import SetGroupDialog # Import check
from .services import AccountValidatorService, AccountOperationsService
from .account_view_helpers import wait_page_networkidle_and_get_nickname
from src.services.browser import PlaywrightBrowserService
from src.infrastructure.common.di.service_locator import ServiceLocator
from src.ui.components.base_dialog import AppMessageBoxBase

logger = logging.getLogger(__name__)


def _swap_messagebox_confirm_cancel_to_right(msg_box):
    """将 Fluent 弹窗的确定按钮置于右侧、取消置于左侧。"""
    lay = getattr(msg_box, "buttonLayout", None)
    if lay is None:
        lay = msg_box.buttonGroup.layout()
    if lay is not None:
        lay.removeWidget(msg_box.yesButton)
        lay.removeWidget(msg_box.cancelButton)
        lay.addWidget(msg_box.cancelButton)
        lay.addWidget(msg_box.yesButton)


from src.plugins.core.plugin_manager import PluginManager
from config.feature_flags import USE_PLUGIN_SYSTEM

class AccountPage(BasePage):
    """账号管理页面"""

    _lazy_content = True

    # 告知 BasePage：首次加载时数据异步到来，由本页面在数据就绪后手动解冻界面更新
    @property
    def _defer_unfreeze(self) -> bool:
        return True

    def __init__(self, parent=None):
        super().__init__("账号管理", parent, enable_scroll=True)  # type: ignore
        self.account_manager = None
        from src.services.auth import CurrentUserService
        self.user_id = CurrentUserService().get_user_id_or_default(1)
        self._active_workers = []
        self._account_page_first_show = True
        self._last_load_time: float = 0.0

        self._reload_timer = QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(100)
        self._reload_timer.timeout.connect(self._load_accounts)
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh_timer)
        # 发布过程中账号状态会频繁更新，不可见时只标记过期，等下次显示再刷
        self._accounts_data_stale: bool = False

        self._init_services()
    
    def _init_services(self):
        """初始化服务"""
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.services.account.account_manager_async import AccountManagerAsync
            from src.infrastructure.common.event.event_bus import EventBus
            
            service_locator = ServiceLocator()
            event_bus = service_locator.get(EventBus)
            
            # 创建账号管理器（已迁移为 Repository 模式）
            self.account_manager = AccountManagerAsync(
                user_id=self.user_id,
                event_bus=event_bus
            )
            
            # 初始化账号组服务（待迁移为 AccountGroupRepositoryAsync）
            from src.services.account.account_group_service import AccountGroupService
            self.group_service = AccountGroupService(event_bus=event_bus)
            
            logger.info("账号管理器初始化成功（异步版本）")
        except Exception as e:
            logger.error(f"初始化账号管理器失败: {e}", exc_info=True)
    
    def _setup_content(self):
        """设置内容"""
        # ThemeManager 已接管样式加载，无需手动加载

        # 导入新组件
        from ...components.statistics_card import StatisticsCard
        
        # 0. 顶部统计区域（使用 QHBoxLayout 替代 qfluentwidgets.FlowLayout，减少 resize/退出阶段与库 FlowLayout 的耦合）
        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(16)

        self.stats_total = StatisticsCard("账号总数", "0", "已绑定账号", FluentIcon.PEOPLE, self)
        self.stats_total.setMinimumWidth(200)

        self.stats_online = StatisticsCard("在线账号", "0", "状态正常", FluentIcon.ACCEPT, self)
        self.stats_online.setMinimumWidth(200)

        self.stats_offline = StatisticsCard("离线账号", "0", "需要重新登录", FluentIcon.INFO, self)
        self.stats_offline.setMinimumWidth(200)

        stats_layout.addWidget(self.stats_total)
        stats_layout.addWidget(self.stats_online)
        stats_layout.addWidget(self.stats_offline)
        stats_layout.addStretch()

        self.content_layout.addLayout(stats_layout)

        from PySide6.QtWidgets import QSizePolicy
        
        # 1. 操作栏（使用 CardWidget 包裹，看起来更统一）
        header_card = CardWidget(self)
        header_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        # header_card.setFixedHeight(80) # Removed fixed height
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(12)
        
        # 左侧：核心操作按钮组
        actions_group = QHBoxLayout()
        actions_group.setSpacing(8)
        
        self.btn_add = PrimaryPushButton(FluentIcon.ADD, "添加账号", self)
        self.btn_refresh = PushButton(FluentIcon.SYNC, "刷新登录状态", self)
        self.btn_auto_refresh = PushButton(FluentIcon.HISTORY, "自动刷新设置", self)
        self.btn_delete = PushButton(FluentIcon.DELETE, "删除账号", self)
        
        self.btn_add.clicked.connect(self._on_add_account)
        self.btn_refresh.clicked.connect(self._on_refresh)
        self.btn_auto_refresh.clicked.connect(self._on_auto_refresh_settings)
        self.btn_delete.clicked.connect(self._on_delete_account)
        
        # 从 ServiceLocator 获取全局 Playwright 服务（已在 main.py 中用 AccountManagerAsync 初始化）
        from src.infrastructure.common.di.service_locator import ServiceLocator
        self.playwright_service = ServiceLocator().get(PlaywrightBrowserService)
        
        # 连接服务全局信号
        self.playwright_service.message_signal.connect(self._show_service_message)
        self.playwright_service.browser_launched.connect(self._on_browser_launched)
        
        # 初始化验证服务
        self.validator_service = AccountValidatorService(self.account_manager, self)
        self.validator_service.started.connect(self._on_verification_started)
        self.validator_service.progress.connect(self._on_verification_progress)
        self.validator_service.finished.connect(self._on_verification_finished)
        self.validator_service.error.connect(self._on_verification_error)
        
        # 初始化操作服务
        self.operations_service = AccountOperationsService(self.account_manager, self)
        self.operations_service.account_added.connect(self._on_account_added)
        self.operations_service.batch_delete_finished.connect(self._on_batch_deleted)
        self.operations_service.batch_delete_error.connect(self._on_batch_delete_error)
        self.operations_service.account_updated.connect(self._on_account_updated)
        
        # 将浏览器操作引起的名字变化也直连到刷新（不可见时只标脏，等显示时再刷）
        self.playwright_service.account_nickname_updated.connect(self._on_playwright_nickname_updated)
        # 静默更新后登录状态变化时刷新列表（不可见时只标脏，等显示时再刷）
        self.playwright_service.account_login_status_updated.connect(self._on_playwright_login_status_updated)
        
        # 将按钮添加到操作组
        actions_group.addWidget(self.btn_add)
        actions_group.addWidget(self.btn_refresh)
        actions_group.addWidget(self.btn_auto_refresh)
        actions_group.addWidget(self.btn_delete)
        
        header_layout.addLayout(actions_group)
        header_layout.addStretch()
        
        # 右侧：搜索和筛选
        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText("搜索账号...")
        self.search_box.setMinimumWidth(150)
        self.search_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.search_box.textChanged.connect(self._filter_accounts)
        
        self.platform_filter = ComboBox(self)
        self.platform_filter.addItems(["全部平台"] + self._get_platform_display_names())
        self.platform_filter.setMinimumWidth(120)
        self.platform_filter.currentIndexChanged.connect(self._filter_accounts)
        
        header_layout.addWidget(self.search_box, 0, Qt.AlignVCenter)
        header_layout.addWidget(self.platform_filter, 0, Qt.AlignVCenter)
        
        self.content_layout.addWidget(header_card)
        
        # 保存按钮引用以便响应式处理
        self._action_buttons = [self.btn_add, self.btn_refresh, self.btn_auto_refresh, self.btn_delete]
        
        # 2. 账号表格区域 (使用 StackedWidget 实现骨架屏切换)
        from PySide6.QtWidgets import QStackedWidget
        from ...components.skeleton import SkeletonTable
        
        self.table_stack = QStackedWidget(self)
        
        # 真实表格 (Index 0)
        self.account_table_widget = AccountTableWidget(self)
        self.account_table_widget.context_menu_requested.connect(self._on_context_menu)
        self.account_table_widget.switch_account_requested.connect(self._on_switch_account)
        # 预创建右键菜单，避免首次右键才初始化 RoundMenu 造成可感知延迟
        self.context_menu_manager = AccountContextMenu(self)
        # 连接双击信号，实现双击打开浏览器
        self.account_table_widget.account_double_clicked.connect(self._on_switch_account)
        self.table_stack.addWidget(self.account_table_widget)
        
        # 骨架屏 (Index 1)
        self.skeleton_table = SkeletonTable(rows=8, columns=5, parent=self)
        self.table_stack.addWidget(self.skeleton_table)
        
        self.content_layout.addWidget(self.table_stack, 1)  # stretch=1
        
        # 3. 加载账号数据
        self._load_accounts()

    def _schedule_reload(self):
        """防抖方式触发 _load_accounts，合并 100ms 内的多次调用"""
        self._reload_timer.start()

    def showEvent(self, event: QShowEvent):
        """页面每次显示时刷新 user_id（含登录后）并视情况刷新列表"""
        was_first_show = not self._content_initialized
        super().showEvent(event)
        # 同步当前用户 ID，避免重启/登录后仍用旧的 user_id 导致账号不显示或新加账号归属错误
        from src.services.auth import CurrentUserService
        self.user_id = CurrentUserService().get_user_id_or_default(1)
        if self.account_manager is not None:
            self.account_manager.user_id = self.user_id  # type: ignore
        if was_first_show:
            return
        # 若发布期间积累了过期标记，显示时立即刷新（忽略5秒节流）
        if getattr(self, "_accounts_data_stale", False):
            self._accounts_data_stale = False
            self._schedule_reload()
            return
        now = time.monotonic()
        if now - self._last_load_time > 5.0:
            self._schedule_reload()
        self._sync_auto_refresh_timer()
        if self._auto_refresh_config().get("enabled") and self._auto_refresh_config().get("on_show"):
            self._on_auto_refresh_timer()
        # 检测并提示长期未完成登录的占位账号
        QTimer.singleShot(1500, self._check_stale_placeholder_accounts)

    def _auto_refresh_config(self) -> Dict[str, Any]:
        try:
            from src.infrastructure.common.config.config_center import ConfigCenter
            cc = ServiceLocator().get(ConfigCenter)
            data = cc.get_app_config().get("account_auto_refresh", {})
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {
            "enabled": bool(data.get("enabled", False)),
            "on_show": bool(data.get("on_show", False)),
            "interval_minutes": max(1, int(data.get("interval_minutes", 30) or 30)),
        }

    def _save_auto_refresh_config(self, enabled: bool, on_show: bool, interval_minutes: int) -> None:
        try:
            from src.infrastructure.common.config.app_config_merge import (
                merge_app_config_top_level_to_disk_sync,
            )
            merge_app_config_top_level_to_disk_sync({
                "account_auto_refresh": {
                    "enabled": bool(enabled),
                    "on_show": bool(on_show),
                    "interval_minutes": max(1, int(interval_minutes)),
                }
            })
        except Exception as e:
            logger.warning("保存自动刷新配置失败: %s", e)

    def _sync_auto_refresh_timer(self) -> None:
        cfg = self._auto_refresh_config()
        if not cfg["enabled"]:
            self._auto_refresh_timer.stop()
            return
        self._auto_refresh_timer.start(int(cfg["interval_minutes"]) * 60 * 1000)

    def _on_auto_refresh_timer(self) -> None:
        if not self.isVisible():
            return
        self._on_refresh(silent=True)

    def _on_auto_refresh_settings(self) -> None:
        cfg = self._auto_refresh_config()
        dlg = AppMessageBoxBase(self.window() or self, header_title="自动刷新登录状态设置")
        ck_enable = CheckBox("开启自动刷新登录状态", dlg)
        ck_on_show = CheckBox("进入页面自动刷新一次", dlg)
        ck_timer = CheckBox("定时自动刷新（分钟）", dlg)
        from qfluentwidgets import LineEdit
        interval_edit = LineEdit(dlg)
        interval_edit.setText(str(cfg["interval_minutes"]))
        interval_edit.setPlaceholderText("分钟，例如 30")
        ck_enable.setChecked(cfg["enabled"])
        ck_on_show.setChecked(cfg["on_show"])
        ck_timer.setChecked(cfg["enabled"])
        dlg.viewLayout.addWidget(ck_enable)
        dlg.viewLayout.addWidget(ck_on_show)
        dlg.viewLayout.addWidget(ck_timer)
        dlg.viewLayout.addWidget(interval_edit)
        dlg.yesButton.setText("保存")
        dlg.cancelButton.setText("取消")
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        try:
            minutes = max(1, int(interval_edit.text().strip() or "30"))
        except ValueError:
            minutes = 30
        enabled = ck_enable.isChecked() and ck_timer.isChecked()
        self._save_auto_refresh_config(enabled, ck_on_show.isChecked(), minutes)
        self._sync_auto_refresh_timer()

    def _show_service_message(self, level, title, content):
        """显示来自服务的消息。浏览器启动失败时追加安装 Chrome 引导并可选跳转设置页。"""
        if level == "error" and title == "启动失败" and content:
            content_lower = (content or "").lower()
            if any(kw in content_lower or kw in (content or "") for kw in (
                "无法启动浏览器", "浏览器服务", "chrome", "executable", "未找到", "未安装"
            )):
                content = "未检测到 Google Chrome 或浏览器启动失败。请前往 设置 → 工具依赖 下载安装 Chrome。"
                try:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(600, self._try_navigate_to_settings_for_chrome)
                except Exception:
                    pass
                InfoBar.error(title=title, content=content, parent=self, duration=7000)
                return
        if level == "info":
            InfoBar.info(title=title, content=content, parent=self)
        elif level == "success":
            InfoBar.success(title=title, content=content, parent=self)
        elif level == "warning":
            InfoBar.warning(title=title, content=content, parent=self)
        elif level == "error":
            InfoBar.error(title=title, content=content, parent=self)

    def _try_navigate_to_settings_for_chrome(self):
        """尝试跳转到设置页，便于用户前往 工具依赖 安装 Chrome。"""
        try:
            mw = self.window()
            if mw and callable(getattr(mw, "navigate_to", None)):
                mw.navigate_to("settings_page")
        except Exception:
            pass

    def _on_browser_launched(self, account_id, platform_username, platform, is_new_account):
        """浏览器启动成功。新流程不再为新账号显示弹窗，仅保留信号供其他用途（如 Toast）。"""
        # 「先占位、后更新」流程：不再显示「添加新账号」弹窗
        # 新账号流程的状态更新、登录检测、关闭浏览器均由 PlaywrightService 内部处理
        pass

    def _load_accounts(self, skip_skeleton: bool = False):
        """加载账号列表
        
        Args:
            skip_skeleton: 已废弃，保留仅为兼容调用方，不再使用。
                骨架屏现在只在表格真正为空（行数为 0）时才显示，
                避免已有数据的情况下出现骨架屏闪烁。
        """
        if not self.account_manager:
            return
        self._last_load_time = time.monotonic()
            
        try:
            import inspect
            import asyncio
            
            # 只有表格当前没有任何行时才显示骨架屏（空表格 → 骨架屏过渡体验更好）；
            # 若表格已有数据（重新进入页面触发的静默刷新），保留旧数据直到新数据就绪，
            # 用户看不到任何闪烁。
            table_is_empty = (
                not hasattr(self, 'account_table_widget')
                or self.account_table_widget.table is None
                or self.account_table_widget.table.rowCount() == 0
            )
            if table_is_empty and hasattr(self, 'table_stack'):
                self.table_stack.setCurrentIndex(1)
            
            # 定义一个内部协程函数来获取数据并直接更新 UI，避免跨线程
            async def _do_fetch_and_update():
                try:
                    # 1. 创建任务
                    # 获取账号任务
                    if not self.account_manager:
                        return
                        
                    if inspect.iscoroutinefunction(self.account_manager.get_accounts):
                        accounts_task = self.account_manager.get_accounts()  # type: ignore
                    else:
                        # 如果不是协程，包装成协程
                        async def _sync_wrapper():
                            return self.account_manager.get_accounts()  # type: ignore
                        accounts_task = _sync_wrapper()
                    
                    # 获取分组任务
                    groups_task = None
                    if hasattr(self, 'group_service') and self.group_service:
                        groups_task = self.group_service.get_groups(self.user_id)
                    
                    # 获取标签任务 (新增)
                    tags_task = None
                    try:
                        from src.services.account.account_tag_service import AccountTagService
                        tags_task = AccountTagService().get_account_tags_mapping()
                    except Exception as e:
                        logger.error(f"准备标签任务失败: {e}")

                    # 2. 分开等待结果解决类型推断不能迭代的问题
                    if groups_task:
                        groups = await groups_task
                        accounts = await accounts_task
                    else:
                        accounts = await accounts_task
                        groups = []
                    
                    tags_map = {}
                    if tags_task:
                        try:
                            tags_map = await tags_task
                        except Exception as e:
                            logger.error(f"等待标签数据失败: {e}")
                    
                    # 3. 建立 group_id -> group_name 映射
                    group_map = {g['id']: g['group_name'] for g in groups}
                    latest_publish_map: Dict[int, str] = {}
                    try:
                        from src.domain.repositories.publish_record_repository_async import (
                            PublishRecordRepositoryAsync,
                        )
                        account_ids = [
                            int(a.get("id")) for a in (accounts or [])
                            if isinstance(a, dict) and a.get("id") is not None
                        ]
                        latest_publish_map = await PublishRecordRepositoryAsync().get_latest_publish_display_time_by_account_ids(account_ids)
                    except Exception as _lp_e:
                        logger.debug("加载账号最晚发布时间失败: %s", _lp_e)
                    
                    # 4. 合并数据
                    result = []
                    accounts_list: list = accounts  # type: ignore
                    for account in accounts_list:
                        # account 已经是 dict
                        acc_dict = account.copy() if hasattr(account, 'copy') else dict(account)
                        group_id = acc_dict.get('group_id')
                        if group_id:
                            acc_dict['group_name'] = group_map.get(group_id)  # type: ignore
                        acc_id = acc_dict.get("id")
                        if acc_id is not None:
                            try:
                                acc_dict["latest_publish_time"] = latest_publish_map.get(int(acc_id), "-")
                            except Exception:
                                acc_dict["latest_publish_time"] = "-"
                            
                            try:
                                acc_dict["tags"] = tags_map.get(int(acc_id), [])
                            except Exception:
                                acc_dict["tags"] = []
                        result.append(acc_dict)
                        
                    # 5. 更新UI (因为处于 qasync 主事件循环，完全可以安全操作UI)
                    if hasattr(self, 'table_stack'):
                        if self.table_stack.currentIndex() == 1 and hasattr(self, 'skeleton_table'):
                            self.skeleton_table.fade_out(
                                on_finished=lambda: self.table_stack.setCurrentIndex(0)
                            )
                        else:
                            self.table_stack.setCurrentIndex(0)
                        
                    if result:
                        self.account_table_widget.load_accounts(result)
                        # 账号列表重载后重放当前筛选，避免打开浏览器后静默刷新导致筛选失效。
                        self._filter_accounts()
                        
                        # 初始化状态缓存以支持精准统计
                        self._account_status_cache = {a['id']: ('online' if a.get('login_status') == 'online' else 'offline') for a in result}
                        
                        # 更新统计
                        total = len(result)
                        online = sum(1 for a in result if a.get('login_status') == 'online')
                        offline = total - online
                        self.stats_total.set_value(str(total))
                        self.stats_online.set_value(str(online))
                        self.stats_offline.set_value(str(offline))
                    else:
                        self.account_table_widget.load_accounts([])
                        self._filter_accounts()
                        
                        # 清空状态缓存
                        self._account_status_cache = {}
                        
                        self.stats_total.set_value("0")
                        self.stats_online.set_value("0")
                        self.stats_offline.set_value("0")
                    
                    # 首次加载完成后解冻界面，确保用户看到的第一帧就是完整数据，而非空表格
                    self._unfreeze_updates()
                except Exception as e:
                    logger.error(f"加载账号内部流程失败: {e}", exc_info=True)
                    if hasattr(self, 'table_stack'):
                        self.table_stack.setCurrentIndex(0)
                    # 异常情况下也要解冻，防止界面永久冻结
                    self._unfreeze_updates()

            # 延后到下一轮事件循环再执行，避免与单篇发布页选择账号等 async 槽并发时 qasync 报 reentrancy 错误
            self._run_bg_task(_do_fetch_and_update(), defer=True)
                
        except Exception as e:
            logger.error(f"加载账号触发失败: {e}", exc_info=True)

    def _remove_worker(self, worker):
        """从活动worker列表移除"""
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def _run_bg_task(self, coro, defer=False):
        """运行后台任务并保持强引用防止GC。defer=True 时延后到下一轮事件循环再 create_task，避免 qasync 下与其它 async 槽并发时触发 “Cannot enter into task” 的 reentrancy 错误。"""
        import asyncio
        if defer:
            loop = asyncio.get_event_loop()
            def _schedule():
                task = asyncio.create_task(coro)
                if not hasattr(self, '_bg_tasks'):
                    self._bg_tasks = set()
                self._bg_tasks.add(task)
                task.add_done_callback(self._bg_tasks.discard)
            loop.call_soon(_schedule)  # type: ignore
            return None
        task = asyncio.create_task(coro)
        if not hasattr(self, '_bg_tasks'):
            self._bg_tasks = set()
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    @staticmethod
    def _get_platform_display_names():
        """从 PluginManager 动态获取平台显示名称列表"""
        from src.utils.platform_names import PLATFORM_ID_TO_NAME, get_platform_display_name
        try:
            from src.plugins.core.plugin_manager import PluginManager
            from src.utils.plugin_settings import get_enabled_platform_ids, filter_enabled_platform_ids
            platform_ids = PluginManager.get_available_platforms()
            enabled = get_enabled_platform_ids()
            platform_ids = filter_enabled_platform_ids(platform_ids, enabled)
            return [get_platform_display_name(pid) for pid in platform_ids]
        except Exception:
            return list(PLATFORM_ID_TO_NAME.values())

    def refresh_platform_filter(self):
        """设置页修改插件启用后，刷新平台筛选下拉"""
        if not hasattr(self, "platform_filter") or not self.platform_filter:
            return
        current = self.platform_filter.currentText()
        try:
            self.platform_filter.blockSignals(True)
            self.platform_filter.clear()
            self.platform_filter.addItems(["全部平台"] + self._get_platform_display_names())
            idx = self.platform_filter.findText(current)
            self.platform_filter.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            try:
                self.platform_filter.blockSignals(False)
            except Exception:
                pass

    def _filter_accounts(self):
        """根据搜索框和平台筛选过滤账号"""
        keyword = self.search_box.text().strip()
        platform_index = self.platform_filter.currentIndex()
        platform = "all"
        if platform_index > 0:
            from src.utils.platform_names import get_platform_id
            display_name = self.platform_filter.currentText()
            platform = get_platform_id(display_name) or "all"
        
        self.account_table_widget.filter_accounts(keyword, platform)

    def _on_context_menu(self, account_data, global_pos):
        """显示右键菜单"""
        mgr = getattr(self, "context_menu_manager", None)
        if mgr is None:
            self.context_menu_manager = AccountContextMenu(self)
            mgr = self.context_menu_manager

        callbacks = {
            'on_switch': lambda acc_id: self._on_switch_account(acc_id),
            'on_fingerprint': lambda acc_id, uname, plat: self._show_fingerprint(acc_id, uname, plat, account_data.get('profile_folder_name')),
            'on_delete': lambda acc_id: self._delete_single_account(account_data),
            'on_set_group': lambda acc_id: self._on_set_account_group(acc_id, account_data),
            'on_copy_name': lambda name: QApplication.clipboard().setText(name),
            'on_refresh_status': lambda acc_id: self._refresh_single_account_status(acc_id)
        }
        
        mgr.show_menu(
            global_pos,
            account_data.get('id'),
            account_data.get('platform_username'),
            account_data.get('platform'),
            callbacks,
        )

    def _on_set_account_group(self, account_id, account_data):
        """设置账号分组"""
        if not hasattr(self, 'group_service') or not self.group_service:
            self._show_error("账号组服务未初始化")
            return
            
        try:
            from src.ui.utils.async_helper import AsyncWorker
            import asyncio
            from .dialogs.set_group_dialog import SetGroupDialog
            
            # 1.获取所有分组
            async def get_groups_and_show():
                groups = await self.group_service.get_groups(self.user_id)
                return groups
                
            def on_groups_loaded(groups):
                # 显示对话框
                current_group_id = account_data.get('group_id')
                dialog = SetGroupDialog(self, current_group_id, groups)
                
                if dialog.exec():
                    new_group_id = dialog.selected_group_id
                    
                    # 2. 更新分组
                    async def update_group():
                        if new_group_id:
                            await self.group_service.add_account_to_group(new_group_id, account_id)
                        else:
                            # 如果选择了未分类，但账号之前有分组，则移除
                            # 需要先获取账号当前所属分组，或者 service 提供 remove_from_group
                            # 假设 remove_account_from_group 需要 account_id
                            await self.group_service.remove_account_from_group(account_id)
                            
                    def on_updated(_):
                        self._show_success("账号分组已更新")
                        self._load_accounts() # 刷新列表
                        self._remove_worker(update_worker)
                        
                    def on_update_error(e):
                        self._show_error(f"更新分组失败: {e}")
                        self._remove_worker(update_worker)
                        
                    update_worker = AsyncWorker(update_group)
                    update_worker.finished.connect(on_updated)
                    update_worker.error.connect(on_update_error)
                    self._active_workers.append(update_worker)
                    update_worker.start()
                    
                self._remove_worker(load_worker)

            def on_load_error(e):
                self._show_error(f"获取分组列表失败: {e}")
                self._remove_worker(load_worker)
                
            load_worker = AsyncWorker(get_groups_and_show)
            load_worker.finished.connect(on_groups_loaded)
            load_worker.error.connect(on_load_error)
            self._active_workers.append(load_worker)
            load_worker.start()
            
        except Exception as e:
            logger.error(f"设置分组流程出错: {e}", exc_info=True)
            self._show_error(f"操作失败: {e}")

    def _show_fingerprint(self, account_id, platform_username, platform, profile_folder_name=None):
        """显示浏览器指纹信息。先从 DB 解析并回填 profile_folder_name，再打开指纹界面，不依赖表格缓存。"""
        async def _ensure_and_show():
            account = await self.account_manager.get_account_for_operation(account_id)  # type: ignore
            if not account:
                self._show_error("账号不存在")
                return
            pf = (account.get("profile_folder_name") or "").strip()
            uname = account.get("platform_username") or platform_username
            plat = account.get("platform") or platform
            if not pf:
                self._show_error("无法解析账号数据目录，请先打开浏览器或刷新登录状态")
                return
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._show_fingerprint_dialog(account_id, uname, plat, pf))
        self._run_bg_task(_ensure_and_show())

    def _show_fingerprint_dialog(self, account_id, platform_username, platform, profile_folder_name):
        """在已解析 profile_folder_name 后显示指纹对话框（主线程）"""
        try:
            from src.infrastructure.browser.profile_manager import ProfileManager
            from .dialogs.fingerprint_dialog import FingerprintDialog
            pm = ProfileManager(
                account_id=str(account_id),
                platform=platform,
                account_name=platform_username,
                profile_folder_name=profile_folder_name
            )
            fingerprint = pm.get_fingerprint()
            dialog = FingerprintDialog(platform_username, platform, fingerprint, self)
            dialog.exec()
        except Exception as e:
            logger.error(f"显示指纹信息失败: {e}", exc_info=True)
            self._show_error(f"查看指纹失败: {str(e)}")

    def _delete_single_account(self, account_data):
        """删除单个账号"""
        accounts_to_delete = [{
            'id': account_data.get('id'),
            'username': account_data.get('platform_username')
        }]
        
        def run_delete(delete_cookie_val):
             self.operations_service.delete_accounts(accounts_to_delete, delete_cookie_val)
             
        username = account_data.get('platform_username', '')
        confirm_text = f"确定要删除账号「{username}」吗？"
        
        msg_box = AppMessageBoxBase(self, header_title="确认删除")
        msg_box.setWindowTitle("删除账号")
        
        content_label = BodyLabel(confirm_text, msg_box)
        msg_box.viewLayout.addWidget(content_label)
        
        cb_delete_cookie = CheckBox("同时删除Cookie和发布记录", msg_box)
        cb_delete_cookie.setChecked(True)
        msg_box.viewLayout.addWidget(cb_delete_cookie)
        
        msg_box.yesButton.setText("删除")
        msg_box.cancelButton.setText("取消")
        _swap_messagebox_confirm_cancel_to_right(msg_box)
        
        if msg_box.exec():
            run_delete(cb_delete_cookie.isChecked())


    def _on_add_account(self):
        """添加账号按钮点击（先占位、后更新流程：选择平台后先在列表中插入占位账号，再打开浏览器）"""
        try:
            from src.services.auth import CurrentUserService
            from src.ui.dialogs.login_dialog import LoginDialog
            curr = CurrentUserService()
            if not curr.is_logged_in():
                from qfluentwidgets import InfoBar
                InfoBar.warning("请先登录", "添加账号需要先登录软件", parent=self)
                login_dialog = LoginDialog(self)
                if not login_dialog.exec():
                    return
                if not curr.is_logged_in():
                    return
                self.user_id = curr.get_user_id_or_default(1)
                if self.account_manager is not None:
                    self.account_manager.user_id = self.user_id  # type: ignore

            from src.ui.account.add_account_dialog import AddAccountDialog
            dialog = AddAccountDialog(self.window() or self)
            result = dialog.show()
            if not result:
                return

            platform = result['platform']
            fingerprint_config = result.get('fingerprint_config')

            if not hasattr(self, 'playwright_service') or self.playwright_service is None:
                from src.ui.utils.fluent_dialogs import show_warning
                show_warning(self, "错误", "PlaywrightService 未初始化")
                return

            # 「先占位、后更新」流程：先创建占位账号，刷新列表，再打开浏览器
            async def _add_account_flow():
                # 1. 创建占位账号
                account_id, profile_folder_name = await self.account_manager.add_placeholder_account(platform)  # type: ignore
                logger.info(f"已创建占位账号: account_id={account_id}, profile={profile_folder_name}")

                # 2. 刷新列表，用户立即看到「待登录」行
                self._schedule_reload()

                # 3. 定义登录成功后的更新回调（列表刷新由 update_* 触发的 EventBus + account_*_updated 信号统一防抖处理，此处不再重复 _schedule_reload）
                async def on_login_detected(acc_id, nickname, plat, cookies, profile_name):
                    await self.account_manager.update_account_after_login(acc_id, nickname, cookies)  # type: ignore
                    logger.info(f"占位账号已更新: account_id={acc_id}, nickname={nickname}")

                # 4. 打开浏览器（不弹窗）
                await self.playwright_service.open_new_account_window(
                    platform=platform,
                    fingerprint_config=fingerprint_config,
                    existing_account_id=account_id,
                    profile_folder_name=profile_folder_name,
                    on_login_detected_callback=on_login_detected,
                )

            self._run_bg_task(_add_account_flow())

        except Exception as e:
            logger.error(f"添加账号失败: {e}", exc_info=True)
            InfoBar.error(
                title='错误',
                content=f"添加账号失败：{str(e)}",
                parent=self
            )
    
    

    
    def _on_account_added(self, account_id: int, account_name: str):
        """账号添加成功回调"""
        logger.info(f"账号添加成功: {account_name}, ID: {account_id}")
        self._schedule_reload()
        self._show_service_message("success", "账号添加成功", f"账号 {account_name} 添加成功")
        
    def _on_account_updated(self, account_id: int, update_type: str):
        """账号更新回调（来自EventBus）。

        发布流程中会高频触发（每次 Cookie 保存都会发此事件），若账号页不可见则仅标记过期，
        等下次页面显示时再刷新，避免重建表格拖慢发布时的主线程。
        对于 status 类型更新，直接通过单行刷新替代全量 reload，避免表格频繁闪烁。
        """
        logger.info(f"收到账号更新通知: ID={account_id}, Type={update_type}")
        if not self.isVisible():
            self._accounts_data_stale = True
            return
        if update_type == "status":
            # Cookie 保存等高频状态更新：仅刷新对应行的登录状态，不重建整张表
            self._refresh_single_row_status(account_id)
        else:
            # 昵称变更、分组变更等需要更新文本的情况，走防抖全量刷新
            self._schedule_reload()

    def _refresh_single_row_status(self, account_id: int) -> None:
        """从 DB 拉取单账号的最新登录状态，然后精准更新对应表格行，避免全量 reload。"""
        if not self.account_manager or not hasattr(self, 'account_table_widget'):
            return

        async def _fetch_and_update():
            try:
                account = await self.account_manager.get_account_by_id(account_id)  # type: ignore
                if account:
                    status = account.get('login_status', 'offline')
                    if hasattr(self, 'account_table_widget'):
                        self.account_table_widget.update_account_status(account_id, status)
                        # 同步更新统计缓存
                        if hasattr(self, '_account_status_cache'):
                            old = self._account_status_cache.get(account_id)
                            if old != status:
                                self._account_status_cache[account_id] = status
                                self._update_stats_from_cache()
            except Exception as e:
                logger.debug("单行状态刷新失败，fallback 到全量: %s", e)
                self._schedule_reload()

        self._run_bg_task(_fetch_and_update(), defer=True)

    def _update_stats_from_cache(self) -> None:
        """根据状态缓存快速更新统计卡片，不重载表格。"""
        if not hasattr(self, '_account_status_cache'):
            return
        total = len(self._account_status_cache)
        online = sum(1 for s in self._account_status_cache.values() if s == 'online')
        offline = total - online
        if hasattr(self, 'stats_total'):
            self.stats_total.set_value(str(total))
        if hasattr(self, 'stats_online'):
            self.stats_online.set_value(str(online))
        if hasattr(self, 'stats_offline'):
            self.stats_offline.set_value(str(offline))

    def _on_playwright_nickname_updated(self, account_id: int, nickname: str) -> None:
        """浏览器侧昵称变更回调。不可见时只标脏，避免发布期间重建账号表格。"""
        if not self.isVisible():
            self._accounts_data_stale = True
            return
        # 昵称变更需更新表格中的文本，走防抖全量刷新（但合并同一防抖窗口内的多次触发）
        self._schedule_reload()

    def _on_playwright_login_status_updated(self, account_id: int) -> None:
        """静默更新后登录状态变更回调。精准刷新对应行，不触发全量 reload。"""
        if not self.isVisible():
            self._accounts_data_stale = True
            return
        self._refresh_single_row_status(account_id)

    def _silent_refresh_status(self, account_id: int):
        """静默刷新单个账号状态（不显示加载条）"""
        if not self.account_manager:
            return
        
        logger.info(f"触发静默状态刷新: {account_id}")
        # 使用服务层的新接口，静默验证
        self.validator_service.start_verify_by_ids([account_id], silent=True)

    def _refresh_single_account_status(self, account_id: int):
        """刷新单个账号状态"""
        if not self.account_manager:
            return
            
        # 使用服务层的新接口，直接通过ID验证
        self.validator_service.start_verify_by_ids([account_id])

    def _on_refresh(self, silent: bool = False):
        """刷新账号列表（验证Cookie有效性）"""
        if not self.account_manager:
            return
        self._refresh_silent_mode = bool(silent)
        # 使用服务层的新接口，验证所有账号
        self.validator_service.start_verify_all(silent=silent)

    def _on_verification_started(self, total):
        """验证开始"""
        if getattr(self, "_refresh_silent_mode", False):
            return
        self.progress_dialog = QProgressDialog(
            "正在验证账号状态...", "取消", 0, total, self.window() or self
        )
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setWindowTitle("同步账号状态")
        self.progress_dialog.resize(400, 150)
        
        # 连接取消按钮
        self.progress_dialog.canceled.connect(self.validator_service.cancel)
        
        self.progress_dialog.show()

    def _on_verification_progress(self, current, total, data):
        """验证进度 - 逐条实时更新 UI"""
        # 更新进度条
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.setValue(current)
        
        # 逐条实时更新表格中该账号的状态
        if data:
            account_id, result = data
            if account_id and result:
                is_online = result.get('is_logged_in', False)
                new_status = 'online' if is_online else 'offline'
                error_msg = result.get('error', '')
                username = result.get('username', '')
                
                # 实时更新表格行的状态图标
                if hasattr(self, 'account_table_widget'):
                    self.account_table_widget.update_account_status(
                        account_id, new_status, error_msg
                    )

    def _on_verification_finished(self, results):
        """验证完成"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
        
        # 直接从验证结果更新统计卡片（不重载表格，否则会清除离线原因提示）
        if results and isinstance(results, dict):
            total = self.account_table_widget.table.rowCount() if hasattr(self, 'account_table_widget') else len(results)
            
            # 维护状态缓存以确保单条刷新时统计数量的准确性
            if not hasattr(self, '_account_status_cache'):
                self._account_status_cache = {}
                
            for acc_id, res in results.items():
                self._account_status_cache[acc_id] = 'online' if res.get('is_logged_in') else 'offline'
                
            online_count = list(self._account_status_cache.values()).count('online')
            offline_count = int(total) - int(online_count)
            
            if hasattr(self, 'stats_total'):
                self.stats_total.set_value(str(total))
            if hasattr(self, 'stats_online'):
                self.stats_online.set_value(str(online_count))
            if hasattr(self, 'stats_offline'):
                self.stats_offline.set_value(str(offline_count))
            
            # 仅验证单个账号时（如右键「刷新登录状态」），只显示该账号的验证结果
            if len(results) == 1 and not getattr(self, "_refresh_silent_mode", False):
                acc_id = next(iter(results))
                res = results[acc_id]
                username = res.get('username') or res.get('account_name') or res.get('platform_username') or f"账号 #{acc_id}"
                if isinstance(username, str):
                    username = username.strip() or f"账号 #{acc_id}"
                else:
                    username = f"账号 #{acc_id}"
                if res.get('is_logged_in'):
                    self._show_success(f"账号 {username} 状态正常")
                else:
                    err = (res.get('error') or "").strip()
                    if err and len(err) > 30:
                        err = str(err)[:27] + "..."  # type: ignore
                    self._show_success(f"账号 {username} 已离线" + (f"（{err}）" if err else ""))
            else:
                self._show_success(f"验证完成：{online_count} 在线，{offline_count} 离线")
        self._refresh_silent_mode = False
        self._schedule_reload()

    def _on_verification_error(self, error):
        """验证出错"""
        if hasattr(self, 'progress_dialog') and self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self._load_accounts()
        self._show_warning(f"验证过程出现错误: {error}")

    def _check_stale_placeholder_accounts(self):
        """检测长期未完成登录的占位账号（超过 2 小时），提示用户清理。"""
        if not hasattr(self, 'account_table_widget') or not self.account_table_widget:
            return
        table = self.account_table_widget.table
        stale_count = 0
        for row in range(table.rowCount()):
            if table.isRowHidden(row):
                continue
            name_item = table.item(row, 1)
            if name_item and name_item.text() == "待登录":
                stale_count += 1
        if stale_count > 0:
            InfoBar.warning(
                title="存在未完成的账号",
                content=f"有 {stale_count} 个账号长期处于「待登录」状态，可选中后点击「删除账号」进行清理。",
                parent=self,
                duration=6000,
                position=InfoBarPosition.TOP_RIGHT,
            )

    def _show_info(self, content):
        InfoBar.info(title='提示', content=content, parent=self)

    def _show_success(self, content):
        InfoBar.success(title='成功', content=content, parent=self)
            
    def _show_error(self, content):
        InfoBar.error(title='错误', content=content, parent=self)
            
    def _show_warning(self, content):
        InfoBar.warning(title='警告', content=content, parent=self)

    def _batch_sync_nicknames(self, accounts, progress_dialog, parent_worker):
        """批量深度同步昵称 (Headless Browser)"""
        logger.info(f"开始批量深度同步昵称，共 {len(accounts)} 个账号")
        
        # 使用 AsyncWorker 执行耗时操作
        from src.ui.utils.async_helper import AsyncWorker
        
        def run_sync_task():
            import asyncio
            from src.infrastructure.browser.browser_factory import BrowserFactory
            
            # 获取事件循环
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            async def process_single(account):
                account_name = account.get('account_name')
                account_id = account.get('id')
                logger.info(f"正在同步账号昵称: {account_name}")
                
                browser_manager = None
                try:
                    # 1. 启动 Headless 浏览器
                    # 使用正确的参数初始化 BrowserFactory
                    browser_manager = BrowserFactory.get_browser_service(
                        account_id=account_id,
                        platform=account.get('platform', 'douyin'),
                        platform_username=account.get('platform_username', account_name)
                    )
                    context = await browser_manager.launch(headless=True)
                    if not context:
                        logger.error(f"启动浏览器失败: {account_name}")
                        return False
                    
                    page = await context.new_page()
                    
                    # 2. 访问创作者中心
                    await page.goto("https://creator.douyin.com/creator-micro/home")
                    # 3. 等待稳定并提取昵称 (抽取到 account_view_helpers)
                    nickname = await wait_page_networkidle_and_get_nickname(
                        page, account.get("platform", "douyin")
                    )
                    
                    if nickname:
                        logger.info(f"成功提取到昵称: {nickname}")
                        # 4. 更新数据库
                        await self.account_manager.data_storage.update_platform_username(account_id, nickname)  # type: ignore
                        sync_worker.progress.emit(1, 1, (account_id, nickname)) # 发射进度信号
                        return True
                    else:
                        logger.warning(f"未能提取到昵称: {account_name}")
                        return False
                        
                except Exception as e:
                    logger.error(f"同步昵称失败 {account_name}: {e}")
                    return False
                finally:
                    if browser_manager:
                        await browser_manager.close()

            # 串行执行，避免并发启动多个浏览器导致资源耗尽
            async def run_loop():
                for i, account in enumerate(accounts):
                    # 通知进度 (当前索引, 总数, 正在处理的账号名)
                    sync_worker.progress.emit(i, len(accounts), account.get('account_name'))
                    await process_single(account)
            
            loop.run_until_complete(run_loop())
            return len(accounts)

        sync_worker = AsyncWorker(run_sync_task)
        
        def on_sync_progress(current, total, data):
            if isinstance(data, str):
                # 正在处理某个账号
                progress_dialog.setLabelText(f"正在深度同步昵称 ({current + 1}/{total}):\n{data}...")
            elif isinstance(data, tuple):
                # 单个完成 (id, nickname)
                pass

        sync_worker.progress.connect(on_sync_progress)
        
        def on_sync_finished(result):
            progress_dialog.close()
            self._load_accounts()
            
            InfoBar.success(
                title='深度同步完成',
                content=f'已完成 {result} 个账号的昵称同步',
                parent=self
            )
            
            self._remove_worker(sync_worker)
            # 清理父worker
            if parent_worker:
                self._remove_worker(parent_worker)

        sync_worker.finished.connect(on_sync_finished)
        
        def on_sync_error(e):
            logger.error(f"深度同步任务失败: {e}", exc_info=True)
            progress_dialog.close()
            InfoBar.warning(title="部分同步失败", content=f"同步过程中发生错误: {e}", parent=self)
            self._remove_worker(sync_worker)
            if parent_worker:
                self._remove_worker(parent_worker)

        sync_worker.error.connect(on_sync_error)
        
        self._active_workers.append(sync_worker)
        sync_worker.start()
    
    def _on_delete_account(self):
        """批量删除账号"""
        selected_rows = self.account_table_widget.table.selectionModel().selectedRows()
        if not selected_rows:
            return
            
        logger.info(f"点击删除按钮，选中 {len(selected_rows)} 行")
        
        # 收集选中账号的信息
        accounts_to_delete = []
        for index in selected_rows:
            row = index.row()
            # 获取账号信息 (从第1列 - 昵称)
            account_item = self.account_table_widget.table.item(row, 1)
            if account_item:
                account_id = account_item.data(Qt.ItemDataRole.UserRole)
                account_username = account_item.text()
                
                accounts_to_delete.append({
                    'id': account_id,
                    'username': account_username
                })
        
        if not accounts_to_delete:
            return

        def run_delete(delete_cookie_val):
             self.operations_service.delete_accounts(accounts_to_delete, delete_cookie_val)

        
        count = len(accounts_to_delete)
        confirm_text = f"确定要删除选中的 {count} 个账号吗？" if count > 1 else f"确定要删除账号「{accounts_to_delete[0]['username']}」吗？"
        
        from PySide6.QtGui import QColor
        msg_box = AppMessageBoxBase(self, header_title="确认删除")
        msg_box.setWindowTitle("删除账号")
        
        content_label = BodyLabel(confirm_text, msg_box)
        msg_box.viewLayout.addWidget(content_label)
        
        cb_delete_cookie = CheckBox("同时删除Cookie和发布记录", msg_box)
        cb_delete_cookie.setChecked(True)
        msg_box.viewLayout.addWidget(cb_delete_cookie)
        
        msg_box.yesButton.setText("删除")
        msg_box.cancelButton.setText("取消")
        _swap_messagebox_confirm_cancel_to_right(msg_box)
        if msg_box.exec():
            run_delete(cb_delete_cookie.isChecked())

    # _execute_batch_delete removed (moved to service)


    def _on_batch_deleted(self, count):
        """批量删除完成回调"""
        self._schedule_reload()
        if count > 0:
            msg = f"成功删除 {count} 个账号"
            InfoBar.success(title="操作成功", content=msg, parent=self)

    def _on_batch_delete_error(self, error_msg: str):
        """批量删除失败回调"""
        self._show_error(error_msg)
    
    def _open_playwright_browser_for_account(self, account_id: int, **kwargs):
        """使用 Playwright 服务打开本地浏览器（唯一方案）；kwargs 兼容发布页调用，仅使用 account_id。"""
        if not hasattr(self, 'playwright_service') or self.playwright_service is None:
            logger.error("Playwright service not initialized")
            InfoBar.error(title="错误", content="浏览器服务未初始化", parent=self)
            return
        import asyncio
        task = self._run_bg_task(self.playwright_service.open_browser_for_db_account(account_id))

        def _on_done(t):
            try:
                exc = t.exception()
                if exc is not None:
                    msg = str(exc) or "未知错误"
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: InfoBar.error(
                        title="打开浏览器失败",
                        content=msg,
                        parent=self,
                        duration=5000,
                    ))
            except Exception:
                pass
        task.add_done_callback(_on_done)  # type: ignore

    def _get_cookie_domain(self, platform: str) -> str:
        """获取平台的Cookie域名
        
        Args:
            platform: 平台ID
        
        Returns:
            Cookie域名
        """
        domain_map = {
            'douyin': '.douyin.com',
            'kuaishou': '.kuaishou.com',
            'wechat_video': '.weixin.qq.com',
            'xiaohongshu': '.xiaohongshu.com'
        }
        return domain_map.get(platform, '')
    
    def _on_switch_account(self, account_id: int):
        """双击账号：使用 Playwright 打开本地浏览器。防抖：同账号 2 秒内仅执行一次。"""
        import time
        now = time.monotonic()
        last_id = getattr(self, "_last_switch_account_id", None)
        last_time = getattr(self, "_last_switch_time", 0)
        if last_id == account_id and (now - last_time) < 2.0:
            from qfluentwidgets import InfoBar
            InfoBar.info("提示", "该账号浏览器正在打开，请查看任务栏", parent=self, duration=2000)
            return
        self._last_switch_account_id = account_id
        self._last_switch_time = now
        try:
            logger.info(f"双击打开浏览器: account_id={account_id}")
            self._open_playwright_browser_for_account(account_id)
        except Exception as e:
            logger.error(f"打开浏览器失败: {e}", exc_info=True)
            from src.ui.utils.fluent_dialogs import show_warning
            show_warning(self, "错误", f"打开浏览器失败：{str(e)}")
    
    def closeEvent(self, event: QEvent) -> None:
        """页面关闭事件，清理定时器并等待所有AsyncWorker完成"""
        if hasattr(self, '_reload_timer') and self._reload_timer:
            self._reload_timer.stop()
        for worker in self._active_workers[:]:  # type: ignore
            if worker.isRunning():
                worker.wait(3000)  # 等待最多3秒
                if worker.isRunning():
                    worker.terminate()
                    worker.wait(1000)
        
        super().closeEvent(event)

