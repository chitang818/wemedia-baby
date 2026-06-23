"""
私信管理页面（Pro 功能）
文件路径：src/pro_features/interaction/pages/private_message_page.py
功能：多平台私信查看与回复
"""

from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, 
    QListWidgetItem, QTextEdit
)
from PySide6.QtCore import Qt

from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, ComboBox, PushButton,
    FluentIcon, InfoBar, InfoBarPosition, ScrollArea, TextEdit
)

from src.ui.pages.base_page import BasePage
from src.services.interaction.message_service import message_service
from src.domain.models.interaction import MessageSession, Message
# 使用 qasync 的 asyncSlot 处理异步操作
from qasync import asyncSlot

class PrivateMessagePage(BasePage):
    """私信管理页面 - 查看与回复各平台私信"""

    def __init__(self, parent: Optional[QWidget] = None):
        BasePage.__init__(self, "私信管理", parent)
        self.current_platform = "douyin"
        self.current_account_id = "test_account"  # 模拟选中账号
        self.current_session: Optional[MessageSession] = None
        self._setup_content()
        # 初始化加载会话
        self._load_sessions()

    def _setup_content(self):
        # 整体布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.addLayout(main_layout)

        # 顶部工具栏
        toolbar_card = CardWidget(self)
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        
        self.platform_combo = ComboBox(self)
        self.platform_combo.addItem("抖音", userData="douyin")
        self.platform_combo.addItem("快手", userData="kuaishou")
        
        self.account_combo = ComboBox(self)
        self.account_combo.addItem("我的账号1", userData="test_account")
        
        refresh_btn = PushButton(FluentIcon.SYNC, "刷新", self)
        refresh_btn.clicked.connect(self._load_sessions)

        toolbar_layout.addWidget(SubtitleLabel("私信互动中心", self))
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(BodyLabel("平台:", self))
        toolbar_layout.addWidget(self.platform_combo)
        toolbar_layout.addWidget(BodyLabel("账号:", self))
        toolbar_layout.addWidget(self.account_combo)
        toolbar_layout.addWidget(refresh_btn)
        main_layout.addWidget(toolbar_card)

        # 主体 Splitter
        self.splitter = QSplitter(Qt.Horizontal, self)
        main_layout.addWidget(self.splitter, 1)

        # 左侧：会话列表
        self.session_list_widget = QListWidget(self)
        self.session_list_widget.setStyleSheet(
            "QListWidget { background: transparent; border: 1px solid #e0e0e0; border-radius: 4px; }"
            "QListWidget::item { padding: 12px; border-bottom: 1px solid #f0f0f0; }"
            "QListWidget::item:selected { background: #eef6ff; }"
        )
        self.session_list_widget.itemClicked.connect(self._on_session_clicked)
        self.splitter.addWidget(self.session_list_widget)

        # 右侧：聊天区域
        self.chat_widget = QWidget(self)
        chat_layout = QVBoxLayout(self.chat_widget)
        chat_layout.setContentsMargins(12, 0, 0, 0)

        # 聊天记录区域
        self.chat_history_area = QListWidget(self)
        self.chat_history_area.setStyleSheet(
            "QListWidget { background: transparent; border: 1px solid #e0e0e0; border-radius: 4px; padding: 8px; }"
            "QListWidget::item { padding: 4px; }"
        )
        chat_layout.addWidget(self.chat_history_area, 1)

        # 输入区域
        input_container = QWidget(self)
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(0, 8, 0, 0)
        
        self.message_input = TextEdit(self)
        self.message_input.setPlaceholderText("输入回复内容...")
        self.message_input.setMaximumHeight(80)
        
        self.send_btn = PushButton(FluentIcon.SEND, "发送", self)
        self.send_btn.clicked.connect(self._on_send_clicked)

        input_layout.addWidget(self.message_input, 1)
        input_layout.addWidget(self.send_btn)
        
        chat_layout.addWidget(input_container)
        self.splitter.addWidget(self.chat_widget)
        
        # 初始占比 左3:右7
        self.splitter.setSizes([300, 700])

    @asyncSlot()
    async def _load_sessions(self):
        """异步加载会话列表"""
        self.session_list_widget.clear()
        self.session_list_widget.addItem("加载中...")
        
        sessions = await message_service.get_sessions(self.current_platform, self.current_account_id)
        self.session_list_widget.clear()
        
        if not sessions:
            self.session_list_widget.addItem("暂无私信会话")
            return

        for s in sessions:
            item = QListWidgetItem()
            # 这里简单用文本展示，实际可以定制 QWidget item
            display_text = f"{s.target_name}\n{s.last_message}"
            item.setText(display_text)
            item.setData(Qt.UserRole, s)
            self.session_list_widget.addItem(item)

    @asyncSlot()
    async def _on_session_clicked(self, item: QListWidgetItem):
        """点击左侧会话，加载聊天记录"""
        session: MessageSession = item.data(Qt.UserRole)
        if not session:
            return
        self.current_session = session
        self.chat_history_area.clear()
        self.chat_history_area.addItem("加载历史消息中...")
        
        messages = await message_service.get_messages(self.current_platform, self.current_account_id, session.session_id)
        self.chat_history_area.clear()
        
        for msg in messages:
            self._append_message_to_ui(msg)

    def _append_message_to_ui(self, msg: Message):
        """将单条消息追加到右侧聊天区"""
        item = QListWidgetItem()
        prefix = "我" if msg.is_self else msg.sender_name
        time_str = msg.create_time.strftime("%H:%M")
        item.setText(f"[{time_str}] {prefix}: {msg.content}")
        # 如果是我发出的，文字靠右或改个颜色
        if msg.is_self:
            item.setTextAlignment(Qt.AlignRight)
        self.chat_history_area.addItem(item)
        self.chat_history_area.scrollToBottom()

    @asyncSlot()
    async def _on_send_clicked(self):
        """点击发送按钮"""
        if not self.current_session:
            InfoBar.warning(
                title="提示",
                content="请先选择一个会话",
                parent=self,
                position=InfoBarPosition.TOP
            )
            return
        
        text = self.message_input.toPlainText().strip()
        if not text:
            return

        self.send_btn.setEnabled(False)
        success = await message_service.send_message(
            self.current_platform, 
            self.current_account_id, 
            self.current_session.session_id, 
            text
        )
        self.send_btn.setEnabled(True)
        
        if success:
            self.message_input.clear()
            # 本地构造一条消息显示上去
            from datetime import datetime
            new_msg = Message(
                message_id="local_temp_id",
                content=text,
                sender_id=self.current_account_id,
                sender_name="我",
                is_self=True,
                create_time=datetime.now()
            )
            self._append_message_to_ui(new_msg)
            InfoBar.success("发送成功", "已回复", parent=self, position=InfoBarPosition.TOP)
        else:
            InfoBar.error("发送失败", "请稍后重试", parent=self, position=InfoBarPosition.TOP)

