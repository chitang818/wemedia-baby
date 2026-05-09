"""
作品简介中的 #话题 解析与粘贴规范化（纯函数，无 Qt 依赖）。

单视频/单图文、批量视频/批量图文及文案库逻辑共用同一套规则，避免解析结果不一致。

模块位置：``src.domain.publish.work_description``（与 ``location_settings`` 并列，供发布任务统一引用）。
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# 全角井号（常见于 Excel/文案库导出），与半角 # 同等视为话题起始/分隔语义
FULLWIDTH_TOPIC_HASH = "\uff03"


def _normalize_topic_hash_chars(text: str) -> str:
    """将全角 ＃ 规范为半角 #，避免「#话题＃话题」被识别成单一大话题。
    同时处理「# 话题」（# 号后跟空格）的情况，将其规范为「#话题」，
    以兼容部分用户习惯或平台导出的带空格话题格式（如 "# 蔬菜种植"）。
    """
    if FULLWIDTH_TOPIC_HASH in text:
        text = text.replace(FULLWIDTH_TOPIC_HASH, "#")
    # 将 "# " + 中文/字母/数字 的格式去除 # 后的空格（仅当后接有效话题内容时才替换）
    if "# " in text:
        text = re.sub(r"#\s+(?=[\u4e00-\u9fa5\w])", "#", text)
    return text



# 每个话题单独匹配：# 后为「连续非空白、非#、非标点」字符；
# 即遇到空白/标点即结束话题，满足“#后连续文本”的业务定义。
_TOPIC_BREAK_PUNCT = (
    "，。！？；：、,.!?;:()（）[]【】{}《》“”‘’\"'`~·…—-+/\\|<>@%^&*= "
)
_TOPIC_PATTERN = re.compile(r"#([^\s#%s]+)" % re.escape(_TOPIC_BREAK_PUNCT))

# 话题末尾需剔除的标点与特殊字符（话题中不含有符号）
_TOPIC_TRAILING_PUNCT = re.compile(
    r"[\s\u3000\u3001\u3002\u300a\u300b\u3010\u3011\u201c\u201d\u2018\u2019"
    r"、。，．；：！？\"\"''（）【】《》…—·,.;:!?\-]+$"
)

# 话题结尾后允许的字符（空白、#、或上述标点均视为话题结束）
_TOPIC_END_OK_CHARS = frozenset(
    " \t\n\r\u3000\u3001\u3002\u300a\u300b\u3010\u3011\u201c\u201d\u2018\u2019"
    "、。，．；：！？\"\"''（）【】《》…—·,.;:!?-#"
)


def strip_topic_trailing_punctuation(match_text: str) -> str:
    """从匹配到的话题文本中剔除末尾的标点与特殊字符，保证话题中不含有符号。"""
    if not match_text or not match_text.startswith("#"):
        return match_text
    after_hash = match_text[1:]
    stripped = _TOPIC_TRAILING_PUNCT.sub("", after_hash)
    return "#" + stripped


def parse_topic_ranges(text: Optional[str]) -> List[Tuple[int, int]]:
    """解析文本中的话题区间：每个 #关键词 单独识别，话题末尾标点剔除。返回 [(start, end), ...]。"""
    if not text:
        return []
    text = _normalize_topic_hash_chars(text)
    ranges: List[Tuple[int, int]] = []
    for m in _TOPIC_PATTERN.finditer(text):
        raw = m.group(0)
        stripped = strip_topic_trailing_punctuation(raw)
        start = m.start()
        end_stripped = start + len(stripped)
        next_ok = (
            end_stripped >= len(text)
            or (end_stripped < len(text) and text[end_stripped] in _TOPIC_END_OK_CHARS)
        )
        if next_ok and len(stripped) > 1:
            ranges.append((start, end_stripped))
    return ranges


def parse_topic_list(text: Optional[str]) -> List[str]:
    """从文本中解析出话题关键词列表（去 # 号，且剔除话题末尾标点）。与 parse_topic_ranges 规则一致。"""
    if text is None:
        return []
    if not text:
        return []
    text = _normalize_topic_hash_chars(text)
    tags: List[str] = []
    for m in _TOPIC_PATTERN.finditer(text):
        raw = m.group(0)
        stripped = strip_topic_trailing_punctuation(raw)
        end_stripped = m.start() + len(stripped)
        next_ok = (
            end_stripped >= len(text)
            or (end_stripped < len(text) and text[end_stripped] in _TOPIC_END_OK_CHARS)
        )
        if next_ok:
            tag = stripped.lstrip("#")
            if tag and tag not in tags:
                tags.append(tag)
    return tags


def normalize_topics_for_paste(text: Optional[str]) -> str:
    """将粘贴文本中的 #话题 规范化为「#话题+空格」，剔除话题末尾标点，相邻 #话题 之间补空格。"""
    if not text:
        return ""
    text = _normalize_topic_hash_chars(text)
    if "#" not in text:
        return text
    out: List[str] = []
    last = 0
    for m in _TOPIC_PATTERN.finditer(text):
        start, end = m.span()
        out.append(text[last:start])
        token = strip_topic_trailing_punctuation(m.group(0))
        out.append(token)
        next_ch = text[end] if end < len(text) else ""
        if next_ch and not next_ch.isspace() and next_ch != "#":
            out.append(" ")
        elif next_ch == "#" or not next_ch:
            out.append(" ")
        last = end
    out.append(text[last:])
    return "".join(out)
