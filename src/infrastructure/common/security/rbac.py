"""
RBAC权限模型
文件路径：src/core/common/security/rbac.py
功能：实现用户→角色→权限模型，支持细粒度权限控制
"""

from typing import Dict, List, Set, Optional
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Permission(Enum):
    """权限枚举"""
    PUBLISH_VIDEO = "publish:video"
    PUBLISH_IMAGE = "publish:image"
    READ_COOKIE = "read:cookie"
    WRITE_COOKIE = "write:cookie"
    MANAGE_ACCOUNT = "manage:account"
    MANAGE_SUBSCRIPTION = "manage:subscription"
    VIEW_STATS = "view:stats"


@dataclass
class Role:
    """角色定义"""
    name: str
    permissions: Set[Permission]
    description: str = ""


class RBAC:
    """RBAC权限模型
    
    实现用户→角色→权限模型，支持细粒度权限控制。
    """
    
    def __init__(self):
        """初始化RBAC"""
        self.roles: Dict[str, Role] = {}
        self.user_roles: Dict[int, Set[str]] = {}  # user_id -> {role_names}
        self.logger = logging.getLogger(__name__)
        
        # 初始化默认角色
        self._init_default_roles()
    
    def _init_default_roles(self) -> None:
        """初始化默认角色"""
        # 试用用户角色
        trial_role = Role(
            name="trial",
            permissions={
                Permission.PUBLISH_VIDEO,
                Permission.PUBLISH_IMAGE,
                Permission.READ_COOKIE,
            },
            description="试用用户，有限权限"
        )
        self.roles["trial"] = trial_role
        
        # 基础用户角色
        basic_role = Role(
            name="basic",
            permissions={
                Permission.PUBLISH_VIDEO,
                Permission.PUBLISH_IMAGE,
                Permission.READ_COOKIE,
                Permission.WRITE_COOKIE,
                Permission.MANAGE_ACCOUNT,
            },
            description="基础用户，标准权限"
        )
        self.roles["basic"] = basic_role
        
        # 高级用户角色
        premium_role = Role(
            name="premium",
            permissions={
                Permission.PUBLISH_VIDEO,
                Permission.PUBLISH_IMAGE,
                Permission.READ_COOKIE,
                Permission.WRITE_COOKIE,
                Permission.MANAGE_ACCOUNT,
                Permission.MANAGE_SUBSCRIPTION,
                Permission.VIEW_STATS,
            },
            description="高级用户，完整权限"
        )
        self.roles["premium"] = premium_role
    
    def add_role(self, role: Role) -> None:
        """添加角色
        
        Args:
            role: 角色定义
        """
        self.roles[role.name] = role
        self.logger.debug(f"添加角色: {role.name}")
    
    def assign_role(self, user_id: int, role_name: str) -> None:
        """分配角色给用户
        
        Args:
            user_id: 用户ID
            role_name: 角色名称
        """
        if role_name not in self.roles:
            raise ValueError(f"角色不存在: {role_name}")
        
        if user_id not in self.user_roles:
            self.user_roles[user_id] = set()
        
        self.user_roles[user_id].add(role_name)
        self.logger.debug(f"分配角色: 用户ID={user_id}, 角色={role_name}")
    
    def remove_role(self, user_id: int, role_name: str) -> None:
        """移除用户角色
        
        Args:
            user_id: 用户ID
            role_name: 角色名称
        """
        if user_id in self.user_roles:
            self.user_roles[user_id].discard(role_name)
            self.logger.debug(f"移除角色: 用户ID={user_id}, 角色={role_name}")
    
    def check_permission(
        self,
        user_id: int,
        operation: str,
        resource: Optional[str] = None
    ) -> bool:
        """检查用户权限
        
        Args:
            user_id: 用户ID
            operation: 操作（如publish、read、manage）
            resource: 资源（如video、cookie、account），可选
        
        Returns:
            如果有权限返回True，否则返回False
        """
        # 构建权限字符串
        if resource:
            permission_str = f"{operation}:{resource}"
        else:
            permission_str = operation
        
        # 尝试匹配权限枚举
        try:
            permission = Permission(permission_str)
        except ValueError:
            # 如果不在枚举中，返回False
            self.logger.warning(f"未知权限: {permission_str}")
            return False
        
        # 获取用户角色
        user_roles = self.user_roles.get(user_id, set())
        
        # 检查是否有任一角色拥有该权限
        for role_name in user_roles:
            role = self.roles.get(role_name)
            if role and permission in role.permissions:
                return True
        
        return False
    
    def get_user_permissions(self, user_id: int) -> Set[Permission]:
        """获取用户所有权限
        
        Args:
            user_id: 用户ID
        
        Returns:
            权限集合
        """
        permissions = set()
        user_roles = self.user_roles.get(user_id, set())
        
        for role_name in user_roles:
            role = self.roles.get(role_name)
            if role:
                permissions.update(role.permissions)
        
        return permissions
    
    def get_user_roles(self, user_id: int) -> List[str]:
        """获取用户角色列表
        
        Args:
            user_id: 用户ID
        
        Returns:
            角色名称列表
        """
        return list(self.user_roles.get(user_id, set()))

