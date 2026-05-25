# -*- coding: utf-8 -*-
import pytest

from src.domain.publish.location_settings import (
    LocationPromotionPublishFields,
    format_poi_info_from_short_name,
)
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
async def test_resolve_poi_info_for_platform(tortoise_db):
    await LocationPromotionRepository.create_or_update_by_short_name(
        {
            "short_name": "遥马",
            "douyin_location": "遥马产业园",
            "kuaishou_location": "潍城区遥马产业园",
            "channels_location": "",
            "xiaohongshu_location": "遥马",
        }
    )
    stored = format_poi_info_from_short_name("遥马", "打卡模式")
    resolved = await LocationPromotionPublishFields.resolve_poi_info_for_platform(
        stored, "douyin"
    )
    assert "遥马产业园" in resolved
    assert "打卡模式" in resolved or "location_mode" in resolved

    ks = await LocationPromotionPublishFields.resolve_poi_info_for_platform(
        stored, "kuaishou"
    )
    assert "潍城区遥马产业园" in ks
