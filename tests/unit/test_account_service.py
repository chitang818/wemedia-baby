"""
账号服务单元测试
测试范围：账号添加、删除、查询
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.account.account_service import AccountService


class TestAccountService:
    """账号服务测试类"""

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.create = AsyncMock(return_value=1)
        repo.delete = AsyncMock(return_value=True)
        repo.find_all = AsyncMock(return_value=[])
        repo.find_by_id = AsyncMock(return_value=None)
        return repo

    @pytest.fixture
    def mock_event_bus(self):
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def mock_file_storage(self):
        # AccountService 构造会从 ServiceLocator 取 AsyncFileStorage；单测未跑 main 注册，必须显式注入
        return MagicMock()

    @pytest.fixture
    def service(self, mock_repo, mock_event_bus, mock_file_storage):
        return AccountService(
            account_repo=mock_repo,
            file_storage=mock_file_storage,
            event_bus=mock_event_bus,
        )

    @pytest.mark.asyncio
    async def test_add_account(self, service, mock_repo):
        account = await service.add_account(
            user_id=1,
            account_name="测试账号",
            platform="douyin",
        )
        assert account.account_id == 1
        assert account.platform == "douyin"
        mock_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_accounts(self, service, mock_repo, sample_account):
        mock_repo.find_all.return_value = [sample_account]
        accounts = await service.get_accounts(user_id=1)
        assert len(accounts) == 1
        assert accounts[0].platform == "douyin"

    @pytest.mark.asyncio
    async def test_delete_account_not_found(self, service, mock_repo):
        mock_repo.find_by_id.return_value = None
        await service.delete_account(account_id=999)
        mock_repo.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_account_found(self, service, mock_repo, mock_event_bus, sample_account):
        mock_repo.find_by_id.return_value = sample_account
        await service.delete_account(account_id=1)
        mock_repo.delete.assert_called_once_with(1)
        mock_event_bus.publish.assert_called()
