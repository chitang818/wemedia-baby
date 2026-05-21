"""
权限控制器（闭源实现）
原路径：src/services/subscription/permission_controller_async.py
"""

from typing import Optional
from datetime import datetime
from src.domain.repositories.user_repository_async import UserRepositoryAsync
from src.domain.repositories.subscription_repository_async import SubscriptionRepositoryAsync
from src.services.auth.current_user_service import CurrentUserService
import logging

logger = logging.getLogger(__name__)


class PermissionControllerAsync:
    """权限控制器（异步版本）"""

    def __init__(
        self,
        user_repo: Optional[UserRepositoryAsync] = None,
        sub_repo: Optional[SubscriptionRepositoryAsync] = None,
    ):
        self.user_repo = user_repo or UserRepositoryAsync()
        self.sub_repo = sub_repo or SubscriptionRepositoryAsync()
        self.logger = logging.getLogger(__name__)

    def check_pro_permission(self, user_id: int) -> bool:
        curr = CurrentUserService()
        if curr.get_user_id() == user_id and curr.is_logged_in():
            return curr.has_pro_permission()
        return False

    async def check_publish_permission(self, user_id: int) -> bool:
        curr = CurrentUserService()
        if curr.get_user_id() == user_id and curr.is_logged_in():
            return True

        subscription_data = await self.sub_repo.get_active_subscription(user_id)
        if subscription_data:
            end_date_str = subscription_data.get("end_date")
            if end_date_str:
                if isinstance(end_date_str, str):
                    try:
                        end_date = datetime.fromisoformat(end_date_str.replace(" ", "T"))
                    except (ValueError, TypeError):
                        end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
                else:
                    end_date = end_date_str
                if datetime.now() <= end_date:
                    return True
                await self.sub_repo.update(subscription_data["id"], status="expired")

        user = await self.user_repo.get_by_id(user_id)
        if user and user.get("trial_count", 0) > 0:
            return True

        return False

    async def check_trial_count(self, user_id: int) -> bool:
        curr = CurrentUserService()
        if curr.get_user_id() == user_id and curr.is_logged_in():
            return True

        subscription_data = await self.sub_repo.get_active_subscription(user_id)
        if subscription_data:
            end_date_str = subscription_data.get("end_date")
            if end_date_str:
                if isinstance(end_date_str, str):
                    try:
                        end_date = datetime.fromisoformat(end_date_str.replace(" ", "T"))
                    except (ValueError, TypeError):
                        end_date = datetime.strptime(end_date_str, "%Y-%m-%d %H:%M:%S")
                else:
                    end_date = end_date_str
                if datetime.now() <= end_date:
                    return True

        user = await self.user_repo.get_by_id(user_id)
        if user:
            return user.get("trial_count", 0) > 0
        return False


class PermissionController:
    """同步包装器（兼容旧逻辑）

    修复：原实现在 qasync 事件循环线程中调用 future.result() 会死锁。
    改为：在事件循环线程内检测到 loop.is_running() 时，使用独立线程运行
    asyncio.run() 避免阻塞事件循环。
    """

    _TIMEOUT = 5

    def __init__(self, data_storage=None):
        self._async_controller = PermissionControllerAsync()
        self.logger = logging.getLogger(__name__)

    def _run_async_safe(self, coro):
        """安全地从同步上下文调用异步方法，避免事件循环死锁。"""
        import asyncio
        import threading
        import concurrent.futures

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            if threading.current_thread() is threading.main_thread():
                # 在主线程（即事件循环线程）中，不能阻塞等待——
                # 用独立线程中的 asyncio.run 执行协程
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, coro)
                    return future.result(timeout=self._TIMEOUT)
            else:
                # 在非主线程中，可安全地将协程提交到主事件循环
                future = asyncio.run_coroutine_threadsafe(coro, loop)
                return future.result(timeout=self._TIMEOUT)
        else:
            if loop is None:
                return asyncio.run(coro)
            return loop.run_until_complete(coro)

    def check_publish_permission(self, user_id: int) -> bool:
        try:
            return self._run_async_safe(
                self._async_controller.check_publish_permission(user_id)
            )
        except Exception as e:
            self.logger.warning("check_publish_permission 同步调用失败: %s", e)
            return False

    def check_trial_count(self, user_id: int) -> bool:
        try:
            return self._run_async_safe(
                self._async_controller.check_trial_count(user_id)
            )
        except Exception as e:
            self.logger.warning("check_trial_count 同步调用失败: %s", e)
            return False

