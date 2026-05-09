"""
poi_info 在表格中的展示辅助（发布列表、回收站、批量预览等）。

与 ``src.domain.publish.location_settings`` 中 poi 编解码一致：
纯文本为旧数据或仅地点；JSON 可含 poi + location_mode（打卡/带货）。

视频号且无 POI 文案时，根据 ``wechat_empty_location_open_picker`` 展示「默认城市」或「不展示位置」。
"""

from __future__ import annotations

from typing import Any, Optional

from src.domain.publish.location_settings import parse_poi_info_storage
from src.ui.pages.publish.task_field_display import TASK_FIELD_EMPTY_DISPLAY

# 视频号空 POI 时在列表/预览中的可读文案（与单条「默认城市定位」复选框、批量弹窗语义一致）
WECHAT_POI_DISPLAY_DEFAULT_CITY = "默认城市"
WECHAT_POI_DISPLAY_HIDE = "不展示位置"


def format_poi_table_cell_display(
    raw: Optional[str],
    *,
    platform: Optional[str] = None,
    wechat_empty_location_open_picker: Any = None,
) -> str:
    """「位置」列表格展示。

    有地点文案：带模式后缀。无文案且为视频号：按 wx 标志显示默认城市/不展示位置。
    其它空文案：—。
    """
    poi_text, mode = parse_poi_info_storage(raw or "")
    if poi_text:
        if mode:
            return f"{poi_text}（{mode}）"
        return poi_text

    plat = (platform or "").strip()
    if plat == "wechat_video" and wechat_empty_location_open_picker is not None:
        if not bool(wechat_empty_location_open_picker):
            return WECHAT_POI_DISPLAY_DEFAULT_CITY
        return WECHAT_POI_DISPLAY_HIDE

    return TASK_FIELD_EMPTY_DISPLAY
