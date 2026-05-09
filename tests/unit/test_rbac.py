"""
RBAC 权限模型单元测试
测试角色定义、权限分配、权限检查的完整逻辑。
"""

import pytest

from src.infrastructure.common.security.rbac import (
    RBAC,
    Role,
    Permission,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def rbac():
    return RBAC()


class TestDefaultRoles:

    def test_has_trial_role(self, rbac):
        assert "trial" in rbac.roles

    def test_has_basic_role(self, rbac):
        assert "basic" in rbac.roles

    def test_has_premium_role(self, rbac):
        assert "premium" in rbac.roles

    def test_trial_can_publish_video(self, rbac):
        assert Permission.PUBLISH_VIDEO in rbac.roles["trial"].permissions

    def test_premium_has_all_permissions(self, rbac):
        premium = rbac.roles["premium"]
        for perm in Permission:
            assert perm in premium.permissions


class TestAddRole:

    def test_add_custom_role(self, rbac):
        custom = Role("custom", {Permission.VIEW_STATS}, "自定义角色")
        rbac.add_role(custom)
        assert "custom" in rbac.roles

    def test_overwrite_existing_role(self, rbac):
        new_trial = Role("trial", {Permission.VIEW_STATS})
        rbac.add_role(new_trial)
        assert Permission.VIEW_STATS in rbac.roles["trial"].permissions
        assert Permission.PUBLISH_VIDEO not in rbac.roles["trial"].permissions


class TestAssignRole:

    def test_assign_role_to_user(self, rbac):
        rbac.assign_role(1, "basic")
        assert "basic" in rbac.get_user_roles(1)

    def test_assign_multiple_roles(self, rbac):
        rbac.assign_role(1, "trial")
        rbac.assign_role(1, "basic")
        roles = rbac.get_user_roles(1)
        assert "trial" in roles
        assert "basic" in roles

    def test_assign_nonexistent_role_raises(self, rbac):
        with pytest.raises(ValueError, match="角色不存在"):
            rbac.assign_role(1, "nonexistent_role")

    def test_assign_same_role_twice_no_duplicate(self, rbac):
        rbac.assign_role(1, "basic")
        rbac.assign_role(1, "basic")
        assert rbac.get_user_roles(1).count("basic") == 1


class TestRemoveRole:

    def test_remove_assigned_role(self, rbac):
        rbac.assign_role(1, "basic")
        rbac.remove_role(1, "basic")
        assert "basic" not in rbac.get_user_roles(1)

    def test_remove_nonexistent_role_no_error(self, rbac):
        rbac.remove_role(99, "basic")  # 不应抛异常

    def test_remove_one_role_keeps_others(self, rbac):
        rbac.assign_role(1, "trial")
        rbac.assign_role(1, "basic")
        rbac.remove_role(1, "trial")
        assert "basic" in rbac.get_user_roles(1)
        assert "trial" not in rbac.get_user_roles(1)


class TestCheckPermission:

    def test_user_with_basic_can_publish_video(self, rbac):
        rbac.assign_role(1, "basic")
        assert rbac.check_permission(1, "publish", "video") is True

    def test_user_with_trial_cannot_manage_account(self, rbac):
        rbac.assign_role(1, "trial")
        assert rbac.check_permission(1, "manage", "account") is False

    def test_user_with_premium_can_view_stats(self, rbac):
        rbac.assign_role(1, "premium")
        assert rbac.check_permission(1, "view", "stats") is True

    def test_user_without_role_has_no_permission(self, rbac):
        assert rbac.check_permission(999, "publish", "video") is False

    def test_unknown_permission_returns_false(self, rbac):
        rbac.assign_role(1, "premium")
        assert rbac.check_permission(1, "delete", "everything") is False

    def test_multiple_roles_union_permissions(self, rbac):
        rbac.assign_role(1, "trial")
        rbac.assign_role(1, "premium")
        assert rbac.check_permission(1, "manage", "subscription") is True


class TestGetUserPermissions:

    def test_no_role_returns_empty_set(self, rbac):
        assert rbac.get_user_permissions(999) == set()

    def test_basic_role_permissions(self, rbac):
        rbac.assign_role(1, "basic")
        perms = rbac.get_user_permissions(1)
        assert Permission.PUBLISH_VIDEO in perms
        assert Permission.MANAGE_ACCOUNT in perms

    def test_union_of_multiple_roles(self, rbac):
        rbac.assign_role(1, "trial")
        rbac.assign_role(1, "premium")
        perms = rbac.get_user_permissions(1)
        assert Permission.VIEW_STATS in perms  # premium only
        assert Permission.PUBLISH_VIDEO in perms  # both
