"""
批量发布 - 文案与标签纯函数
文件路径：src/pro_features/batch/copywriting_helpers.py

此模块已将核心逻辑迁移至 src.services.copywriting.helpers。
当前保留此文件仅用于向下兼容，建议新代码直接引用 src.services.copywriting.helpers。
"""

from __future__ import annotations
from typing import List, Optional

from src.services.copywriting.helpers import (
    parse_topic_list,
    extract_work_id_from_filename,
    merge_title_desc_from_copywriting_item,
)

__all__ = [
    "parse_topic_list",
    "extract_work_id_from_filename",
    "merge_title_desc_from_copywriting_item",
]
