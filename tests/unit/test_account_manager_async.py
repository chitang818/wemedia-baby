"""AccountManagerAsync 关键路径单测（昵称变更触发的素材目录重命名等）。"""
from unittest.mock import AsyncMock, patch

import pytest

from src.services.account.account_manager_async import AccountManagerAsync


@pytest.mark.asyncio
async def test_update_platform_username_calls_material_library_rename():
    """昵称变更时应调用 MaterialLibraryManager.rename（模块已导入，不再 NameError）。"""
    mock_bus = AsyncMock()
    mgr = AccountManagerAsync(user_id=1, event_bus=mock_bus)
    mgr.account_repository = AsyncMock()
    mgr.account_repository.find_by_id = AsyncMock(
        return_value={
            "id": 1,
            "platform": "douyin",
            "platform_username": "旧昵称",
        }
    )
    mgr.account_repository.update_platform_username = AsyncMock(return_value=True)

    with patch(
        "src.services.account.account_manager_async.MaterialLibraryManager.rename_platform_account_folder",
        return_value=True,
    ) as rename_mock:
        with patch.object(mgr, "_try_sync_material_library", new_callable=AsyncMock):
            ok = await mgr.update_platform_username(1, "新昵称")

    assert ok is True
    rename_mock.assert_called_once_with("douyin", "旧昵称", "新昵称")
