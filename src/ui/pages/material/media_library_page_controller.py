"""Shared controller/state helpers for media library pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, List


@dataclass
class MediaLibraryPageState:
    total_count: int = 0
    visible_count: int = 0
    owner_status: str = "全部"
    owner: str = "全部账号"


class MediaLibraryPageController:
    """Keeps media library filtering state outside the page widget."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.state = MediaLibraryPageState()

    def filter_items(self, items: Iterable[Any], *, owner_status: str, owner: str) -> List[Any]:
        filtered = list(items or [])
        total = len(filtered)

        if owner_status == "未分配":
            filtered = [item for item in filtered if getattr(item, "owner", "") == "未分配"]
        elif owner_status == "已分配":
            filtered = [item for item in filtered if getattr(item, "owner", "") != "未分配"]

        if owner != "全部账号" and owner_status != "未分配":
            filtered = [item for item in filtered if getattr(item, "owner", "") == owner]

        self.state = MediaLibraryPageState(
            total_count=total,
            visible_count=len(filtered),
            owner_status=owner_status,
            owner=owner,
        )
        return filtered
