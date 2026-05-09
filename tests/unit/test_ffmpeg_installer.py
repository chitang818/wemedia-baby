"""
FFmpeg 安装检查单元测试
测试范围：_find_ffmpeg_executable、check_ffmpeg_installed（mock PathManager 与 subprocess）
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils.ffmpeg_installer import (
    _find_ffmpeg_executable,
    check_ffmpeg_installed,
)


class TestFindFfmpegExecutable:
    """_find_ffmpeg_executable 单元测试"""

    def test_returns_path_when_app_data_ffmpeg_exists(self):
        """用户数据目录下存在 ffmpeg.exe 时返回该路径"""
        with patch("src.infrastructure.common.path_manager.PathManager") as PM:
            PM.get_app_data_dir.return_value = Path("/fake/appdata")
            with patch.object(Path, "exists", return_value=True):
                result = _find_ffmpeg_executable()
                assert result is not None
                assert "ffmpeg" in result

    def test_returns_none_when_no_path_exists(self):
        """所有候选路径都不存在时返回 None"""
        with patch("src.infrastructure.common.path_manager.PathManager") as PM:
            PM.get_app_data_dir.return_value = Path("/fake/appdata")
            with patch.object(Path, "exists", return_value=False):
                with patch("src.utils.ffmpeg_installer.sys") as mock_sys:
                    mock_sys.frozen = False
                    mock_sys.executable = "/fake/python"
                    mock_sys.__file__ = getattr(sys, "__file__", "/fake/ffmpeg_installer.py")
                    result = _find_ffmpeg_executable()
                    assert result is None


class TestCheckFfmpegInstalled:
    """check_ffmpeg_installed 单元测试"""

    def test_returns_false_when_ffmpeg_not_found(self):
        """找不到 ffmpeg 可执行文件时返回 (False, 提示信息)"""
        with patch("src.utils.ffmpeg_installer._find_ffmpeg_executable", return_value=None):
            ok, msg = check_ffmpeg_installed()
            assert ok is False
            assert "未找到" in msg or "请先安装" in msg

    def test_returns_true_when_version_run_succeeds(self):
        """ffmpeg -version 执行成功时返回 (True, 版本信息)"""
        with patch("src.utils.ffmpeg_installer._find_ffmpeg_executable", return_value="/fake/ffmpeg.exe"):
            with patch("src.utils.ffmpeg_installer.subprocess.run") as run:
                run.return_value = MagicMock(returncode=0, stdout="ffmpeg version 1.0\n")
                ok, msg = check_ffmpeg_installed()
                assert ok is True
                assert "ffmpeg" in msg or "1.0" in msg or "已安装" in msg

    def test_returns_false_when_version_run_fails(self):
        """ffmpeg -version 返回非零时返回 (False, 错误信息)"""
        with patch("src.utils.ffmpeg_installer._find_ffmpeg_executable", return_value="/fake/ffmpeg.exe"):
            with patch("src.utils.ffmpeg_installer.subprocess.run") as run:
                run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
                ok, msg = check_ffmpeg_installed()
                assert ok is False
                assert "执行失败" in msg or "失败" in msg
