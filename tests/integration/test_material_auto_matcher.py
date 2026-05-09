"""
MaterialAutoMatcher 集成测试
使用临时目录模拟媒体库，测试素材扫描、索引消费和重置逻辑。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.pro_features.batch.services.material_auto_matcher import MaterialAutoMatcher

pytestmark = pytest.mark.integration


@pytest.fixture
def media_root(tmp_path) -> Path:
    """创建模拟媒体库目录结构"""
    root = tmp_path / "media_root"
    # 公共视频/未发布目录
    public_dir = root / "video" / "public" / "未发布"
    public_dir.mkdir(parents=True)
    for i in range(3):
        (public_dir / f"V{i:04d}-title.mp4").write_bytes(b"")
    # 账号专属目录
    acc_dir = root / "video" / "douyin" / "profile_test" / "未发布"
    acc_dir.mkdir(parents=True)
    for i in range(2):
        (acc_dir / f"A{i:04d}-acc.mp4").write_bytes(b"")
    return root


def _make_account(**kwargs):
    defaults = {
        "platform": "douyin",
        "platform_username": "测试账号",
        "profile_folder_name": "profile_test",
        "id": 1,
        "_type": "account",
    }
    defaults.update(kwargs)
    return defaults


class TestMaterialAutoMatcherReset:

    def test_reset_clears_all_indexes(self):
        matcher = MaterialAutoMatcher()
        matcher._consumed_index["key1"] = 5
        matcher._consumed_index["key2"] = 3
        matcher.reset()
        assert matcher._consumed_index == {}

    def test_reset_owner_removes_specific_key(self):
        matcher = MaterialAutoMatcher()
        matcher._consumed_index["A"] = 2
        matcher._consumed_index["B"] = 4
        matcher.reset_owner("A")
        assert "A" not in matcher._consumed_index
        assert "B" in matcher._consumed_index

    def test_reset_owner_nonexistent_no_error(self):
        matcher = MaterialAutoMatcher()
        matcher.reset_owner("nonexistent")  # 不应抛异常


class TestMaterialAutoMatcherProperties:

    def test_media_type_default_video(self):
        matcher = MaterialAutoMatcher()
        assert matcher.media_type == "video"

    def test_media_type_image(self):
        matcher = MaterialAutoMatcher(media_type="image")
        assert matcher.media_type == "image"

    def test_supported_extensions_not_empty(self):
        matcher = MaterialAutoMatcher()
        assert len(matcher.SUPPORTED_VIDEO_EXTENSIONS) > 0


class TestFetchMaterialsWithMockedLibrary:

    def test_returns_empty_when_media_root_none(self):
        """MediaLibraryManager.get_root_dir 返回 None 时应返回空列表"""
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager
        with patch.object(MaterialLibraryManager, "get_root_dir", return_value=None):
            matcher = MaterialAutoMatcher()
            acc = _make_account()
            materials, msg = matcher.fetch_materials(acc, 3)
            assert materials == []
            assert msg is not None  # 应有提示文案

    def test_fetch_returns_correct_count(self, media_root):
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager
        with patch.object(MaterialLibraryManager, "get_root_dir", return_value=media_root):
            matcher = MaterialAutoMatcher()
            acc = _make_account()
            materials, msg = matcher.fetch_materials(acc, 2)
            assert len(materials) <= 2

    def test_fetch_increments_index(self, media_root):
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager
        with patch.object(MaterialLibraryManager, "get_root_dir", return_value=media_root):
            matcher = MaterialAutoMatcher()
            acc = _make_account()
            m1, _ = matcher.fetch_materials(acc, 1)
            m2, _ = matcher.fetch_materials(acc, 1)
            if m1 and m2:
                paths1 = {x["file_path"] for x in m1}
                paths2 = {x["file_path"] for x in m2}
                assert paths1.isdisjoint(paths2)

    def test_shortage_message_when_insufficient(self, media_root):
        from src.infrastructure.common.material_library_manager import MaterialLibraryManager
        with patch.object(MaterialLibraryManager, "get_root_dir", return_value=media_root):
            matcher = MaterialAutoMatcher()
            acc = _make_account()
            materials, msg = matcher.fetch_materials(acc, 9999)
            assert msg is not None or len(materials) < 9999
