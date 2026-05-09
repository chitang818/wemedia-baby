# -*- coding: utf-8 -*-
"""作品描述 / #话题 领域规则（无 Qt）。"""

from .topics import (
    FULLWIDTH_TOPIC_HASH,
    normalize_topics_for_paste,
    parse_topic_list,
    parse_topic_ranges,
    strip_topic_trailing_punctuation,
)

__all__ = [
    "FULLWIDTH_TOPIC_HASH",
    "normalize_topics_for_paste",
    "parse_topic_list",
    "parse_topic_ranges",
    "strip_topic_trailing_punctuation",
]
