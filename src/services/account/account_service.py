"""
账号服务
文件路径：src/services/account/account_service.py
功能：账号管理业务逻辑协调（仅用于查询/事件转发）

【职责边界说明】
本类仅封装账号的查询、分组变更和事件发布，
不负责 Cookie 写入、Profile 目录创建、配额校验等完整创建流程。
添加账号请统一走 AccountManagerAsync，避免出现「DB 有记录、磁盘无目录」的不一致状态。
"""

from typing import List, Optional, Dict, Any
import logging

from src.infrastructure.common.di.service_locator import ServiceLocator
from src.infrastructure.common.event.event_bus import EventBus
from src.domain import Account
from src.domain.repositories.account_repository_async import AccountRepositoryAsync
from src.infrastructure.storage.file_storage import AsyncFileStorage

logger = logging.getLogger(__name__)


class AccountService:
    """账号服务 - 账号管理业务逻辑协调"""
    
    def __init__(
        self,
        account_repo: Optional[AccountRepositoryAsync] = None,
        file_storage: Optional[AsyncFileStorage] = None,
        event_bus: Optional[EventBus] = None
    ):
        """初始化账号服务
        
        Args:
            account_repo: 账号 Repository（可选，默认从 ServiceLocator 获取）
            file_storage: 文件存储服务（可选，默认从 ServiceLocator 获取）
            event_bus: 事件总线（可选，默认从 ServiceLocator 获取）
        """
        self.service_locator = ServiceLocator()
        self.account_repo = account_repo or self.service_locator.get(AccountRepositoryAsync)
        self.file_storage = file_storage or self.service_locator.get(AsyncFileStorage)
        self.event_bus = event_bus or self.service_locator.get(EventBus)
        self.logger = logging.getLogger(__name__)
    
    async def add_account(
        self,
        user_id: int,
        account_name: str,
        platform: str,
        platform_username: Optional[str] = None
    ) -> Account:
        """添加账号（异步）
        
        Args:
            user_id: 用户ID
            account_name: 账号名称
            platform: 平台名称
            platform_username: 平台用户名（可选）
        
        Returns:
            Account实体
        """
        # 创建账号记录
        account_id = await self.account_repo.create(
            user_id=user_id,
            platform=platform,
            platform_username=platform_username or account_name,
        )
        
        # 创建Account实体
        account = Account(
            account_id=account_id,
            user_id=user_id,
            platform=platform,
            account_name=account_name,
            platform_username=platform_username,
            status="active",
            login_status="offline"
        )
        
        # 发布账号添加事件
        from src.infrastructure.common.event.events import AccountAddedEvent
        await self.event_bus.publish(AccountAddedEvent(
            user_id=user_id,
            platform_username=platform_username or account_name,
            platform=platform,
        ))
        
        self.logger.info(f"添加账号成功: {account_name}, 平台: {platform}")
        return account
    
    async def get_accounts(
        self,
        user_id: int,
        platform: Optional[str] = None
    ) -> List[Account]:
        """获取账号列表（异步）
        
        Args:
            user_id: 用户ID
            platform: 平台名称（可选）
        
        Returns:
            Account实体列表
        """
        accounts_data = await self.account_repo.find_all(user_id, platform)
        
        accounts = []
        for data in accounts_data:
            account = Account.from_dict({
                'account_id': data['id'],
                'user_id': data['user_id'],
                'platform': data['platform'],
                'account_name': data['account_name'],
                'platform_username': data.get('platform_username'),
                'status': data.get('status', 'active'),
                'login_status': data.get('login_status', 'offline'),
                'last_login_at': data.get('last_login_at'),
                'is_active': data.get('is_active', True),
                'created_at': data.get('created_at'),
                'updated_at': data.get('updated_at'),
            })
            accounts.append(account)
        
        return accounts
    
    async def update_account_status(
        self,
        account_id: int,
        login_status: str
    ) -> None:
        """更新账号状态（异步）
        
        Args:
            account_id: 账号ID
            login_status: 登录状态（online/offline）
        """
        await self.account_repo.update_status(
            account_id=account_id,
            login_status=login_status,
        )
    
    async def delete_account(self, account_id: int) -> None:
        """删除账号（异步）
        
        Args:
            account_id: 账号ID
        """
        account_data = await self.account_repo.find_by_id(account_id=account_id)
        if not account_data:
            return
        
        # 删除账号记录
        await self.account_repo.delete(account_id)
        
        # 发布账号删除事件
        from src.infrastructure.common.event.events import AccountRemovedEvent
        await self.event_bus.publish(AccountRemovedEvent(
            user_id=account_data['user_id'],
            platform_username=account_data.get('platform_username')
            or account_data.get('account_name', ''),
            platform=account_data['platform'],
        ))
        
        self.logger.info(f"删除账号成功: ID {account_id}")
    
    async def get_accounts_by_group(self, group_id: int) -> List[Account]:
        """获取账号组内的所有账号
        
        Args:
            group_id: 账号组ID
            
        Returns:
            Account实体列表
        """
        accounts_data = await self.account_repo.find_by_group(group_id)
        
        accounts = []
        for data in accounts_data:
            account = Account.from_dict({
                'account_id': data['id'],
                'user_id': data['user_id'],
                'platform': data['platform'],
                'account_name': data.get('platform_username', ''),
                'platform_username': data.get('platform_username'),
                'login_status': data.get('login_status', 'offline'),
                'last_login_at': data.get('last_login_at'),
                'created_at': data.get('created_at'),
                'group_id': data.get('group_id'),
            })
            accounts.append(account)
        
        return accounts
    
    async def update_account_group(self, account_id: int, group_id: Optional[int]) -> None:
        """更新账号的分组
        
        Args:
            account_id: 账号ID
            group_id: 账号组ID（None 表示从组中移除）
        """
        await self.account_repo.update_group(
            account_id=account_id,
            group_id=group_id,
        )
        
        if group_id:
            self.logger.info(f"账号 {account_id} 已分配到账号组 {group_id}")
        else:
            self.logger.info(f"账号 {account_id} 已从账号组中移除")

