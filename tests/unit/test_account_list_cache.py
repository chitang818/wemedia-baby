import pytest

from src.services.account import account_list_cache


def test_account_list_cache_roundtrip_and_invalidate():
    account_list_cache.invalidate_account_list_cache()
    assert account_list_cache.get_cached_accounts() is None

    account_list_cache.set_cached_accounts([{"id": 1, "platform": "douyin"}])
    cached = account_list_cache.get_cached_accounts()

    assert cached == [{"id": 1, "platform": "douyin"}]
    cached[0]["id"] = 2
    assert account_list_cache.get_cached_accounts() == [{"id": 1, "platform": "douyin"}]

    account_list_cache.invalidate_account_list_cache()
    assert account_list_cache.get_cached_accounts() is None


@pytest.mark.asyncio
async def test_account_list_cache_loader_uses_cached_value_without_refresh(monkeypatch):
    account_list_cache.invalidate_account_list_cache()
    account_list_cache.set_cached_accounts([{"id": 1}])

    async def fail_find_all(*_args, **_kwargs):
        raise AssertionError("repository should not be queried on cache hit")

    monkeypatch.setattr(
        "src.domain.repositories.account_repository_async.AccountRepositoryAsync.find_all",
        fail_find_all,
    )

    assert await account_list_cache.load_accounts_for_publish_cache() == [{"id": 1}]
    account_list_cache.invalidate_account_list_cache()
