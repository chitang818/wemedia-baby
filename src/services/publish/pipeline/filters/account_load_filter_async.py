"""
账号加载过滤器（异步版本）
文件路径：src/business/publish_pipeline/filters/account_load_filter_async.py
功能：加载账号信息和Cookie（异步）
"""

from src.infrastructure.common.pipeline.base_filter import BaseFilter, PublishContext
from src.services.account.account_manager_async import AccountManagerAsync
from .account_utils import find_account_by_name
import logging

logger = logging.getLogger(__name__)


class AccountLoadFilterAsync(BaseFilter):
    """账号加载过滤器（异步版本）"""
    
    def __init__(self, account_manager: AccountManagerAsync):
        """初始化账号加载过滤器
        
        Args:
            account_manager: 账号管理器实例（异步版本）
        """
        super().__init__()
        self.account_manager = account_manager
    
    async def process(self, context: PublishContext) -> bool:
        """加载账号信息（异步）
        
        Args:
            context: 发布上下文
        
        Returns:
            如果加载成功返回True，否则返回False
        """
        try:
            # 获取账号信息（异步）
            accounts = await self.account_manager.get_accounts(platform=context.platform)
            account = find_account_by_name(accounts, context.account_name)

            if not account:
                self.set_error(f"账号不存在: {context.account_name}")
                return False
            
            # 将账号数据转换为Account实体（如果需要）
            # 这里暂时直接使用字典
            context.account = account
            
            # 加载Cookie（异步）
            account_id = account.get('id')
            cookie_data = await self.account_manager.load_account_cookie(
                account_id, merge_storage_state=True
            )

            if not cookie_data:
                self.set_error(f"Cookie不存在或已失效: {context.account_name}")
                return False
            if not isinstance(cookie_data, (dict, list)):
                self.set_error(f"Cookie格式不正确: {type(cookie_data)}")
                return False
            
            self.logger.info(f"账号与Cookie校验通过: {context.account_name}")
            return True
            
        except Exception as e:
            self.set_error(f"账号加载失败: {str(e)}")
            self.logger.error(self.get_error(), exc_info=True)
            return False
