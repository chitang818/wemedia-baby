"""
抖音接口签名生成器模块 (脱机环境)
文件路径：src/infrastructure/security/douyin_signer.py
"""

import hashlib
import time
import urllib.parse
import os
import logging
from typing import Dict, Any

try:
    import execjs
except ImportError:
    logging.warning("尚未安装 PyExecJS 库。如需生成签名，请运行: pip install PyExecJS")

logger = logging.getLogger(__name__)

class DouyinSigner:
    """
    负责处理抖音 Web 端接口请求所需的各类防风控签名。
    包括但不限于 X-Bogus, _signature, msToken 等。
    在脱机(非浏览器)环境下，通过纯算法或内嵌 JS 沙盒生成签名。
    """
    
    def __init__(self, user_agent: str, js_path: str | None = None):
        self.user_agent = user_agent
        if not js_path:
            # 默认同目录下的 webmssdk.js
            js_path = os.path.join(os.path.dirname(__file__), "webmssdk.js")
        
        self.js_path = js_path
        self._ctx = None
        self._init_js_env()

    def _init_js_env(self):
        """初始化 JS 沙盒执行环境"""
        if not os.path.exists(self.js_path):
            logger.error(f"找不到签名 JS 文件: {self.js_path}，脱机签名将无法工作！")
            return
            
        try:
            with open(self.js_path, "r", encoding="utf-8") as f:
                js_code = f.read()
            self._ctx = execjs.compile(js_code)
            logger.info("签名 JS 沙盒初始化成功。")
        except Exception as e:
            logger.error(f"编译签名 JS 失败: {e}")

    def generate_msToken(self, length: int = 107) -> str:
        """
        生成虚拟的 msToken (随机字符串，有些接口不强校验，有些需要与 JS 环境强绑定)
        """
        import random
        import string
        characters = string.ascii_letters + string.digits + "-_"
        return "".join(random.choices(characters, k=length))
        
    def generate_x_bogus(self, url: str) -> str:
        """
        通过注入的 JS 沙盒调用签名函数生成 X-Bogus
        """
        if not self._ctx:
            logger.warning("JS 沙盒未初始化，返回占位签名。")
            return "DFK-XXXXXXXXXXXXXXXXXXXXXXXX"
            
        try:
            parsed = urllib.parse.urlparse(url)
            query_string = parsed.query
            
            # 通常逆向出来的 JS 函数名称如 'sign' 或 'getXBogus'
            # 传入 query_string 和 User-Agent
            # 注意: 这里假设 webmssdk.js 暴露了一个名为 `get_x_bogus` 的全局函数
            x_bogus = self._ctx.call("get_x_bogus", query_string, self.user_agent)
            return x_bogus
        except Exception as e:
            logger.error(f"执行 X-Bogus 签名失败: {e}")
            return "DFK-ERROR"

    def sign_request(self, method: str, url: str, headers: dict, json_data: dict | None = None) -> Dict[str, Any]:
        """
        对即将发送的请求进行完整签名，返回注入签名后的新 URL 和 Headers。
        """
        parsed = urllib.parse.urlparse(url)
        query = dict(urllib.parse.parse_qsl(parsed.query))
        
        # 补充常见的防爬参数
        if 'msToken' not in query:
            query['msToken'] = self.generate_msToken()
            
        # 重新拼接 URL 用于计算 X-Bogus
        new_query_str = urllib.parse.urlencode(query)
        url_for_sign = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{new_query_str}"
        
        # 计算 X-Bogus
        x_bogus = self.generate_x_bogus(url_for_sign)
        query['X-Bogus'] = x_bogus
        
        # 最终带签名的 URL
        final_query_str = urllib.parse.urlencode(query)
        final_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{final_query_str}"
        
        return {
            "url": final_url,
            "headers": headers
        }
