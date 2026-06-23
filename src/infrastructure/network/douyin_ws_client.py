"""
抖音脱机 WebSocket 客户端 (单一账号)
文件路径：src/infrastructure/network/douyin_ws_client.py
"""

import asyncio
import json
import logging
import gzip
from typing import Callable, Optional, Any

# 如果项目中没有安装 websockets，请在 requirements 中补充 `websockets>=11.0`
try:
    import websockets
except ImportError:
    logging.warning("尚未安装 websockets 库。如需使用脱机长连接，请运行: pip install websockets")

from src.infrastructure.security.douyin_signer import DouyinSigner

logger = logging.getLogger("douyin_ws_client")

class DouyinWsClient:
    """
    负责维护单个抖音账号与服务器的长连接。
    负责重连、心跳包维持、以及消息的抛出。
    """
    
    def __init__(self, account_id: str, cookies: str, user_agent: str, on_message: Callable[[str, dict], None]):
        self.account_id = account_id
        self.cookies = cookies
        self.user_agent = user_agent
        self.on_message = on_message  # 接收到消息时的回调函数: (account_id, msg_dict)
        
        self.ws: Optional[Any] = None
        self._is_running = False
        self._ping_task: Optional[asyncio.Task] = None
        
        self.signer = DouyinSigner(user_agent)
        
    async def start(self):
        """启动连接"""
        self._is_running = True
        while self._is_running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"[WS:{self.account_id}] 连接异常断开: {e}，5秒后重连...")
                await asyncio.sleep(5)

    async def stop(self):
        """停止连接"""
        self._is_running = False
        if self._ping_task:
            self._ping_task.cancel()
        if self.ws:
            await self.ws.close()
            logger.info(f"[WS:{self.account_id}] 连接已主动关闭。")

    async def _connect_and_listen(self):
        # 实际抓包中常见的 WSS 端点
        base_ws_url = "wss://frontier.snssdk.com/ws/v2"
        
        # 使用签名器为 WS URL 加上必要的防风控参数
        # 注意: 真实的抖音 wss 链接会在 query 中包含 device_id, app_name, msToken, X-Bogus 等几十个参数
        headers = {
            "Cookie": self.cookies,
            "User-Agent": self.user_agent
        }
        
        signed_req = self.signer.sign_request("GET", base_ws_url, headers)
        target_url = signed_req["url"]
        target_headers = signed_req["headers"]

        logger.info(f"[WS:{self.account_id}] 正在建立长连接...")
        
        # 建立连接
        async with websockets.connect(target_url, extra_headers=target_headers) as ws:
            self.ws = ws
            logger.info(f"[WS:{self.account_id}] 连接成功建立！")
            
            # 开启心跳协程
            self._ping_task = asyncio.create_task(self._keep_alive())
            
            # 监听消息
            async for message in ws:
                await self._handle_raw_message(message)

    async def _keep_alive(self):
        """定时发送心跳包以维持连接"""
        try:
            while self._is_running and self.ws:
                # 抖音心跳包通常为特定的 Protobuf 结构，这里使用伪代码占位
                ping_payload = b"PING" 
                await self.ws.send(ping_payload)
                await asyncio.sleep(30)  # 每30秒发送一次心跳
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"[WS:{self.account_id}] 心跳任务异常: {e}")

    async def _handle_raw_message(self, message: bytes | str):
        """
        处理原始二进制封包
        抖音的长连接通常会对载荷进行 Gzip 压缩，解压后可能是 Protobuf 或者 JSON
        """
        try:
            if isinstance(message, str):
                message = message.encode('utf-8')
                
            # 1. 尝试解压 Gzip
            # gzip 魔数是 1f 8b
            if len(message) > 2 and message[0] == 0x1f and message[1] == 0x8b:
                uncompressed_data = gzip.decompress(message)
                logger.debug(f"[WS:{self.account_id}] 成功解压 Gzip 封包，大小: {len(uncompressed_data)} bytes")
            else:
                uncompressed_data = message
                
            # 2. 尝试解析 (Protobuf / JSON)
            # 这里先尝试当作 JSON 解析，如果是 Protobuf 必须替换为 .proto 生成的解析类
            msg_dict = {}
            try:
                # 若为 JSON 格式
                text_data = uncompressed_data.decode('utf-8', errors='ignore')
                msg_dict = json.loads(text_data)
                logger.info(f"[WS:{self.account_id}] 解析到 JSON 消息: {msg_dict.get('method', 'unknown')}")
            except json.JSONDecodeError:
                # 走到这里通常说明是 Protobuf 格式，或者自定义二进制封包
                # TODO: my_douyin_pb2.Frame().ParseFromString(uncompressed_data)
                msg_dict = {
                    "raw_size": len(message), 
                    "type": "binary_protobuf", 
                    "hint": "需要在此处接入从逆向获取的 .proto 解析器"
                }
            
            # 3. 触发回调，交由上层（Manager）处理
            if self.on_message:
                self.on_message(self.account_id, msg_dict)
                
        except Exception as e:
            logger.error(f"[WS:{self.account_id}] 解包或解析消息失败: {e}")
