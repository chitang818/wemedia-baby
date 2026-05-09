"""
工作台视图模型
文件路径：src/ui/viewmodels/workspace_viewmodel.py
功能：封装工作台页面的业务逻辑和数据
"""

from typing import Optional
from PySide6.QtCore import Signal, Property
import logging

from .base_viewmodel import BaseViewModel

logger = logging.getLogger(__name__)


class WorkspaceViewModel(BaseViewModel):
    """工作台视图模型"""
    
    # 数据变化信号
    accountCountChanged = Signal(int)  # 账号数量变化
    todayPublishCountChanged = Signal(int)  # 今日发布数量变化
    pendingPublishCountChanged = Signal(int)  # 待发布数量变化
    
    def __init__(self, parent=None):
        """初始化工作台视图模型"""
        super().__init__(parent)
        
        # 统计数据
        self._account_count: int = 0
        self._today_publish_count: int = 0
        self._pending_publish_count: int = 0
        
        # 加载统计数据
        self.load_statistics()
    
    @Property(int, notify=accountCountChanged)
    def account_count(self) -> int:
        """账号数量"""
        return self._account_count
    
    @Property(int, notify=todayPublishCountChanged)
    def today_publish_count(self) -> int:
        """今日发布数量"""
        return self._today_publish_count
    
    @Property(int, notify=pendingPublishCountChanged)
    def pending_publish_count(self) -> int:
        """待发布数量"""
        return self._pending_publish_count
    
    def load_statistics(self):
        """加载统计数据"""
        try:
            self.set_loading(True)
            
            # 加载账号数量
            self._load_account_count()
            
            # 加载发布统计（暂时使用默认值，后续实现）
            self._today_publish_count = 0
            self._pending_publish_count = 0
            self.todayPublishCountChanged.emit(0)
            self.pendingPublishCountChanged.emit(0)
            
        except Exception as e:
            logger.error(f"加载统计数据失败: {e}", exc_info=True)
            self.handle_error(e, "加载统计数据")
        finally:
            self.set_loading(False)
    
    def _load_account_count(self):
        """加载账号数量 — 使用 AccountRepositoryAsync（新架构）"""
        try:
            from src.domain.repositories.account_repository_async import AccountRepositoryAsync
            from src.ui.utils.async_helper import AsyncWorker
            
            repo = self.get_service(AccountRepositoryAsync)
            if not repo:
                self._account_count = 0
                self.accountCountChanged.emit(0)
                return
            
            from src.services.auth.current_user_service import CurrentUserService
            user_id = CurrentUserService().get_user_id_or_default(1)

            async def count_async():
                accounts = await repo.find_all(user_id=user_id)
                return len(accounts)
            
            worker = AsyncWorker(count_async)
            worker.finished.connect(self._on_account_count_loaded)
            worker.setParent(self)
            worker.start()
            
        except Exception as e:
            logger.error(f"加载账号数量失败: {e}", exc_info=True)
            self._account_count = 0
            self.accountCountChanged.emit(0)
    
    def _on_account_count_loaded(self, count):
        """账号数量加载完成回调"""
        self._account_count = count
        self.accountCountChanged.emit(count)
        logger.debug(f"加载账号数量成功: {count}")
    
    def refresh_statistics(self):
        """刷新统计数据"""
        self.load_statistics()

