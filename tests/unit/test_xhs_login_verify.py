# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Optional

import pytest

from src.plugins.pro.xiaohongshu.login_plugin import XiaohongshuLoginPlugin


pytestmark = pytest.mark.unit


class _FakeResponse:
    def __init__(self, status: int, json_data: Optional[Any] = None) -> None:
        self.status = status
        self._json = json_data

    async def json(self) -> Any:
        if self._json is None:
            raise ValueError("no json")
        return self._json

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *args) -> None:
        return None


class _FakeSession:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.last_get_kwargs: dict = {}

    def get(self, url: str, **kwargs):
        self.last_get_kwargs = kwargs
        return self.response


@pytest.mark.asyncio
async def test_xhs_verify_treats_400_as_online_when_session_cookie_exists() -> None:
    plugin = XiaohongshuLoginPlugin()
    session = _FakeSession(_FakeResponse(400))
    cookies = {
        "access-token-creator.xiaohongshu.com": "token",
        "x-user-id-creator.xiaohongshu.com": "9402628224",
    }

    result = await plugin.verify_cookie_http(session, cookies)

    assert result.success is True
    assert result.nickname is None
    assert result.user_id == "9402628224"
    assert "access-token-creator.xiaohongshu.com=token" in session.last_get_kwargs["headers"]["Cookie"]


@pytest.mark.asyncio
async def test_xhs_verify_rejects_401_even_when_session_cookie_exists() -> None:
    plugin = XiaohongshuLoginPlugin()
    session = _FakeSession(_FakeResponse(401))
    cookies = {
        "access-token-creator.xiaohongshu.com": "expired",
        "x-user-id-creator.xiaohongshu.com": "9402628224",
    }

    result = await plugin.verify_cookie_http(session, cookies)

    assert result.success is False
    assert "401/403" in (result.error_message or "")


@pytest.mark.asyncio
async def test_xhs_verify_rejects_400_without_session_cookie() -> None:
    plugin = XiaohongshuLoginPlugin()
    session = _FakeSession(_FakeResponse(400))
    cookies = {"a1": "tracking-cookie"}

    result = await plugin.verify_cookie_http(session, cookies)

    assert result.success is False
    assert "状态码 400" in (result.error_message or "")
