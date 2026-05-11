"""
权限控制器（开源包装层）
闭源版实现：`src/proprietary/subscription/permission_controller_async.py`
"""

from __future__ import annotations

from typing import Any


try:
    from src.proprietary.subscription.permission_controller_async import PermissionControllerAsync, PermissionController
except Exception:
    class PermissionControllerAsync:  # type: ignore[no-redef]
        """权限控制器开源占位 —— 默认放行所有权限检查。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def check_pro_permission(self, user_id: int) -> bool:
            return False

        async def check_publish_permission(self, user_id: int) -> bool:
            return True

        async def check_trial_count(self, user_id: int) -> bool:
            return True

    class PermissionController:  # type: ignore[no-redef]
        """同步版权限控制器开源占位。"""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def check_publish_permission(self, user_id: int) -> bool:
            return True

        def check_trial_count(self, user_id: int) -> bool:
            return True
