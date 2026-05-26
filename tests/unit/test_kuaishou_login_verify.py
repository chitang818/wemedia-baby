# -*- coding: utf-8 -*-
"""快手登录插件 HTTP 校验单元测试"""

from __future__ import annotations

from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from src.plugins.community.kuaishou.login_plugin import KuaishouLoginPlugin


class _FakeResponse:
    def __init__(
        self,
        status: int,
        url: str = "",
        text: str = "",
        json_data: Optional[Any] = None,
    ) -> None:
        self.status = status
        self.url = url or "https://cp.kuaishou.com/"
        self._text = text
        self._json = json_data

    async def text(self) -> str:
        return self._text

    async def json(self) -> Any:
        if self._json is None:
            raise ValueError("no json")
        return self._json

    async def __aenter__(self) -> "_FakeResponse":
        return self

    async def __aexit__(self, *args) -> None:
        return None


class _FakeSession:
    def __init__(
        self,
        *,
        post_response: Optional[_FakeResponse] = None,
        get_response: Optional[_FakeResponse] = None,
    ) -> None:
        self._post_response = post_response
        self._get_response = get_response
        self.last_post_kwargs: dict = {}
        self.last_get_kwargs: dict = {}

    def post(self, url: str, **kwargs):
        self.last_post_kwargs = kwargs
        return self._post_response or _FakeResponse(500)

    def get(self, url: str, **kwargs):
        self.last_get_kwargs = kwargs
        return self._get_response or _FakeResponse(500)


@pytest.fixture
def plugin() -> KuaishouLoginPlugin:
    return KuaishouLoginPlugin()


@pytest.fixture
def valid_cookies() -> dict:
    return {
        "userId": "123",
        "kuaishou.web.cp.api_st": "token",
        "kuaishou.web.cp.api_ph": "ph_token",
    }


@pytest.mark.asyncio
async def test_verify_cookie_http_rejects_missing_session(plugin: KuaishouLoginPlugin) -> None:
    result = await plugin.verify_cookie_http(MagicMock(), {"userId": "1"})
    assert result.success is False
    assert "缺失关键会话" in (result.error_message or "")


@pytest.mark.asyncio
async def test_verify_cookie_http_accepts_authority_api(
    plugin: KuaishouLoginPlugin, valid_cookies: dict
) -> None:
    session = _FakeSession(
        post_response=_FakeResponse(
            200,
            json_data={
                "result": 1,
                "data": {"userName": "刘强东"},
            },
        ),
    )
    result = await plugin.verify_cookie_http(session, valid_cookies)
    assert result.success is True
    assert result.nickname == "刘强东"
    assert session.last_get_kwargs == {}


@pytest.mark.asyncio
async def test_verify_cookie_http_rejects_authority_api_offline(
    plugin: KuaishouLoginPlugin, valid_cookies: dict
) -> None:
    session = _FakeSession(
        post_response=_FakeResponse(200, json_data={"result": 0, "message": "未登录"}),
    )
    result = await plugin.verify_cookie_http(session, valid_cookies)
    assert result.success is False
    assert "鉴权 API" in (result.error_message or "")


@pytest.mark.asyncio
async def test_verify_cookie_http_rejects_login_redirect(
    plugin: KuaishouLoginPlugin, valid_cookies: dict
) -> None:
    session = _FakeSession(
        post_response=_FakeResponse(502),
        get_response=_FakeResponse(
            200,
            "https://passport.kuaishou.com/pc/account/login",
            "<html>login</html>",
        ),
    )
    result = await plugin.verify_cookie_http(session, valid_cookies)
    assert result.success is False


@pytest.mark.asyncio
async def test_verify_cookie_http_rejects_login_page_html(
    plugin: KuaishouLoginPlugin, valid_cookies: dict
) -> None:
    html = "<html><body>扫码登录 立即登录</body></html>"
    session = _FakeSession(
        post_response=_FakeResponse(502),
        get_response=_FakeResponse(200, "https://cp.kuaishou.com/profile", html),
    )
    result = await plugin.verify_cookie_http(session, valid_cookies)
    assert result.success is False


@pytest.mark.asyncio
async def test_verify_cookie_http_accepts_logged_in_page(
    plugin: KuaishouLoginPlugin, valid_cookies: dict
) -> None:
    html = (
        '<script>window.__INITIAL_STATE__={"userId":"123","nickname":"测试号"}</script>'
    )
    session = _FakeSession(
        post_response=_FakeResponse(502),
        get_response=_FakeResponse(200, "https://cp.kuaishou.com/profile", html),
    )
    result = await plugin.verify_cookie_http(session, valid_cookies)
    assert result.success is True
    assert result.nickname == "测试号"


@pytest.mark.asyncio
async def test_verify_cookie_http_accepts_spa_shell_via_profile_fallback(
    plugin: KuaishouLoginPlugin, valid_cookies: dict
) -> None:
    session = _FakeSession(
        post_response=_FakeResponse(502),
        get_response=_FakeResponse(200, "https://cp.kuaishou.com/profile", "<html></html>"),
    )
    result = await plugin.verify_cookie_http(session, valid_cookies)
    assert result.success is True
