"""
账号仓储集成测试
模块：src/domain/repositories/account_repository_async.py
"""
import pytest
from src.domain.repositories.account_repository_async import AccountRepositoryAsync
from src.infrastructure.storage.orm_models.user import User


@pytest.fixture
async def repo(test_db):
    # 先创建一个用户，满足外键约束
    user = await User.create(username="test_user", password_hash="hash", email="t@t.com")
    return AccountRepositoryAsync(), user.id


async def _create(repo_user, platform, username="u1"):
    repo, uid = repo_user
    return await repo.create(user_id=uid, platform=platform, platform_username=username)


class TestAccountRepositoryCRUD:
    @pytest.mark.asyncio
    async def test_create_and_find_all(self, repo):
        repo_obj, uid = repo
        acc_id = await repo_obj.create(user_id=uid, platform="douyin", platform_username="user1")
        assert isinstance(acc_id, int) and acc_id > 0
        accounts = await repo_obj.find_all(user_id=uid)
        assert any(a["id"] == acc_id for a in accounts)

    @pytest.mark.asyncio
    async def test_find_by_id(self, repo):
        repo_obj, uid = repo
        acc_id = await repo_obj.create(user_id=uid, platform="kuaishou", platform_username="ks_user")
        found = await repo_obj.find_by_id(acc_id)
        assert found is not None
        assert found["platform"] == "kuaishou"

    @pytest.mark.asyncio
    async def test_find_by_id_not_found_returns_none(self, repo):
        repo_obj, uid = repo
        result = await repo_obj.find_by_id(99999)
        assert result is None

    @pytest.mark.asyncio
    async def test_username_at_prefix_stripped(self, repo):
        """平台昵称前置 @ 应被去掉"""
        repo_obj, uid = repo
        acc_id = await repo_obj.create(user_id=uid, platform="douyin", platform_username="@my_user")
        found = await repo_obj.find_by_id(acc_id)
        assert found["platform_username"] == "my_user"

    @pytest.mark.asyncio
    async def test_update_login_status(self, repo):
        repo_obj, uid = repo
        acc_id = await repo_obj.create(user_id=uid, platform="douyin", platform_username="u1")
        await repo_obj.update_status(acc_id, "online")
        found = await repo_obj.find_by_id(acc_id)
        assert found["login_status"] == "online"

    @pytest.mark.asyncio
    async def test_delete_account(self, repo):
        repo_obj, uid = repo
        acc_id = await repo_obj.create(user_id=uid, platform="douyin", platform_username="to_delete")
        deleted = await repo_obj.delete(acc_id)
        assert deleted is True
        assert await repo_obj.find_by_id(acc_id) is None

    @pytest.mark.asyncio
    async def test_find_all_filters_by_user(self, repo):
        repo_obj, uid = repo
        # 创建第二个用户验证过滤
        user2 = await User.create(username="user2", password_hash="h", email="u2@t.com")
        await repo_obj.create(user_id=uid, platform="douyin", platform_username="u1")
        await repo_obj.create(user_id=user2.id, platform="kuaishou", platform_username="u2")
        user1_accounts = await repo_obj.find_all(user_id=uid)
        ids = {a.get("user_id") for a in user1_accounts}
        assert uid in ids
        assert user2.id not in ids
