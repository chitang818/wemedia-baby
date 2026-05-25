# -*- coding: utf-8 -*-
from src.domain.publish.location_settings import (
    format_poi_info_from_short_name,
    location_preview_display,
    parse_location_short_name_from_storage,
    parse_poi_info_storage,
)


def test_format_and_parse_location_short_name():
    raw = format_poi_info_from_short_name("遥马", "打卡模式")
    assert parse_location_short_name_from_storage(raw) == "遥马"
    text, mode = parse_poi_info_storage(raw)
    assert text == "遥马"
    assert mode == "打卡模式"


def test_location_preview_display_short_name():
    raw = format_poi_info_from_short_name("遥马")
    assert location_preview_display(raw) == "遥马"


def test_legacy_poi_text_unchanged():
    raw = '{"poi": "南京路", "location_mode": "带货模式"}'
    text, mode = parse_poi_info_storage(raw)
    assert text == "南京路"
    assert mode == "带货模式"
    assert parse_location_short_name_from_storage(raw) == ""
