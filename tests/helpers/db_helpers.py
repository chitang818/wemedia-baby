"""
集成测试数据库辅助工具
使用 Tortoise ORM 的内存 SQLite，为集成测试提供隔离环境。
"""

from __future__ import annotations

from typing import AsyncGenerator

import pytest
from tortoise import Tortoise


TORTOISE_TEST_CONFIG = {
    "connections": {
        "default": "sqlite://:memory:"
    },
    "apps": {
        "models": {
            "models": ["src.infrastructure.storage.orm_models"],
            "default_connection": "default",
        }
    },
}


async def init_test_db() -> None:
    """初始化内存测试数据库并生成表结构"""
    await Tortoise.init(config=TORTOISE_TEST_CONFIG)
    await Tortoise.generate_schemas(safe=True)


async def close_test_db() -> None:
    """关闭测试数据库连接"""
    await Tortoise.close_connections()


async def reset_test_db() -> None:
    """关闭旧连接并重新初始化（每个测试用例隔离）"""
    try:
        await Tortoise.close_connections()
    except Exception:
        pass
    await init_test_db()
