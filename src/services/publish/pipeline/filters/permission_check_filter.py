"""
权限检查过滤器
文件路径：src/business/publish_pipeline/filters/permission_check_filter.py
功能：检查用户发布权限
"""

from typing import Optional
from .. import Filter, PublishContext
import logging

logger = logging.getLogger(__name__)


class PermissionCheckFilter(Filter):
    """权限检查过滤器"""
    
    def __init__(self, permission_controller=None):
        """初始化权限检查过滤器
        
        Args:
            permission_controller: 权限控制器实例
        """
        super().__init__()
        self.permission_controller = permission_controller
        self._error_message: Optional[str] = None
    
    def process(self, context: PublishContext) -> bool:
        """检查发布权限
        
        Args:
            context: 发布上下文
            
        Returns:
            如果有权限返回True，否则返回False
        """
        try:
            # 开源/社区版：订阅功能默认不启用；或闭源控制器缺失时放行，避免启动时报 ImportError
            try:
                from config.feature_flags import FeatureFlags
                if not FeatureFlags.is_feature_enabled("subscription"):
                    return True
            except Exception:
                return True

            if self.permission_controller is None:
                return True

            # 检查订阅状态
            if not self.permission_controller.check_publish_permission(context.user_id):
                self._error_message = "用户无发布权限，请检查订阅状态"
                return False
            
            # 检查试用次数（如果是试用用户）
            if not self.permission_controller.check_trial_count(context.user_id):
                self._error_message = "试用次数已用完，请购买订阅"
                return False
            
            self.logger.info(f"权限检查通过: 用户ID={context.user_id}")
            return True
            
        except Exception as e:
            self._error_message = f"权限检查失败: {str(e)}"
            self.logger.error(self._error_message, exc_info=True)
            return False
    
    def get_error(self) -> Optional[str]:
        """获取错误信息"""
        return self._error_message

