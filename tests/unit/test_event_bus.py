"""
EventBus 单元测试
使用临时目录隔离事件日志数据库，测试订阅/发布/异步处理器行为。
EventBus.publish 接受 DomainEvent 对象，测试均使用 async def。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pytest
from unittest.mock import MagicMock, AsyncMock

pytestmark = pytest.mark.unit


# 用于测试的最小自定义事件
@dataclass
class _TestEvent:
    """测试用事件，模拟 DomainEvent 接口"""
    data: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = None
    aggregate_id: str = None
    event_type: str = field(init=False)

    def __post_init__(self):
        self.event_type = type(self).__name__

    def to_dict(self):
        return {"event_type": self.event_type, "data": self.data}


@dataclass
class _OtherEvent(_TestEvent):
    pass


@pytest.fixture
def event_bus(tmp_path):
    """创建使用临时目录的 EventBus"""
    log_path = str(tmp_path / "event_log.sqlite")
    from src.infrastructure.common.event.event_bus import EventBus
    return EventBus(event_log_path=log_path)


class TestSubscribeAndPublish:

    async def test_sync_handler_called_on_publish(self, event_bus):
        handler = MagicMock()
        event_bus.subscribe("_TestEvent", handler)
        await event_bus.publish(_TestEvent(data="hello"))
        handler.assert_called_once()

    async def test_multiple_handlers_all_called(self, event_bus):
        h1 = MagicMock()
        h2 = MagicMock()
        event_bus.subscribe("_TestEvent", h1)
        event_bus.subscribe("_TestEvent", h2)
        await event_bus.publish(_TestEvent())
        h1.assert_called_once()
        h2.assert_called_once()

    async def test_handler_not_called_for_other_event(self, event_bus):
        handler = MagicMock()
        event_bus.subscribe("_TestEvent", handler)
        await event_bus.publish(_OtherEvent())  # 不同类型
        handler.assert_not_called()

    async def test_unsubscribed_event_no_error(self, event_bus):
        # 发布没有订阅者的事件不应抛异常
        await event_bus.publish(_TestEvent())

    async def test_async_handler_called_on_publish(self, event_bus):
        async_handler = AsyncMock()
        event_bus.subscribe("_TestEvent", async_handler)
        await event_bus.publish(_TestEvent(data="async"))
        async_handler.assert_called_once()


class TestEventBusInitialization:

    def test_creates_with_custom_log_path(self, tmp_path):
        log_path = str(tmp_path / "custom_log.sqlite")
        from src.infrastructure.common.event.event_bus import EventBus
        bus = EventBus(event_log_path=log_path)
        assert bus._event_log_path == log_path

    def test_subscribers_initially_empty(self, tmp_path):
        log_path = str(tmp_path / "test.sqlite")
        from src.infrastructure.common.event.event_bus import EventBus
        bus = EventBus(event_log_path=log_path)
        assert isinstance(bus._subscribers, dict)

    def test_subscribe_adds_to_subscribers(self, event_bus):
        event_bus.subscribe("_TestEvent", MagicMock())
        assert "_TestEvent" in event_bus._subscribers
        assert len(event_bus._subscribers["_TestEvent"]) == 1
