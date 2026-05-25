"""debug/screenshots 超期 png 清理"""

from __future__ import annotations

import os
import time

import pytest

from src.infrastructure.common.path_manager import PathManager
from src.utils.debug_screenshots_cleanup import (
    cleanup_debug_artifacts_older_than,
    cleanup_debug_screenshots_older_than,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def reset_path_manager():
    PathManager._app_data_dir = None
    yield
    PathManager._app_data_dir = None


def test_cleanup_removes_old_png(tmp_path):
    PathManager._app_data_dir = tmp_path
    old_dir = PathManager.get_debug_screenshots_dir("douyin")
    old_file = old_dir / "old.png"
    old_file.write_bytes(b"x")
    old_time = time.time() - 10 * 86400
    os.utime(old_file, (old_time, old_time))

    new_file = old_dir / "new.png"
    new_file.write_bytes(b"y")

    n = cleanup_debug_screenshots_older_than(days=7)
    assert n == 1
    assert not old_file.exists()
    assert new_file.exists()


def test_cleanup_no_root_returns_zero(tmp_path):
    PathManager._app_data_dir = tmp_path
    n = cleanup_debug_screenshots_older_than(days=7)
    assert n == 0


def test_cleanup_removes_old_diagnostic_files(tmp_path):
    PathManager._app_data_dir = tmp_path
    bundle_dir = PathManager.get_debug_diagnostics_dir("douyin") / "20260525" / "old_bundle"
    bundle_dir.mkdir(parents=True)
    old_file = bundle_dir / "metadata.json"
    old_file.write_text("{}", encoding="utf-8")
    old_time = time.time() - 10 * 86400
    os.utime(old_file, (old_time, old_time))

    new_file = PathManager.get_debug_diagnostics_dir("douyin") / "20260525" / "new.json"
    new_file.write_text("{}", encoding="utf-8")

    n = cleanup_debug_artifacts_older_than(days=7)

    assert n == 1
    assert not old_file.exists()
    assert new_file.exists()
