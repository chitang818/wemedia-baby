"""
批量发布目标展开逻辑单元测试
模块：src/ui/pages/publish/batch_publish_targets.py
"""
import pytest
from unittest.mock import AsyncMock
from src.ui.pages.publish.batch_publish_targets import (
    expand_batch_selected_accounts_for_publish,
    resolve_batch_publish_targets_to_accounts,
)


ACCOUNT_A = {"id": 1, "account_name": "抖音账号1", "platform": "douyin"}
ACCOUNT_B = {"id": 2, "account_name": "快手账号1", "platform": "kuaishou"}
ACCOUNT_C = {"id": 3, "account_name": "视频号账号1", "platform": "wechat_video"}


class TestResolveAccountType:
    @pytest.mark.asyncio
    async def test_single_account(self):
        result = {"type": "account", "data": ACCOUNT_A}
        accounts = await resolve_batch_publish_targets_to_accounts(result)
        assert len(accounts) == 1
        assert accounts[0]["id"] == 1

    @pytest.mark.asyncio
    async def test_account_list(self):
        result = {"type": "account", "data": [ACCOUNT_A, ACCOUNT_B]}
        accounts = await resolve_batch_publish_targets_to_accounts(result)
        assert len(accounts) == 2

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty(self):
        accounts = await resolve_batch_publish_targets_to_accounts({})
        assert accounts == []

    @pytest.mark.asyncio
    async def test_none_result_returns_empty(self):
        accounts = await resolve_batch_publish_targets_to_accounts(None)
        assert accounts == []

    @pytest.mark.asyncio
    async def test_account_data_none_returns_empty(self):
        result = {"type": "account", "data": None}
        accounts = await resolve_batch_publish_targets_to_accounts(result)
        assert accounts == []

    @pytest.mark.asyncio
    async def test_returns_copy_not_original(self):
        """修改返回的账号不影响原始数据"""
        data = {"id": 1, "account_name": "test"}
        result = {"type": "account", "data": data}
        accounts = await resolve_batch_publish_targets_to_accounts(result)
        accounts[0]["account_name"] = "modified"
        assert data["account_name"] == "test"


class TestResolveGroupType:
    @pytest.mark.asyncio
    async def test_single_group_with_accounts(self):
        group = {"id": 10, "accounts": [ACCOUNT_A, ACCOUNT_B]}
        result = {"type": "group", "data": group}
        accounts = await resolve_batch_publish_targets_to_accounts(result)
        assert len(accounts) == 2

    @pytest.mark.asyncio
    async def test_multiple_groups_deduplication(self):
        """同一账号出现在两个组中，应去重"""
        group1 = {"id": 10, "accounts": [ACCOUNT_A, ACCOUNT_B]}
        group2 = {"id": 11, "accounts": [ACCOUNT_B, ACCOUNT_C]}
        result = {"type": "group", "data": [group1, group2]}
        accounts = await resolve_batch_publish_targets_to_accounts(result)
        ids = [a["id"] for a in accounts]
        assert len(ids) == len(set(ids)), "应去重"
        assert len(accounts) == 3

    @pytest.mark.asyncio
    async def test_group_with_empty_accounts_falls_back_to_service(self):
        """账号组 accounts 为空时，通过 group_service 回填"""
        mock_service = AsyncMock()
        mock_service.get_group_by_id.return_value = {
            "id": 10,
            "accounts": [ACCOUNT_A],
        }
        group = {"id": 10, "accounts": []}
        result = {"type": "group", "data": group}
        accounts = await resolve_batch_publish_targets_to_accounts(
            result, group_service=mock_service
        )
        mock_service.get_group_by_id.assert_called_once_with(10)
        assert len(accounts) == 1

    @pytest.mark.asyncio
    async def test_group_service_exception_returns_empty(self):
        """group_service 抛异常时，该组返回空，不影响其他组"""
        mock_service = AsyncMock()
        mock_service.get_group_by_id.side_effect = RuntimeError("DB error")
        group = {"id": 10, "accounts": []}
        result = {"type": "group", "data": group}
        accounts = await resolve_batch_publish_targets_to_accounts(
            result, group_service=mock_service
        )
        assert accounts == []

    @pytest.mark.asyncio
    async def test_unknown_type_returns_empty(self):
        result = {"type": "unknown", "data": [ACCOUNT_A]}
        accounts = await resolve_batch_publish_targets_to_accounts(result)
        assert accounts == []


class TestExpandBatchSelectedAccountsForPublish:
    @pytest.mark.asyncio
    async def test_plain_account_keeps_reference(self):
        sel = [ACCOUNT_A]
        res = await expand_batch_selected_accounts_for_publish(sel)
        assert len(res.expanded_accounts) == 1
        assert res.expanded_accounts[0] is ACCOUNT_A
        assert res.empty_group_names == []

    @pytest.mark.asyncio
    async def test_group_expands_with_source_group_id(self):
        group_placeholder = {
            "_type": "group",
            "group_id": 99,
            "group_name": "测试组",
            "_group_data": {"id": 99, "accounts": [ACCOUNT_A, ACCOUNT_B]},
        }
        res = await expand_batch_selected_accounts_for_publish([group_placeholder])
        assert res.empty_group_names == []
        assert len(res.expanded_accounts) == 2
        assert all(a.get("_source_group_id") == 99 for a in res.expanded_accounts)
        assert {a["id"] for a in res.expanded_accounts} == {1, 2}

    @pytest.mark.asyncio
    async def test_empty_group_records_name(self):
        group_placeholder = {
            "_type": "group",
            "group_id": 42,
            "group_name": "空组",
            "_group_data": {"id": 42, "accounts": []},
        }
        res = await expand_batch_selected_accounts_for_publish([group_placeholder])
        assert res.expanded_accounts == []
        assert res.empty_group_names == ["空组"]

    @pytest.mark.asyncio
    async def test_mixed_plain_and_group(self):
        group_placeholder = {
            "_type": "group",
            "group_id": 1,
            "group_name": "G",
            "_group_data": {"id": 1, "accounts": [ACCOUNT_B]},
        }
        res = await expand_batch_selected_accounts_for_publish([ACCOUNT_A, group_placeholder])
        assert res.empty_group_names == []
        assert res.expanded_accounts[0] is ACCOUNT_A
        assert res.expanded_accounts[1]["id"] == 2
        assert res.expanded_accounts[1].get("_source_group_id") == 1
