"""
账号管理视图模型（异步版本）
文件路径：src/ui/viewmodels/account_viewmodel_async.py
功能：封装账号管理页面的业务逻辑和数据（异步版本）
"""

from typing import List, Dict, Optional, Any
from PySide6.QtCore import Signal, Property, QThread
import logging
import asyncio

from .base_viewmodel import BaseViewModel
from src.services.account.account_manager_async import AccountManagerAsync

logger = logging.getLogger(__name__)


class LoadAccountsThread(QThread):
    """加载账号列表的异步线程"""
    
    finished = Signal(list)
    error = Signal(str)
    
    def __init__(self, account_manager: AccountManagerAsync):
        super().__init__()
        self.account_manager = account_manager
    
    def run(self):
        """在线程中执行异步操作"""
        try:
            accounts = asyncio.run(self.account_manager.get_accounts())
            self.finished.emit(accounts)
        except Exception as e:
            self.error.emit(str(e))


class AccountViewModelAsync(BaseViewModel):
    """账号管理视图模型（异步版本）"""
    
    # 数据变化信号
    accountsChanged = Signal(list)  # 账号列表变化
    selectedAccountChanged = Signal(dict)  # 选中的账号变化
    platformFilterChanged = Signal(str)  # 平台筛选变化
    searchTextChanged = Signal(str)  # 搜索文本变化
    
    def __init__(self, parent=None):
        """初始化账号视图模型"""
        super().__init__(parent)
        
        # 数据属性
        self._accounts: List[Dict[str, Any]] = []
        self._filtered_accounts: List[Dict[str, Any]] = []
        self._selected_account: Optional[Dict[str, Any]] = None
        self._platform_filter: str = "全部平台"
        self._search_text: str = ""
        
        # 账号管理器
        self._account_manager: Optional[AccountManagerAsync] = None
        
        # 初始化服务
        self._init_account_manager()
        
        # 加载账号列表
        self.load_accounts()
    
    def _init_account_manager(self):
        """初始化账号管理器"""
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.infrastructure.common.event.event_bus import EventBus
            
            service_locator = ServiceLocator()
            event_bus = service_locator.get(EventBus)
            
            from src.services.auth.current_user_service import CurrentUserService
            user_id = CurrentUserService().get_user_id_or_default(1)
            # 创建账号管理器（已迁移为 Repository 模式）
            self._account_manager = AccountManagerAsync(
                user_id=user_id,
                event_bus=event_bus
            )
            logger.info("账号管理器初始化成功（异步版本）")
        except Exception as e:
            logger.error(f"初始化账号管理器失败: {e}", exc_info=True)
            self.handle_error(e, "初始化账号管理器")
    
    @Property(list, notify=accountsChanged)
    def accounts(self) -> List[Dict[str, Any]]:
        """账号列表"""
        return self._filtered_accounts
    
    @Property(dict, notify=selectedAccountChanged)
    def selected_account(self) -> Optional[Dict[str, Any]]:
        """选中的账号"""
        return self._selected_account
    
    @Property(str, notify=platformFilterChanged)
    def platform_filter(self) -> str:
        """平台筛选"""
        return self._platform_filter
    
    @Property(str, notify=searchTextChanged)
    def search_text(self) -> str:
        """搜索文本"""
        return self._search_text
    
    def set_platform_filter(self, platform: str):
        """设置平台筛选"""
        if self._platform_filter != platform:
            self._platform_filter = platform
            self.platformFilterChanged.emit(platform)
            self._apply_filters()
    
    def set_search_text(self, text: str):
        """设置搜索文本"""
        if self._search_text != text:
            self._search_text = text
            self.searchTextChanged.emit(text)
            self._apply_filters()
    
    def load_accounts(self, platform: Optional[str] = None):
        """加载账号列表（异步）"""
        if not self._account_manager:
            logger.warning("账号管理器未初始化")
            return
        
        # 保持线程强引用，防止 GC 提前回收；上次未完成时先停止
        if hasattr(self, '_load_thread') and self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()
            self._load_thread.wait(2000)
        self._load_thread = LoadAccountsThread(self._account_manager)
        self._load_thread.finished.connect(self._on_accounts_loaded)
        self._load_thread.finished.connect(lambda _: self._load_thread.deleteLater() if self._load_thread else None)
        self._load_thread.error.connect(self._on_load_error)
        self._load_thread.start()
    
    def _on_accounts_loaded(self, accounts: List[Dict[str, Any]]):
        """账号列表加载完成回调"""
        self._accounts = accounts
        self._apply_filters()
        self.accountsChanged.emit(self._filtered_accounts)
        logger.info(f"账号列表加载成功: {len(accounts)}个账号")
    
    def _on_load_error(self, error: str):
        """加载错误回调"""
        logger.error(f"加载账号列表失败: {error}")
        self.handle_error(Exception(error), "加载账号列表")
    
    def _apply_filters(self):
        """应用筛选条件"""
        filtered = self._accounts.copy()
        
        # 平台筛选
        if self._platform_filter != "全部平台":
            filtered = [
                acc for acc in filtered
                if acc.get('platform') == self._platform_filter
            ]
        
        # 搜索筛选
        if self._search_text:
            search_lower = self._search_text.lower()
            filtered = [
                acc for acc in filtered
                if search_lower in acc.get('platform_username', '').lower()
            ]
        
        self._filtered_accounts = filtered
        self.accountsChanged.emit(self._filtered_accounts)
    
    async def add_account_async(
        self,
        platform: str,
        platform_username: str
    ) -> int:
        """添加账号（异步）"""
        if not self._account_manager:
            raise ValueError("账号管理器未初始化")
        
        return await self._account_manager.add_account(
            platform=platform,
            platform_username=platform_username
        )
    
    async def delete_account_async(self, account_id: int) -> bool:
        """删除账号（异步）"""
        if not self._account_manager:
            return False
        
        return await self._account_manager.delete_account(account_id)

