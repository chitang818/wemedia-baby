"""
视频元数据提取工具
文件路径：src/utils/video_metadata.py
功能：通过 ffprobe/ffmpeg 命令行提取视频元数据与缩略图（不依赖 ffmpeg-python，与打包环境一致）
"""

import json
import os
import sys
import threading
from pathlib import Path
from typing import Dict, Optional, Any
import logging
import subprocess

from src.utils.subprocess_helpers import subprocess_hide_window_kwargs

logger = logging.getLogger(__name__)

# 保留常量：历史代码曾用其判断；现与设置页一致，仅以本机 ffmpeg 可执行为准，打包后不再依赖 ffmpeg-python
FFMPEG_AVAILABLE = True

# 尝试配置 ffmpeg 路径
_FFMPEG_PATH = None
_FFMPEG_DIR = None
# 仅缓存「ffmpeg 可执行」成功结果；失败不写入缓存，避免会话内安装 FFmpeg 后仍沿用旧的否定结果
# （设置页用 ffmpeg_installer.check_ffmpeg_installed 每次查盘，与此处曾缓存的 False 不一致）
_FFMPEG_EXEC_OK: Optional[bool] = None
_FFMPEG_EXEC_CHECK_LOCK = threading.Lock()


class FFmpegCliError(Exception):
    """ffprobe/ffmpeg 子进程失败（替代原 ffmpeg-python 的 ffmpeg.Error）。"""

    def __init__(self, cmd: str, stderr: bytes, stdout: bytes = b""):
        self.cmd = cmd
        self.stderr = stderr
        self.stdout = stdout
        super().__init__(cmd)


def invalidate_ffmpeg_availability_cache() -> None:
    """清除 ffmpeg 可用性缓存（路径变更或安装完成后应调用）。"""
    global _FFMPEG_EXEC_OK
    _FFMPEG_EXEC_OK = None


def ensure_ffmpeg_on_path() -> None:
    """批量调用 get_video_metadata 前执行一次，统一把 ffmpeg 目录加入 PATH，减少多线程下反复改写环境变量。"""
    _initialize_ffmpeg_path(force_refresh=False)
    if _FFMPEG_DIR and _FFMPEG_DIR not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")


def _initialize_ffmpeg_path(force_refresh=False):
    """初始化 ffmpeg 路径配置
    
    Args:
        force_refresh: 是否强制重新查找（即使已经找到过）
    """
    global _FFMPEG_PATH, _FFMPEG_DIR
    if force_refresh:
        invalidate_ffmpeg_availability_cache()
    if _FFMPEG_PATH is None or force_refresh:
        try:
            from .ffmpeg_installer import _find_ffmpeg_executable
            _FFMPEG_PATH = _find_ffmpeg_executable()
            if _FFMPEG_PATH:
                _FFMPEG_DIR = os.path.dirname(_FFMPEG_PATH)
                if _FFMPEG_DIR not in os.environ.get('PATH', ''):
                    os.environ['PATH'] = _FFMPEG_DIR + os.pathsep + os.environ.get('PATH', '')
                # 仅在首次发现时输出 INFO，后续刷新降为 DEBUG 避免每个文件都刷日志
                if force_refresh:
                    logger.debug(f"找到 ffmpeg: {_FFMPEG_PATH}")
                    logger.debug(f"ffmpeg 目录: {_FFMPEG_DIR}")
                else:
                    logger.info(f"找到 ffmpeg: {_FFMPEG_PATH}")
                    logger.info(f"ffmpeg 目录: {_FFMPEG_DIR}")
            else:
                logger.warning("未找到 ffmpeg 可执行文件")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"初始化 ffmpeg 路径失败: {e}")

# 初始化路径
_initialize_ffmpeg_path()


def check_ffmpeg_available() -> bool:
    """检查 ffmpeg 是否可用

    仅在探测成功时缓存 True；失败不缓存，以便同一会话内完成安装后再次调用能重新查找可执行文件
    （与 ``ffmpeg_installer.check_ffmpeg_installed`` 行为一致；不依赖 ffmpeg-python，避免 Nuitka 下误判）。

    Returns:
        如果 ffmpeg 可用返回 True，否则返回 False
    """
    global _FFMPEG_EXEC_OK
    if _FFMPEG_EXEC_OK is True:
        return True

    with _FFMPEG_EXEC_CHECK_LOCK:
        if _FFMPEG_EXEC_OK is True:
            return True

        # 仅在未找到路径时才重新查找；已有缓存路径则直接用
        _initialize_ffmpeg_path(force_refresh=False)

        try:
            # 使用找到的 ffmpeg 路径，如果没有则使用系统 PATH
            ffmpeg_cmd = _FFMPEG_PATH if _FFMPEG_PATH else 'ffmpeg'

            # 确保 PATH 包含 ffmpeg 目录（ffmpeg-python 需要找到 ffprobe）
            env = os.environ.copy()
            if _FFMPEG_DIR and _FFMPEG_DIR not in env.get('PATH', ''):
                env['PATH'] = _FFMPEG_DIR + os.pathsep + env.get('PATH', '')

            # 尝试运行 ffmpeg 命令检查是否可用
            result = subprocess.run(
                [ffmpeg_cmd, '-version'],
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
                **subprocess_hide_window_kwargs(),
            )
            if result.returncode == 0:
                logger.debug(f"ffmpeg 可用: {ffmpeg_cmd}")
                _FFMPEG_EXEC_OK = True
                return True
            logger.warning("ffmpeg 命令执行失败")
            return False
        except FileNotFoundError:
            logger.warning("ffmpeg 未找到")
            return False
        except subprocess.TimeoutExpired:
            logger.warning("ffmpeg 检查超时")
            return False
        except Exception as e:
            logger.warning(f"检查 ffmpeg 可用性时出错: {e}")
            return False


def _resolve_ffprobe_executable() -> str:
    """与便携式 ffmpeg 同目录的 ffprobe；不用 ffmpeg-python 内置 Popen，以便在 Windows 上隐藏控制台。"""
    if _FFMPEG_DIR:
        d = Path(_FFMPEG_DIR)
        if sys.platform == "win32":
            candidates = (d / "ffprobe.exe", d / "ffprobe")
        else:
            candidates = (d / "ffprobe", d / "ffprobe.exe")
        for p in candidates:
            if p.is_file():
                return str(p)
    return "ffprobe"


def _ffprobe_json(file_path: str) -> Dict[str, Any]:
    """调用 ffprobe 输出 JSON（与 ffmpeg.probe 等价），Windows 下附带 CREATE_NO_WINDOW。"""
    ffprobe_cmd = _resolve_ffprobe_executable()
    env = os.environ.copy()
    if _FFMPEG_DIR and _FFMPEG_DIR not in env.get("PATH", ""):
        env["PATH"] = _FFMPEG_DIR + os.pathsep + env.get("PATH", "")
    args = [ffprobe_cmd, "-show_format", "-show_streams", "-of", "json", file_path]
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=env,
        **subprocess_hide_window_kwargs(),
    )
    if completed.returncode != 0:
        out_b = (completed.stdout or "").encode("utf-8", errors="replace")
        err_b = (completed.stderr or "").encode("utf-8", errors="replace")
        raise FFmpegCliError("ffprobe", err_b, out_b)
    return json.loads(completed.stdout)


def get_video_metadata(file_path: str) -> Dict[str, Any]:
    """提取视频文件的元数据
    
    Args:
        file_path: 视频文件路径
    
    Returns:
        包含以下键的字典：
        - duration: 视频时长（秒，float）
        - width: 视频宽度（像素，int）
        - height: 视频高度（像素，int）
        - resolution: 分辨率字符串（如 "1920x1080"，str）
        
        如果提取失败，返回的字典中对应值为 None
    
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: ffmpeg 不可用或文件不是有效的视频文件
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    # 仅在尚未找到路径时才初始化，避免批量处理时每个文件都重复查找
    _initialize_ffmpeg_path(force_refresh=False)

    # 检查 ffmpeg 是否真的可用
    if not check_ffmpeg_available():
        logger.error(f"ffmpeg 不可用，无法提取视频元数据: {file_path}")
        if _FFMPEG_PATH:
            logger.error(f"找到的 ffmpeg 路径: {_FFMPEG_PATH}，但无法执行")
        else:
            logger.error("未找到 ffmpeg，请确保已安装 ffmpeg")
        return {
            'duration': None,
            'width': None,
            'height': None,
            'resolution': None
        }
    
    try:
        # 确保 PATH 环境变量包含 ffmpeg 目录（ffmpeg-python 需要找到 ffprobe）
        if _FFMPEG_DIR and _FFMPEG_DIR not in os.environ.get('PATH', ''):
            os.environ['PATH'] = _FFMPEG_DIR + os.pathsep + os.environ.get('PATH', '')
        
        # 使用 ffprobe 探测视频信息（避免 ffmpeg-python 内部 Popen 在 Windows 上闪控制台）
        probe = _ffprobe_json(file_path)
        
        # 获取视频流信息
        video_stream = None
        for stream in probe.get('streams', []):
            if stream.get('codec_type') == 'video':
                video_stream = stream
                break
        
        if not video_stream:
            raise ValueError("文件中未找到视频流")
        
        # 提取时长（秒）
        duration = None
        format_info = probe.get('format', {})
        if 'duration' in format_info:
            try:
                duration = float(format_info['duration'])
            except (ValueError, TypeError):
                logger.warning(f"无法解析视频时长: {format_info.get('duration')}")
        
        # 提取分辨率
        width = None
        height = None
        resolution = None
        
        if 'width' in video_stream and 'height' in video_stream:
            try:
                width = int(video_stream['width'])
                height = int(video_stream['height'])
                resolution = f"{width}x{height}"
            except (ValueError, TypeError) as e:
                logger.warning(f"无法解析视频分辨率: {e}")
        
        return {
            'duration': duration,
            'width': width,
            'height': height,
            'resolution': resolution
        }
    
    except FFmpegCliError as e:
        error_msg = e.stderr.decode(errors="replace") if e.stderr else str(e)
        logger.error(f"ffmpeg 提取元数据失败: {error_msg}")
        # 不抛出异常，返回空值，让调用者决定如何处理
        return {
            'duration': None,
            'width': None,
            'height': None,
            'resolution': None
        }
    except Exception as e:
        logger.error(f"提取视频元数据时发生错误: {e}", exc_info=True)
        # 不抛出异常，返回空值，让调用者决定如何处理
        return {
            'duration': None,
            'width': None,
            'height': None,
            'resolution': None
        }


def format_duration(seconds: Optional[float]) -> str:
    """格式化视频时长为可读字符串
    
    Args:
        seconds: 时长（秒）
    
    Returns:
        格式化后的时长字符串，如 "01:23:45" 或 "12:34"
    """
    if seconds is None:
        return "未知"
    
    try:
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "未知"


def extract_video_thumbnail(file_path: str) -> Optional[str]:
    """提取视频缩略图（首帧）
    
    Args:
        file_path: 视频文件路径
        
    Returns:
        缩略图文件路径（临时文件），如果提取失败返回 None
    """
    if not os.path.exists(file_path):
        return None
        
    _initialize_ffmpeg_path()

    if not check_ffmpeg_available():
        logger.warning("ffmpeg 不可用，无法提取缩略图")
        return None

    try:
        import tempfile

        # 创建临时文件保存缩略图
        fd, temp_path = tempfile.mkstemp(suffix='.jpg')
        os.close(fd)

        # 确保 PATH 包含 ffmpeg 目录
        if _FFMPEG_DIR and _FFMPEG_DIR not in os.environ.get('PATH', ''):
            os.environ['PATH'] = _FFMPEG_DIR + os.pathsep + os.environ.get('PATH', '')

        cmd0 = _FFMPEG_PATH if _FFMPEG_PATH else "ffmpeg"
        args = [
            cmd0,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "0",
            "-i",
            file_path,
            "-vf",
            "scale=1280:-1",
            "-frames:v",
            "1",
            "-q:v",
            "2",
            temp_path,
        ]
        env = os.environ.copy()
        if _FFMPEG_DIR and _FFMPEG_DIR not in env.get("PATH", ""):
            env["PATH"] = _FFMPEG_DIR + os.pathsep + env.get("PATH", "")
        completed = subprocess.run(
            args,
            capture_output=True,
            timeout=300,
            env=env,
            **subprocess_hide_window_kwargs(),
        )
        if completed.returncode != 0:
            err = (completed.stderr or b"").decode(errors="replace")
            logger.error("ffmpeg 提取缩略图失败: %s", err[:800])
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return None

        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            return temp_path
        logger.warning("缩略图提取失败：文件为空或未生成")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return None
    except Exception as e:
        logger.error(f"提取缩略图时发生错误: {e}", exc_info=True)
        return None
