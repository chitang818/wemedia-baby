from __future__ import annotations

import os
from pathlib import Path

from src.services.material.media_library_stats_service import build_media_library_stats
from src.services.material.media_library_stats_service import (
    build_account_video_stats,
    build_account_image_stats,
    _dedupe_paths,
)
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


def test_dedupe_paths_keeps_unique_order(tmp_path: Path) -> None:
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    a.write_text("1")
    b.write_text("2")
    out = _dedupe_paths([a, a, b, a])
    assert len(out) == 2
    assert out[0] == a and out[1] == b

