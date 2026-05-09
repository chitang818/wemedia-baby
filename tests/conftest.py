"""
全局测试配置与 Fixture
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent.parent))


# ──────────────────────────────────────────────
# 基础数据 Fixture
# ──────────────────────────────────────────────

@pytest.fixture
def sample_account():
    """标准测试账号字典（匹配 AccountRepositoryAsync._to_dict 输出格式）"""
    return {
        "id": 1,
        "user_id": 1,
        "platform": "douyin",
        "account_name": "测试账号",
        "platform_username": "测试账号",
        "cookie_path": "",
        "login_status": "offline",
        "last_login_at": None,
        "profile_folder_name": "profile_test_001",
        "group_id": None,
        "created_at": None,
    }


@pytest.fixture
def sample_cookies():
    """标准测试 Cookie 数据"""
    return {
        "sessionid": "test_session_id",
        "sessionid_ss": "test_session_ss",
        "sid_tt": "test_sid_tt",
    }


# ──────────────────────────────────────────────
# 路径 Fixture
# ──────────────────────────────────────────────

@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """临时 SQLite 数据库路径（字符串）"""
    return str(tmp_path / "test.db")


@pytest.fixture
def tmp_app_data_dir(tmp_path: Path, monkeypatch) -> Path:
    """隔离的 App 数据目录，覆盖 PathManager._app_data_dir，避免污染真实用户数据。"""
    from src.infrastructure.common.path_manager import PathManager
    app_dir = tmp_path / "WeMediaBaby"
    app_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PathManager, "_app_data_dir", app_dir)
    monkeypatch.setattr(PathManager, "_resource_dir", None)
    return app_dir


# ──────────────────────────────────────────────
# 服务 Mock Fixture
# ──────────────────────────────────────────────

@pytest.fixture
def mock_event_bus():
    """Mock EventBus，记录 publish 调用"""
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus


@pytest.fixture
def mock_repo():
    """通用 Mock 仓储，提供常见异步方法"""
    repo = MagicMock()
    repo.create = AsyncMock(return_value={"id": 1})
    repo.get_by_id = AsyncMock(return_value=None)
    repo.update = AsyncMock(return_value=True)
    repo.delete = AsyncMock(return_value=True)
    repo.list_all = AsyncMock(return_value=[])
    return repo
