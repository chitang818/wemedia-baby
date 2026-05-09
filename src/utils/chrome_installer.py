import asyncio
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple, Dict, Any


CHROME_PAGE_URL = "https://www.google.com/chrome/"
CHROME_MANUAL_DOWNLOAD_URL = CHROME_PAGE_URL
# 国内可访问的 Chrome 下载页（点击「下载 Chrome」时用默认浏览器打开此页，由用户手动下载安装）
CHROME_DOWNLOAD_PAGE_CN = "https://www.google.cn/chrome/index.html"


@dataclass
class ChromeInfo:
    installed: bool
    path: Optional[str] = None
    version: Optional[str] = None
    source: Optional[str] = None  # registry/path/cli


def _expand(p: str) -> str:
    return os.path.expandvars(p)


def _candidate_paths() -> list[str]:
    return [
        _expand(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        _expand(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        _expand(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
    ]


def _winreg_query_app_paths() -> Optional[str]:
    """Read chrome.exe path from App Paths. Returns path or None."""
    try:
        import winreg  # type: ignore
    except Exception:
        return None

    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
    ]
    for root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as k:
                val, _ = winreg.QueryValueEx(k, None)
                if isinstance(val, str) and val.strip():
                    return val.strip().strip('"')
        except Exception:
            continue
    return None


def _winreg_query_version() -> Optional[str]:
    try:
        import winreg  # type: ignore
    except Exception:
        return None

    keys = [
        (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Google\Chrome\BLBeacon"),
    ]
    for root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as k:
                val, _ = winreg.QueryValueEx(k, "version")
                if isinstance(val, str) and val.strip():
                    return val.strip()
        except Exception:
            continue
    return None


def _get_version_by_cli(chrome_path: str) -> Optional[str]:
    try:
        cp = subprocess.run(
            [chrome_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        out = (cp.stdout or cp.stderr or "").strip()
        # Examples:
        # "Google Chrome 122.0.6261.112"
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", out)
        return m.group(1) if m else None
    except Exception:
        return None


def detect_chrome() -> Tuple[bool, Dict[str, Any]]:
    """Detect system-installed Google Chrome on Windows.

    Returns:
        (installed, info_dict) where info_dict has keys: path, version, source
    """
    # 1) Registry App Paths
    reg_path = _winreg_query_app_paths()
    if reg_path and os.path.exists(reg_path):
        version = _winreg_query_version() or _get_version_by_cli(reg_path)
        return True, {"path": reg_path, "version": version, "source": "registry_app_paths"}

    # 2) Common locations
    for p in _candidate_paths():
        if p and os.path.exists(p):
            version = _winreg_query_version() or _get_version_by_cli(p)
            return True, {"path": p, "version": version, "source": "common_path"}

    return False, {"path": None, "version": None, "source": None}


async def _download_with_progress(url: str, dest: Path, progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=60 * 30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, allow_redirects=True) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 256):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)


async def _resolve_installer_url_from_chrome_page() -> str:
    """Resolve an installer download URL starting from https://www.google.com/chrome/.

    Constraint: user requested the download is initiated from that page.
    Strategy:
    - Fetch the page HTML
    - Extract any direct dl.google.com .exe link if present
    - Otherwise, look for common Chrome download endpoints embedded in the page and follow redirects.
    """
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(CHROME_PAGE_URL, allow_redirects=True) as resp:
            resp.raise_for_status()
            html = await resp.text(errors="ignore")

    # Try direct dl.google.com exe links embedded in html
    exe_urls = re.findall(r"https?://[^\\s\"']+?\\.exe", html, flags=re.IGNORECASE)
    for u in exe_urls:
        if "dl.google.com" in u.lower() and "chrome" in u.lower():
            return u

    # Try known google chrome download endpoints referenced from the Chrome page.
    # These are still "from google.com/chrome" flow (redirect-based).
    candidates = [
        "https://www.google.com/chrome/?standalone=1",
        "https://www.google.com/chrome/?platform=win64",
        "https://www.google.com/chrome/?standalone=1&platform=win64",
    ]

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for c in candidates:
            try:
                async with session.get(c, allow_redirects=True) as resp:
                    resp.raise_for_status()
                    # If it redirects directly to an exe, aiohttp keeps final URL in resp.url
                    final_url = str(resp.url)
                    if final_url.lower().endswith(".exe"):
                        return final_url
                    # Or the HTML contains a direct .exe link
                    h = await resp.text(errors="ignore")
                    exe_urls = re.findall(r"https?://[^\\s\"']+?\\.exe", h, flags=re.IGNORECASE)
                    for u in exe_urls:
                        if "dl.google.com" in u.lower() and "chrome" in u.lower():
                            return u
            except Exception:
                continue

    raise RuntimeError("无法从 https://www.google.com/chrome/ 解析到可下载的安装包链接，请手动下载。")


def _run_installer(installer_path: Path) -> Tuple[bool, str]:
    """Run installer silently when possible."""
    try:
        # Common silent flags for ChromeSetup/standalone installers.
        # If flags are unsupported, installer may still open UI; that's acceptable as 'auto install' requirement.
        args = [str(installer_path), "/silent", "/install"]
        cp = subprocess.run(args, capture_output=True, text=True, check=False)
        if cp.returncode == 0:
            return True, "安装器执行成功"
        # Some installers return non-zero but still install; we'll verify by detect_chrome() later.
        return False, f"安装器返回码 {cp.returncode}: {(cp.stderr or cp.stdout or '').strip()[:200]}"
    except Exception as e:
        return False, f"运行安装器失败: {e}"


async def download_and_install_chrome_async(
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> Tuple[bool, str, Dict[str, Any]]:
    """Download Chrome installer via https://www.google.com/chrome/ flow and install it.

    Returns:
        (ok, message, chrome_info_dict)
    """
    installed, info = detect_chrome()
    if installed:
        return True, "已检测到 Chrome 已安装，无需下载。", info

    url = await _resolve_installer_url_from_chrome_page()
    tmp_dir = Path(tempfile.gettempdir()) / "wemedia_baby"
    installer = tmp_dir / "chrome_installer_win64.exe"

    await _download_with_progress(url, installer, progress_callback)

    # Run installer in executor to avoid blocking event loop
    ok, msg = await asyncio.get_running_loop().run_in_executor(None, _run_installer, installer)

    # Verify installation
    for _ in range(10):
        await asyncio.sleep(1)
        installed2, info2 = detect_chrome()
        if installed2:
            return True, "Chrome 安装完成。", info2

    # If installer reported success but we still can't detect, return failure with msg.
    return False, f"安装后仍未检测到 Chrome。{msg}。请手动访问 {CHROME_MANUAL_DOWNLOAD_URL} 下载安装。", {"path": None, "version": None, "source": None}

