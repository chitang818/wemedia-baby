"""Launch normal Chrome profiles without Playwright attachment."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil

from src.infrastructure.common.path_manager import PathManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DetachedChromeLaunchResult:
    account_id: str
    platform: str
    pid: Optional[int]
    profile_folder_name: str
    user_data_dir: str
    url: str
    launched: bool
    already_running: bool = False


class DetachedChromeLauncher:
    """Starts system Chrome with an account-scoped user data directory."""

    _active_sessions: dict[str, DetachedChromeLaunchResult] = {}

    @classmethod
    def get_user_data_dir(
        cls,
        *,
        platform: str,
        platform_username: str,
        profile_folder_name: str,
    ) -> Path:
        account_root = PathManager.get_platform_account_dir(
            platform,
            platform_username,
            profile_folder_name,
        )
        user_data_dir = account_root / "browser" / "user_data"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        return user_data_dir

    @classmethod
    def launch(
        cls,
        *,
        account_id: int | str,
        platform: str,
        platform_username: str,
        profile_folder_name: str,
        url: str,
    ) -> DetachedChromeLaunchResult:
        user_data_dir = cls.get_user_data_dir(
            platform=platform,
            platform_username=platform_username,
            profile_folder_name=profile_folder_name,
        )
        existing_pid = cls.find_profile_process(user_data_dir)
        if existing_pid:
            result = DetachedChromeLaunchResult(
                account_id=str(account_id),
                platform=platform,
                pid=existing_pid,
                profile_folder_name=profile_folder_name,
                user_data_dir=str(user_data_dir),
                url=url,
                launched=False,
                already_running=True,
            )
            cls._active_sessions[str(account_id)] = result
            return result

        chrome_path = cls.resolve_chrome_path()
        args = cls.build_args(chrome_path, user_data_dir, url)
        try:
            process = subprocess.Popen(args, shell=False)
        except Exception:
            logger.exception("启动普通 Chrome 失败: %s", args)
            raise

        result = DetachedChromeLaunchResult(
            account_id=str(account_id),
            platform=platform,
            pid=process.pid,
            profile_folder_name=profile_folder_name,
            user_data_dir=str(user_data_dir),
            url=url,
            launched=True,
        )
        cls._active_sessions[str(account_id)] = result
        return result

    @classmethod
    def build_args(cls, chrome_path: str, user_data_dir: Path, url: str) -> list[str]:
        return [
            chrome_path,
            f"--user-data-dir={str(user_data_dir)}",
            "--new-window",
            url,
        ]

    @classmethod
    def resolve_chrome_path(cls) -> str:
        try:
            from src.infrastructure.common.config.app_config_merge import get_app_config_for_read

            configured = str(get_app_config_for_read().get("chrome_executable_path") or "").strip().strip('"')
            if configured and os.path.exists(configured):
                return configured
        except Exception:
            pass

        from src.utils.chrome_installer import detect_chrome

        installed, info = detect_chrome()
        path = (info or {}).get("path") if installed else None
        if isinstance(path, str) and path.strip() and os.path.exists(path):
            return path
        raise FileNotFoundError("未检测到 Google Chrome，请先在设置中安装或配置 Chrome。")

    @classmethod
    def find_profile_process(cls, user_data_dir: str | Path) -> Optional[int]:
        target = cls._normalize_user_data_dir(user_data_dir)
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if "chrome" not in name and "chromium" not in name:
                    continue
                cmdline = proc.info.get("cmdline") or []
                for arg in cmdline:
                    if not isinstance(arg, str):
                        continue
                    if not arg.lower().startswith("--user-data-dir="):
                        continue
                    value = arg.split("=", 1)[1].strip().strip('"')
                    if cls._normalize_user_data_dir(value) == target:
                        return int(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
            except Exception:
                continue
        return None

    @classmethod
    def is_profile_in_use(cls, user_data_dir: str | Path) -> bool:
        return cls.find_profile_process(user_data_dir) is not None

    @classmethod
    def is_account_profile_in_use(
        cls,
        *,
        platform: str,
        platform_username: str,
        profile_folder_name: str,
    ) -> bool:
        user_data_dir = cls.get_user_data_dir(
            platform=platform,
            platform_username=platform_username,
            profile_folder_name=profile_folder_name,
        )
        return cls.is_profile_in_use(user_data_dir)

    @classmethod
    def forget_account(cls, account_id: int | str) -> None:
        cls._active_sessions.pop(str(account_id), None)

    @staticmethod
    def _normalize_user_data_dir(path: str | Path) -> str:
        return str(Path(path).expanduser().resolve()).lower().replace("\\", "/").rstrip("/")
