"""
账号管理业务模块
"""

# 异步版本 (新架构)
from .account_manager_async import AccountManagerAsync
from .cookie_manager import CookieManager
from .account_group_service import AccountGroupService

from .account_verifier import AccountVerifier

# 兼容性别名
AccountManager = AccountManagerAsync

__all__ = ['AccountManagerAsync', 'AccountManager', 'CookieManager', 'AccountVerifier', 'AccountGroupService']

