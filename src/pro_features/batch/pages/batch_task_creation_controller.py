"""Controller/state boundary for the batch task creation page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class BatchTaskCreationState:
    selected_account_count: int = 0
    video_count: int = 0
    time_slot_count: int = 0
    auto_match_enabled: bool = False
    match_mode: str = "standard"

    @classmethod
    def from_page(cls, page: Any) -> "BatchTaskCreationState":
        return cls(
            selected_account_count=len(getattr(page, "selected_accounts", []) or []),
            video_count=len(getattr(page, "video_list", []) or []),
            time_slot_count=len(getattr(page, "time_slots", []) or []),
            auto_match_enabled=bool(getattr(page, "auto_match_enabled", False)),
            match_mode=str(getattr(page, "match_mode", "standard") or "standard"),
        )


class BatchTaskCreationController:
    """Coordinates batch page actions while the legacy page logic is split out."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.state = BatchTaskCreationState.from_page(page)

    def sync_state(self) -> BatchTaskCreationState:
        self.state = BatchTaskCreationState.from_page(self.page)
        return self.state

    def import_files(self) -> None:
        self.sync_state()
        return self.page._on_import_files_legacy()

    def import_folder(self) -> None:
        self.sync_state()
        return self.page._on_import_folder_legacy()

    def choose_from_library(self) -> None:
        self.sync_state()
        return self.page._on_choose_from_library_legacy()
