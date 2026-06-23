"""
多账号即时通讯长连接管理器
文件路径：src/services/interaction/im_connection_manager.py
"""

import asyncio
import logging
from typing import Dict

from src.infrastructure.network.douyin_ws_client import DouyinWsClient
from src.infrastructure.common.event.event_bus import EventBus  # 假设项目中有基础的事件总线
from src.infrastructure.common.event.events import ImNewMessageEvent

logger = logging.getLogger("im_connection_manager")

class ImConnectionManager:
    """
    管理所有账号的脱机 WebSocket 长连接的生命周期。
    支持高并发的异步连接，将收取到的消息统一分发到 EventBus 供 UI 消费。
    """
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.clients: Dict[str, DouyinWsClient] = {}
        self.tasks: Dict[str, asyncio.Task] = {}
        
    def _on_message_received(self, account_id: str, msg_dict: dict):
        """内部回调：当任意一个客户端收到消息时触发"""
        logger.info(f"[IMManager] 账号 {account_id} 收到新消息: {msg_dict}")
        
        # 将消息持久化到 SQLite 数据库 (此处逻辑后续交由服务层处理)
        # TODO: self.repository.save_message(account_id, msg_dict)
        
        # 将消息抛给事件总线，通知 UI 更新
        self.event_bus.publish_sync(ImNewMessageEvent(account_id=account_id, message=msg_dict))
        
    async def add_account_connection(self, account_id: str, cookies: str, user_agent: str):
        """为指定账号添加并启动长连接"""
        if account_id in self.clients:
            logger.warning(f"账号 {account_id} 的长连接已存在。")
            return
            
        client = DouyinWsClient(
            account_id=account_id,
            cookies=cookies,
            user_agent=user_agent,
            on_message=self._on_message_received
        )
        
        self.clients[account_id] = client
        
        # 在后台以协程方式启动
        task = asyncio.create_task(client.start())
        self.tasks[account_id] = task
        logger.info(f"已启动账号 {account_id} 的监听任务。")
        
    async def remove_account_connection(self, account_id: str):
        """主动断开并移除指定账号的长连接"""
        if account_id in self.clients:
            client = self.clients.pop(account_id)
            await client.stop()
            
        if account_id in self.tasks:
            task = self.tasks.pop(account_id)
            task.cancel()
            logger.info(f"已移除账号 {account_id} 的监听任务。")
            
    async def start_all(self, account_list: list):
        """
        初始化时批量启动。
        account_list 格式例如: [{"account_id": "xxx", "cookies": "yyy", "user_agent": "zzz"}, ...]
        """
        logger.info(f"准备批量启动 {len(account_list)} 个账号的脱机长连接...")
        for acc in account_list:
            await self.add_account_connection(
                acc["account_id"],
                acc["cookies"],
                acc["user_agent"]
            )
            
    async def stop_all(self):
        """停止所有连接（通常在退出程序时调用）"""
        logger.info("正在关闭所有长连接...")
        for account_id in list(self.clients.keys()):
            await self.remove_account_connection(account_id)
        logger.info("所有长连接已成功关闭。")
