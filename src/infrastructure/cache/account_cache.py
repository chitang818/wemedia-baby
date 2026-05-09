"""
账号缓存
文件路径：src/core/cache/account_cache.py
功能：提供账号相关的缓存功能
"""

from typing import List, Dict, Any, Optional
import logging

from .cache_manager import CacheManager

logger = logging.getLogger(__name__)


class AccountCache:
    """账号缓存 - 封装账号相关的缓存操作"""
    
    def __init__(
        self,
        cache_manager: CacheManager,
        ttl: int = 1800
    ):
        """初始化账号缓存
        
        Args:
            cache_manager: 缓存管理器实例
            ttl: 默认生存时间（秒）
        """
        self.cache_manager = cache_manager
        self.ttl = ttl
        self.logger = logging.getLogger(__name__)
    
    def _get_accounts_key(self, user_id: int, platform: Optional[str] = None) -> str:
        """生成账号列表缓存键
        
        Args:
            user_id: 用户ID
            platform: 平台名称（可选）
            
        Returns:
            缓存键
        """
        if platform:
            return f"accounts:{user_id}:{platform}"
        return f"accounts:{user_id}:all"
    
    def _get_account_key(self, account_id: int) -> str:
        """生成单个账号缓存键
        
        Args:
            account_id: 账号ID
            
        Returns:
            缓存键
        """
        return f"account:{account_id}"
    
    def get_accounts(
        self,
        user_id: int,
        platform: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """获取账号列表（从缓存）
        
        Args:
            user_id: 用户ID
            platform: 平台名称（可选）
            
        Returns:
            账号列表，缓存不存在返回None
        """
        key = self._get_accounts_key(user_id, platform)
        return self.cache_manager.get(key)
    
    def set_accounts(
        self,
        user_id: int,
        accounts: List[Dict[str, Any]],
        platform: Optional[str] = None,
        ttl: Optional[int] = None
    ):
        """缓存账号列表
        
        Args:
            user_id: 用户ID
            accounts: 账号列表
            platform: 平台名称（可选）
            ttl: 生存时间（秒），None 使用默认值
        """
        key = self._get_accounts_key(user_id, platform)
        self.cache_manager.set(key, accounts, ttl or self.ttl)
        self.logger.debug(f"缓存账号列表: {key}, 数量: {len(accounts)}")
    
    def get_account(self, account_id: int) -> Optional[Dict[str, Any]]:
        """获取单个账号（从缓存）
        
        Args:
            account_id: 账号ID
            
        Returns:
            账号字典，缓存不存在返回None
        """
        key = self._get_account_key(account_id)
        return self.cache_manager.get(key)
    
    def set_account(
        self,
        account: Dict[str, Any],
        ttl: Optional[int] = None
    ):
        """缓存单个账号
        
        Args:
            account: 账号字典
            ttl: 生存时间（秒），None 使用默认值
        """
        account_id = account.get('id')
        if account_id:
            key = self._get_account_key(account_id)
            self.cache_manager.set(key, account, ttl or self.ttl)
            self.logger.debug(f"缓存账号: {key}")
    
    def invalidate_account(self, account_id: int):
        """使账号缓存失效
        
        Args:
            account_id: 账号ID
        """
        key = self._get_account_key(account_id)
        self.cache_manager.delete(key)
        self.logger.debug(f"使账号缓存失效: {key}")
    
    def invalidate_accounts(self, user_id: int, platform: Optional[str] = None):
        """使账号列表缓存失效
        
        Args:
            user_id: 用户ID
            platform: 平台名称（可选）
        """
        # 删除特定平台的缓存
        if platform:
            key = self._get_accounts_key(user_id, platform)
            self.cache_manager.delete(key)
        
        # 删除全部账号的缓存
        key_all = self._get_accounts_key(user_id, None)
        self.cache_manager.delete(key_all)
        
        self.logger.debug(f"使账号列表缓存失效: user_id={user_id}, platform={platform}")
    
    def invalidate_all(self, user_id: int):
        """使所有账号相关缓存失效
        
        Args:
            user_id: 用户ID
        """
        # 删除所有可能的账号列表缓存键
        # 注意：这里需要知道所有平台，或者使用通配符删除
        # 简化实现：删除已知的缓存键
        self.invalidate_accounts(user_id, None)
        self.logger.debug(f"使所有账号缓存失效: user_id={user_id}")

