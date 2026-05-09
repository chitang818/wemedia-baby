"""领域模型单元测试"""

import pytest
from datetime import datetime, timedelta

from src.domain.models.account import Account
from src.domain.models.account_group import AccountGroup
from src.domain.models.publish_task import PublishTask
from src.domain.models.subscription import Subscription


class TestAccount:
    def test_create_with_defaults(self):
        acc = Account(user_id=1, platform="douyin", account_name="test")
        assert acc.user_id == 1
        assert acc.platform == "douyin"
        assert acc.status == "active"
        assert acc.login_status == "offline"
        assert acc.is_active is True

    def test_to_dict_roundtrip(self):
        acc = Account(user_id=1, platform="douyin", account_name="test", account_id=42)
        d = acc.to_dict()
        restored = Account.from_dict(d)
        assert restored.user_id == acc.user_id
        assert restored.platform == acc.platform
        assert restored.account_name == acc.account_name
        assert restored.account_id == acc.account_id

    def test_from_dict_missing_required_raises(self):
        with pytest.raises(KeyError):
            Account.from_dict({"user_id": 1, "platform": "douyin"})

    def test_with_updates_returns_new_instance(self):
        acc = Account(user_id=1, platform="douyin", account_name="test")
        updated = acc.with_updates(login_status="online")
        assert updated.login_status == "online"
        assert acc.login_status == "offline"

    def test_frozen_raises_on_assignment(self):
        acc = Account(user_id=1, platform="douyin", account_name="test")
        with pytest.raises(AttributeError):
            acc.status = "inactive"

    def test_encrypted_cookies_hex_roundtrip(self):
        raw = b"\x01\x02\x03\xff"
        acc = Account(user_id=1, platform="douyin", account_name="t", encrypted_cookies=raw)
        d = acc.to_dict()
        assert d["encrypted_cookies"] == raw.hex()
        restored = Account.from_dict(d)
        assert restored.encrypted_cookies == raw


class TestPublishTask:
    def test_status_helpers(self):
        task = PublishTask(user_id=1, account_name="a", platform="douyin",
                          content={"file_path": "/tmp/v.mp4"})
        assert task.is_pending() is True
        assert task.is_running() is False
        assert task.is_completed() is False

    def test_can_retry(self):
        task = PublishTask(user_id=1, account_name="a", platform="douyin",
                          content={}, status="failed", retry_count=2)
        assert task.can_retry(max_retries=3) is True
        assert task.can_retry(max_retries=2) is False

    def test_to_dict_roundtrip(self):
        task = PublishTask(user_id=1, account_name="a", platform="douyin",
                          content={"title": "hello"}, task_id=10)
        d = task.to_dict()
        restored = PublishTask.from_dict(d)
        assert restored.task_id == 10
        assert restored.content == {"title": "hello"}

    def test_with_updates(self):
        task = PublishTask(user_id=1, account_name="a", platform="douyin", content={})
        updated = task.with_updates(status="running")
        assert updated.is_running() is True
        assert task.is_pending() is True


class TestSubscription:
    def _make_sub(self, days_ahead=30, **kwargs):
        now = datetime.now()
        return Subscription(
            user_id=1,
            plan_type="basic",
            price=29.9,
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=days_ahead),
            **kwargs,
        )

    def test_is_active(self):
        sub = self._make_sub()
        assert sub.is_active() is True

    def test_is_expired(self):
        sub = self._make_sub(days_ahead=-1)
        assert sub.is_expired() is True

    def test_days_remaining(self):
        sub = self._make_sub(days_ahead=10)
        remaining = sub.days_remaining()
        assert 9 <= remaining <= 11

    def test_to_dict_roundtrip(self):
        sub = self._make_sub(subscription_id=5)
        d = sub.to_dict()
        restored = Subscription.from_dict(d)
        assert restored.subscription_id == 5
        assert restored.plan_type == "basic"
        assert restored.price == 29.9

    def test_from_dict_missing_dates_raises(self):
        with pytest.raises(ValueError):
            Subscription.from_dict({
                "user_id": 1, "plan_type": "basic", "price": 10,
            })

    def test_with_updates(self):
        sub = self._make_sub()
        updated = sub.with_updates(status="cancelled")
        assert updated.status == "cancelled"
        assert sub.status == "active"


class TestAccountGroup:
    def test_create_defaults(self):
        group = AccountGroup(user_id=1, group_name="我的账号组")
        assert group.user_id == 1
        assert group.group_name == "我的账号组"
        assert group.group_id is None
        assert group.description is None

    def test_to_dict_contains_both_id_keys(self):
        group = AccountGroup(user_id=1, group_name="组A", group_id=10)
        d = group.to_dict()
        assert d["group_id"] == 10
        assert d["id"] == 10

    def test_from_dict_roundtrip(self):
        group = AccountGroup(user_id=2, group_name="组B", group_id=5, description="desc")
        d = group.to_dict()
        restored = AccountGroup.from_dict(d)
        assert restored.user_id == 2
        assert restored.group_name == "组B"
        assert restored.group_id == 5
        assert restored.description == "desc"

    def test_with_updates_returns_new(self):
        group = AccountGroup(user_id=1, group_name="旧名")
        updated = group.with_updates(group_name="新名")
        assert updated.group_name == "新名"
        assert group.group_name == "旧名"

    def test_frozen_raises_on_assignment(self):
        group = AccountGroup(user_id=1, group_name="测试组")
        with pytest.raises(AttributeError):
            group.group_name = "修改"
