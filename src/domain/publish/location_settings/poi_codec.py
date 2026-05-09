# -*- coding: utf-8 -*-
"""poi_info 存储编解码：纯文本（旧）与 JSON（poi + location_mode）。"""
from __future__ import annotations

import json
from typing import Tuple

from .constants import LOCATION_MODE_CHOICES_SET


def parse_poi_info_storage(raw: str) -> Tuple[str, str]:
    """从 poi_info 解析 (地点文案, 打卡/带货模式)。"""
    s = (raw or "").strip()
    if not s:
        return "", ""
    if s.startswith("{"):
        try:
            d = json.loads(s)
            if isinstance(d, dict):
                main = (
                    d.get("poi")
                    or d.get("location")
                    or d.get("text")
                    or ""
                )
                if not isinstance(main, str):
                    main = str(main) if main is not None else ""
                mode = d.get("location_mode") or d.get("tuan_mode") or ""
                if not isinstance(mode, str):
                    mode = str(mode) if mode is not None else ""
                mode = mode.strip()
                if mode and mode not in LOCATION_MODE_CHOICES_SET:
                    mode = ""
                return main.strip(), mode
        except (json.JSONDecodeError, TypeError):
            pass
    return s, ""


def format_poi_info_storage(poi: str, location_mode: str = "") -> str:
    """写入 poi_info：无模式为纯文本；有模式为 JSON。主文案为空则返回空串（不落占位 JSON）。"""
    poi = (poi or "").strip()
    mode = (location_mode or "").strip()
    if mode not in LOCATION_MODE_CHOICES_SET:
        mode = ""
    if not poi:
        return ""
    if not mode:
        return poi
    return json.dumps(
        {"poi": poi, "location_mode": mode},
        ensure_ascii=False,
    )
