import os

from src.infrastructure.common.path_utils import normalize_media_path


def test_normalize_media_path_windows_drive_case() -> None:
    """Windows 下盘符大小写不同应归一化为同一路径（避免集合比较漏过滤）。"""
    p1 = r"d:\tmp\Video.mp4"
    p2 = r"D:\tmp\Video.mp4"
    assert normalize_media_path(p1) == normalize_media_path(p2)


def test_normalize_media_path_is_stable() -> None:
    p = os.path.join("tmp", "a", "..", "b", "v.mp4")
    assert normalize_media_path(p) == normalize_media_path(normalize_media_path(p))

