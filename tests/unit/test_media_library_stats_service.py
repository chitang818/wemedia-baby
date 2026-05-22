from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from src.services.material.media_library_stats_service import build_media_library_stats
from src.services.material.media_library_stats_service import (
    MediaLibraryStatsService,
    build_account_video_stats,
    build_account_image_stats,
    _build_account_and_group_path_maps,
    _dedupe_paths,
    _build_scan_cache_fingerprint,
    _load_scan_cache_incremental_sync,
    _scan_cache_db_path,
    _scan_cache_file_path,
    _load_scan_cache_sync,
    _save_scan_cache_sync,
)
from src.infrastructure.common.media_library_assign import (
    ImageLibraryScanEntry,
    VideoLibraryScanEntry,
)
from src.infrastructure.common.material_library_manager import MaterialLibraryManager
from src.infrastructure.common.path_manager import PathManager
from src.services.material.media_usage_service import PendingMediaUsage


def test_build_media_library_stats_counts_global_and_by_owner() -> None:
    def _norm(p: str) -> str:
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))

    usage = PendingMediaUsage(
        used_video_files={_norm("D:/a/1.mp4")},
        used_image_folders={_norm("D:/img/f1")},
    )

    video_paths = [Path("D:/a/1.mp4"), Path("D:/a/2.mp4")]
    video_owners = ["未分配", "账号A"]

    image_folders = [Path("D:/img/f1"), Path("D:/img/f2"), Path("D:/img/f3")]
    image_owners = ["账号A", "账号A", "账号组-组1"]

    stats = build_media_library_stats(
        video_owner_labels=video_owners,
        video_paths=video_paths,
        image_owner_labels=image_owners,
        image_folder_paths=image_folders,
        usage=usage,
    )

    assert stats.error == ""

    # 全局汇总
    assert stats.video.counts.total == 2
    assert stats.video.counts.used == 1
    assert stats.video.counts.unused == 1

    assert stats.image.counts.total == 3
    assert stats.image.counts.used == 1
    assert stats.image.counts.unused == 2

    assert stats.all_media.total == 5
    assert stats.all_media.used == 2
    assert stats.all_media.unused == 3

    # 按归属汇总
    assert stats.video.by_owner["未分配"].total == 1
    assert stats.video.by_owner["未分配"].used == 1
    assert stats.video.by_owner["未分配"].unused == 0

    assert stats.video.by_owner["账号A"].total == 1
    assert stats.video.by_owner["账号A"].used == 0
    assert stats.video.by_owner["账号A"].unused == 1

    assert stats.image.by_owner["账号A"].total == 2
    assert stats.image.by_owner["账号A"].used == 1
    assert stats.image.by_owner["账号A"].unused == 1

    assert stats.image.by_owner["账号组-组1"].total == 1
    assert stats.image.by_owner["账号组-组1"].used == 0
    assert stats.image.by_owner["账号组-组1"].unused == 1


def test_build_account_video_stats_and_image_stats() -> None:
    def _norm(p: str) -> str:
        return os.path.normcase(os.path.normpath(os.path.abspath(p)))

    usage = PendingMediaUsage(
        used_video_files={_norm("D:/a/u1.mp4"), _norm("D:/b/u2.mp4")},
        used_image_folders={_norm("D:/img/f1")},
    )

    video_by_account = {
        1: [Path("D:/a/u1.mp4"), Path("D:/a/x.mp4")],
        2: [Path("D:/b/u2.mp4")],
        3: [],
    }
    out_v = build_account_video_stats(account_id_to_video_paths=video_by_account, usage=usage)
    assert out_v[1].total == 2 and out_v[1].used == 1 and out_v[1].unused == 1
    assert out_v[2].total == 1 and out_v[2].used == 1 and out_v[2].unused == 0
    assert out_v[3].total == 0 and out_v[3].used == 0 and out_v[3].unused == 0

    image_by_account = {
        1: [Path("D:/img/f1"), Path("D:/img/f2")],
        2: [Path("D:/img/f3")],
    }
    out_i = build_account_image_stats(account_id_to_image_folder_paths=image_by_account, usage=usage)
    assert out_i[1].total == 2 and out_i[1].used == 1 and out_i[1].unused == 1
    assert out_i[2].total == 1 and out_i[2].used == 0 and out_i[2].unused == 1

    # 账号组统计与账号统计复用同一聚合函数（输入 key 为 group_id 即可）
    group_video = {101: [Path("D:/a/u1.mp4"), Path("D:/a/x.mp4")]}
    out_gv = build_account_video_stats(account_id_to_video_paths=group_video, usage=usage)
    assert out_gv[101].total == 2 and out_gv[101].used == 1 and out_gv[101].unused == 1


def test_build_account_and_group_path_maps_uses_scan_entries(tmp_path: Path) -> None:
    account = {"id": 1, "platform": "douyin", "platform_username": "Alice"}
    group = {"id": 101, "group_name": "TeamA"}
    account_owner = MaterialLibraryManager.platform_account_folder_name("douyin", "Alice")
    group_owner = MaterialLibraryManager.owner_label_for_group_material_folder(
        MaterialLibraryManager.account_group_material_folder_name("TeamA")
    )

    account_video = tmp_path / "account.mp4"
    group_video = tmp_path / "group.mp4"
    account_image = tmp_path / "account-image"
    group_image = tmp_path / "group-image"
    unassigned_video = tmp_path / "public.mp4"

    video_by_account, image_by_account, video_by_group, image_by_group = _build_account_and_group_path_maps(
        root=tmp_path,
        accounts=[account],
        groups=[group],
        video_entries=[
            VideoLibraryScanEntry(account_video, account_owner, 10),
            VideoLibraryScanEntry(group_video, group_owner, 10),
            VideoLibraryScanEntry(unassigned_video, "未分配", 10),
        ],
        image_entries=[
            ImageLibraryScanEntry(account_image, account_owner, 10, image_count=1),
            ImageLibraryScanEntry(group_image, group_owner, 10, image_count=1),
        ],
        video_exts={".mp4"},
    )

    assert video_by_account[1] == [account_video]
    assert image_by_account[1] == [account_image]
    assert video_by_group[101] == [group_video]
    assert image_by_group[101] == [group_image]


def test_dedupe_paths_keeps_unique_order(tmp_path: Path) -> None:
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_text("1")
    b.write_text("2")
    out = _dedupe_paths([a, a, b, a])
    assert len(out) == 2
    assert out[0] == a and out[1] == b


def test_scan_cache_roundtrip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(PathManager, "get_cache_dir", classmethod(lambda cls: tmp_path))
    root = tmp_path / "library"
    (root / "视频库").mkdir(parents=True)
    (root / "图片库").mkdir(parents=True)
    video_exts = {".mp4", ".mov"}
    image_exts = {".jpg", ".png"}
    video_entries = [
        VideoLibraryScanEntry(
            path=root / "视频库" / "a.mp4",
            owner_label="未分配",
            size_bytes=10,
            mtime=1.0,
        )
    ]
    image_entries = [
        ImageLibraryScanEntry(
            path=root / "图片库" / "set1",
            owner_label="账号A",
            size_bytes=20,
            image_count=2,
            mtime=2.0,
        )
    ]

    _save_scan_cache_sync(
        root=root,
        video_exts=video_exts,
        image_exts=image_exts,
        video_entries=video_entries,
        image_entries=image_entries,
    )

    loaded = _load_scan_cache_sync(
        root=root,
        video_exts=video_exts,
        image_exts=image_exts,
        max_age_seconds=3600,
    )
    assert loaded is not None
    loaded_v, loaded_i = loaded
    assert loaded_v == video_entries
    assert loaded_i == image_entries
    assert _scan_cache_db_path().exists()


def test_scan_cache_loads_from_sqlite_when_json_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(PathManager, "get_cache_dir", classmethod(lambda cls: tmp_path))
    root = tmp_path / "library"
    (root / MaterialLibraryManager.VIDEO_FOLDER_NAME).mkdir(parents=True)
    (root / MaterialLibraryManager.IMAGE_FOLDER_NAME).mkdir(parents=True)
    video = root / MaterialLibraryManager.VIDEO_FOLDER_NAME / "a.mp4"
    video.write_text("x", encoding="utf-8")
    video_entries = [VideoLibraryScanEntry(video, "未分配", 1, mtime=1.0)]

    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=video_entries,
        image_entries=[],
    )
    _scan_cache_file_path().unlink()

    loaded = _load_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        max_age_seconds=3600,
    )
    assert loaded is not None
    loaded_v, loaded_i = loaded
    assert loaded_v == video_entries
    assert loaded_i == []


def test_scan_cache_sqlite_incremental_save_preserves_unchanged_bucket(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(PathManager, "get_cache_dir", classmethod(lambda cls: tmp_path))
    root = tmp_path / "library"
    video_dir = root / MaterialLibraryManager.VIDEO_FOLDER_NAME
    image_dir = root / MaterialLibraryManager.IMAGE_FOLDER_NAME
    account_dir = MaterialLibraryManager.account_library_root(root) / "douyin_Alice"
    account_video_dir = (
        account_dir
        / MaterialLibraryManager.ACCOUNT_MEDIA_VIDEO_NAME
        / MaterialLibraryManager.UNPUBLISHED_NAME
    )
    video_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)
    account_video_dir.mkdir(parents=True)

    public_video = video_dir / "public.mp4"
    account_video = account_video_dir / "account.mp4"
    public_video.write_text("public", encoding="utf-8")
    account_video.write_text("account", encoding="utf-8")
    public_entry = VideoLibraryScanEntry(public_video, "未分配", 6)
    account_owner = MaterialLibraryManager.owner_label_for_account_library_entry(account_dir.name)

    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=[public_entry],
        image_entries=[],
    )

    with sqlite3.connect(str(_scan_cache_db_path())) as conn:
        before_rowid = conn.execute(
            "SELECT rowid FROM scan_cache_entries WHERE kind = 'video' AND path = ?",
            (str(public_video),),
        ).fetchone()[0]

    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=[
            public_entry,
            VideoLibraryScanEntry(account_video, account_owner, 7),
        ],
        image_entries=[],
    )

    with sqlite3.connect(str(_scan_cache_db_path())) as conn:
        after_rowid = conn.execute(
            "SELECT rowid FROM scan_cache_entries WHERE kind = 'video' AND path = ?",
            (str(public_video),),
        ).fetchone()[0]
        paths = {
            row[0]
            for row in conn.execute(
                "SELECT path FROM scan_cache_entries WHERE kind = 'video'"
            )
        }

    assert after_rowid == before_rowid
    assert paths == {str(public_video), str(account_video)}


def test_scan_cache_sqlite_save_removes_stale_bucket(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(PathManager, "get_cache_dir", classmethod(lambda cls: tmp_path))
    root = tmp_path / "library"
    video_dir = root / MaterialLibraryManager.VIDEO_FOLDER_NAME
    image_dir = root / MaterialLibraryManager.IMAGE_FOLDER_NAME
    account_dir = MaterialLibraryManager.account_library_root(root) / "douyin_Alice"
    account_video_dir = (
        account_dir
        / MaterialLibraryManager.ACCOUNT_MEDIA_VIDEO_NAME
        / MaterialLibraryManager.UNPUBLISHED_NAME
    )
    video_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)
    account_video_dir.mkdir(parents=True)
    account_video = account_video_dir / "account.mp4"
    account_video.write_text("account", encoding="utf-8")
    account_owner = MaterialLibraryManager.owner_label_for_account_library_entry(account_dir.name)

    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=[VideoLibraryScanEntry(account_video, account_owner, 7)],
        image_entries=[],
    )
    shutil.rmtree(account_dir)
    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=[],
        image_entries=[],
    )

    with sqlite3.connect(str(_scan_cache_db_path())) as conn:
        stale_entries = conn.execute(
            "SELECT COUNT(*) FROM scan_cache_entries WHERE path = ?",
            (str(account_video),),
        ).fetchone()[0]
        account_buckets = conn.execute(
            "SELECT COUNT(*) FROM scan_cache_buckets WHERE path = ?",
            (str(account_video_dir),),
        ).fetchone()[0]

    assert stale_entries == 0
    assert account_buckets == 0


def test_scan_cache_targeted_invalidation_deletes_only_selected_bucket(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(PathManager, "get_cache_dir", classmethod(lambda cls: tmp_path))
    root = tmp_path / "library"
    video_dir = root / MaterialLibraryManager.VIDEO_FOLDER_NAME
    image_dir = root / MaterialLibraryManager.IMAGE_FOLDER_NAME
    video_dir.mkdir(parents=True)
    image_set = image_dir / "set1"
    image_set.mkdir(parents=True)
    public_video = video_dir / "public.mp4"
    image_file = image_set / "a.jpg"
    public_video.write_text("public", encoding="utf-8")
    image_file.write_text("image", encoding="utf-8")

    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=[VideoLibraryScanEntry(public_video, "未分配", 6)],
        image_entries=[ImageLibraryScanEntry(image_set, "未分配", 5, image_count=1)],
    )

    MediaLibraryStatsService().invalidate_bucket_paths([video_dir], kinds=("video",))

    with sqlite3.connect(str(_scan_cache_db_path())) as conn:
        video_count = conn.execute(
            "SELECT COUNT(*) FROM scan_cache_entries WHERE kind = 'video'"
        ).fetchone()[0]
        image_count = conn.execute(
            "SELECT COUNT(*) FROM scan_cache_entries WHERE kind = 'image'"
        ).fetchone()[0]

    assert video_count == 0
    assert image_count == 1
    assert not _scan_cache_file_path().exists()


def test_scan_cache_falls_back_to_json_when_sqlite_is_corrupt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(PathManager, "get_cache_dir", classmethod(lambda cls: tmp_path))
    root = tmp_path / "library"
    video_dir = root / MaterialLibraryManager.VIDEO_FOLDER_NAME
    image_dir = root / MaterialLibraryManager.IMAGE_FOLDER_NAME
    video_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)
    video = video_dir / "a.mp4"
    video.write_text("x", encoding="utf-8")
    video_entries = [VideoLibraryScanEntry(video, "未分配", 1)]

    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=video_entries,
        image_entries=[],
    )
    _scan_cache_db_path().write_bytes(b"not a sqlite database")

    loaded = _load_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        max_age_seconds=3600,
    )

    assert loaded is not None
    assert loaded[0] == video_entries
    assert loaded[1] == []


def test_scan_cache_miss_when_extensions_change(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(PathManager, "get_cache_dir", classmethod(lambda cls: tmp_path))
    root = tmp_path / "library"
    (root / "视频库").mkdir(parents=True)
    (root / "图片库").mkdir(parents=True)
    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=[],
        image_entries=[],
    )

    loaded = _load_scan_cache_sync(
        root=root,
        video_exts={".mp4", ".mov"},
        image_exts={".jpg"},
        max_age_seconds=3600,
    )
    assert loaded is None


def test_scan_cache_miss_when_directory_fingerprint_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(PathManager, "get_cache_dir", classmethod(lambda cls: tmp_path))
    root = tmp_path / "library"
    video_dir = root / "视频库"
    image_dir = root / "图片库"
    video_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)

    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=[],
        image_entries=[],
    )
    assert _load_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        max_age_seconds=3600,
    ) is not None

    (video_dir / "new.mp4").write_text("x", encoding="utf-8")

    assert _load_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        max_age_seconds=3600,
    ) is None


def test_scan_cache_fingerprint_tracks_nested_material_dirs(tmp_path: Path) -> None:
    root = tmp_path / "library"
    nested = root / "账号库" / "账号A" / "视频" / "未发布"
    nested.mkdir(parents=True)
    before = _build_scan_cache_fingerprint(root)

    (nested / "a.mp4").write_text("x", encoding="utf-8")
    after = _build_scan_cache_fingerprint(root)

    assert before != after


def test_scan_cache_fingerprint_tracks_file_content_metadata(tmp_path: Path) -> None:
    root = tmp_path / "library"
    video_dir = root / MaterialLibraryManager.VIDEO_FOLDER_NAME
    video_dir.mkdir(parents=True)
    video_file = video_dir / "a.mp4"
    video_file.write_text("x", encoding="utf-8")
    before = _build_scan_cache_fingerprint(root)

    video_file.write_text("changed-content", encoding="utf-8")
    after = _build_scan_cache_fingerprint(root)

    assert before != after


def test_scan_cache_incremental_reuses_unchanged_buckets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(PathManager, "get_cache_dir", classmethod(lambda cls: tmp_path))
    root = tmp_path / "library"
    video_dir = root / MaterialLibraryManager.VIDEO_FOLDER_NAME
    image_dir = root / MaterialLibraryManager.IMAGE_FOLDER_NAME
    account_dir = MaterialLibraryManager.account_library_root(root) / "douyin_Alice"
    account_video_dir = (
        account_dir
        / MaterialLibraryManager.ACCOUNT_MEDIA_VIDEO_NAME
        / MaterialLibraryManager.UNPUBLISHED_NAME
    )
    account_image_dir = (
        account_dir
        / MaterialLibraryManager.ACCOUNT_MEDIA_IMAGE_NAME
        / MaterialLibraryManager.UNPUBLISHED_NAME
    )
    video_dir.mkdir(parents=True)
    image_dir.mkdir(parents=True)
    account_video_dir.mkdir(parents=True)
    account_image_dir.mkdir(parents=True)

    public_video = video_dir / "public.mp4"
    old_account_video = account_video_dir / "old.mp4"
    public_video.write_text("public", encoding="utf-8")
    old_account_video.write_text("old", encoding="utf-8")

    owner = MaterialLibraryManager.owner_label_for_account_library_entry(account_dir.name)
    _save_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        video_entries=[
            VideoLibraryScanEntry(public_video, "未分配", 6),
            VideoLibraryScanEntry(old_account_video, owner, 3),
        ],
        image_entries=[],
    )

    new_account_video = account_video_dir / "new.mp4"
    new_account_video.write_text("new", encoding="utf-8")

    assert _load_scan_cache_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        max_age_seconds=3600,
    ) is None

    loaded = _load_scan_cache_incremental_sync(
        root=root,
        video_exts={".mp4"},
        image_exts={".jpg"},
        max_age_seconds=3600,
    )
    assert loaded is not None
    video_entries, image_entries, err = loaded
    assert err == ""
    assert image_entries == []
    assert {e.path for e in video_entries} == {public_video, old_account_video, new_account_video}

