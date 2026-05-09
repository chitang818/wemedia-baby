"""
账号组服务
文件路径：src/services/account/account_group_service.py
功能：账号组管理业务逻辑
已迁移：使用 AccountGroupRepositoryAsync 替代 AsyncDataStorage
"""

from typing import List, Optional, Dict, Any
import logging

from src.infrastructure.common.di.service_locator import ServiceLocator
from src.infrastructure.common.event.event_bus import EventBus
from src.domain import AccountGroup, Account
from src.domain.repositories.account_group_repository_async import AccountGroupRepositoryAsync
from src.domain.repositories.account_repository_async import AccountRepositoryAsync

logger = logging.getLogger(__name__)


class AccountGroupService:
    """账号组服务 - 账号组管理业务逻辑
    
    使用 AccountGroupRepositoryAsync 进行数据访问，已完成从 AsyncDataStorage 的迁移。
    """
    
    def __init__(
        self,
        event_bus: Optional[EventBus] = None
    ):
        """初始化账号组服务
        
        Args:
            event_bus: 事件总线（可选，默认从ServiceLocator获取）
        """
        self.service_locator = ServiceLocator()
        self.event_bus = event_bus or self.service_locator.get(EventBus)
        
        # 使用 Repository 替代 AsyncDataStorage
        self.group_repository = AccountGroupRepositoryAsync()
        self.account_repository = AccountRepositoryAsync()
        self.logger = logging.getLogger(__name__)

    async def _sync_material_library_group_tree(self) -> None:
        """同步媒体库「账号库」下账号与账号组目录（含视频/图文子结构；失败仅记日志）。"""
        try:
            from src.infrastructure.common.material_library_manager import MaterialLibraryManager
            await MaterialLibraryManager.sync_platform_account_tree()
        except Exception as e:
            self.logger.warning("同步媒体库账号组目录失败: %s", e, exc_info=True)
    
    async def create_group(
        self,
        user_id: int,
        group_name: str,
        description: Optional[str] = None
    ) -> AccountGroup:
        """创建账号组
        
        Args:
            user_id: 用户ID
            group_name: 账号组名称
            description: 描述（可选）
            
        Returns:
            AccountGroup 实体
            
        Raises:
            ValueError: 如果同名账号组已存在
        """
        # 通过 Repository 创建（内部已处理重复检查）
        group_id = await self.group_repository.create(
            user_id=user_id,
            group_name=group_name,
            description=description
        )
        
        group = AccountGroup(
            group_id=group_id,
            user_id=user_id,
            group_name=group_name,
            description=description
        )
        
        await self._sync_material_library_group_tree()
        self.logger.info(f"创建账号组成功: {group_name} (ID: {group_id})")
        return group
    
    async def get_groups(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取账号组列表（含组内账号）
        
        单用户模式：user_id 为 None 时返回本地全部账号组。
        
        Args:
            user_id: 用户ID（可选；None 时返回全部）
            
        Returns:
            账号组列表，每个账号组包含 accounts 字段
        """
        groups_data = await self.group_repository.find_all(user_id)
        
        result = []
        for group_dict in groups_data:
            # 通过 Repository 获取该组内的账号
            accounts = await self.group_repository.find_accounts_by_group(group_dict['id'])
            
            result.append({
                'group_id': group_dict['id'],
                'id': group_dict['id'],
                'user_id': group_dict.get('user_id'),
                'group_name': group_dict['group_name'],
                'description': group_dict.get('description'),
                'created_at': group_dict.get('created_at'),
                'updated_at': group_dict.get('updated_at'),
                'accounts': accounts,
                'account_count': len(accounts),
                'platforms': [acc['platform'] for acc in accounts]
            })
        
        return result
    
    async def get_group_by_id(self, group_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取账号组详情
        
        Args:
            group_id: 账号组ID
            
        Returns:
            账号组字典或 None
        """
        group_dict = await self.group_repository.find_by_id(group_id)
        if not group_dict:
            return None
        
        # 通过 Repository 获取组内账号
        accounts = await self.group_repository.find_accounts_by_group(group_id)
        
        group_dict['accounts'] = accounts
        group_dict['account_count'] = len(accounts)
        group_dict['platforms'] = [acc['platform'] for acc in accounts]
        
        return group_dict
    
    async def update_group(
        self,
        group_id: int,
        group_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> None:
        """更新账号组信息
        
        Args:
            group_id: 账号组ID
            group_name: 新名称（可选）
            description: 新描述（可选）
        """
        # 通过 Repository 更新
        await self.group_repository.update(
            group_id=group_id,
            group_name=group_name,
            description=description
        )
        await self._sync_material_library_group_tree()
        self.logger.info(f"更新账号组成功: ID {group_id}")
    
    async def delete_group(self, group_id: int) -> None:
        """删除账号组（不删除组内账号，仅解除关联）
        
        Args:
            group_id: 账号组ID
        """
        # 通过 Repository 删除（内部已处理解除账号关联）
        await self.group_repository.delete(group_id)
        await self._sync_material_library_group_tree()
        self.logger.info(f"删除账号组成功: ID {group_id}")
    
    async def add_account_to_group(self, group_id: int, account_id: int) -> None:
        """将账号添加到账号组
        
        Args:
            group_id: 账号组ID
            account_id: 账号ID
            
        Raises:
            ValueError: 如果同平台账号已存在于该组中
        """
        # 获取要添加的账号信息（通过 AccountRepositoryAsync）
        # 注意：find_by_id 需要 user_id，这里我们直接查询 ORM
        from src.infrastructure.storage.orm_models.platform_account import PlatformAccount
        account_orm = await PlatformAccount.get_or_none(id=account_id)
        if not account_orm:
            raise ValueError(f"账号 ID {account_id} 不存在")
        
        platform = account_orm.platform
        
        # 检查该组内是否已有同平台账号
        existing = await self.group_repository.check_platform_conflict(group_id, platform)
        if existing:
            existing_name = existing.get('platform_username', '未知')
            raise ValueError(
                f"该账号组内已有{self._get_platform_name(platform)}账号: {existing_name}"
            )
        
        # 通过 Repository 添加
        await self.group_repository.add_account(group_id, account_id)
        await self._sync_material_library_group_tree()
        self.logger.info(f"账号 {account_id} 已添加到账号组 {group_id}")
    
    async def remove_account_from_group(self, account_id: int) -> None:
        """将账号从账号组中移除
        
        Args:
            account_id: 账号ID
        """
        # 通过 Repository 移除
        await self.group_repository.remove_account(account_id)
        await self._sync_material_library_group_tree()
        self.logger.info(f"账号 {account_id} 已从账号组中移除")
    
    async def get_ungrouped_accounts(self, user_id: int) -> List[Dict[str, Any]]:
        """获取未分组的账号
        
        Args:
            user_id: 用户ID
            
        Returns:
            未分组账号列表
        """
        # 通过 Repository 获取
        return await self.group_repository.find_ungrouped_accounts(user_id)
    
    async def get_all_accounts(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取所有账号（用于添加组成员选择）
        
        单用户模式：user_id 为 None 时返回本地全部账号。
        
        Args:
            user_id: 用户ID（可选；None 时返回全部）
            
        Returns:
            账号列表
        """
        return await self.account_repository.find_all(user_id)

    def _get_platform_name(self, platform: str) -> str:
        """获取平台中文名"""
        platform_map = {
            'douyin': '抖音',
            'kuaishou': '快手',
            'xiaohongshu': '小红书',
            'bilibili': 'B站',
            'video_number': '视频号'
        }
        return platform_map.get(platform, platform)
