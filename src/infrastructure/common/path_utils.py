"""
路径工具

说明：
- 项目内涉及“文件是否相同/是否已占用”时，需要对路径做一致归一化；
- Windows 下路径比较需考虑盘符与大小写（使用 normcase）。
"""

from __future__ import annotations

import os
from typing import Optional


def normalize_media_path(path: Optional[str]) -> str:
    """归一化媒体文件路径，用于跨模块一致比较。

    规则：
    - 空值返回空字符串
    - 先转为绝对路径，再 normpath
    - Windows 下追加 normcase（解决盘符/大小写差异导致的集合比较失效）
    """
    if not path:
        return ""
    p = str(path).strip()
    if not p:
        return ""
    try:
        p = os.path.abspath(p)
    except Exception:
        # abspath 失败时仍尽量继续做 normpath/normcase
        pass
    try:
        p = os.path.normpath(p)
    except Exception:
        pass
    # normcase 在非 Windows 基本不改变路径；在 Windows 会统一大小写与分隔符
    try:
        p = os.path.normcase(p)
    except Exception:
        pass
    return p

