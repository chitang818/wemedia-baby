# -*- coding: utf-8 -*-
from src.ui.pages.publish.poi_info_display import (
    WECHAT_POI_DISPLAY_DEFAULT_CITY,
    WECHAT_POI_DISPLAY_HIDE,
    format_poi_table_cell_display,
)


def test_format_poi_empty_json_with_mode_shows_placeholder():
    raw = '{"poi": "", "location_mode": "打卡模式"}'
    assert format_poi_table_cell_display(raw) == "—"


def test_format_poi_with_text_and_mode():
    raw = '{"poi": "天安门", "location_mode": "打卡模式"}'
    assert format_poi_table_cell_display(raw) == "天安门（打卡模式）"


def test_format_poi_plain_text():
    assert format_poi_table_cell_display("南京路") == "南京路"
    assert format_poi_table_cell_display("") == "—"
    assert format_poi_table_cell_display("   ") == "—"


def test_wechat_video_empty_poi_shows_default_city_when_flag_false():
    assert (
        format_poi_table_cell_display(
            "",
            platform="wechat_video",
            wechat_empty_location_open_picker=False,
        )
        == WECHAT_POI_DISPLAY_DEFAULT_CITY
    )


def test_wechat_video_empty_poi_shows_hide_when_flag_true():
    assert (
        format_poi_table_cell_display(
            "",
            platform="wechat_video",
            wechat_empty_location_open_picker=True,
        )
        == WECHAT_POI_DISPLAY_HIDE
    )


def test_wechat_video_empty_poi_unknown_flag_still_dash():
    assert (
        format_poi_table_cell_display(
            "",
            platform="wechat_video",
            wechat_empty_location_open_picker=None,
        )
        == "—"
    )


def test_non_wechat_empty_poi_ignores_flag():
    assert (
        format_poi_table_cell_display(
            "",
            platform="douyin",
            wechat_empty_location_open_picker=False,
        )
        == "—"
    )
