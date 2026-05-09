"""
路径管理器
文件路径：src/infrastructure/common/path_manager.py
功能：统一管理应用路径，区分程序资源目录（只读）和用户数据目录（可写）

账号目录约定：仅使用 profile_folder_name（如 profile_xxx）作为 data/{platform}/ 下目录名，
禁止使用平台昵称建目录。未提供 profile_folder_name 时报错。
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

class PathManager:
    """路径管理器 - 统一管理应用路径"""
    
    _app_name = "WeMediaBaby"
    _app_data_dir: Optional[Path] = None
    _resource_dir: Optional[Path] = None
    
    @classmethod
    def get_resource_dir(cls) -> Path:
        """获取资源目录（只读，安装目录）"""
        if cls._resource_dir is None:
            if getattr(sys, 'frozen', False):
                # 打包环境 (PyInstaller / Nuitka)
                if hasattr(sys, '_MEIPASS'):
                    # PyInstaller 运行时解压的临时资源目录
                    cls._resource_dir = Path(sys._MEIPASS)
                else:
                    # Nuitka 运行时的可执行文件所在目录
                    cls._resource_dir = Path(sys.executable).parent
            else:
                # 开发环境 (根据当前文件位置往上推算根目录: src/infrastructure/common -> root)
                cls._resource_dir = Path(os.path.abspath(__file__)).parent.parent.parent.parent
        return cls._resource_dir
    
    @classmethod
    def get_resource_path(cls, relative_path: str) -> Path:
        """获取资源文件的绝对路径（兼容开发/PyInstaller/Nuitka 环境）
        
        所有需要访问项目内置资源（如 icons、qss、config 等）的模块，
        都应通过此方法获取路径，禁止直接使用 __file__ 推算。
        
        Args:
            relative_path: 相对于项目根目录的路径，如 'resources/icons/app.ico'
        
        Returns:
            Path: 资源文件的绝对路径
        """
        return cls.get_resource_dir() / relative_path
    
    @classmethod
    def get_app_data_dir(cls) -> Path:
        """获取用户数据目录（可写，AppData）"""
        if cls._app_data_dir is None:
            if sys.platform == 'win32':
                # Windows: %LOCALAPPDATA%\WeMediaBaby
                # 明确只使用 LOCALAPPDATA，避免数据存储到 Roaming
                local_app_data = os.environ.get('LOCALAPPDATA')
                if not local_app_data:
                     # 极端回退：如果获取不到环境变量，使用用户目录下的 AppData/Local
                    local_app_data = os.path.expanduser('~\\AppData\\Local')
                base_path = Path(local_app_data)
            elif sys.platform == 'darwin':
                # macOS: ~/Library/Application Support/WeMediaBaby
                base_path = Path(os.path.expanduser('~/Library/Application Support'))
            else:
                # Linux: ~/.local/share/WeMediaBaby
                base_path = Path(os.path.expanduser('~/.local/share'))
            
            cls._app_data_dir = base_path / cls._app_name
            # 确保基础目录存在
            cls._app_data_dir.mkdir(parents=True, exist_ok=True)
            
        return cls._app_data_dir

    @classmethod
    def get_db_path(cls) -> Path:
        """获取数据库路径"""
        return cls.get_app_data_dir() / "data" / "database.db"
        
    @classmethod
    def get_log_dir(cls) -> Path:
        """获取日志目录"""
        dir_path = cls.get_app_data_dir() / "logs"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path
        
    @classmethod
    def get_config_dir(cls) -> Path:
        """获取配置目录"""
        dir_path = cls.get_app_data_dir() / "config"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    @classmethod
    def get_cache_dir(cls) -> Path:
        """获取缓存目录"""
        dir_path = cls.get_app_data_dir() / "cache"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    @classmethod
    def get_debug_screenshots_root(cls) -> Path:
        """诊断截图根目录: AppData/debug/screenshots"""
        dir_path = cls.get_app_data_dir() / "debug" / "screenshots"
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    @classmethod
    def get_debug_screenshots_dir(cls, platform: str) -> Path:
        """发布失败时按平台保存的截图目录: AppData/debug/screenshots/{platform}"""
        pid = (platform or "").strip()
        if not pid:
            raise ValueError("platform is required for debug screenshots directory")
        dir_path = cls.get_debug_screenshots_root() / pid
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    @classmethod
    def get_platform_account_dir(
        cls,
        platform: str,
        platform_username: str,
        profile_folder_name: Optional[str] = None,
    ) -> Path:
        """获取平台账号根目录，仅使用 profile_folder_name 作为目录名。
        
        Args:
            platform: 平台名称 (如 douyin)
            platform_username: 平台用户名（仅用于错误提示）
            profile_folder_name: 目录名 (如 profile_xxx)，必填
            
        Returns:
            Path: data/{platform}/{profile_folder_name}
            
        Raises:
            ValueError: profile_folder_name 为空时
        """
        folder_name = (profile_folder_name or "").strip()
        if not folder_name:
            raise ValueError(
                "profile_folder_name is required for account path. "
                "Use PathManager.get_account_root(account_dict) when you have account dict."
            )
        return cls.get_app_data_dir() / "data" / platform / folder_name

    @classmethod
    def get_account_root(cls, account: Dict[str, Any]) -> Path:
        """从账号字典解析账号根目录（单一入口，杜绝昵称目录）
        
        优先使用 account['profile_folder_name']；若缺失则从 account['cookie_path'] 解析
        （路径形如 .../data/{platform}/{profile_xxx}/cookies.json）。
        
        Args:
            account: 至少含 platform, platform_username；建议含 profile_folder_name 或 cookie_path
            
        Returns:
            Path: data/{platform}/{profile_xxx}
            
        Raises:
            ValueError: 无法解析出 profile 目录名时
        """
        platform = account.get("platform") or ""
        platform_username = account.get("platform_username") or account.get("account_name") or ""
        profile_folder_name = (account.get("profile_folder_name") or "").strip()
        if not profile_folder_name and account.get("cookie_path"):
            try:
                parent_name = Path(account.get("cookie_path", "")).parent.name
                if parent_name and parent_name.startswith("profile_"):
                    profile_folder_name = parent_name
            except Exception:
                pass
        if not profile_folder_name:
            raise ValueError(
                "Cannot resolve account root: account must have profile_folder_name or cookie_path "
                "pointing to a profile_xxx directory."
            )
        return cls.get_platform_account_dir(platform, platform_username, profile_folder_name)
