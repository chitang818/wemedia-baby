"""媒体库分配算法单元测试。"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.common import media_library_assign as mla
from src.infrastructure.common.material_library_manager import MaterialLibraryManager


def _make_media_root(tmp: Path) -> Path:
    root = tmp / MaterialLibraryManager.ROOT_FOLDER_NAME
    (root / MaterialLibraryManager.VIDEO_FOLDER_NAME).mkdir(parents=True)
    (root / MaterialLibraryManager.IMAGE_FOLDER_NAME).mkdir(parents=True)
    (root / MaterialLibraryManager.ACCOUNT_LIBRARY_FOLDER_NAME).mkdir(parents=True)
    return root


def test_move_sources_collision_and_skip_same(tmp_path: Path) -> None:
    target = tmp_path / "dest"
    target.mkdir()
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_text("1")
    b.write_text("2")
    (target / "b.mp4").write_text("old")

    n = mla.move_sources_to_assign_target([a, b], target, skip_if_already_in_target=True)
    assert n == 2
    assert (target / "a.mp4").read_text() == "1"
    assert (target / "b.mp4").read_text() == "old"
    assert (target / "b (1).mp4").read_text() == "2"

    # 已在目标路径：跳过
    c = target / "c.mp4"
    c.write_text("3")
    n2 = mla.move_sources_to_assign_target([c], target, skip_if_already_in_target=True)
    assert n2 == 0


def test_scan_video_library_entries(tmp_path: Path) -> None:
    root = _make_media_root(tmp_path)
    (root / MaterialLibraryManager.VIDEO_FOLDER_NAME / "x.mp4").write_text("x")

    acc = root / MaterialLibraryManager.ACCOUNT_LIBRARY_FOLDER_NAME / "抖音_测试号"
    unpublished = (
        acc / MaterialLibraryManager.ACCOUNT_MEDIA_VIDEO_NAME / MaterialLibraryManager.UNPUBLISHED_NAME
    )
    unpublished.mkdir(parents=True)
    (unpublished / "y.mov").write_text("y")

    entries, err = mla.scan_video_library_entries(root, {".mp4", ".mov"})
    assert err is None
    paths = {e.path.name for e in entries}
    assert paths == {"x.mp4", "y.mov"}
    owners = {e.path.name: e.owner_label for e in entries}
    assert owners["x.mp4"] == mla.UNASSIGNED_OWNER_LABEL
    assert owners["y.mov"] == "抖音_测试号"


def test_resolve_assign_target_account_video(tmp_path: Path) -> None:
    root = _make_media_root(tmp_path)
    account = {"platform": "douyin", "platform_username": "昵称A"}
    at = mla.resolve_assign_target(
        root, media_kind="video", target_type="account", target_data=account
    )
    expected = MaterialLibraryManager.resolve_account_video_unpublished_dir(root, account)
    assert at.directory == expected
    assert "昵称A" in at.label


def test_resolve_assign_target_group_image(tmp_path: Path) -> None:
    root = _make_media_root(tmp_path)
    at = mla.resolve_assign_target(
        root,
        media_kind="image",
        target_type="group",
        target_data={"group_name": "我的组"},
    )
    expected = MaterialLibraryManager.group_image_unpublished_dir(root, "我的组")
    assert at.directory == expected
    assert "我的组" in at.label


def test_account_library_owner_folder_matches_fuzzy_nickname() -> None:
    acc = {"platform": "wechat_video", "platform_username": "爱种地的90后"}
    assert MaterialLibraryManager.account_library_owner_folder_matches_account(
        "视频号_爱种地的90后小伙", acc
    )


def test_account_library_owner_folder_rejects_group_folder() -> None:
    acc = {"platform": "wechat_video", "platform_username": "x"}
    assert not MaterialLibraryManager.account_library_owner_folder_matches_account(
        "账号组_某组", acc
    )


def test_resolve_assign_target_account_video_prefers_fuzzy_existing_dir(tmp_path: Path) -> None:
    root = _make_media_root(tmp_path)
    account = {"platform": "douyin", "platform_username": "昵称A"}
    lib = root / MaterialLibraryManager.ACCOUNT_LIBRARY_FOLDER_NAME
    fuzzy = lib / "抖音_昵称A手写后缀"
    unpublished = (
        fuzzy
        / MaterialLibraryManager.ACCOUNT_MEDIA_VIDEO_NAME
        / MaterialLibraryManager.UNPUBLISHED_NAME
    )
    unpublished.mkdir(parents=True)

    at = mla.resolve_assign_target(
        root, media_kind="video", target_type="account", target_data=account
    )
    assert at.directory == unpublished
