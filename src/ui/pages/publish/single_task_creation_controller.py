"""Controller/state boundary for the single publish task page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional


@dataclass
class SingleTaskFormState:
    media_mode: Literal["video", "image"]
    selected_file_path: str = ""
    selected_account_type: str = ""
    editing_record_id: Optional[int] = None
    is_auto_library_file: bool = False

    @classmethod
    def from_page(cls, page: Any) -> "SingleTaskFormState":
        selected_account = getattr(page, "selected_account", None) or {}
        return cls(
            media_mode=getattr(page, "_media_mode", "video"),
            selected_file_path=getattr(page, "selected_file_path", "") or "",
            selected_account_type=str(selected_account.get("type") or ""),
            editing_record_id=getattr(page, "editing_record_id", None),
            is_auto_library_file=bool(getattr(page, "_file_from_auto_library", False)),
        )


class SingleTaskCreationController:
    """Keeps single-task business orchestration out of the page surface."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.state = SingleTaskFormState.from_page(page)

    def sync_state(self) -> SingleTaskFormState:
        self.state = SingleTaskFormState.from_page(self.page)
        return self.state

    def publish(self) -> None:
        self.sync_state()
        return self.page._on_publish_legacy()
