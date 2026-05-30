"""
PostPublishFileHandler 文件夹整体移动功能单元测试
覆盖：
- 图片来源为文件夹时整体移动而非逐文件移动
- 文件夹移动后数据库路径（含 __FOLDER__: 标记）正确更新
- 文件夹不存在时优雅处理
- 普通散图路径行为不变（回归）
- 删除操作时整体删除文件夹

注意：
1. 使用 tempfile.TemporaryDirectory() 替代 tmp_path fixture，
   避免 Windows 下 .pytest-tmp 权限问题导致 setup ERROR。
2. MaterialLibraryManager 在 _execute_file_action 内部通过局部 import 引入，
   patch 目标路径为 src.infrastructure.common.material_library_manager，
   而非 post_publish_file_handler 模块属性。
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.common.post_publish_file_handler import (
    FileGroupInfo,
    PostPublishFileHandler,
)

# MaterialLibraryManager 的正确 patch 路径（局部 import 场景）
_MLM_GET_ROOT = "src.infrastructure.common.material_library_manager.MaterialLibraryManager.get_root_dir"
_HANDLER_RESOLVE = "src.infrastructure.common.post_publish_file_handler.PostPublishFileHandler._resolve_target_dir"


# ──────────────────────────────────────────────────────────────────────────────
# 辅助工具
# ──────────────────────────────────────────────────────────────────────────────

def _make_user_log() -> MagicMock:
    """返回带 info/warning/debug 的 mock Logger。"""
    log = MagicMock()
    log.info = MagicMock()
    log.warning = MagicMock()
    log.debug = MagicMock()
    return log


def _info_for_folder(
    src_folder: str,
    image_paths: list,
    *,
    platform: str = "douyin",
    platform_username: str = "测试账号",
) -> FileGroupInfo:
    """构造一个图片文件夹来源的 FileGroupInfo。"""
    return FileGroupInfo(
        file_paths=image_paths,
        file_type="image",
        target_type="account",
        platform=platform,
        platform_username=platform_username,
        source_folder=src_folder,
    )


def _info_for_images(image_paths: list) -> FileGroupInfo:
    """构造普通散图（无文件夹来源）的 FileGroupInfo。"""
    return FileGroupInfo(
        file_paths=image_paths,
        file_type="image",
        target_type="account",
        platform="douyin",
        platform_username="测试账号",
        source_folder="",
    )


# ──────────────────────────────────────────────────────────────────────────────
# _extract_folder_path 测试
# ──────────────────────────────────────────────────────────────────────────────

class TestExtractFolderPath:
    def test_extracts_folder_from_composite_path(self):
        folder = "D:/media/pack"
        img1 = "D:/media/pack/a.jpg"
        img2 = "D:/media/pack/b.png"
        fp = f"__FOLDER__:{folder},{img1},{img2}"
        assert PostPublishFileHandler._extract_folder_path(fp) == folder

    def test_returns_empty_for_plain_images(self):
        img1 = "D:/media/a.jpg"
        img2 = "D:/media/b.png"
        fp = f"{img1},{img2}"
        assert PostPublishFileHandler._extract_folder_path(fp) == ""

    def test_returns_empty_for_video(self):
        video = "D:/media/video.mp4"
        assert PostPublishFileHandler._extract_folder_path(video) == ""

    def test_handles_folder_only_marker(self):
        folder = "D:/media/pack"
        fp = f"__FOLDER__:{folder}"
        assert PostPublishFileHandler._extract_folder_path(fp) == folder

    def test_strips_extra_spaces(self):
        folder = "D:/media/pack"
        fp = f"__FOLDER__: {folder} "
        extracted = PostPublishFileHandler._extract_folder_path(fp)
        assert extracted == folder


# ──────────────────────────────────────────────────────────────────────────────
# _execute_file_action - 文件夹整体移动
# ──────────────────────────────────────────────────────────────────────────────

class TestExecuteFileActionFolderMove:
    """图片来源为文件夹时，整体移动文件夹而非逐图移动。"""

    @pytest.mark.asyncio
    async def test_folder_move_moves_whole_folder(self):
        """发布后将整个文件夹移动至目标已发布目录。"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            # 准备源文件夹及图片
            src_folder = td / "素材包"
            src_folder.mkdir()
            img1 = src_folder / "a.jpg"
            img2 = src_folder / "b.png"
            img1.write_bytes(b"img1")
            img2.write_bytes(b"img2")

            target_dir = td / "已发布" / "20260529"
            target_dir.mkdir(parents=True)

            info = _info_for_folder(
                str(src_folder),
                [str(img1), str(img2)],
            )

            with (
                patch(_MLM_GET_ROOT, return_value=td),
                patch(_HANDLER_RESOLVE, return_value=target_dir),
            ):
                user_log = _make_user_log()
                path_results = await PostPublishFileHandler._execute_file_action(
                    info, "move", user_log
                )

            # 整个文件夹应已被移走
            assert not src_folder.exists(), "源文件夹应已被移走"
            # 目标目录下应存在该文件夹
            dst_folder = target_dir / "素材包"
            assert dst_folder.exists() and dst_folder.is_dir()

            # path_results 应包含 __FOLDER__: 键 → 新文件夹路径
            folder_key = f"__FOLDER__:{src_folder}"
            assert folder_key in path_results
            assert path_results[folder_key] == f"__FOLDER__:{dst_folder}"

            # 各图片键 → 新图片路径
            assert path_results[str(img1)] == str(dst_folder / "a.jpg")
            assert path_results[str(img2)] == str(dst_folder / "b.png")

    @pytest.mark.asyncio
    async def test_folder_move_renames_on_conflict(self):
        """目标目录中已有同名文件夹时，应追加序号而非覆盖。"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src_folder = td / "pack"
            src_folder.mkdir()
            (src_folder / "a.jpg").write_bytes(b"a")

            target_dir = td / "published"
            target_dir.mkdir()
            # 预先创建同名文件夹
            (target_dir / "pack").mkdir()

            info = _info_for_folder(str(src_folder), [str(src_folder / "a.jpg")])

            with (
                patch(_MLM_GET_ROOT, return_value=td),
                patch(_HANDLER_RESOLVE, return_value=target_dir),
            ):
                user_log = _make_user_log()
                path_results = await PostPublishFileHandler._execute_file_action(
                    info, "move", user_log
                )

            # 源文件夹已移走
            assert not src_folder.exists()
            # 目标应为 "pack (1)"
            dst_folder = target_dir / "pack (1)"
            assert dst_folder.exists()
            folder_key = f"__FOLDER__:{src_folder}"
            assert path_results[folder_key] == f"__FOLDER__:{dst_folder}"

    @pytest.mark.asyncio
    async def test_folder_move_graceful_when_folder_missing(self):
        """源文件夹不存在时，所有条目标记为 None，不抛出异常。"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src_folder = td / "not_exist"
            img1 = str(src_folder / "a.jpg")

            target_dir = td / "published"
            target_dir.mkdir()

            info = _info_for_folder(str(src_folder), [img1])

            with (
                patch(_MLM_GET_ROOT, return_value=td),
                patch(_HANDLER_RESOLVE, return_value=target_dir),
            ):
                user_log = _make_user_log()
                path_results = await PostPublishFileHandler._execute_file_action(
                    info, "move", user_log
                )

            folder_key = f"__FOLDER__:{src_folder}"
            assert path_results.get(folder_key) is None
            assert path_results.get(img1) is None
            user_log.warning.assert_called()

    @pytest.mark.asyncio
    async def test_folder_move_no_media_library_path(self):
        """未配置媒体库路径时，所有条目标记为 None。"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src_folder = td / "pack"
            src_folder.mkdir()
            img1 = str(src_folder / "a.jpg")
            (src_folder / "a.jpg").write_bytes(b"a")

            info = _info_for_folder(str(src_folder), [img1])

            with patch(_MLM_GET_ROOT, return_value=None):
                user_log = _make_user_log()
                path_results = await PostPublishFileHandler._execute_file_action(
                    info, "move", user_log
                )

            folder_key = f"__FOLDER__:{src_folder}"
            assert path_results.get(folder_key) is None
            assert path_results.get(img1) is None


# ──────────────────────────────────────────────────────────────────────────────
# _execute_file_action - 文件夹整体删除
# ──────────────────────────────────────────────────────────────────────────────

class TestExecuteFileActionFolderDelete:
    @pytest.mark.asyncio
    async def test_folder_delete_removes_whole_folder(self):
        """删除操作应将整个文件夹目录删除。"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            src_folder = td / "pack"
            src_folder.mkdir()
            img1 = src_folder / "a.jpg"
            img1.write_bytes(b"a")

            info = _info_for_folder(str(src_folder), [str(img1)])

            user_log = _make_user_log()
            path_results = await PostPublishFileHandler._execute_file_action(
                info, "delete", user_log
            )

            assert not src_folder.exists(), "文件夹应被整体删除"
            folder_key = f"__FOLDER__:{src_folder}"
            assert path_results[folder_key] == "__DELETED__"
            assert path_results[str(img1)] == "__DELETED__"


# ──────────────────────────────────────────────────────────────────────────────
# _execute_file_action - 普通散图回归测试（不受新代码影响）
# ──────────────────────────────────────────────────────────────────────────────

class TestExecuteFileActionPlainImages:
    @pytest.mark.asyncio
    async def test_plain_images_move_individually(self):
        """散图任务（无 source_folder）应继续逐文件移动，行为不变。"""
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            img1 = td / "a.jpg"
            img2 = td / "b.png"
            img1.write_bytes(b"a")
            img2.write_bytes(b"b")

            target_dir = td / "published"
            target_dir.mkdir()

            info = _info_for_images([str(img1), str(img2)])

            with (
                patch(_MLM_GET_ROOT, return_value=td),
                patch(_HANDLER_RESOLVE, return_value=target_dir),
            ):
                user_log = _make_user_log()
                path_results = await PostPublishFileHandler._execute_file_action(
                    info, "move", user_log
                )

            assert not img1.exists()
            assert not img2.exists()
            assert (target_dir / "a.jpg").exists()
            assert (target_dir / "b.png").exists()
            assert path_results[str(img1)] == str(target_dir / "a.jpg")
            assert path_results[str(img2)] == str(target_dir / "b.png")


# ──────────────────────────────────────────────────────────────────────────────
# _update_file_path_in_db - 支持 __FOLDER__: 条目替换
# ──────────────────────────────────────────────────────────────────────────────

class TestUpdateFilePathInDb:
    @pytest.mark.asyncio
    async def test_folder_marker_and_images_updated_in_db(self):
        """文件夹移动后，__FOLDER__: 标记和各图片路径均应被更新到数据库。"""
        old_folder = "D:/media/旧文件夹"
        new_folder = "D:/media/published/旧文件夹"
        old_img1 = f"{old_folder}/a.jpg"
        old_img2 = f"{old_folder}/b.png"
        new_img1 = f"{new_folder}/a.jpg"
        new_img2 = f"{new_folder}/b.png"

        # 原始 file_path（包含 __FOLDER__: 条目）
        original_fp = f"__FOLDER__:{old_folder},{old_img1},{old_img2}"

        # 模拟 _execute_file_action 返回的 path_results
        path_results: dict[str, Optional[str]] = {
            f"__FOLDER__:{old_folder}": f"__FOLDER__:{new_folder}",
            old_img1: new_img1,
            old_img2: new_img2,
        }

        repo = MagicMock()
        repo.update_content = AsyncMock()
        user_log = _make_user_log()

        await PostPublishFileHandler._update_file_path_in_db(
            task_id=42,
            original_file_path=original_fp,
            path_results=path_results,
            publish_repo=repo,
            user_log=user_log,
        )

        repo.update_content.assert_awaited_once()
        new_fp_written = repo.update_content.call_args.kwargs.get("file_path", "")
        assert f"__FOLDER__:{new_folder}" in new_fp_written
        assert new_img1 in new_fp_written
        assert new_img2 in new_fp_written
        # 确认旧路径不在新值中
        assert f"__FOLDER__:{old_folder}" not in new_fp_written
        assert old_img1 not in new_fp_written

    @pytest.mark.asyncio
    async def test_plain_images_db_update_unchanged(self):
        """普通散图路径更新不受新逻辑影响。"""
        old_img = "D:/media/a.jpg"
        new_img = "D:/media/published/a.jpg"
        original_fp = old_img
        path_results: dict[str, Optional[str]] = {old_img: new_img}

        repo = MagicMock()
        repo.update_content = AsyncMock()
        user_log = _make_user_log()

        await PostPublishFileHandler._update_file_path_in_db(
            task_id=1,
            original_file_path=original_fp,
            path_results=path_results,
            publish_repo=repo,
            user_log=user_log,
        )

        repo.update_content.assert_awaited_once()
        new_fp = repo.update_content.call_args.kwargs.get("file_path", "")
        assert new_fp == new_img

    @pytest.mark.asyncio
    async def test_no_change_skips_db_write(self):
        """所有 path_results 均为 None 时，不写数据库。"""
        old_img = "D:/media/a.jpg"
        original_fp = old_img
        path_results: dict[str, Optional[str]] = {old_img: None}

        repo = MagicMock()
        repo.update_content = AsyncMock()
        user_log = _make_user_log()

        await PostPublishFileHandler._update_file_path_in_db(
            task_id=1,
            original_file_path=original_fp,
            path_results=path_results,
            publish_repo=repo,
            user_log=user_log,
        )

        repo.update_content.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deleted_folder_marker_updated_in_db(self):
        """文件夹删除后，数据库中各条目均应更新为 __DELETED__。"""
        old_folder = "D:/media/旧文件夹"
        old_img1 = f"{old_folder}/a.jpg"
        original_fp = f"__FOLDER__:{old_folder},{old_img1}"
        path_results: dict[str, Optional[str]] = {
            f"__FOLDER__:{old_folder}": "__DELETED__",
            old_img1: "__DELETED__",
        }

        repo = MagicMock()
        repo.update_content = AsyncMock()
        user_log = _make_user_log()

        await PostPublishFileHandler._update_file_path_in_db(
            task_id=5,
            original_file_path=original_fp,
            path_results=path_results,
            publish_repo=repo,
            user_log=user_log,
        )

        repo.update_content.assert_awaited_once()
        new_fp = repo.update_content.call_args.kwargs.get("file_path", "")
        assert "__DELETED__" in new_fp


# ──────────────────────────────────────────────────────────────────────────────
# FileGroupInfo.source_folder 字段测试
# ──────────────────────────────────────────────────────────────────────────────

class TestFileGroupInfoSourceFolder:
    def test_source_folder_default_empty(self):
        info = FileGroupInfo(file_paths=["/img/a.jpg"])
        assert info.source_folder == ""

    def test_source_folder_set_correctly(self):
        info = FileGroupInfo(file_paths=["/folder/a.jpg"], source_folder="/folder")
        assert info.source_folder == "/folder"

    def test_extract_folder_path_roundtrip(self):
        folder = "D:/media/pack"
        fp = f"__FOLDER__:{folder},{folder}/a.jpg"
        extracted = PostPublishFileHandler._extract_folder_path(fp)
        assert extracted == folder
