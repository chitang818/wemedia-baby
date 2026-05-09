"""bundled_config：内置 JSON 路径与缓存。"""

import pytest

from src.infrastructure.common import path_manager as path_manager_mod
from src.infrastructure.common.bundled_config import (
    clear_bundled_json_cache,
    load_platform_bundle,
    read_bundled_json,
)


@pytest.fixture(autouse=True)
def _reset_path_manager_and_cache():
    path_manager_mod.PathManager._resource_dir = None
    clear_bundled_json_cache()
    yield
    path_manager_mod.PathManager._resource_dir = None
    clear_bundled_json_cache()


def test_read_bundled_json_missing_returns_empty(tmp_path):
    path_manager_mod.PathManager._resource_dir = tmp_path
    assert read_bundled_json("config/nope.json") == {}


def test_read_bundled_json_loads_and_cache_invalidates(tmp_path):
    path_manager_mod.PathManager._resource_dir = tmp_path
    rel = "config/platforms/x.json"
    p = tmp_path / rel
    p.parent.mkdir(parents=True)
    p.write_text('{"k": 1}', encoding="utf-8")
    assert read_bundled_json(rel) == {"k": 1}
    assert read_bundled_json(rel) == {"k": 1}
    p.write_text('{"k": 2}', encoding="utf-8")
    assert read_bundled_json(rel) == {"k": 2}


def test_read_bundled_json_invalid_returns_empty(tmp_path):
    path_manager_mod.PathManager._resource_dir = tmp_path
    rel = "config/bad.json"
    p = tmp_path / rel
    p.parent.mkdir(parents=True)
    p.write_text("not json", encoding="utf-8")
    assert read_bundled_json(rel) == {}


def test_read_bundled_json_non_object_returns_empty(tmp_path):
    path_manager_mod.PathManager._resource_dir = tmp_path
    rel = "config/list.json"
    p = tmp_path / rel
    p.parent.mkdir(parents=True)
    p.write_text("[1,2]", encoding="utf-8")
    assert read_bundled_json(rel) == {}


def test_load_platform_bundle_empty_id(tmp_path):
    path_manager_mod.PathManager._resource_dir = tmp_path
    assert load_platform_bundle("") == {}
    assert load_platform_bundle("  ") == {}


def test_load_platform_bundle_reads_platforms(tmp_path):
    path_manager_mod.PathManager._resource_dir = tmp_path
    p = tmp_path / "config" / "platforms" / "douyin.json"
    p.parent.mkdir(parents=True)
    p.write_text('{"platform_name": "douyin"}', encoding="utf-8")
    assert load_platform_bundle("douyin") == {"platform_name": "douyin"}
