# -*- coding: utf-8 -*-
"""
团购推广领域模型（占位）
文件路径：src/domain/publish/promotion_settings/group_buy.py

当前为占位实现，后续根据各平台团购挂载逻辑补充。
现有 anchor_info 字段（发布记录列）暂作载体，与单条任务页「添加标签-团购」保持兼容。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class GroupBuyPublishFields:
    """团购推广发布字段（占位）。

    Attributes:
        anchor_text: 团购主内容（链接或名称），对应 publish_records.anchor_info
    """

    anchor_text: str = ""

    def apply_to_plugin_metadata(self, metadata: Dict[str, Any]) -> None:
        """将团购信息写入 metadata["anchor_info"]（与现有抖音团购步骤兼容）。"""
        val = (self.anchor_text or "").strip()
        if val:
            metadata["anchor_info"] = val

    def is_empty(self) -> bool:
        return not (self.anchor_text or "").strip()
