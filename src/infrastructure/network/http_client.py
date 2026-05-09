"""
异步HTTP客户端模块
文件路径：src/core/infrastructure/network/http_client.py
功能：提供异步HTTP请求，使用aiohttp替代requests，支持重试和熔断
"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any, Union
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pybreaker import CircuitBreaker

logger = logging.getLogger(__name__)


# 创建熔断器
circuit_breaker = CircuitBreaker(
    fail_max=5,  # 最多失败5次
    reset_timeout=30  # 熔断30秒后尝试恢复
)


class AsyncHttpClient:
    """异步HTTP客户端
    
    使用aiohttp进行所有HTTP请求，完全异步化。
    支持重试机制和熔断机制。
    """
    
    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        base_url: Optional[str] = None
    ):
        """初始化异步HTTP客户端
        
        Args:
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
            base_url: 基础URL（可选）
        """
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock: Optional[asyncio.Lock] = None  # 延迟创建，避免在无 loop 时初始化失败
        self.logger = logging.getLogger(__name__)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建HTTP会话（并发安全）"""
        if self._session_lock is None:
            self._session_lock = asyncio.Lock()
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    timeout=self.timeout,
                    base_url=self.base_url
                )
        return self._session
    
    async def close(self) -> None:
        """关闭HTTP会话"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    @circuit_breaker
    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """发送GET请求（异步，支持重试和熔断）
        
        Args:
            url: 请求URL
            params: 查询参数
            headers: 请求头
        
        Returns:
            响应JSON字典
        
        Raises:
            aiohttp.ClientError: HTTP请求错误
            asyncio.TimeoutError: 请求超时
        """
        session = await self._get_session()
        
        try:
            async with session.get(url, params=params, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            self.logger.error(f"GET请求失败: {url}, 错误: {e}", exc_info=True)
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    @circuit_breaker
    async def post(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """发送POST请求（异步，支持重试和熔断）
        
        Args:
            url: 请求URL
            data: 表单数据
            json: JSON数据
            headers: 请求头
        
        Returns:
            响应JSON字典
        
        Raises:
            aiohttp.ClientError: HTTP请求错误
            asyncio.TimeoutError: 请求超时
        """
        session = await self._get_session()
        
        try:
            async with session.post(url, data=data, json=json, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            self.logger.error(f"POST请求失败: {url}, 错误: {e}", exc_info=True)
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    @circuit_breaker
    async def put(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str]] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """发送PUT请求（异步，支持重试和熔断）
        
        Args:
            url: 请求URL
            data: 表单数据
            json: JSON数据
            headers: 请求头
        
        Returns:
            响应JSON字典
        
        Raises:
            aiohttp.ClientError: HTTP请求错误
            asyncio.TimeoutError: 请求超时
        """
        session = await self._get_session()
        
        try:
            async with session.put(url, data=data, json=json, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            self.logger.error(f"PUT请求失败: {url}, 错误: {e}", exc_info=True)
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    @circuit_breaker
    async def delete(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """发送DELETE请求（异步，支持重试和熔断）
        
        Args:
            url: 请求URL
            headers: 请求头
        
        Returns:
            响应JSON字典
        
        Raises:
            aiohttp.ClientError: HTTP请求错误
            asyncio.TimeoutError: 请求超时
        """
        session = await self._get_session()
        
        try:
            async with session.delete(url, headers=headers) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            self.logger.error(f"DELETE请求失败: {url}, 错误: {e}", exc_info=True)
            raise

