"""
Repository CRUD 集成测试
基于内存 SQLite 验证 CopywritingRepository 的增删改查操作。
"""

from __future__ import annotations

import pytest
from tortoise import Tortoise

from src.infrastructure.storage.repositories.copywriting_repository import CopywritingRepository
from src.infrastructure.storage.orm_models.copywriting_item import CopywritingItem

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def db():
    """每个测试函数独享一个干净的内存数据库"""
    await Tortoise.init(
        db_url="sqlite://:memory:",
        modules={"models": ["src.infrastructure.storage.orm_models"]},
    )
    await Tortoise.generate_schemas(safe=True)
    yield
    await Tortoise.close_connections()


class TestCopywritingRepositoryCRUD:

    async def test_list_items_empty(self):
        items = await CopywritingRepository.list_items()
        assert items == []

    async def _create(self, work_id, short_title="T", description="D", topics="", content="C"):
        """辅助方法：创建一条文案记录"""
        return await CopywritingRepository.create_or_update_by_work_id({
            "work_id": work_id,
            "short_title": short_title,
            "description": description,
            "topics": topics,
            "content": content,
        })

    async def test_create_or_update_creates_new(self):
        result = await self._create("A0001", short_title="标题", content="内容")
        assert result is not None
        assert result["work_id"] == "A0001"

    async def test_create_or_update_rejects_invalid_work_id(self):
        with pytest.raises(ValueError, match="作品编号"):
            await CopywritingRepository.create_or_update_by_work_id({
                "work_id": "invalid",
                "short_title": "t",
                "content": "c",
            })

    async def test_list_items_after_create(self):
        await self._create("B0001")
        items = await CopywritingRepository.list_items()
        assert len(items) == 1
        assert items[0]["work_id"] == "B0001"

    async def test_get_by_work_id_found(self):
        await self._create("C0001")
        item = await CopywritingRepository.get_by_work_id("C0001")
        assert item is not None
        assert item["work_id"] == "C0001"

    async def test_get_by_work_id_not_found(self):
        result = await CopywritingRepository.get_by_work_id("nonexistent")
        assert result is None

    async def test_get_by_work_id_invalid_format_returns_none_without_legacy_match(self):
        """非新格式查询参数一律视为不存在，不与库内旧数据兼容。"""
        legacy = await CopywritingItem.create(work_id="legacy-old", content="x")
        assert await CopywritingRepository.get_by_work_id("legacy-old") is None
        assert await CopywritingRepository.get_by_id(legacy.id) is None
        listed = await CopywritingRepository.list_items(page=1, page_size=50)
        assert not any(r["work_id"] == "legacy-old" for r in listed)

    async def test_get_by_work_id_empty_returns_none(self):
        result = await CopywritingRepository.get_by_work_id("")
        assert result is None

    async def test_create_or_update_updates_existing(self):
        await self._create("D0001", short_title="原标题")
        await self._create("D0001", short_title="新标题")
        item = await CopywritingRepository.get_by_work_id("D0001")
        assert item["short_title"] == "新标题"

    async def test_count_total(self):
        for i in range(3):
            await self._create(f"E{i:04d}", content=f"内容{i}")
        total = await CopywritingItem.all().count()
        assert total == 3

    async def test_pagination(self):
        for i in range(5):
            await self._create(f"F{i:04d}", content=f"c{i}")
        page1 = await CopywritingRepository.list_items(page=1, page_size=2)
        page2 = await CopywritingRepository.list_items(page=2, page_size=2)
        assert len(page1) == 2
        assert len(page2) == 2
        assert {i["work_id"] for i in page1}.isdisjoint({i["work_id"] for i in page2})

    async def test_delete_by_id(self):
        item = await self._create("G0001")
        item_id = item["id"]
        await CopywritingRepository.delete_items([item_id])
        result = await CopywritingRepository.get_by_id(item_id)
        assert result is None
