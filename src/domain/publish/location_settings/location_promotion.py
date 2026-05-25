# -*- coding: utf-8 -*-
"""
位置推广领域模型
按位置简称 + 平台查询位置库，返回该平台搜索词并注入 metadata。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict

from .poi_codec import format_poi_info_storage, parse_location_short_name_from_storage

logger = logging.getLogger(__name__)

LOCATION_PLATFORM_FIELD_MAP: Dict[str, str] = {
    "douyin": "douyin_location",
    "kuaishou": "kuaishou_location",
    "wechat_video": "channels_location",
    "xiaohongshu": "xiaohongshu_location",
}


@dataclass
class LocationPromotionPublishFields:
    """位置推广发布字段。"""

    short_name: str = ""
    platform_search_text: str = ""
    location_mode: str = ""

    @staticmethod
    async def from_short_name_and_platform(
        short_name: str, platform: str, *, location_mode: str = ""
    ) -> "LocationPromotionPublishFields":
        """从位置库按简称查询，按平台取对应搜索词。"""
        short_name = (short_name or "").strip()
        platform = (platform or "").strip()
        mode = (location_mode or "").strip()
        if not short_name:
            return LocationPromotionPublishFields(location_mode=mode)

        try:
            from src.infrastructure.storage.repositories.location_promotion_repository import (
                LocationPromotionRepository,
            )

            rows = await LocationPromotionRepository.list_all()
            matched = next((r for r in rows if r.get("short_name") == short_name), None)
            if matched is None:
                logger.warning("位置推广库未找到简称：%s", short_name)
                return LocationPromotionPublishFields(
                    short_name=short_name, location_mode=mode
                )

            db_field = LOCATION_PLATFORM_FIELD_MAP.get(platform, "")
            search_text = (
                (matched.get(db_field) or "").strip() if db_field else ""
            )
            if not search_text:
                logger.info(
                    "位置「%s」在平台「%s」无对应搜索词（字段=%s）",
                    short_name,
                    platform,
                    db_field,
                )

            return LocationPromotionPublishFields(
                short_name=short_name,
                platform_search_text=search_text,
                location_mode=mode,
            )
        except Exception as e:
            logger.error(
                "查询位置推广配置失败（short_name=%s）: %s",
                short_name,
                e,
                exc_info=True,
            )
            return LocationPromotionPublishFields(
                short_name=short_name, location_mode=mode
            )

    @classmethod
    async def resolve_poi_info_for_platform(
        cls, poi_info_storage: str, platform: str
    ) -> str:
        """将含 location_short_name 的 poi_info 解析为平台可搜索文案。"""
        short_name = parse_location_short_name_from_storage(poi_info_storage or "")
        if not short_name:
            return (poi_info_storage or "").strip()

        from .poi_codec import parse_poi_info_storage

        _, mode = parse_poi_info_storage(poi_info_storage or "")
        fields = await cls.from_short_name_and_platform(
            short_name, platform, location_mode=mode
        )
        return fields.to_poi_info_storage()

    def to_poi_info_storage(self) -> str:
        """转为插件可消费的 poi_info 存储串（平台搜索词 + 可选模式）。"""
        return format_poi_info_storage(
            self.platform_search_text,
            self.location_mode,
        )

    def apply_to_plugin_metadata(self, metadata: Dict[str, Any]) -> None:
        """将解析后的位置搜索词写入 metadata.poi_info。"""
        pi = self.to_poi_info_storage()
        if pi:
            metadata["poi_info"] = pi

    def is_empty(self) -> bool:
        return not (self.platform_search_text or "").strip()
