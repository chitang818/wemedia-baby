"""
集成测试专用 Fixture
提供 Tortoise ORM 内存数据库的初始化/销毁。
"""

import pytest
from tests.helpers.db_helpers import init_test_db, close_test_db


@pytest.fixture
async def test_db():
    """每个集成测试函数独享一个初始化后的内存数据库"""
    await init_test_db()
    yield
    await close_test_db()
