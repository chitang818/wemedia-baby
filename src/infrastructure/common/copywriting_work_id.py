"""
文案作品编号规则
文件路径：src/infrastructure/common/copywriting_work_id.py

约定：共 5 个字符 — 第 1 位为大写英文字母，后 4 位为数字（如 A0001、B8888）。
用于文案库新建/编辑/Excel 导入校验，以及批量视频按文件名前缀匹配文案库。
"""

from __future__ import annotations

import re
from typing import Final

COPYWRITING_WORK_ID_LENGTH: Final = 5

_COPYWRITING_WORK_ID_RE: Final = re.compile(r"^[A-Z][0-9]{4}$")

COPYWRITING_WORK_ID_FORMAT_HINT: Final = (
    "须为 5 个字符：1 个大写英文字母 + 4 位数字，例如 A0001、B8888"
)


def is_valid_copywriting_work_id(work_id: str) -> bool:
    """作品编号是否符合「大写字母 + 四位数字」。"""
    s = (work_id or "").strip()
    return bool(_COPYWRITING_WORK_ID_RE.fullmatch(s))
