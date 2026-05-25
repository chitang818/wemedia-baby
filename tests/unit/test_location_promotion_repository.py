# -*- coding: utf-8 -*-
"""位置推广仓储单元测试。"""
from __future__ import annotations

import pytest

from src.infrastructure.storage.repositories.location_promotion_repository import (
    LocationPromotionRepository,
)
from tests.helpers.db_helpers import init_test_db, close_test_db


@pytest.fixture
async def tortoise_db():
    await init_test_db()
    yield
    await close_test_db()


@pytest.mark.asyncio
async def test_create_update_list_delete(tortoise_db):
    created = await LocationPromotionRepository.create_or_update_by_short_name(
        {
            "short_name": "遥马",
            "douyin_location": "遥马产业园",
            "kuaishou_location": "潍城区遥马产业园",
            "channels_location": "遥马产业园",
            "xiaohongshu_location": "遥马",
        }
    )
    assert created["short_name"] == "遥马"
    assert created["douyin_location"] == "遥马产业园"

    updated = await LocationPromotionRepository.create_or_update_by_short_name(
        {
            "short_name": "遥马",
            "douyin_location": "遥马产业园更新",
            "kuaishou_location": "潍城区遥马产业园",
            "channels_location": "",
            "xiaohongshu_location": "",
        }
    )
    assert updated["douyin_location"] == "遥马产业园更新"

    rows = await LocationPromotionRepository.list_all()
    assert len(rows) == 1
    assert rows[0]["short_name"] == "遥马"

    deleted = await LocationPromotionRepository.delete_by_ids([created["id"]])
    assert deleted == 1
    assert await LocationPromotionRepository.list_all() == []


@pytest.mark.asyncio
async def test_bulk_import_overwrite(tortoise_db):
    await LocationPromotionRepository.bulk_import(
        [
            {
                "short_name": "A",
                "douyin_location": "抖音A",
                "kuaishou_location": "",
                "channels_location": "",
                "xiaohongshu_location": "",
            },
            {
                "short_name": "B",
                "douyin_location": "抖音B",
                "kuaishou_location": "快手B",
                "channels_location": "",
                "xiaohongshu_location": "",
            },
        ],
        overwrite=True,
    )
    assert len(await LocationPromotionRepository.list_all()) == 2

    result = await LocationPromotionRepository.bulk_import(
        [
            {
                "short_name": "A",
                "douyin_location": "抖音A新",
                "kuaishou_location": "",
                "channels_location": "",
                "xiaohongshu_location": "",
            },
        ],
        overwrite=True,
    )
    assert result["success"] == 1
    rows = await LocationPromotionRepository.list_all()
    a = next(r for r in rows if r["short_name"] == "A")
    assert a["douyin_location"] == "抖音A新"


@pytest.mark.asyncio
async def test_create_requires_short_name(tortoise_db):
    with pytest.raises(ValueError, match="位置简称"):
        await LocationPromotionRepository.create_or_update_by_short_name({})
