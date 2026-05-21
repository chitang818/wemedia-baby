"""
批量发布「描述配置」卡片与弹窗勾选项的统一映射规则。

索引约定：
0 自动（标题+简介）
1 自动（标题）
2 自动（简介）
3 手动
"""

from __future__ import annotations

from typing import Tuple


def combo_index_from_flags(use_library_title: bool, use_library_desc: bool) -> int:
    """根据弹窗勾选状态计算卡片下拉索引。"""
    if use_library_title and use_library_desc:
        return 0
    if use_library_title and (not use_library_desc):
        return 1
    if (not use_library_title) and use_library_desc:
        return 2
    return 3


def flags_from_combo_index(index: int) -> Tuple[bool, bool]:
    """根据卡片下拉索引计算弹窗勾选状态。"""
    if index == 0:
        return True, True
    if index == 1:
        return True, False
    if index == 2:
        return False, True
    return False, False

