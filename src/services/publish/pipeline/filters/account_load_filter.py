"""
账号加载过滤器
文件路径：src/business/publish_pipeline/filters/account_load_filter.py
功能：加载账号信息和Cookie
"""

from typing import Optional, List, Dict, Any
from .. import Filter, PublishContext
from src.services.account import AccountManager
from .account_utils import find_account_by_name
import logging

logger = logging.getLogger(__name__)


class AccountLoadFilter(Filter):
    """账号加载过滤器"""
    
    def __init__(self, account_manager: AccountManager):
        """初始化账号加载过滤器
        
        Args:
            account_manager: 账号管理器实例
        """
        super().__init__()
        self.account_manager = account_manager
        self._error_message: Optional[str] = None
    
    def process(self, context: PublishContext) -> bool:
        """加载账号信息
        
        Args:
            context: 发布上下文
            
        Returns:
            如果加载成功返回True，否则返回False
        """
        try:
            # 获取账号信息
            accounts = self.account_manager.get_accounts(platform=context.platform)
            account = find_account_by_name(accounts, context.account_name)

            if not account:
                self._error_message = f"账号不存在: {context.account_name}"
                return False
            
            context.account_data = account
            
            # 加载Cookie
            account_id = account.get('id')
            cookie_data = self.account_manager.load_account_cookie(account_id)
            
            if not cookie_data:
                self._error_message = f"Cookie不存在或已失效: {context.account_name}"
                return False
            if not isinstance(cookie_data, (dict, list)):
                self._error_message = f"Cookie格式不正确: {type(cookie_data)}"
                return False
            
            context.cookie_data = cookie_data
            self.logger.info(f"账号与Cookie校验通过: {context.account_name}")
            return True
            
        except Exception as e:
            self._error_message = f"账号加载失败: {str(e)}"
            self.logger.error(self._error_message, exc_info=True)
            return False
    
    def get_error(self) -> Optional[str]:
        """获取错误信息"""
        return self._error_message

