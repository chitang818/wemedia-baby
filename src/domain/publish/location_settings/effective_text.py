# -*- coding: utf-8 -*-
"""从发布 metadata 得到「有效地理位置文案」（与各列表展示规则一致）。"""
from __future__ import annotations

import json
from typing import Any, Dict


def effective_location_string_from_metadata(metadata: Dict[str, Any]) -> str:
    """JSON 内 poi 为空则视为未设置位置；供各平台位置步骤共用。"""
    raw = (metadata.get("location") or metadata.get("poi_info") or "").strip()
    if not raw:
        return ""
    if raw.startswith("{"):
        try:
            d = json.loads(raw)
            if isinstance(d, dict):
                main = (
                    d.get("poi")
                    or d.get("location")
                    or d.get("text")
                    or ""
                )
                return str(main).strip() if main is not None else ""
        except (json.JSONDecodeError, TypeError):
            pass
    return raw
