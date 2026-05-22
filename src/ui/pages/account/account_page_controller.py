"""Controller/state helpers for account management page actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AccountPageState:
    account_count: int = 0
    stale: bool = False
    first_show: bool = True

    @classmethod
    def from_page(cls, page: Any) -> "AccountPageState":
        return cls(
            account_count=len(getattr(page, "accounts", []) or []),
            stale=bool(getattr(page, "_accounts_data_stale", False)),
            first_show=bool(getattr(page, "_account_page_first_show", True)),
        )


class AccountPageController:
    """Owns non-visual account page orchestration."""

    def __init__(self, page: Any) -> None:
        self.page = page
        self.state = AccountPageState.from_page(page)

    def sync_state(self) -> AccountPageState:
        self.state = AccountPageState.from_page(self.page)
        return self.state

    def refresh(self, *, silent: bool = False) -> None:
        self.sync_state()
        return self.page._on_refresh_legacy(silent=silent)
