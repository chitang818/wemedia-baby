"""
权限控制器单元测试
覆盖：PermissionController 同步包装器在不同线程/事件循环场景下的安全性
"""
import asyncio
import threading
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def mock_permission_controller():
    """创建带 mock 异步控制器的 PermissionController。"""
    with patch("src.proprietary.subscription.permission_controller_async.PermissionControllerAsync") as MockAsync:
        instance = MockAsync.return_value
        instance.check_publish_permission = AsyncMock(return_value=True)
        instance.check_trial_count = AsyncMock(return_value=True)

        from src.proprietary.subscription.permission_controller_async import PermissionController
        ctrl = PermissionController()
        yield ctrl


class TestPermissionControllerSync:
    """同步包装器测试"""

    def test_check_publish_permission_returns_true(self, mock_permission_controller):
        result = mock_permission_controller.check_publish_permission(user_id=1)
        assert result is True

    def test_check_trial_count_returns_true(self, mock_permission_controller):
        result = mock_permission_controller.check_trial_count(user_id=1)
        assert result is True

    def test_check_publish_permission_exception_returns_false(self, mock_permission_controller):
        mock_permission_controller._async_controller.check_publish_permission = AsyncMock(
            side_effect=RuntimeError("test error")
        )
        result = mock_permission_controller.check_publish_permission(user_id=1)
        assert result is False

    def test_check_from_background_thread(self, mock_permission_controller):
        """从后台线程调用同步包装器不应死锁。"""
        results = []

        def worker():
            r = mock_permission_controller.check_publish_permission(user_id=1)
            results.append(r)

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=10)
        assert not t.is_alive(), "线程超时——可能发生死锁"
        assert results == [True]


class TestPermissionControllerAsync:
    """异步控制器测试"""

    @pytest.mark.asyncio
    async def test_check_publish_permission_logged_in(self):
        with patch("src.proprietary.subscription.permission_controller_async.CurrentUserService") as MockCUS:
            mock_cus = MockCUS.return_value
            mock_cus.get_user_id.return_value = 42
            mock_cus.is_logged_in.return_value = True

            from src.proprietary.subscription.permission_controller_async import PermissionControllerAsync
            ctrl = PermissionControllerAsync()
            result = await ctrl.check_publish_permission(42)
            assert result is True

    @pytest.mark.asyncio
    async def test_check_publish_permission_not_logged_in_no_subscription(self):
        with patch("src.proprietary.subscription.permission_controller_async.CurrentUserService") as MockCUS:
            mock_cus = MockCUS.return_value
            mock_cus.get_user_id.return_value = 0
            mock_cus.is_logged_in.return_value = False

            mock_sub_repo = AsyncMock()
            mock_sub_repo.get_active_subscription.return_value = None
            mock_user_repo = AsyncMock()
            mock_user_repo.get_by_id.return_value = {"trial_count": 0}

            from src.proprietary.subscription.permission_controller_async import PermissionControllerAsync
            ctrl = PermissionControllerAsync(user_repo=mock_user_repo, sub_repo=mock_sub_repo)
            result = await ctrl.check_publish_permission(99)
            assert result is False
