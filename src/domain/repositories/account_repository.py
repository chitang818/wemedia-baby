"""
账号 Repository（同步版本，已废弃）

⚠️ 已废弃：请使用 AccountRepositoryAsync 替代。
此文件保留用于向后兼容，将在后续版本中移除。
"""
import warnings
warnings.warn(
    "account_repository.py (sync) 已废弃，请使用 account_repository_async.py",
    DeprecationWarning,
    stacklevel=2
)

from typing import List, Dict, Any, Optional
import logging

from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class AccountRepository(BaseRepository):
    """账号 Repository - 封装账号数据访问逻辑"""
    
    def create(
        self,
        user_id: int,
        account_name: str,
        platform: str,
        cookie_path: str,
        platform_username: Optional[str] = None
    ) -> int:
        """创建账号
        
        Args:
            user_id: 用户ID
            account_name: 账号名称
            platform: 平台名称
            cookie_path: Cookie文件路径
            platform_username: 平台用户名（可选）
            
        Returns:
            新创建的账号ID
        """
        try:
            return self.data_storage.create_platform_account(
                user_id=user_id,
                account_name=account_name,
                platform=platform,
                cookie_path=cookie_path,
                platform_username=platform_username
            )
        except Exception as e:
            self.handle_error(e, "create")
    
    def find_all(
        self,
        user_id: int,
        platform: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """查找所有账号
        
        Args:
            user_id: 用户ID
            platform: 平台名称（可选，用于筛选）
            
        Returns:
            账号列表
        """
        try:
            return self.data_storage.get_platform_accounts(
                user_id=user_id,
                platform=platform
            )
        except Exception as e:
            self.handle_error(e, "find_all")
            return []
    
    def find_by_id(self, user_id: int, account_id: int) -> Optional[Dict[str, Any]]:
        """根据ID查找账号
        
        Args:
            user_id: 用户ID
            account_id: 账号ID
            
        Returns:
            账号字典，不存在返回None
        """
        try:
            # DataStorage 没有直接的 find_by_id 方法，需要从列表中查找
            accounts = self.data_storage.get_platform_accounts(user_id=user_id)
            for account in accounts:
                if account.get('id') == account_id:
                    return account
            return None
        except Exception as e:
            self.handle_error(e, "find_by_id")
            return None
    
    def update_status(
        self,
        account_id: int,
        login_status: str,
        last_login_at: Optional[str] = None
    ) -> bool:
        """更新账号状态
        
        Args:
            account_id: 账号ID
            login_status: 登录状态
            last_login_at: 最后登录时间（可选）
            
        Returns:
            是否成功
        """
        try:
            self.data_storage.update_account_status(
                account_id=account_id,
                login_status=login_status,
                last_login_at=last_login_at
            )
            return True
        except Exception as e:
            self.handle_error(e, "update_status")
            return False
    
    def update_platform_username(
        self,
        account_id: int,
        platform_username: str
    ) -> bool:
        """更新平台用户名
        
        Args:
            account_id: 账号ID
            platform_username: 平台用户名
            
        Returns:
            是否成功
        """
        try:
            self.data_storage.update_platform_username(
                account_id=account_id,
                platform_username=platform_username
            )
            return True
        except Exception as e:
            self.handle_error(e, "update_platform_username")
            return False
    
    def update_cookie_path(
        self,
        account_id: int,
        cookie_path: str
    ) -> bool:
        """更新Cookie路径
        
        Args:
            account_id: 账号ID
            cookie_path: Cookie文件路径
            
        Returns:
            是否成功
        """
        try:
            # DataStorage 可能没有直接的方法，需要检查
            # 这里先使用 update_account_status 的扩展方式
            # 或者需要添加新的方法到 DataStorage
            # 暂时返回 False，表示功能待实现
            self.logger.warning("update_cookie_path 方法待实现")
            return False
        except Exception as e:
            self.handle_error(e, "update_cookie_path")
            return False
    
    def delete(self, account_id: int) -> bool:
        """删除账号
        
        Args:
            account_id: 账号ID
            
        Returns:
            是否成功
        """
        try:
            self.data_storage.delete_platform_account(account_id)
            return True
        except Exception as e:
            self.handle_error(e, "delete")
            return False
    
    def exists(self, user_id: int, account_name: str, platform: str) -> bool:
        """检查账号是否存在
        
        Args:
            user_id: 用户ID
            account_name: 账号名称
            platform: 平台名称
            
        Returns:
            是否存在
        """
        try:
            accounts = self.find_all(user_id=user_id, platform=platform)
            return any(acc.get('account_name') == account_name for acc in accounts)
        except Exception as e:
            self.logger.error(f"检查账号是否存在失败: {e}")
            return False

