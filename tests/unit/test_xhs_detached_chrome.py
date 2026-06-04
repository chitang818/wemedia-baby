from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.browser.detached_chrome_launcher import DetachedChromeLauncher
from src.services.account.account_verifier import AccountVerifier
from src.services.account.xhs_profile_identity_reader import XhsProfileIdentity, XhsProfileIdentityReader
from src.services.account.xhs_profile_sync_service import XhsProfileSyncService


pytestmark = pytest.mark.unit


def test_detached_chrome_args_do_not_include_automation_flags(tmp_path: Path) -> None:
    args = DetachedChromeLauncher.build_args(
        "C:/Chrome/chrome.exe",
        tmp_path / "profile" / "browser" / "user_data",
        "https://creator.xiaohongshu.com/new/home",
    )

    joined = " ".join(args).lower()
    assert "--user-data-dir=" in joined
    assert "--new-window" in args
    assert "--remote-debugging" not in joined
    assert "--enable-automation" not in joined
    assert "--disable-blink-features" not in joined
    assert "playwright" not in joined


def test_detached_chrome_profile_process_match_is_account_scoped(monkeypatch, tmp_path: Path) -> None:
    target_profile = tmp_path / "account_a" / "browser" / "user_data"
    other_profile = tmp_path / "account_b" / "browser" / "user_data"
    target_profile.mkdir(parents=True)
    other_profile.mkdir(parents=True)

    class FakeProcess:
        def __init__(self, pid: int, user_data_dir: Path) -> None:
            self.info = {
                "pid": pid,
                "name": "chrome.exe",
                "cmdline": [f"--user-data-dir={user_data_dir}"],
            }

    monkeypatch.setattr(
        "src.infrastructure.browser.detached_chrome_launcher.psutil.process_iter",
        lambda _attrs: [FakeProcess(11, other_profile)],
    )
    assert DetachedChromeLauncher.find_profile_process(target_profile) is None

    monkeypatch.setattr(
        "src.infrastructure.browser.detached_chrome_launcher.psutil.process_iter",
        lambda _attrs: [FakeProcess(22, target_profile)],
    )
    assert DetachedChromeLauncher.find_profile_process(target_profile) == 22


@pytest.mark.asyncio
async def test_xhs_profile_sync_updates_cookie_and_nickname(monkeypatch, tmp_path: Path) -> None:
    class FakeAccountManager:
        def __init__(self) -> None:
            self.updated_cookie = None
            self.updated_nickname = None
            self.status = None

        async def ensure_account_has_profile_folder(self, account_id: int) -> bool:
            return True

        async def get_account_by_id(self, account_id: int):
            return {
                "id": account_id,
                "platform": "xiaohongshu",
                "platform_username": "old_name",
                "profile_folder_name": "profile_abc",
                "login_status": "offline",
            }

        async def update_cookie(self, account_id: int, cookie_data):
            self.updated_cookie = (account_id, cookie_data)
            return True

        async def update_platform_username(self, account_id: int, platform_username: str):
            self.updated_nickname = (account_id, platform_username)
            return True

        async def update_account_login_status(self, account_id: int, status: str, **kwargs):
            self.status = (account_id, status)
            return True

    class FakeCookieReader:
        def read_cookie_dict(self, user_data_dir, *, domains):
            return {"access-token-creator.xiaohongshu.com": "token"}

    class FakeIdentityReader:
        def read_identity(self, user_data_dir):
            return XhsProfileIdentity(nickname="new_name", user_id="9402628224")

    monkeypatch.setattr(
        "src.services.account.xhs_profile_sync_service.DetachedChromeLauncher.get_user_data_dir",
        lambda **kwargs: tmp_path,
    )
    monkeypatch.setattr(
        "src.services.account.xhs_profile_sync_service.DetachedChromeLauncher.is_profile_in_use",
        lambda _path: False,
    )

    manager = FakeAccountManager()
    result = await XhsProfileSyncService(
        manager,
        cookie_reader=FakeCookieReader(),
        identity_reader=FakeIdentityReader(),
    ).sync_account(7)

    assert result.success is True
    assert result.status == "online"
    assert result.nickname == "new_name"
    assert manager.updated_cookie == (
        7,
        {"access-token-creator.xiaohongshu.com": "token"},
    )
    assert manager.updated_nickname == (7, "new_name")


@pytest.mark.asyncio
async def test_xhs_profile_sync_uses_local_storage_nickname_when_http_has_none(
    monkeypatch, tmp_path: Path
) -> None:
    class FakeAccountManager:
        def __init__(self) -> None:
            self.updated_cookie = None
            self.updated_nickname = None

        async def ensure_account_has_profile_folder(self, account_id: int) -> bool:
            return True

        async def get_account_by_id(self, account_id: int):
            return {
                "id": account_id,
                "platform": "xiaohongshu",
                "platform_username": "待登录",
                "profile_folder_name": "profile_abc",
                "login_status": "offline",
            }

        async def update_cookie(self, account_id: int, cookie_data):
            self.updated_cookie = (account_id, cookie_data)
            return True

        async def update_platform_username(self, account_id: int, platform_username: str):
            self.updated_nickname = (account_id, platform_username)
            return True

        async def update_account_login_status(self, account_id: int, status: str, **kwargs):
            return True

    class FakeCookieReader:
        def read_cookie_dict(self, user_data_dir, *, domains):
            return {"access-token-creator.xiaohongshu.com": "token"}

    class FakeIdentityReader:
        def read_identity(self, user_data_dir):
            return XhsProfileIdentity(nickname="真实昵称", user_id="9402628224")

    monkeypatch.setattr(
        "src.services.account.xhs_profile_sync_service.DetachedChromeLauncher.get_user_data_dir",
        lambda **kwargs: tmp_path,
    )
    monkeypatch.setattr(
        "src.services.account.xhs_profile_sync_service.DetachedChromeLauncher.is_profile_in_use",
        lambda _path: False,
    )

    manager = FakeAccountManager()
    result = await XhsProfileSyncService(
        manager,
        cookie_reader=FakeCookieReader(),
        identity_reader=FakeIdentityReader(),
    ).sync_account(9)

    assert result.success is True
    assert result.nickname == "真实昵称"
    assert manager.updated_nickname == (9, "真实昵称")


@pytest.mark.asyncio
async def test_xhs_profile_sync_does_not_write_generated_fallback_nickname(
    monkeypatch, tmp_path: Path
) -> None:
    class FakeAccountManager:
        def __init__(self) -> None:
            self.updated_nickname = None

        async def ensure_account_has_profile_folder(self, account_id: int) -> bool:
            return True

        async def get_account_by_id(self, account_id: int):
            return {
                "id": account_id,
                "platform": "xiaohongshu",
                "platform_username": "待登录",
                "profile_folder_name": "profile_abc",
                "login_status": "offline",
            }

        async def update_cookie(self, account_id: int, cookie_data):
            return True

        async def update_platform_username(self, account_id: int, platform_username: str):
            self.updated_nickname = (account_id, platform_username)
            return True

        async def update_account_login_status(self, account_id: int, status: str, **kwargs):
            return True

    class FakeCookieReader:
        def read_cookie_dict(self, user_data_dir, *, domains):
            return {"access-token-creator.xiaohongshu.com": "token"}

    class EmptyIdentityReader:
        def read_identity(self, user_data_dir):
            return XhsProfileIdentity()

    monkeypatch.setattr(
        "src.services.account.xhs_profile_sync_service.DetachedChromeLauncher.get_user_data_dir",
        lambda **kwargs: tmp_path,
    )
    monkeypatch.setattr(
        "src.services.account.xhs_profile_sync_service.DetachedChromeLauncher.is_profile_in_use",
        lambda _path: False,
    )

    manager = FakeAccountManager()
    result = await XhsProfileSyncService(
        manager,
        cookie_reader=FakeCookieReader(),
        identity_reader=EmptyIdentityReader(),
    ).sync_account(10)

    assert result.success is True
    assert result.nickname is None
    assert manager.updated_nickname is None


@pytest.mark.asyncio
async def test_xhs_profile_sync_marks_offline_when_session_cookie_missing(monkeypatch, tmp_path: Path) -> None:
    class FakeAccountManager:
        def __init__(self) -> None:
            self.updated_cookie = None
            self.status = None

        async def ensure_account_has_profile_folder(self, account_id: int) -> bool:
            return True

        async def get_account_by_id(self, account_id: int):
            return {
                "id": account_id,
                "platform": "xiaohongshu",
                "platform_username": "old_name",
                "profile_folder_name": "profile_abc",
                "login_status": "online",
            }

        async def update_cookie(self, account_id: int, cookie_data):
            self.updated_cookie = (account_id, cookie_data)
            return True

        async def update_account_login_status(self, account_id: int, status: str, **kwargs):
            self.status = (account_id, status)
            return True

    class FakeCookieReader:
        def read_cookie_dict(self, user_data_dir, *, domains):
            return {"a1": "tracking-cookie"}

    monkeypatch.setattr(
        "src.services.account.xhs_profile_sync_service.DetachedChromeLauncher.get_user_data_dir",
        lambda **kwargs: tmp_path,
    )
    monkeypatch.setattr(
        "src.services.account.xhs_profile_sync_service.DetachedChromeLauncher.is_profile_in_use",
        lambda _path: False,
    )

    manager = FakeAccountManager()
    result = await XhsProfileSyncService(manager, cookie_reader=FakeCookieReader()).sync_account(8)

    assert result.success is False
    assert result.status == "offline"
    assert result.error == "未读取到小红书创作者平台关键登录 Cookie，请确认已在普通 Chrome 中完成登录"
    assert manager.status == (8, "offline")
    assert manager.updated_cookie is None


def test_xhs_profile_identity_reader_extracts_nickname_from_local_storage(tmp_path: Path) -> None:
    storage_dir = tmp_path / "Default" / "Local Storage" / "leveldb"
    storage_dir.mkdir(parents=True)
    (storage_dir / "000003.log").write_text(
        'https://creator.xiaohongshu.com\x00USER_INFO{"nickname":"真实昵称","userId":"9402628224"}',
        encoding="utf-8",
    )

    identity = XhsProfileIdentityReader().read_identity(tmp_path)

    assert identity.nickname == "真实昵称"
    assert identity.user_id == "9402628224"


@pytest.mark.asyncio
async def test_account_verifier_uses_local_xhs_sync_without_http(monkeypatch) -> None:
    class FakeAccountManager:
        def __init__(self) -> None:
            self.status_updates = []

        async def get_account_for_operation(self, account_id: int):
            return {
                "id": account_id,
                "platform": "xiaohongshu",
                "platform_username": "待登录",
                "profile_folder_name": "profile_abc",
                "login_status": "offline",
            }

        async def load_account_cookie(self, account_id: int, *, merge_storage_state: bool = False):
            return {"access-token-creator.xiaohongshu.com": "token"}

        async def update_account_login_status(self, account_id: int, status: str, **kwargs):
            self.status_updates.append((account_id, status, kwargs))
            return True

    class FakeXhsProfileSyncService:
        def __init__(self, account_manager) -> None:
            self.account_manager = account_manager

        async def sync_account(self, account_id: int):
            from src.services.account.xhs_profile_sync_service import XhsProfileSyncResult

            return XhsProfileSyncResult(
                account_id=account_id,
                success=True,
                status="online",
                nickname=None,
            )

    http_called = False

    async def fake_verify_login_status(**kwargs):
        nonlocal http_called
        http_called = True
        raise AssertionError("小红书刷新登录状态不应调用 HTTP 验证")

    monkeypatch.setattr(
        "src.services.account.xhs_profile_sync_service.XhsProfileSyncService",
        FakeXhsProfileSyncService,
    )
    monkeypatch.setattr(
        "src.services.account.login_status_verifier.verify_login_status",
        fake_verify_login_status,
    )
    monkeypatch.setattr("src.services.account.account_verifier.random.uniform", lambda *_args: 0)

    manager = FakeAccountManager()
    result = await AccountVerifier(manager).verify_accounts_batch(
        [{"id": 26, "platform": "xiaohongshu", "platform_username": "待登录"}]
    )

    assert http_called is False
    assert result[26]["method"] == "xhs_profile_sync"
    assert result[26]["is_logged_in"] is True
    assert manager.status_updates[-1][1] == "online"
