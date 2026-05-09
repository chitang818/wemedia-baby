"""
Tortoise ORM 管理器集成测试
使用内存 SQLite 验证配置生成、初始化和关闭流程。
"""

from __future__ import annotations

import pytest
from tortoise import Tortoise

from src.infrastructure.storage.tortoise_manager import get_tortoise_config

pytestmark = pytest.mark.integration


class TestGetTortoiseConfig:

    def test_returns_dict(self):
        config = get_tortoise_config(db_path=":memory:")
        assert isinstance(config, dict)

    def test_has_connections_key(self):
        config = get_tortoise_config(db_path="/tmp/test.db")
        assert "connections" in config

    def test_has_apps_key(self):
        config = get_tortoise_config(db_path="/tmp/test.db")
        assert "apps" in config

    def test_custom_db_path_used(self):
        config = get_tortoise_config(db_path="/custom/path/test.db")
        file_path = config["connections"]["default"]["credentials"]["file_path"]
        assert file_path == "/custom/path/test.db"

    def test_does_not_mutate_global_template(self):
        config1 = get_tortoise_config(db_path="/path1.db")
        config2 = get_tortoise_config(db_path="/path2.db")
        p1 = config1["connections"]["default"]["credentials"]["file_path"]
        p2 = config2["connections"]["default"]["credentials"]["file_path"]
        assert p1 == "/path1.db"
        assert p2 == "/path2.db"


@pytest.mark.slow
class TestTortoiseInitAndClose:

    async def test_init_with_memory_db(self):
        """使用内存 SQLite 验证 Tortoise 可以正常初始化"""
        try:
            await Tortoise.init(
                db_url="sqlite://:memory:",
                modules={"models": ["src.infrastructure.storage.orm_models"]},
            )
            await Tortoise.generate_schemas(safe=True)
        finally:
            await Tortoise.close_connections()

    async def test_generate_schemas_no_error(self):
        try:
            await Tortoise.init(
                db_url="sqlite://:memory:",
                modules={"models": ["src.infrastructure.storage.orm_models"]},
            )
            # 不应抛异常
            await Tortoise.generate_schemas(safe=True)
        finally:
            await Tortoise.close_connections()
