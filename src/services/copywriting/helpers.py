"""
文案库匹配相关辅助函数
文件路径：src/services/copywriting/helpers.py
"""

from __future__ import annotations
import os
from typing import List, Optional, Any, Dict

from src.infrastructure.common.copywriting_work_id import (
    COPYWRITING_WORK_ID_LENGTH,
    is_valid_copywriting_work_id,
)
from src.domain.publish.work_description import normalize_topics_for_paste


def parse_topic_list(text: Optional[str]) -> List[str]:
    """从文本中解析 #话题 关键词列表。"""
    from src.domain.publish.work_description import parse_topic_list as _parse
    return _parse(text)


def extract_work_id_from_filename(file_path_or_name: str) -> str:
    """从文件名提取作品编号（如 A0001）。"""
    name = os.path.basename(file_path_or_name)
    stem, _ = os.path.splitext(name)
    stem = (stem or "").strip()
    if len(stem) < COPYWRITING_WORK_ID_LENGTH:
        return ""
    candidate = stem[:COPYWRITING_WORK_ID_LENGTH]
    return candidate if is_valid_copywriting_work_id(candidate) else ""


def merge_title_desc_from_copywriting_item(
    *,
    apply_all: bool,
    same_title: str,
    same_desc: str,
    use_lib_title: bool,
    use_lib_desc: bool,
    item: Optional[Dict[str, Any] | Any],
) -> tuple[str, str]:
    """合并标题与简介逻辑（支持标准库 item 和随机库 item）。"""
    
    # 辅助函数：由于不同模型字段名可能不同，尝试多种可能的键名
    def get_val(obj, keys: List[str]) -> str:
        if obj is None:
            return ""
        for k in keys:
            if isinstance(obj, dict):
                v = obj.get(k)
                if v: return str(v).strip()
            else:
                v = getattr(obj, k, None)
                if v: return str(v).strip()
        return ""

    # 标准库字段：short_title, description
    # 随机库字段：title (可能没有), content
    lib_title = get_val(item, ["short_title", "title"])
    lib_desc = get_val(item, ["description", "content"])

    if apply_all:
        title = (same_title or "").strip()
        desc = (same_desc or "").strip()
        filled_desc_from_lib = False
        if item:
            if use_lib_title and not title:
                title = lib_title
            if use_lib_desc and not desc:
                desc = lib_desc
                filled_desc_from_lib = bool(desc)
        if filled_desc_from_lib and desc:
            desc = normalize_topics_for_paste(desc)
        return title, desc
    
    title, desc = "", ""
    if item:
        if use_lib_title:
            title = lib_title
        if use_lib_desc:
            desc = lib_desc
    if use_lib_desc and desc:
        desc = normalize_topics_for_paste(desc)
    return title, desc
