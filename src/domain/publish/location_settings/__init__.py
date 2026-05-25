# -*- coding: utf-8 -*-
"""
位置扩展 — 领域层统一入口

- ``poi_info`` 编解码、有效文案解析
- ``LocationPublishFields``：落库与 metadata 的标准字段集（含视频号空位置是否打开下拉的策略位）
- 各平台发布步骤请使用 ``effective_location_string_from_metadata`` 与 metadata 中的标准键，
  勿各自解析 JSON。
"""
from .constants import (
    LOCATION_MODE_CHECKIN,
    LOCATION_MODE_SELLING,
    LOCATION_MODE_CHOICES,
    LOCATION_MODE_CHOICES_SET,
)
from .poi_codec import (
    format_poi_info_from_short_name,
    format_poi_info_storage,
    location_preview_display,
    parse_location_short_name_from_storage,
    parse_poi_info_storage,
)
from .location_promotion import (
    LOCATION_PLATFORM_FIELD_MAP,
    LocationPromotionPublishFields,
)
from .effective_text import effective_location_string_from_metadata
from .publish_fields import LocationPublishFields
from .location_intent import (
    LocationPoiInputChoice,
    WechatNoPoiSubchoice,
    batch_location_summary_text,
    dialog_state_from_persisted,
    location_publish_fields_from_batch_persisted,
    location_publish_fields_from_intent,
)

__all__ = [
    "LOCATION_MODE_CHECKIN",
    "LOCATION_MODE_SELLING",
    "LOCATION_MODE_CHOICES",
    "LOCATION_MODE_CHOICES_SET",
    "parse_poi_info_storage",
    "parse_location_short_name_from_storage",
    "format_poi_info_storage",
    "format_poi_info_from_short_name",
    "location_preview_display",
    "LOCATION_PLATFORM_FIELD_MAP",
    "LocationPromotionPublishFields",
    "effective_location_string_from_metadata",
    "LocationPublishFields",
    "LocationPoiInputChoice",
    "WechatNoPoiSubchoice",
    "location_publish_fields_from_intent",
    "dialog_state_from_persisted",
    "batch_location_summary_text",
    "location_publish_fields_from_batch_persisted",
]
