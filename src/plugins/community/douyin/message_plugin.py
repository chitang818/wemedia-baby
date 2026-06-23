"""
抖音私信插件
文件路径：src/plugins/community/douyin/message_plugin.py
"""

import asyncio
import logging
from datetime import datetime
from typing import List

from src.plugins.core.interfaces.message_plugin import MessagePluginInterface
from src.domain.models.interaction import MessageSession, Message
from src.services.browser.patchright_service import PatchrightService

logger = logging.getLogger(__name__)

class DouyinMessagePlugin(MessagePluginInterface):
    """
    抖音私信插件
    基于 Playwright 实现，通过控制隐藏的浏览器与创作者中心 DOM 交互来拉取和发送私信。
    """
    
    def __init__(self):
        self._browser_service = PatchrightService()

    @property
    def platform_id(self) -> str:
        return "douyin"

    async def get_sessions(self, account_id: str, limit: int = 20) -> List[MessageSession]:
        """获取最近会话列表"""
        logger.info(f"正在拉取抖音账号 {account_id} 的会话列表...")
        # TODO: 由于需要真实的浏览器上下文，这里展示骨架实现
        # 实际实现需要：
        # 1. context = await self._browser_service.get_or_create_context(self.platform_id, account_id)
        # 2. page = await context.new_page()
        # 3. await page.goto("https://creator.douyin.com/creator-micro/interaction/message")
        # 4. 解析左侧 `.contact-list` 的 DOM 节点
        
        # 为了演示和不阻塞进程，我们返回假数据或占位
        await asyncio.sleep(1) # 模拟网络延迟
        return [
            MessageSession(
                session_id="session_123",
                target_id="user_456",
                target_name="测试粉丝A",
                target_avatar="",
                last_message="催更啦",
                unread_count=1,
                update_time=datetime.now()
            )
        ]

    async def get_messages(self, account_id: str, session_id: str, limit: int = 50) -> List[Message]:
        """获取指定会话的消息记录"""
        logger.info(f"正在拉取会话 {session_id} 的历史消息...")
        # TODO: 实际实现中需要点击对应的 session_id 然后提取右侧聊天气泡
        await asyncio.sleep(1)
        return [
            Message(
                message_id="msg_001",
                content="催更啦，什么时候发新视频？",
                sender_id="user_456",
                sender_name="测试粉丝A",
                is_self=False,
                create_time=datetime.now()
            )
        ]

    async def send_message(self, account_id: str, session_id: str, content: str) -> bool:
        """发送私信回复"""
        logger.info(f"正在向会话 {session_id} 发送回复: {content}")
        # TODO: 实际实现中需要 page.fill("textarea", content) 然后 page.click("button.send")
        await asyncio.sleep(1)
        return True
