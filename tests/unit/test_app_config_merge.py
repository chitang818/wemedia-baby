"""app_config 深度合并写入逻辑（内存侧）。"""

from __future__ import annotations

import copy

import pytest

from src.infrastructure.common.config.app_config_merge import _deep_merge_inplace

pytestmark = pytest.mark.unit


def test_deep_merge_inplace_nested_dicts():
    base = {"batch_publish": {"auto_match": {"video_library": False}, "declare_original": True}}
    patch = {"batch_publish": {"auto_match": {"video_library": True}}}
    out = copy.deepcopy(base)
    _deep_merge_inplace(out, patch)
    assert out["batch_publish"]["declare_original"] is True
    assert out["batch_publish"]["auto_match"]["video_library"] is True


def test_deep_merge_inplace_replaces_non_dict_values():
    base = {"publish_list": {"speed_index": 1}}
    patch = {"publish_list": {"speed_index": 2}}
    out = copy.deepcopy(base)
    _deep_merge_inplace(out, patch)
    assert out["publish_list"]["speed_index"] == 2
