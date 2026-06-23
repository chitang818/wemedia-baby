"""
互动与私信管理页面
文件路径：src/ui/pages/interaction/message_page.py
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTreeWidgetItem
import qasync
from qfluentwidgets import (
    ScrollArea, 
    LineEdit, 
    PrimaryPushButton, 
    ListWidget, 
    TreeWidget,
    SubtitleLabel, 
    TextEdit,
    InfoBar,
    InfoBarPosition
)

from src.infrastructure.common.di.service_locator import ServiceLocator
from src.services.account.account_service import AccountService
from src.services.auth.current_user_service import CurrentUserService

class MessagePage(QWidget):
    """
    私信聚合管理界面
    负责展示多账号的私信会话及实时聊天内容
    """
    
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("message_page")
        
        # 页面主布局 (左右分栏)
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(16)
        
        # --- 左侧：会话列表 ---
        self.left_widget = QWidget()
        self.left_layout = QVBoxLayout(self.left_widget)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        
        self.title_label = SubtitleLabel("账号与会话", self)
        
        # 使用树状视图来按平台展示账号
        self.account_tree = TreeWidget(self)
        self.account_tree.setHeaderHidden(True)
        self.account_tree.itemClicked.connect(self._on_account_clicked)
        
        self.left_layout.addWidget(self.title_label)
        self.left_layout.addWidget(self.account_tree)
        
        # --- 右侧：聊天主窗口 ---
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.chat_title = SubtitleLabel("与 粉丝张三 聊天中...", self)
        
        # 消息流显示区 (ScrollArea)
        self.message_area = ScrollArea(self)
        self.message_area.setWidgetResizable(True)
        self.message_content = ListWidget(self.message_area)
        self.message_content.addItem("粉丝张三: 你好，请问这个产品怎么卖？")
        self.message_content.addItem("我: 您好，这款产品目前售价 99 元。")
        self.message_area.setWidget(self.message_content)
        
        # 底部输入区
        self.input_layout = QHBoxLayout()
        self.input_edit = TextEdit(self)
        self.input_edit.setPlaceholderText("请输入回复内容，按 Enter 发送...")
        self.input_edit.setMaximumHeight(80)
        
        self.send_button = PrimaryPushButton("发送", self)
        
        self.input_layout.addWidget(self.input_edit)
        self.input_layout.addWidget(self.send_button)
        
        self.right_layout.addWidget(self.chat_title)
        self.right_layout.addWidget(self.message_area)
        self.right_layout.addLayout(self.input_layout)
        
        # 设置左右比例分配
        self.main_layout.addWidget(self.left_widget, 1)
        self.main_layout.addWidget(self.right_widget, 2)
        
        # 绑定事件
        self.send_button.clicked.connect(self._on_send_clicked)
        
        # 延迟异步加载数据，确保 UI 层级挂载完毕
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._trigger_load)

    def _trigger_load(self):
        import asyncio
        asyncio.create_task(self.load_accounts())

    async def load_accounts(self):
        """从本地数据库拉取已登录的账号"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            service_locator = ServiceLocator()
            account_service = service_locator.get(AccountService)
            current_user_service = service_locator.get(CurrentUserService)
            
            user_id = current_user_service.get_user_id_or_default()
            logger.info(f"MessagePage: 正在为 user_id={user_id} 拉取已登录账号...")
            
            accounts = await account_service.get_accounts(user_id=user_id)
            logger.info(f"MessagePage: 成功拉取到 {len(accounts)} 个账号。")
            
            self.account_tree.clear()
            
            if not accounts:
                empty_item = QTreeWidgetItem(["(暂无已登录的账号)"])
                self.account_tree.addTopLevelItem(empty_item)
                return
                
            # 按平台分组
            platform_dict = {}
            for acc in accounts:
                platform_dict.setdefault(acc.platform, []).append(acc)
                
            self.account_tree.clear()
            for platform, acc_list in platform_dict.items():
                platform_item = QTreeWidgetItem([platform.capitalize()])
                platform_item.setFlags(platform_item.flags() & ~Qt.ItemFlag.ItemIsSelectable) # 平台不可点
                
                for acc in acc_list:
                    # 将实体数据存入 Data 角色中
                    display_name = acc.account_name or acc.platform_username or "未知账号"
                    acc_item = QTreeWidgetItem([display_name])
                    acc_item.setData(0, Qt.ItemDataRole.UserRole, {"id": acc.account_id, "platform": acc.platform})
                    platform_item.addChild(acc_item)
                
                self.account_tree.addTopLevelItem(platform_item)
                platform_item.setExpanded(True)
                
        except Exception as e:
            InfoBar.error("加载失败", f"无法读取本地账号: {e}", position=InfoBarPosition.TOP, parent=self)

    def _on_account_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data:
            # 说明点击的是具体的账号
            account_name = item.text(0)
            platform = data["platform"]
            
            self.chat_title.setText(f"【{platform}】{account_name} 的私信记录")
            self.message_content.clear()
            self.message_content.addItem("系统提示: 已切换账号。等待获取真实私信内容...")
            
            # TODO: 调用底层的 im_connection_manager 载入该账号的 websocket 会话

    def _on_send_clicked(self):
        text = self.input_edit.toPlainText().strip()
        if text:
            # TODO: 调用底层的 im_connection_manager 或 im_service 发送接口
            self.message_content.addItem(f"我: {text}")
            self.input_edit.clear()
