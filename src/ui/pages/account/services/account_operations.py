# -*- coding: utf-8 -*-
"""
账号操作服务
文件路径：src/ui/pages/account/services/account_operations.py
功能：负责账号的加载、删除、清理Cookie等业务操作
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional, Union
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

class AccountOperationsService(QObject):
    """账号操作服务"""
    
    # 信号定义
    accounts_loaded = Signal(list)  # 账号列表加载完成
    load_error = Signal(str)        # 加载失败
    
    batch_delete_finished = Signal(int) # 删除成功数量
    batch_delete_error = Signal(str)    # 删除失败
    
    account_added = Signal(int, str)    # ID, Name
    add_account_error = Signal(str)     # 添加失败
    
    cookie_cleared = Signal(bool, str)  # 成功, 平台用户名
    clear_cookie_error = Signal(str)    # 清理失败
    
    account_updated = Signal(int, str)  # account_id, update_type (status/nickname)

    def __init__(self, account_manager, parent=None):
        super().__init__(parent)
        self.account_manager = account_manager
        
        # 保存异步任务的强引用，防止被GC静默回收
        self._active_tasks = set()
        
        # 订阅账号更新事件
        self._subscribe_events()

    def _subscribe_events(self):
        """订阅事件"""
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.infrastructure.common.event.event_bus import EventBus
            from src.infrastructure.common.event.events import AccountUpdatedEvent
            
            event_bus = ServiceLocator().get(EventBus)
            if event_bus:
                # 订阅键必须为字符串（与 DomainEvent.event_type = type(self).__name__ 对齐）
                event_bus.subscribe("AccountUpdatedEvent", self._on_account_updated_event)
        except Exception as e:
            logger.error(f"订阅账号更新事件失败: {e}")

    def _on_account_updated_event(self, event):
        """处理账号更新事件"""
        try:
            self.account_updated.emit(event.account_id, getattr(event, 'update_type', 'status'))
        except Exception as e:
            logger.error(f"处理账号更新事件失败: {e}")

    def add_account(self, account_name: str, platform: str, cookie_data: Dict, profile_folder_name: Optional[str] = None):
        """添加账号"""
        async def run_add():
            try:
                account_id = await self.account_manager.add_account(
                    platform_username=account_name,
                    platform=platform,
                    cookie_data=cookie_data,
                    profile_folder_name=profile_folder_name
                )
                self._on_add_finished(account_id, account_name)
            except Exception as e:
                self._on_add_error(str(e))
                
        task = asyncio.create_task(run_add())
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    def load_accounts(self):
        """加载账号列表"""
        logger.debug("开始加载账号列表...")
        
        async def run_load():
            try:
                import inspect
                if inspect.iscoroutinefunction(self.account_manager.get_accounts):
                    accounts = await self.account_manager.get_accounts()
                else:
                    accounts = self.account_manager.get_accounts()
                self._on_load_finished(accounts)
            except Exception as e:
                logger.error(f"加载账号失败: {e}", exc_info=True)
                self._on_load_error(str(e))
                
        task = asyncio.create_task(run_load())
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    def delete_accounts(self, accounts: List[Dict], delete_cookie: bool = False):
        """批量删除账号"""
        if not accounts:
            return

        async def run_delete():
            success_count = 0
            failed_names: List[str] = []
            for acc in accounts:
                try:
                    res = await self.account_manager.delete_account(
                        account_id=acc['id'],
                        delete_cookie=delete_cookie,
                        delete_records=delete_cookie
                    )
                    if res:
                        success_count += 1
                    else:
                        failed_names.append(acc.get('username') or str(acc.get('id', '')))
                except Exception as e:
                    logger.error(f"删除账号失败 {acc.get('username')}: {e}")
                    failed_names.append(acc.get('username') or str(acc.get('id', '')))
            if failed_names:
                from PySide6.QtCore import QTimer
                err_msg = f"以下账号删除失败：{', '.join(failed_names)}"
                QTimer.singleShot(0, lambda: self._on_delete_error(err_msg))
            self._on_delete_finished(success_count)
            
        task = asyncio.create_task(run_delete())
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    def clear_cookie(self, account_id: int, platform_username: str, platform: str):
        """清理账号 Cookie"""
        async def run_clear():
            try:
                success = await self.account_manager.cleanup_cookie(account_id)
                self.cookie_cleared.emit(bool(success), platform_username)
            except Exception as e:
                logger.error(f"清理Cookie失败: {e}")
                self.clear_cookie_error.emit(str(e))

        task = asyncio.create_task(run_clear())
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    # --- 内部辅助方法 ---

    def _on_add_finished(self, account_id, account_name):
        logger.info(f"账号添加成功: {account_name}, ID: {account_id}")
        self.account_added.emit(account_id, account_name)

    def _on_add_error(self, error):
        logger.error(f"添加账号失败: {error}")
        self.add_account_error.emit(str(error))

    def _on_load_finished(self, accounts):
        self.accounts_loaded.emit(accounts)

    def _on_load_error(self, error):
        logger.error(f"异步加载账号出错: {error}")
        self.load_error.emit(str(error))

    def _on_delete_finished(self, count):
        logger.info(f"批量删除完成，成功删除 {count} 个")
        self.batch_delete_finished.emit(count)

    def _on_delete_error(self, error):
        logger.error(f"批量删除出错: {error}")
        self.batch_delete_error.emit(str(error))
