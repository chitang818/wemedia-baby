# -*- coding: utf-8 -*-
"""
写入发布记录 / 注入插件 metadata 的「标准位置字段」集合。

单条任务、批量任务、发布执行器均应通过本模块约定读写，便于各平台步骤统一消费。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class LocationPublishFields:
    """与 publish_records 及发布管道透传一致的位置相关列。"""

    poi_info: str = ""
    wechat_empty_location_open_picker: Optional[bool] = None

    @classmethod
    def from_publish_record_dict(cls, row: Dict[str, Any]) -> "LocationPublishFields":
        poi = row.get("poi_info")
        poi_str = "" if poi is None else str(poi).strip()
        wx = row.get("wechat_empty_location_open_picker")
        return cls(
            poi_info=poi_str,
            wechat_empty_location_open_picker=None if wx is None else bool(wx),
        )

    def to_common_fields_dict(self) -> Dict[str, Any]:
        """批量任务 common_fields 片段。"""
        return {
            "poi_info": self.poi_info or "",
            "wechat_empty_location_open_picker": self.wechat_empty_location_open_picker,
        }

    def apply_to_plugin_metadata(self, metadata: Dict[str, Any]) -> None:
        """写入插件 publish(metadata)；与 publish_executor 行为一致。"""
        pi = (self.poi_info or "").strip()
        if pi:
            metadata["poi_info"] = pi
        if self.wechat_empty_location_open_picker is not None:
            metadata["wechat_empty_location_open_picker"] = bool(
                self.wechat_empty_location_open_picker
            )
