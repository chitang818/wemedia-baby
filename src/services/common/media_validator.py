"""
媒体文件验证器
文件路径：src/business/common/media_validator.py
功能：验证媒体文件的有效性（格式、大小、平台适配性）
"""

from pathlib import Path
from typing import Dict, Any
import logging

from ...utils.file_utils import (
    is_valid_video_file, is_valid_image_file, get_file_size
)

logger = logging.getLogger(__name__)


# 平台文件大小限制（单位：字节）
PLATFORM_SIZE_LIMITS: Dict[str, Dict[str, int]] = {
    'douyin': {
        'video': 4 * 1024 * 1024 * 1024,  # 4GB
        'image': 20 * 1024 * 1024,  # 20MB
    },
    'kuaishou': {
        'video': 2 * 1024 * 1024 * 1024,  # 2GB
        'image': 10 * 1024 * 1024,  # 10MB
    },
    'xiaohongshu': {
        'video': 1 * 1024 * 1024 * 1024,  # 1GB
        'image': 10 * 1024 * 1024,  # 10MB
    }
}

# 支持的视频格式
SUPPORTED_VIDEO_FORMATS = {'.mp4', '.avi', '.mov', '.flv', '.mkv', '.wmv', '.m4v'}

# 支持的图片格式
SUPPORTED_IMAGE_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}


class MediaValidator:
    """媒体文件验证器"""
    
    def __init__(self):
        """初始化媒体验证器"""
        self.logger = logging.getLogger(__name__)
    
    def validate_format(
        self,
        file_path: str,
        file_type: str,
        platform: str
    ) -> bool:
        """验证文件格式
        
        Args:
            file_path: 文件路径
            file_type: 文件类型（video/image）
            platform: 平台名称
            
        Returns:
            如果格式支持返回True，否则返回False
        """
        try:
            file_path_obj = Path(file_path)
            extension = file_path_obj.suffix.lower()
            
            if file_type == 'video':
                if extension not in SUPPORTED_VIDEO_FORMATS:
                    self.logger.warning(
                        f"不支持的视频格式: {extension}, 文件: {file_path}"
                    )
                    return False
                if not is_valid_video_file(file_path):
                    self.logger.warning(f"无效的视频文件: {file_path}")
                    return False
                    
            elif file_type == 'image':
                if extension not in SUPPORTED_IMAGE_FORMATS:
                    self.logger.warning(
                        f"不支持的图片格式: {extension}, 文件: {file_path}"
                    )
                    return False
                if not is_valid_image_file(file_path):
                    self.logger.warning(f"无效的图片文件: {file_path}")
                    return False
            else:
                self.logger.warning(f"不支持的文件类型: {file_type}")
                return False
            
            self.logger.debug(f"文件格式验证通过: {file_path}, 类型={file_type}")
            return True
            
        except Exception as e:
            self.logger.error(f"验证文件格式时出错: {e}", exc_info=True)
            return False
    
    def validate_size(
        self,
        file_path: str,
        file_type: str,
        platform: str
    ) -> bool:
        """验证文件大小
        
        Args:
            file_path: 文件路径
            file_type: 文件类型（video/image）
            platform: 平台名称
            
        Returns:
            如果大小符合要求返回True，否则返回False
        """
        try:
            # 获取平台大小限制
            platform_limits = PLATFORM_SIZE_LIMITS.get(platform, {})
            max_size = platform_limits.get(file_type)
            
            if max_size is None:
                # 如果没有配置，使用默认限制
                max_size = 4 * 1024 * 1024 * 1024  # 默认4GB
                self.logger.warning(
                    f"平台 {platform} 未配置 {file_type} 大小限制，使用默认值: {max_size}"
                )
            
            # 获取文件大小
            file_size = get_file_size(file_path)
            
            if file_size > max_size:
                self.logger.warning(
                    f"文件大小超出限制: {file_path}, "
                    f"大小={file_size}, 限制={max_size}"
                )
                return False
            
            self.logger.debug(
                f"文件大小验证通过: {file_path}, 大小={file_size}, 限制={max_size}"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"验证文件大小时出错: {e}", exc_info=True)
            return False
    
    def validate(
        self,
        file_path: str,
        file_type: str,
        platform: str
    ) -> tuple[bool, str]:
        """综合验证文件（格式和大小）
        
        Args:
            file_path: 文件路径
            file_type: 文件类型（video/image）
            platform: 平台名称
            
        Returns:
            (是否通过, 错误信息)
        """
        # 检查文件是否存在
        if not Path(file_path).exists():
            return False, f"文件不存在: {file_path}"
        
        # 验证格式
        if not self.validate_format(file_path, file_type, platform):
            return False, f"文件格式不支持: {file_path}"
        
        # 验证大小
        if not self.validate_size(file_path, file_type, platform):
            return False, f"文件大小超出限制: {file_path}"
        
        return True, ""

