"""
ServiceLocator 单元测试
测试服务注册、获取、工厂模式及作用域行为。
注意：ServiceLocator 是单例，每个测试后需清理。
"""

from __future__ import annotations

import pytest

from src.infrastructure.common.di.service_locator import (
    ServiceLocator,
    ServiceFactory,
    ServiceNotFoundError,
    get_service_locator,
)
from src.infrastructure.common.di.scopes import Scope

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clean_service_locator():
    """每个测试前后清理 ServiceLocator 单例状态"""
    locator = ServiceLocator()
    locator.clear()
    yield locator
    locator.clear()


class MyService:
    """测试用服务类"""
    def hello(self):
        return "hello"


class AnotherService(MyService):
    """MyService 的子类，用于类型兼容测试"""
    pass


class TestServiceRegistration:

    def test_register_and_get_service(self, clean_service_locator):
        locator = clean_service_locator
        instance = MyService()
        locator.register(MyService, instance)
        retrieved = locator.get(MyService)
        assert retrieved is instance

    def test_register_factory_and_get(self, clean_service_locator):
        locator = clean_service_locator
        locator.register_factory(MyService, lambda: MyService(), Scope.SINGLETON)
        retrieved = locator.get(MyService)
        assert isinstance(retrieved, MyService)

    def test_singleton_factory_returns_same_instance(self, clean_service_locator):
        locator = clean_service_locator
        locator.register_factory(MyService, lambda: MyService(), Scope.SINGLETON)
        r1 = locator.get(MyService)
        r2 = locator.get(MyService)
        assert r1 is r2

    def test_prototype_factory_returns_new_instance(self, clean_service_locator):
        locator = clean_service_locator
        locator.register_factory(MyService, lambda: MyService(), Scope.PROTOTYPE)
        r1 = locator.get(MyService)
        r2 = locator.get(MyService)
        assert r1 is not r2

    def test_type_mismatch_raises_value_error(self, clean_service_locator):
        locator = clean_service_locator
        with pytest.raises((ValueError, TypeError)):
            locator.register(MyService, "not_a_service")  # type: ignore


class TestServiceLookup:

    def test_get_unregistered_raises_not_found(self, clean_service_locator):
        locator = clean_service_locator
        with pytest.raises((ServiceNotFoundError, KeyError, Exception)):
            locator.get(MyService)

    def test_get_service_locator_singleton(self):
        loc1 = get_service_locator()
        loc2 = get_service_locator()
        assert loc1 is loc2


class TestServiceFactory:

    def test_singleton_scope(self):
        factory = ServiceFactory(lambda: MyService(), Scope.SINGLETON)
        r1 = factory.create()
        r2 = factory.create()
        assert r1 is r2

    def test_prototype_scope(self):
        factory = ServiceFactory(lambda: MyService(), Scope.PROTOTYPE)
        r1 = factory.create()
        r2 = factory.create()
        assert r1 is not r2
