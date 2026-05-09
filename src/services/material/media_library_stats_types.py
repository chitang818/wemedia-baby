from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class MediaCounts:
    total: int = 0
    used: int = 0
    unused: int = 0


@dataclass(frozen=True)
class MediaKindStats:
    """某一种素材类型（视频/图文）的统计结果。"""

    counts: MediaCounts = field(default_factory=MediaCounts)
    by_owner: Dict[str, MediaCounts] = field(default_factory=dict)
    # 账号维度：key=account_id（平台账号 ID）
    by_account_id: Dict[int, MediaCounts] = field(default_factory=dict)
    # 账号组维度：key=group_id（账号组 ID）
    by_group_id: Dict[int, MediaCounts] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaLibraryStats:
    """媒体库统计结果（全局 + 按归属 owner_label）。"""

    video: MediaKindStats = field(default_factory=MediaKindStats)
    image: MediaKindStats = field(default_factory=MediaKindStats)
    all_media: MediaCounts = field(default_factory=MediaCounts)
    error: str = ""

