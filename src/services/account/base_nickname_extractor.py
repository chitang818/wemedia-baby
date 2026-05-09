"""
昵称提取器基类
文件路径: src/services/account/base_nickname_extractor.py

提供通用的昵称提取逻辑,子类只需配置平台特定的选择器和关键词
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import logging
import json

logger = logging.getLogger(__name__)


class BaseNicknameExtractor(ABC):
    """昵称提取器基类
    
    提供通用的昵称提取逻辑,子类只需配置平台特定的选择器和关键词
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def get_selector_config(self) -> Dict[str, List[str]]:
        """获取平台特定的选择器配置
        
        Returns:
            包含不同优先级选择器的字典:
            {
                'priority1_selectors': [...],  # 最高优先级
                'priority2_selectors': [...],  # 次优先级
            }
        """
        pass
    
    @abstractmethod
    def get_invalid_keywords(self) -> List[str]:
        """获取平台特定的无效关键词列表
        
        Returns:
            需要过滤的关键词列表,如 ['登录', '注册', ...]
        """
        pass
    
    @abstractmethod
    def get_global_var_sources(self) -> List[str]:
        """获取全局变量来源列表
        
        Returns:
            全局变量名列表,如 ['__INITIAL_STATE__', '__USER_INFO__', ...]
        """
        pass
    
    def generate_nickname_extraction_script(self) -> str:
        """生成昵称提取JavaScript脚本(通用实现)
        
        Returns:
            完整的JavaScript脚本字符串
        """
        config = self.get_selector_config()
        invalid_keywords = self.get_invalid_keywords()
        global_vars = self.get_global_var_sources()
        
        # 将Python列表转换为JavaScript数组字符串
        invalid_keywords_js = json.dumps(invalid_keywords, ensure_ascii=False)
        
        # 生成JavaScript代码
        script = f"""
        (function() {{
            try {{
                var result = {{
                    nickname: '',
                    source: '',
                    debug: []
                }};
                
                result.debug.push('页面readyState: ' + document.readyState);
                result.debug.push('当前URL: ' + window.location.href);
                
                var nickname = '';
                
                // 辅助函数:清理和验证昵称
                function cleanAndValidate(text) {{
                    if (!text) return '';
                    text = text.trim();
                    if (text.length >= 1 && text.length <= 50) {{
                        var invalidKeywords = {invalid_keywords_js};
                        for (var k = 0; k < invalidKeywords.length; k++) {{
                            if (text === invalidKeywords[k]) return '';
                        }}
                        if (text.startsWith('http')) return '';
                        return text;
                    }}
                    return '';
                }}
                
                {self._generate_priority_selectors_js(config.get('priority1_selectors', []), 'priority1')}
                
                {self._generate_priority_selectors_js(config.get('priority2_selectors', []), 'priority2')}
                
                {self._generate_global_vars_js(global_vars)}
                
                // 最终验证
                if (nickname) {{
                    nickname = cleanAndValidate(nickname);
                }}
                
                result.nickname = nickname;
                if (!nickname) {{
                    result.debug.push('❌ 所有方法均未能提取到昵称');
                }}
                return JSON.stringify(result);
            }} catch (e) {{
                return JSON.stringify({{
                    nickname: '',
                    source: '',
                    error: e.toString(),
                    debug: ['异常: ' + e.toString()]
                }});
            }}
        }})();
        """
        return script
    
    def _generate_priority_selectors_js(self, selectors: List[str], priority_name: str) -> str:
        """生成选择器JavaScript代码片段"""
        if not selectors:
            return ""
        
        selectors_js = json.dumps(selectors, ensure_ascii=False)
        
        return f"""
                // 优先级: {priority_name}
                if (!nickname) {{
                    var selectors_{priority_name} = {selectors_js};
                    result.debug.push('尝试 ' + selectors_{priority_name}.length + ' 个{priority_name}选择器');
                    for (var i = 0; i < selectors_{priority_name}.length; i++) {{
                        var el = document.querySelector(selectors_{priority_name}[i]);
                        if (el) {{
                            var text = el.innerText || el.textContent;
                            result.debug.push('选择器 [' + selectors_{priority_name}[i] + '] 找到元素,文本: "' + text + '"');
                            var cleaned = cleanAndValidate(text);
                            if (cleaned) {{
                                nickname = cleaned;
                                result.source = '{priority_name}_element_' + selectors_{priority_name}[i];
                                result.debug.push('✅ 从{priority_name}元素提取成功: ' + nickname);
                                break;
                            }} else {{
                                result.debug.push('验证失败,文本无效');
                            }}
                        }}
                    }}
                }}
        """
    
    def _generate_global_vars_js(self, global_vars: List[str]) -> str:
        """生成全局变量提取JavaScript代码"""
        if not global_vars:
            return ""
        
        js_code = """
                // 全局变量提取
                if (!nickname) {
                    result.debug.push('尝试从全局变量提取');
                    try {
        """
        
        for var_name in global_vars:
            js_code += f"""
                        // {var_name}
                        if (!nickname && window.{var_name}) {{
                            result.debug.push('发现 window.{var_name}');
                            var state = window.{var_name};
                            if (state.user) {{
                                nickname = state.user.name || state.user.nickname;
                                if (nickname) result.source = '{var_name}.user';
                            }}
                            if (!nickname && state.userInfo) {{
                                nickname = state.userInfo.name || state.userInfo.nickname;
                                if (nickname) result.source = '{var_name}.userInfo';
                            }}
                            if (!nickname && state.creator) {{
                                nickname = state.creator.name || state.creator.nickname;
                                if (nickname) result.source = '{var_name}.creator';
                            }}
                            if (nickname) {{
                                result.debug.push('✅ 从 {var_name} 提取成功: ' + nickname);
                            }}
                        }}
            """
        
        # localStorage和sessionStorage
        js_code += """
                        // localStorage
                        if (!nickname) {
                            try {
                                var storedUser = localStorage.getItem('user_info') || localStorage.getItem('userInfo');
                                if (storedUser) {
                                    result.debug.push('发现 localStorage 用户信息');
                                    var parsed = JSON.parse(storedUser);
                                    nickname = parsed.nickname || parsed.name || parsed.userName;
                                    if (nickname) {
                                        result.source = 'localStorage';
                                        result.debug.push('✅ 从 localStorage 提取成功: ' + nickname);
                                    }
                                }
                            } catch(e) {
                                result.debug.push('localStorage 解析失败: ' + e.message);
                            }
                        }
                        
                        // sessionStorage
                        if (!nickname) {
                            try {
                                var sessionUser = sessionStorage.getItem('user_info') || sessionStorage.getItem('userInfo');
                                if (sessionUser) {
                                    result.debug.push('发现 sessionStorage 用户信息');
                                    var parsed = JSON.parse(sessionUser);
                                    nickname = parsed.nickname || parsed.name || parsed.userName;
                                    if (nickname) {
                                        result.source = 'sessionStorage';
                                        result.debug.push('✅ 从 sessionStorage 提取成功: ' + nickname);
                                    }
                                }
                            } catch(e) {
                                result.debug.push('sessionStorage 解析失败: ' + e.message);
                            }
                        }
                    } catch(e) {
                        result.debug.push('全局变量提取异常: ' + e.message);
                    }
                }
        """
        
        return js_code
