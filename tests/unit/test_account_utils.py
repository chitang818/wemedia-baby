"""
账号查找工具单元测试
模块：src/services/publish/pipeline/filters/account_utils.py
"""
import pytest
from src.services.publish.pipeline.filters.account_utils import find_account_by_name


ACCOUNTS = [
    {"id": 1, "account_name": "alice", "platform": "douyin"},
    {"id": 2, "account_name": "bob",   "platform": "kuaishou"},
    {"id": 3, "account_name": "carol", "platform": "douyin"},
]


class TestFindAccountByName:
    def test_found(self):
        result = find_account_by_name(ACCOUNTS, "bob")
        assert result is not None
        assert result["id"] == 2

    def test_not_found_returns_none(self):
        result = find_account_by_name(ACCOUNTS, "dave")
        assert result is None

    def test_empty_list(self):
        assert find_account_by_name([], "alice") is None

    def test_returns_first_match(self):
        """同名账号时返回第一个匹配"""
        accounts = [
            {"id": 1, "account_name": "alice"},
            {"id": 2, "account_name": "alice"},
        ]
        result = find_account_by_name(accounts, "alice")
        assert result["id"] == 1

    def test_case_sensitive(self):
        """账号名大小写敏感"""
        result = find_account_by_name(ACCOUNTS, "Alice")
        assert result is None
