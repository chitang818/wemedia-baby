# -*- coding: utf-8 -*-
"""
位置「分层二选一」领域语义：先是否要填写 POI，再在视频号 + 不填时区分保留默认 / 不显示位置。

与落库字段对应关系：
- 需要输入位置 → 非空 ``poi_info``，``wechat_empty_location_open_picker=False``
- 不需要 + 非视频号语境 → 空 ``poi_info``，``False``
- 不需要 + 视频号 + 保留发布页默认 → 空 ``poi_info``，``False``
- 不需要 + 视频号 + 不显示位置 → 空 ``poi_info``，``True``
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Tuple

from .poi_codec import format_poi_info_storage, parse_poi_info_storage
from .publish_fields import LocationPublishFields


class LocationPoiInputChoice(Enum):
    NEED_INPUT = "need_input"
    NO_INPUT = "no_input"


class WechatNoPoiSubchoice(Enum):
    """仅在「不需要输入位置」且存在视频号任务时由用户选择。"""
    NOT_APPLICABLE = "na"
    KEEP_PAGE_DEFAULT = "keep"
    HIDE_LOCATION = "hide"


def location_publish_fields_from_intent(
    *,
    input_choice: LocationPoiInputChoice,
    wechat_sub: WechatNoPoiSubchoice,
    loc_text: str,
    loc_mode: str,
) -> LocationPublishFields:
    if input_choice == LocationPoiInputChoice.NEED_INPUT:
        poi = format_poi_info_storage((loc_text or "").strip(), (loc_mode or "").strip())
        return LocationPublishFields(
            poi_info=poi,
            wechat_empty_location_open_picker=False,
        )
    if wechat_sub == WechatNoPoiSubchoice.HIDE_LOCATION:
        return LocationPublishFields(
            poi_info="",
            wechat_empty_location_open_picker=True,
        )
    return LocationPublishFields(
        poi_info="",
        wechat_empty_location_open_picker=False,
    )


def dialog_state_from_persisted(
    poi_info_storage: str,
    wx_flag: Optional[bool],
    *,
    show_wechat_subchoice: bool,
) -> Tuple[LocationPoiInputChoice, WechatNoPoiSubchoice]:
    """从已保存的 poi_info / wx 反推弹窗单选状态。"""
    text, _mode = parse_poi_info_storage(poi_info_storage or "")
    if (text or "").strip():
        return LocationPoiInputChoice.NEED_INPUT, WechatNoPoiSubchoice.NOT_APPLICABLE
    if not show_wechat_subchoice:
        return LocationPoiInputChoice.NO_INPUT, WechatNoPoiSubchoice.NOT_APPLICABLE
    if wx_flag is True:
        return LocationPoiInputChoice.NO_INPUT, WechatNoPoiSubchoice.HIDE_LOCATION
    if wx_flag is False:
        return LocationPoiInputChoice.NO_INPUT, WechatNoPoiSubchoice.KEEP_PAGE_DEFAULT
    # None：旧数据兼容，与 step_06 一致视为要去选「不显示位置」
    return LocationPoiInputChoice.NO_INPUT, WechatNoPoiSubchoice.HIDE_LOCATION


def batch_location_summary_text(
    poi_info_storage: str,
    wx_flag: Optional[bool],
    *,
    show_wechat_subchoice: bool,
) -> str:
    """批量页按钮旁摘要一行话。

    弹窗内「视频号两项」始终可配；摘要里用「（视频号）」提示仅视频号发布生效。
    当所选目标里不含视频号时，仍可根据 wx_flag 显示「不展示/保留」，避免与落库不一致。
    """
    t, m = parse_poi_info_storage(poi_info_storage or "")
    if (t or "").strip():
        return f"指定：{t}" + (f"（{m}）" if m else "")
    # 无 POI 文案：与 dialog_state 对齐，None 且含视频号语境时按旧数据视为「不展示」
    if wx_flag is True or (wx_flag is None and show_wechat_subchoice):
        return "不展示位置（视频号）"
    if show_wechat_subchoice:
        return "保留发布页位置（视频号）"
    return "不设置位置"


def location_publish_fields_from_batch_persisted(
    poi_info_storage: str,
    wx_flag: Optional[bool],
) -> LocationPublishFields:
    """批量 common：直接由当前存储的字符串与布尔生成字段（与弹窗保存结果一致）。"""
    text, _ = parse_poi_info_storage(poi_info_storage or "")
    if (text or "").strip():
        return LocationPublishFields(
            poi_info=(poi_info_storage or "").strip(),
            wechat_empty_location_open_picker=False,
        )
    if wx_flag is True:
        return LocationPublishFields(
            poi_info="",
            wechat_empty_location_open_picker=True,
        )
    return LocationPublishFields(
        poi_info="",
        wechat_empty_location_open_picker=False,
    )
