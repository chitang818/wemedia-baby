"""
文件选择对话框
文件路径：src/ui/dialogs/file_select_dialog.py
功能：选择单个文件或文件夹
"""

from typing import Optional, List
import os
import logging

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QWidget, QFileDialog

try:
    from qfluentwidgets import MessageBox
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False

logger = logging.getLogger(__name__)

# 与文档/发布设置等本地偏好一致，使用固定组织名；应用名与 main.py 中 setApplicationName 一致
_SETTINGS_ORG = "WeMediaBaby"
_SETTINGS_APP = "媒小宝"
_KEY_LAST_VIDEO_IMPORT_DIR = "file_dialog/last_video_import_directory"


def get_last_video_import_directory() -> str:
    """上次「添加视频」文件/文件夹选择所在的目录；无效或不存在则返回空字符串。"""
    s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    d = s.value(_KEY_LAST_VIDEO_IMPORT_DIR, "")
    if isinstance(d, str) and d and os.path.isdir(d):
        return d
    return ""


def save_last_video_import_directory_from_path(path: str) -> None:
    """根据所选视频文件路径或文件夹路径，记住其所在目录供下次打开对话框使用。"""
    if not path:
        return
    try:
        p = os.path.abspath(os.path.normpath(path))
    except (OSError, ValueError):
        return
    d = p if os.path.isdir(p) else os.path.dirname(p)
    if d and os.path.isdir(d):
        QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(_KEY_LAST_VIDEO_IMPORT_DIR, d)


class FileSelectDialog:
    """文件选择对话框 - 用于选择文件或文件夹"""
    
    @staticmethod
    def select_file(parent: Optional[QWidget] = None) -> Optional[str]:
        """选择单个视频文件
        
        Args:
            parent: 父窗口
        
        Returns:
            选中的文件路径，如果取消则返回None
        """
        start = get_last_video_import_directory()
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "选择视频文件",
            start,
            "视频文件 (*.mp4 *.avi *.mov *.flv *.mkv *.wmv *.m4v *.webm);;所有文件 (*.*)"
        )
        
        if file_path:
            save_last_video_import_directory_from_path(file_path)
            return file_path
        return None
    
    @staticmethod
    def select_folder(parent: Optional[QWidget] = None) -> Optional[str]:
        """选择文件夹
        
        Args:
            parent: 父窗口
        
        Returns:
            选中的文件夹路径，如果取消则返回None
        """
        start = get_last_video_import_directory()
        folder_path = QFileDialog.getExistingDirectory(
            parent,
            "选择视频文件夹",
            start,
        )
        
        if folder_path:
            save_last_video_import_directory_from_path(folder_path)
            return folder_path
        return None
    
    @staticmethod
    def select_files(parent: Optional[QWidget] = None) -> List[str]:
        """选择多个视频文件
        
        Args:
            parent: 父窗口
        
        Returns:
            选中的文件路径列表，如果取消则返回空列表
        """
        start = get_last_video_import_directory()
        files, _ = QFileDialog.getOpenFileNames(
            parent,
            "选择视频文件",
            start,
            "视频文件 (*.mp4 *.avi *.mov *.flv *.mkv *.wmv *.m4v *.webm);;所有文件 (*.*)"
        )
        
        if files:
            save_last_video_import_directory_from_path(files[0])
        return files if files else []

