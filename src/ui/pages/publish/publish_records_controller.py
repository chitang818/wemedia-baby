"""Controller/state helpers for publish record table pages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PublishRecordsPageState:
    loaded_count: int = 0
    total_count: int = 0
    has_more: bool = False
    loading_more: bool = False

    @classmethod
    def from_page(cls, page: Any) -> "PublishRecordsPageState":
        return cls(
            loaded_count=len(getattr(page, "publish_records", []) or []),
            total_count=int(getattr(page, "_total_record_count", 0) or 0),
            has_more=bool(getattr(page, "_has_more_records", False)),
            loading_more=bool(getattr(page, "_loading_more_records", False)),
        )


class PublishRecordsController:
    """Owns publish record page action orchestration."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.state = PublishRecordsPageState.from_page(page)

    def sync_state(self) -> PublishRecordsPageState:
        self.state = PublishRecordsPageState.from_page(self.page)
        return self.state

    def load_more(self) -> None:
        self.sync_state()
        return self.page._load_more_publish_records()
