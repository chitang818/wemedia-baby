# -*- coding: utf-8 -*-
"""
账号右键菜单管理器
文件路径：src/ui/pages/account/menus/account_context_menu.py
功能：管理账号表格的右键菜单，处理菜单项的显示和回调
性能优化：使用单例菜单实例和预创建Action，减少右键延迟
"""

from PySide6.QtCore import QObject, QPoint
from PySide6.QtWidgets import QWidget, QMenu
import logging

from src.ui.components.fluent_context_menu import install_round_menu_close_on_app_inactive

try:
    from qfluentwidgets import RoundMenu, Action, FluentIcon
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False

logger = logging.getLogger(__name__)


class AccountContextMenu(QObject):
    """账号右键菜单管理器
    
    负责管理账号表格的右键菜单，将菜单逻辑与主页面解耦。
    采用复用策略优化性能。
    """
    
    def __init__(self, parent: QWidget):
        """初始化"""
        super().__init__(parent)
        self.parent_widget = parent
        
        # 缓存菜单实例
        self._menu = None
        self._actions = {}
        
        # 当前上下文数据 (每次 show_menu 时更新)
        self._current_context = {}
        self._current_callbacks = {}

        # 预初始化菜单（页面侧也可在 _setup_content 再构造本类，使首次右键不再承担建菜单成本）
        if FLUENT_WIDGETS_AVAILABLE:
            self._init_fluent_menu()

    def _ensure_fluent_menu(self) -> None:
        """主窗口重建等导致 RoundMenu 已销毁时重新挂载。"""
        if not FLUENT_WIDGETS_AVAILABLE:
            return
        if self._menu is not None:
            try:
                self._menu.actions()
            except RuntimeError:
                self._menu = None
                self._actions = {}
        if self._menu is None:
            self._init_fluent_menu()

    @staticmethod
    def _has_callable(callbacks: dict, key: str) -> bool:
        fn = callbacks.get(key)
        return callable(fn)

    def _sync_action_visibility(self, callbacks: dict) -> None:
        """按回调是否存在更新项显隐，避免无回调仍展示或反复无效点击。"""
        pairs = [
            ("open", "on_switch"),
            ("copy", "on_copy_name"),
            ("refresh", "on_refresh_status"),
            ("group", "on_set_group"),
            ("fingerprint", "on_fingerprint"),
            ("delete", "on_delete"),
        ]
        for act_key, cb_key in pairs:
            act = self._actions.get(act_key)
            if act is not None:
                act.setVisible(self._has_callable(callbacks, cb_key))

    def _init_fluent_menu(self):
        """初始化 Fluent 风格菜单和动作"""
        # 使用 parent_widget 的 window 作为父级，确保样式渲染正确
        # 注意：如果 parent 销毁，menu 也会销毁，需要重建的检查在 show_menu 中做
        parent = self.parent_widget.window() if self.parent_widget else None
        self._menu = RoundMenu(parent=parent)
        
        # --- 创建动作 ---
        
        # 1. 打开浏览器
        self._actions['open'] = Action(FluentIcon.GLOBE, "打开浏览器", parent)
        self._actions['open'].triggered.connect(lambda: self._handle_action('on_switch'))
        self._menu.addAction(self._actions['open'])

        # 2. 复制账号
        self._actions['copy'] = Action(FluentIcon.COPY, "复制账号名", parent)
        self._actions['copy'].triggered.connect(lambda: self._handle_action('on_copy_name'))
        self._menu.addAction(self._actions['copy'])
        
        self._menu.addSeparator()
        
        # 3. 刷新状态
        self._actions['refresh'] = Action(FluentIcon.SYNC, "刷新登录状态", parent)
        self._actions['refresh'].triggered.connect(lambda: self._handle_action('on_refresh_status'))
        self._menu.addAction(self._actions['refresh'])
        
        # 4. 设置分组
        self._actions['group'] = Action(FluentIcon.PEOPLE, "移动至分组", parent)
        self._actions['group'].triggered.connect(lambda: self._handle_action('on_set_group'))
        self._menu.addAction(self._actions['group'])
        
        self._menu.addSeparator()
        
        # 6. 查看指纹
        icon_fp = getattr(FluentIcon, 'FINGERPRINT', FluentIcon.SEARCH)
        self._actions['fingerprint'] = Action(icon_fp, "查看环境指纹", parent)
        self._actions['fingerprint'].triggered.connect(lambda: self._handle_action('on_fingerprint'))
        self._menu.addAction(self._actions['fingerprint'])
        
        # 7. 删除 (放在最后，加分隔符)
        self._menu.addSeparator()
        self._actions['delete'] = Action(FluentIcon.DELETE, "删除此账号", parent)
        self._actions['delete'].triggered.connect(lambda: self._handle_action('on_delete'))
        self._menu.addAction(self._actions['delete'])

        install_round_menu_close_on_app_inactive(self._menu)

    def show_menu(
        self,
        global_pos: QPoint,
        account_id: int,
        platform_username: str,
        platform: str,
        callbacks: dict
    ):
        """显示右键菜单"""
        # 更新上下文
        self._current_context = {
            'account_id': account_id,
            'username': platform_username,
            'platform': platform
        }
        self._current_callbacks = callbacks
        
        if FLUENT_WIDGETS_AVAILABLE:
            self._ensure_fluent_menu()
            self._sync_action_visibility(callbacks)
            self._menu.exec(global_pos)
        else:
            self._show_fallback_menu(global_pos, callbacks)
            
    def _handle_action(self, callback_key: str):
        """统一处理动作触发"""
        callback = self._current_callbacks.get(callback_key)
        if not callback:
            logger.warning(f"No callback found for key: {callback_key}")
            return
            
        ctx = self._current_context
        
        try:
            # 根据 key 传递不同参数
            if callback_key == 'on_switch':
                callback(ctx['account_id'])
            elif callback_key == 'on_copy_name':
                callback(ctx['username'])
            elif callback_key == 'on_refresh_status':
                callback(ctx['account_id'])
            elif callback_key == 'on_set_group':
                callback(ctx['account_id'])
            elif callback_key == 'on_fingerprint':
                callback(ctx['account_id'], ctx['username'], ctx['platform'])
            elif callback_key == 'on_delete':
                callback(ctx['account_id'])
            else:
                # 默认无参调用
                callback()
        except Exception as e:
            logger.error(f"Error executing menu action {callback_key}: {e}", exc_info=True)

    def _show_fallback_menu(self, global_pos, callbacks):
        """显示回退菜单 (每次重建，作为 fallback 不做深度优化)"""
        menu = QMenu(self.parent_widget)
        ctx = self._current_context
        
        menu.addAction("打开浏览器", lambda: callbacks.get('on_switch', lambda x: None)(ctx['account_id']))
        menu.addAction("复制账号名", lambda: callbacks.get('on_copy_name', lambda x: None)(ctx['username']))
        menu.addSeparator()
        menu.addAction("刷新登录状态", lambda: callbacks.get('on_refresh_status', lambda x: None)(ctx['account_id']))
        menu.addAction("移动至分组", lambda: callbacks.get('on_set_group', lambda x: None)(ctx['account_id']))
        menu.addSeparator()
        menu.addAction("查看指纹", lambda: callbacks.get('on_fingerprint', lambda x: None)(ctx['account_id'], ctx['username'], ctx['platform']))
        
        if 'on_delete' in callbacks:
            menu.addSeparator()
            menu.addAction("删除此账号", lambda: callbacks['on_delete'](ctx['account_id']))
            
        menu.exec(global_pos)
