"""
FFmpeg 安装检查工具
文件路径：src/utils/ffmpeg_installer.py
功能：检查 ffmpeg 是否安装，如果未安装则提供安装方法
"""

import os
import sys
import subprocess
import platform
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Tuple, Optional, Callable

from src.utils.subprocess_helpers import subprocess_hide_window_kwargs

logger = logging.getLogger(__name__)


def _find_ffmpeg_executable() -> Optional[str]:
    """查找 ffmpeg 可执行文件路径
    
    优先查找用户数据目录（AppData/tools/ffmpeg），再查安装/项目目录下的便携式安装。
    打包环境（PyInstaller/Nuitka）下使用 PathManager 获取资源目录。
    
    Returns:
        ffmpeg 可执行文件的路径，如果未找到返回 None
    """
    try:
        from src.infrastructure.common.path_manager import PathManager
        app_data_ffmpeg = PathManager.get_app_data_dir() / "tools" / "ffmpeg"
        for path in [
            app_data_ffmpeg / "ffmpeg.exe",
            app_data_ffmpeg / "bin" / "ffmpeg.exe",
        ]:
            if path.exists():
                logger.info(f"找到用户数据目录 ffmpeg: {path}")
                return str(path)
    except Exception as e:
        logger.debug(f"查找用户数据目录 ffmpeg 时跳过: {e}")

    # 打包环境下使用统一资源目录（安装目录），否则按源码目录推算
    if getattr(sys, "frozen", False):
        try:
            from src.infrastructure.common.path_manager import PathManager
            project_root = PathManager.get_resource_dir()
        except Exception as e:
            logger.debug("获取 PathManager 资源目录失败，回退到可执行文件目录: %s", e)
            project_root = Path(sys.executable).parent
    else:
        project_root = Path(__file__).parent.parent.parent
    # 检查安装/项目目录下的便携式安装
    portable_paths = [
        project_root / 'tools' / 'ffmpeg' / 'ffmpeg.exe',
        project_root / 'tools' / 'ffmpeg' / 'bin' / 'ffmpeg.exe',
        project_root / 'ffmpeg' / 'ffmpeg.exe',
        project_root / 'ffmpeg' / 'bin' / 'ffmpeg.exe',
    ]
    for path in portable_paths:
        if path.exists():
            logger.info(f"找到便携式 ffmpeg: {path}")
            return str(path)

    logger.warning("未找到便携式 ffmpeg 安装")
    return None


def check_ffmpeg_installed() -> Tuple[bool, Optional[str]]:
    """检查 ffmpeg 是否已安装
    
    Returns:
        (是否已安装, 版本信息或错误信息)
    """
    # 首先查找 ffmpeg 可执行文件
    ffmpeg_path = _find_ffmpeg_executable()
    
    if not ffmpeg_path:
        return False, "ffmpeg 未找到，请先安装"
    
    try:
        result = subprocess.run(
            [ffmpeg_path, '-version'],
            capture_output=True,
            text=True,
            timeout=5,
            **subprocess_hide_window_kwargs(),
        )
        if result.returncode == 0:
            # 提取版本信息
            version_line = result.stdout.split('\n')[0] if result.stdout else "已安装"
            return True, version_line
        else:
            return False, "ffmpeg 命令执行失败"
    except FileNotFoundError:
        return False, "ffmpeg 未找到，请先安装"
    except subprocess.TimeoutExpired:
        return False, "ffmpeg 检查超时"
    except Exception as e:
        return False, f"检查失败: {str(e)}"


def check_ffmpeg_python_installed() -> bool:
    """检查 ffmpeg-python 包是否已安装
    
    Returns:
        如果已安装返回 True，否则返回 False
    """
    try:
        import ffmpeg
        return True
    except ImportError:
        return False


def install_ffmpeg_python() -> Tuple[bool, str]:
    """安装 ffmpeg-python Python 包
    
    Returns:
        (是否成功, 消息)
    """
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'ffmpeg-python>=0.2.0'],
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        if result.returncode == 0:
            return True, "ffmpeg-python 安装成功"
        else:
            error_msg = result.stderr if result.stderr else result.stdout
            return False, f"安装失败: {error_msg}"
    except subprocess.TimeoutExpired:
        return False, "安装超时，请检查网络连接"
    except Exception as e:
        return False, f"安装过程出错: {str(e)}"


# 一键下载 FFmpeg 的直链（gyan.dev，仅 Windows 使用）
FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
# 手动下载说明链接，用于错误提示与设置页文案
FFMPEG_MANUAL_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/"


async def download_and_install_ffmpeg_async(
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[bool, str]:
    """下载 FFmpeg 压缩包并解压到用户数据目录（仅支持 Windows）。

    Args:
        progress_callback: 可选，下载进度回调 (current_bytes, total_bytes)，total 可能为 0。

    Returns:
        (是否成功, 成功时为安装路径或提示，失败时为错误描述)
    """
    if platform.system() != "Windows":
        return False, "仅支持 Windows 一键下载，其他系统请手动安装 FFmpeg。"

    try:
        from src.infrastructure.common.path_manager import PathManager
    except ImportError:
        return False, "无法加载 PathManager。"

    target_dir = PathManager.get_app_data_dir() / "tools" / "ffmpeg"
    cache_dir = PathManager.get_cache_dir()
    zip_path = cache_dir / "ffmpeg-download.zip"
    extract_dir = cache_dir / "ffmpeg-extract"

    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. 下载
    try:
        import aiohttp
    except ImportError:
        return False, "缺少 aiohttp 库，无法执行下载。"

    try:
        timeout = aiohttp.ClientTimeout(total=600, sock_connect=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(FFMPEG_DOWNLOAD_URL) as resp:
                resp.raise_for_status()
                total = int(resp.headers.get("Content-Length") or 0)
                if progress_callback and total:
                    progress_callback(0, total)
                downloaded = 0
                with open(zip_path, "wb") as f:
                    async for chunk in resp.content.iter_chunked(64 * 1024):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total:
                            progress_callback(downloaded, total)
                if progress_callback and total:
                    progress_callback(total, total)
    except aiohttp.ClientError as e:
        return False, f"下载失败（网络错误）: {e}"
    except Exception as e:
        logger.exception("下载 FFmpeg 时出错")
        return False, f"下载失败: {e}"

    # 2. 解压并复制到目标目录
    try:
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)

        # 识别解压后的单层子目录（如 ffmpeg-7.x-essentials_build）
        subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
        if not subdirs:
            return False, "压缩包结构异常，未找到 FFmpeg 目录。"

        root = subdirs[0]
        bin_dir = root / "bin"
        if bin_dir.exists():
            target_bin = target_dir / "bin"
            target_bin.mkdir(parents=True, exist_ok=True)
            for f in bin_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, target_bin / f.name)
        else:
            # 可执行文件可能在根目录
            for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                p = root / name
                if p.exists():
                    shutil.copy2(p, target_dir / name)

        # 确保至少复制了 ffmpeg.exe
        if not (target_dir / "ffmpeg.exe").exists() and not (target_dir / "bin" / "ffmpeg.exe").exists():
            return False, "解压后未找到 ffmpeg.exe。"

        # 3. 清理临时文件
        try:
            zip_path.unlink(missing_ok=True)
            shutil.rmtree(extract_dir, ignore_errors=True)
        except OSError:
            pass

        install_path = str(target_dir)
        logger.info(f"FFmpeg 已安装到: {install_path}")
        return True, f"FFmpeg 已安装到 {install_path}，可立即使用。"
    except zipfile.BadZipFile:
        return False, f"下载的文件不是有效的 ZIP，请检查网络或手动从 {FFMPEG_MANUAL_DOWNLOAD_URL} 下载。"
    except Exception as e:
        logger.exception("解压或复制 FFmpeg 时出错")
        return False, f"解压失败: {e}"


def install_ffmpeg_windows() -> Tuple[bool, str]:
    """在 Windows 系统上安装 ffmpeg
    
    Returns:
        (是否成功, 消息)
    """
    system = platform.system()
    if system != 'Windows':
        return False, f"当前系统为 {system}，此函数仅支持 Windows"
    
    # 方法1: 尝试使用 imageio-ffmpeg（Python 包，包含 ffmpeg 二进制）
    try:
        logger.info("尝试使用 imageio-ffmpeg 安装 ffmpeg...")
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', 'imageio-ffmpeg'],
            capture_output=True,
            text=True,
            timeout=300
        )
        if result.returncode == 0:
            # imageio-ffmpeg 安装后需要配置环境变量或使用其提供的路径
            try:
                import imageio_ffmpeg
                ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
                logger.info(f"imageio-ffmpeg 安装成功，ffmpeg 路径: {ffmpeg_path}")
                # 将 ffmpeg 路径添加到当前进程的 PATH（临时）
                ffmpeg_dir = os.path.dirname(ffmpeg_path)
                os.environ['PATH'] = ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')
                # 验证是否可用
                test_result = subprocess.run(
                    [ffmpeg_path, '-version'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if test_result.returncode == 0:
                    return True, "使用 imageio-ffmpeg 安装成功，ffmpeg 已可用"
            except Exception as e:
                logger.warning(f"imageio-ffmpeg 配置失败: {e}")
    except Exception as e:
        logger.warning(f"imageio-ffmpeg 安装出错: {e}")
    
    # 方法2: 尝试使用 winget（Windows 10/11 自带）
    try:
        logger.info("尝试使用 winget 安装 ffmpeg...")
        # 使用 --source winget 避免 msstore 源的问题
        result = subprocess.run(
            ['winget', 'install', 'Gyan.FFmpeg', '--source', 'winget', '--accept-package-agreements', '--accept-source-agreements'],
            capture_output=True,
            text=True,
            timeout=600  # 10分钟超时
        )
        if result.returncode == 0:
            return True, "使用 winget 安装成功，请重启命令行后使用"
        else:
            error_output = result.stderr if result.stderr else result.stdout
            logger.warning(f"winget 安装失败: {error_output}")
            # 如果是因为需要指定源，尝试不带自动确认参数
            if '--source' in error_output or '源' in error_output:
                logger.info("尝试使用 winget 安装（指定源）...")
                result2 = subprocess.run(
                    ['winget', 'install', 'Gyan.FFmpeg', '--source', 'winget'],
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                if result2.returncode == 0:
                    return True, "使用 winget 安装成功，请重启命令行后使用"
    except FileNotFoundError:
        logger.warning("winget 未找到，尝试其他方法...")
    except subprocess.TimeoutExpired:
        logger.warning("winget 安装超时")
    except Exception as e:
        logger.warning(f"winget 安装出错: {e}")
    
    # 方法3: 尝试使用 scoop
    try:
        logger.info("尝试使用 scoop 安装 ffmpeg...")
        result = subprocess.run(
            ['scoop', 'install', 'ffmpeg'],
            capture_output=True,
            text=True,
            timeout=600
        )
        if result.returncode == 0:
            return True, "使用 scoop 安装成功，请重启命令行后使用"
        else:
            logger.warning(f"scoop 安装失败: {result.stderr}")
    except FileNotFoundError:
        logger.warning("scoop 未找到，尝试其他方法...")
    except subprocess.TimeoutExpired:
        logger.warning("scoop 安装超时")
    except Exception as e:
        logger.warning(f"scoop 安装出错: {e}")
    
    # 方法4: 尝试使用 chocolatey
    try:
        logger.info("尝试使用 chocolatey 安装 ffmpeg...")
        result = subprocess.run(
            ['choco', 'install', 'ffmpeg', '-y'],
            capture_output=True,
            text=True,
            timeout=600
        )
        if result.returncode == 0:
            return True, "使用 chocolatey 安装成功，请重启命令行后使用"
        else:
            logger.warning(f"chocolatey 安装失败: {result.stderr}")
    except FileNotFoundError:
        logger.warning("chocolatey 未找到，尝试其他方法...")
    except subprocess.TimeoutExpired:
        logger.warning("chocolatey 安装超时")
    except Exception as e:
        logger.warning(f"chocolatey 安装出错: {e}")
    
    # 方法5: 尝试使用 conda（如果环境中有 conda）
    try:
        conda_exe = os.environ.get('CONDA_EXE', 'conda')
        logger.info("尝试使用 conda 安装 ffmpeg...")
        result = subprocess.run(
            [conda_exe, 'install', '-c', 'conda-forge', 'ffmpeg', '-y'],
            capture_output=True,
            text=True,
            timeout=600
        )
        if result.returncode == 0:
            return True, "使用 conda 安装成功，请重启命令行后使用"
        else:
            logger.warning(f"conda 安装失败: {result.stderr}")
    except FileNotFoundError:
        logger.warning("conda 未找到，尝试其他方法...")
    except subprocess.TimeoutExpired:
        logger.warning("conda 安装超时")
    except Exception as e:
        logger.warning(f"conda 安装出错: {e}")
    
    # 如果自动安装都失败，返回手动安装说明
    return False, f"""自动安装失败，请使用便携式安装（推荐）：

便携式安装（无需管理员权限，推荐）:
  1. 下载 ffmpeg 压缩包: {FFMPEG_MANUAL_DOWNLOAD_URL}
     或: https://github.com/BtbN/FFmpeg-Builds/releases
     选择 "ffmpeg-release-essentials.zip" 或类似版本
  2. 解压到项目目录下的 tools/ffmpeg/ 文件夹
     确保 ffmpeg.exe 位于 tools/ffmpeg/ 目录下
  3. 程序会自动检测并使用此路径
  4. 无需配置 PATH 环境变量，无需重启

目录结构示例：
  wemedia-baby/
  ├── tools/
  │   └── ffmpeg/
  │       ├── ffmpeg.exe
  │       ├── ffplay.exe
  │       └── ffprobe.exe

安装完成后，刷新文件列表即可使用。

注意：本程序仅使用项目目录下的便携式安装，不会使用系统 PATH 中的 ffmpeg。"""


def install_ffmpeg_auto() -> Tuple[bool, str]:
    """自动检测系统并安装 ffmpeg
    
    Returns:
        (是否成功, 消息)
    """
    system = platform.system()
    
    if system == 'Windows':
        return install_ffmpeg_windows()
    elif system == 'Linux':
        return False, """Linux 系统请使用包管理器安装：
  Ubuntu/Debian: sudo apt-get install ffmpeg
  CentOS/RHEL: sudo yum install ffmpeg
  Arch: sudo pacman -S ffmpeg"""
    elif system == 'Darwin':  # macOS
        return False, """macOS 系统请使用 Homebrew 安装：
  brew install ffmpeg"""
    else:
        return False, f"不支持的系统: {system}"


def check_and_install_ffmpeg(install_if_missing: bool = False) -> Tuple[bool, str]:
    """检查并可选地安装 ffmpeg
    
    Args:
        install_if_missing: 如果未安装是否自动安装
    
    Returns:
        (是否已安装, 消息)
    """
    # 检查 ffmpeg 是否已安装
    is_installed, version_info = check_ffmpeg_installed()
    if is_installed:
        ffmpeg_path = _find_ffmpeg_executable()
        source = "便携式安装"
        if ffmpeg_path:
            # 确认是否为便携式安装
            if 'tools' in ffmpeg_path or Path(ffmpeg_path).parent.parent.name == 'ffmpeg':
                source = "便携式安装"
            else:
                source = "便携式安装"  # 默认显示便携式安装
        return True, f"ffmpeg 已安装 ({source}): {version_info}"
    
    # 检查 ffmpeg-python 包
    if not check_ffmpeg_python_installed():
        logger.info("ffmpeg-python 包未安装，正在安装...")
        success, msg = install_ffmpeg_python()
        if not success:
            return False, f"ffmpeg-python 安装失败: {msg}"
        logger.info("ffmpeg-python 安装成功")
    
    # 如果 ffmpeg 未安装且需要自动安装
    if not is_installed and install_if_missing:
        logger.info("ffmpeg 未安装，尝试自动安装...")
        success, msg = install_ffmpeg_auto()
        return success, msg
    
    # 返回未安装信息
    if not is_installed:
        install_msg = install_ffmpeg_auto()[1] if install_if_missing else "请手动安装 ffmpeg"
        return False, f"ffmpeg 未安装。{install_msg}"
    
    return True, version_info


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    print("检查 ffmpeg 安装状态...")
    is_installed, msg = check_and_install_ffmpeg(install_if_missing=False)
    print(f"结果: {is_installed}")
    print(f"消息: {msg}")

