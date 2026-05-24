# -*- coding: utf-8 -*-
"""Small in-process cache for publish account pickers."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from src.domain.repositories.account_repository_async import AccountRepositoryAsync

logger = logging.getLogger(__name__)

_CACHE: Optional[List[Dict[str, Any]]] = None
_LOADED_AT: float = 0.0
_LOCK = asyncio.Lock()


def get_cached_accounts() -> Optional[List[Dict[str, Any]]]:
    if _CACHE is None:
        return None
    return [dict(acc) for acc in _CACHE]


def set_cached_accounts(accounts: List[Dict[str, Any]]) -> None:
    global _CACHE, _LOADED_AT
    _CACHE = [dict(acc) for acc in (accounts or [])]
    _LOADED_AT = time.monotonic()


def invalidate_account_list_cache() -> None:
    global _CACHE, _LOADED_AT
    _CACHE = None
    _LOADED_AT = 0.0


async def load_accounts_for_publish_cache(*, force_refresh: bool = False) -> List[Dict[str, Any]]:
    cached = get_cached_accounts()
    if cached is not None and not force_refresh:
        return cached

    async with _LOCK:
        cached = get_cached_accounts()
        if cached is not None and not force_refresh:
            return cached
        repo = AccountRepositoryAsync()
        accounts = await repo.find_all(user_id=None)
        set_cached_accounts(accounts)
        logger.debug("账号列表缓存已刷新: %d", len(accounts))
        return get_cached_accounts() or []


def account_list_cache_age_seconds() -> Optional[float]:
    if _CACHE is None or _LOADED_AT <= 0:
        return None
    return max(0.0, time.monotonic() - _LOADED_AT)
