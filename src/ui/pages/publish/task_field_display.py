"""
发布任务在表格/说明卡片中的字段展示：内容为空或仅空白时统一为 em dash（—）。
"""

from __future__ import annotations

import json
from typing import Any, Optional

# 与同页其它列（购物车、团购、声明原创等）一致
TASK_FIELD_EMPTY_DISPLAY = "—"


def format_cart_info_table_cell(cart_info_raw: Optional[str]) -> str:
    """表格「购物车」列：购物车推广 JSON 显示商品简称；其它非空 cart_info 显示 ✅。"""
    s = (cart_info_raw or "").strip()
    if s.startswith("{"):
        try:
            d = json.loads(s)
            if isinstance(d, dict):
                # 新键优先，兼容旧键
                sn = (d.get("cart_short_name") or d.get("yellow_cart_short_name") or "").strip()
                if sn:
                    return task_field_str_or_dash(sn)
        except (json.JSONDecodeError, TypeError):
            pass
    if s:
        return "✅"
    return TASK_FIELD_EMPTY_DISPLAY


def task_field_str_or_dash(value: Any) -> str:
    """任意值转为展示用字符串；None 或去掉首尾空白后为空则返回 —。"""
    if value is None:
        return TASK_FIELD_EMPTY_DISPLAY
    s = str(value).strip()
    return s if s else TASK_FIELD_EMPTY_DISPLAY
