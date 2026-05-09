"""
登录检测器基类
提供通用的Cookie登录检测逻辑
文件路径: src/services/account/base_login_detector.py
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class BaseLoginDetector(ABC):
    """登录检测器基类
    
    提供通用的Cookie登录检测逻辑,子类只需实现配置方法
    """
    
    def __init__(self):
        """初始化登录检测器"""
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def get_critical_cookies(self) -> List[str]:
        """获取核心Cookie列表
        
        核心Cookie必须存在才能判定为已登录
        
        Returns:
            核心Cookie名称列表
            
        Example:
            return ['sessionid', 'sessionid_ss']
        """
        pass
    
    @abstractmethod
    def get_supporting_cookies(self) -> List[str]:
        """获取辅助Cookie列表
        
        辅助Cookie用于增强检测可靠性,但不是必需的
        
        Returns:
            辅助Cookie名称列表
            
        Example:
            return ['sid_ucp_v1', 'sid_tt', 'passport_csrf_token']
        """
        pass
    
    @abstractmethod
    def validate_login_by_cookies(
        self, 
        found_critical: List[str], 
        found_supporting: List[str]
    ) -> bool:
        """根据找到的Cookie判断是否登录
        
        子类可以实现自定义的验证逻辑,例如:
        - 至少需要1个核心Cookie
        - 必须所有核心Cookie都存在
        - 核心Cookie + 辅助Cookie的组合判断
        
        Args:
            found_critical: 找到的核心Cookie列表
            found_supporting: 找到的辅助Cookie列表
        
        Returns:
            是否已登录
            
        Example:
            # 至少需要一个核心Cookie
            return len(found_critical) > 0
            
            # 必须所有核心Cookie都存在
            return len(found_critical) == len(self.get_critical_cookies())
        """
        pass
    
    def detect_by_cookies(self, cookies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """通过Cookie检测登录状态(通用实现)
        
        这是基类提供的通用实现,子类通常不需要重写此方法
        
        Args:
            cookies: Cookie列表,每个元素包含name, value, domain等字段
        
        Returns:
            检测结果字典:
            {
                'is_logged_in': bool,           # 是否已登录
                'found_critical': List[str],    # 找到的核心Cookie
                'found_supporting': List[str],  # 找到的辅助Cookie
                'missing_critical': List[str],  # 缺失的核心Cookie
                'cookie_count': int             # 总Cookie数量
            }
        """
        result = {
            'is_logged_in': False,
            'found_critical': [],
            'found_supporting': [],
            'missing_critical': [],
            'cookie_count': 0
        }
        
        if not cookies:
            self.logger.warning("Cookie列表为空,无法检测登录状态")
            return result
        
        # 构建Cookie字典(名称小写化以便匹配)
        cookie_map = {
            c.get('name', '').lower(): c 
            for c in cookies 
            if c.get('name')
        }
        
        self.logger.debug(f"收到{len(cookies)}个Cookie,有效Cookie {len(cookie_map)}个")
        
        # 获取配置(转为小写以便匹配)
        critical_cookies = [c.lower() for c in self.get_critical_cookies()]
        supporting_cookies = [c.lower() for c in self.get_supporting_cookies()]
        
        # 检查核心Cookie
        for cookie_name in critical_cookies:
            if cookie_name in cookie_map:
                result['found_critical'].append(cookie_name)
                self.logger.debug(f"✓ 找到核心Cookie: {cookie_name}")
            else:
                result['missing_critical'].append(cookie_name)
                self.logger.debug(f"✗ 缺失核心Cookie: {cookie_name}")
        
        # 检查辅助Cookie
        for cookie_name in supporting_cookies:
            if cookie_name in cookie_map:
                result['found_supporting'].append(cookie_name)
                self.logger.debug(f"✓ 找到辅助Cookie: {cookie_name}")
        
        # 统计总数
        result['cookie_count'] = len(result['found_critical']) + len(result['found_supporting'])
        
        # 调用子类的验证逻辑
        result['is_logged_in'] = self.validate_login_by_cookies(
            result['found_critical'],
            result['found_supporting']
        )
        
        # 记录检测结果
        if result['is_logged_in']:
            self.logger.info(
                f"✅ Cookie检测通过: 找到{len(result['found_critical'])}个核心Cookie, "
                f"{len(result['found_supporting'])}个辅助Cookie"
            )
        else:
            self.logger.warning(
                f"❌ Cookie检测未通过: 缺失核心Cookie {result['missing_critical']}"
            )
        
        return result
