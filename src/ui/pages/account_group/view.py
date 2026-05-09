"""
账号组管理页面
文件路径：src/ui/pages/account_group/view.py
功能：账号组的创建、编辑、删除和账号分配
"""

# pyre-ignore-all-errors
import asyncio
import logging
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea,
    QGridLayout, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal, QSize
from qfluentwidgets import (
    CardWidget, BodyLabel, SubtitleLabel, CaptionLabel,
    PushButton, ToolButton, FluentIcon, InfoBar, InfoBarPosition,
    SearchLineEdit, IconWidget, isDarkTheme
)

from src.services.account import AccountGroupService
from src.infrastructure.common.di.service_locator import ServiceLocator

logger = logging.getLogger(__name__)


class AccountGroupCard(CardWidget):
    """账号组卡片组件"""
    
    # 信号
    edit_clicked = Signal(dict)  # 编辑按钮点击
    delete_clicked = Signal(dict)  # 删除按钮点击
    add_account_clicked = Signal(dict) # 添加账号点击
    remove_account_clicked = Signal(int) # 移除账号点击 (account_id)
    
    def __init__(self, group_data: Dict[str, Any], parent=None):
        super().__init__(parent)  # type: ignore
        self.group_data = group_data
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        
        # 顶部：标题和操作按钮
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        
        # 账号组名称
        self.title_label = SubtitleLabel(self.group_data.get('group_name', '未命名'), self)
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        # 添加账号按钮
        self.add_btn = ToolButton(FluentIcon.ADD, self)
        self.add_btn.setToolTip("添加账号到此组")
        self.add_btn.clicked.connect(lambda: self.add_account_clicked.emit(self.group_data))
        header_layout.addWidget(self.add_btn)
        
        # 编辑按钮
        self.edit_btn = ToolButton(FluentIcon.EDIT, self)
        self.edit_btn.setToolTip("编辑账号组")
        self.edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self.group_data))
        header_layout.addWidget(self.edit_btn)
        
        # 删除按钮
        self.delete_btn = ToolButton(FluentIcon.DELETE, self)
        self.delete_btn.setToolTip("删除账号组")
        self.delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.group_data))
        header_layout.addWidget(self.delete_btn)
        
        layout.addLayout(header_layout)
        
        # 描述
        description = self.group_data.get('description', '')
        if description:
            desc_label = CaptionLabel(description, self)
            desc_color = "#AAAAAA" if isDarkTheme() else "#888888"
            desc_label.setStyleSheet(f"color: {desc_color};")
            layout.addWidget(desc_label)
        
        # 分隔线
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        sep_color = "rgba(255,255,255,0.12)" if isDarkTheme() else "rgba(0,0,0,0.1)"
        line.setStyleSheet(f"background-color: {sep_color};")
        layout.addWidget(line)
        
        # 账号列表
        accounts = self.group_data.get('accounts', [])
        if accounts:
            for account in accounts:
                account_widget = self._create_account_item(account)
                layout.addWidget(account_widget)
        else:
            empty_label = CaptionLabel("暂无账号", self)
            empty_color = "#AAAAAA" if isDarkTheme() else "#888888"
            empty_label.setStyleSheet(f"color: {empty_color}; font-style: italic;")
            layout.addWidget(empty_label)
        
        layout.addStretch()
        
        # 设置卡片大小
        self.setMinimumWidth(280)
        self.setMinimumHeight(180)
    
    def _create_account_item(self, account: Dict) -> QWidget:
        """创建账号列表项"""
        widget = QWidget(self)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)
        
        # 平台图标
        platform = account.get('platform', '')
        platform_icon = self._get_platform_icon(platform)
        icon_widget = IconWidget(platform_icon, self)
        icon_widget.setFixedSize(20, 20)
        layout.addWidget(icon_widget)
        
        # 平台名称和用户名
        platform_name = self._get_platform_name(platform)
        username = account.get('platform_username', '未知')
        label = BodyLabel(f"{platform_name}: {username}", self)
        layout.addWidget(label)
        
        # 登录状态指示
        login_status = account.get('login_status', 'offline')
        status_color = "#52c41a" if login_status == 'online' else "#999"
        status_dot = QFrame(self)
        status_dot.setFixedSize(8, 8)
        status_dot.setStyleSheet(f"background-color: {status_color}; border-radius: 4px;")
        layout.addWidget(status_dot)
        
        layout.addStretch()
        
        # 移除按钮
        remove_btn = ToolButton(FluentIcon.CLOSE, self)
        remove_btn.setFixedSize(24, 24)
        remove_btn.setIconSize(QSize(10, 10))
        remove_btn.setToolTip("从组中移除")
        # 注意: 闭包陷阱，需要绑定 account['id']
        account_id = account.get('id')
        remove_btn.clicked.connect(lambda checked=False, aid=account_id: self.remove_account_clicked.emit(aid))
        layout.addWidget(remove_btn)
        
        return widget
    
    def _get_platform_icon(self, platform: str):
        """获取平台图标"""
        icon_map = {
            'douyin': FluentIcon.VIDEO,
            'kuaishou': FluentIcon.VIDEO,
            'xiaohongshu': FluentIcon.BOOK_SHELF,
            'bilibili': FluentIcon.VIDEO,
            'video_number': FluentIcon.CHAT
        }
        return icon_map.get(platform, FluentIcon.PEOPLE)
    
    @staticmethod
    def _get_platform_name(platform: str) -> str:
        """获取平台中文名"""
        from src.utils.platform_names import get_platform_display_name
        return get_platform_display_name(platform)


class AccountGroupPage(QWidget):
    """账号组管理页面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)  # type: ignore
        self.setObjectName("account_group_page")
        
        # 服务
        self.group_service = AccountGroupService()
        
        # 数据
        self.groups: List[Dict] = []
        
        self._setup_ui()
        
        # 延迟加载数据
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._load_data)
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(16)
        
        # 顶部工具栏
        toolbar_layout = QHBoxLayout()
        toolbar_layout.setSpacing(10)
        
        # 新建账号组按钮
        self.create_btn = PushButton(FluentIcon.ADD, "新建账号组", self)
        self.create_btn.clicked.connect(self._on_create_group)
        toolbar_layout.addWidget(self.create_btn)
        
        # 刷新按钮
        self.refresh_btn = ToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.setToolTip("刷新")
        self.refresh_btn.clicked.connect(self._load_data)
        toolbar_layout.addWidget(self.refresh_btn)
        
        toolbar_layout.addStretch()
        
        # 搜索框
        self.search_box = SearchLineEdit(self)
        self.search_box.setPlaceholderText("搜索账号组...")
        self.search_box.setFixedWidth(200)
        self.search_box.textChanged.connect(self._on_search)
        toolbar_layout.addWidget(self.search_box)
        
        layout.addLayout(toolbar_layout)
        
        # 功能说明卡片
        info_card = CardWidget(self)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 12, 16, 12)
        
        info_title = SubtitleLabel("什么是账号组？", self)
        info_layout.addWidget(info_title)
        
        info_text = BodyLabel(
            "账号组是将不同平台的多个账号组合在一起的逻辑单元。"
            "每个账号组可包含多个账号，但同一平台最多只能有一个账号。"
            "发布内容时，选择账号组可以一键向组内所有账号发布。",
            self
        )
        info_text.setWordWrap(True)
        info_desc_color = "#AAAAAA" if isDarkTheme() else "#888888"
        info_text.setStyleSheet(f"color: {info_desc_color};")
        info_layout.addWidget(info_text)
        
        layout.addWidget(info_card)
        
        # 账号组卡片网格
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        
        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("QWidget { background: transparent; }")
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(16)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        scroll_area.setWidget(self.cards_container)
        layout.addWidget(scroll_area)
    
    def _load_data(self):
        """加载账号组数据。延后到下一轮事件循环再创建任务，避免 qasync 下与其它 async 槽并发时触发 “Cannot enter into task” 的 reentrancy 错误。"""
        loop = asyncio.get_event_loop()
        loop.call_soon(lambda: asyncio.ensure_future(self._async_load_data()))  # type: ignore
    
    async def _async_load_data(self):
        """异步加载账号组数据（单用户模式：加载本地全部账号组）"""
        try:
            self.groups = await self.group_service.get_groups(user_id=None)
            self._render_cards()
        except Exception as e:
            logger.error(f"加载账号组失败: {e}")
            InfoBar.error(
                title="加载失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )
    
    def _render_cards(self, filter_text: str = ""):
        """渲染账号组卡片"""
        # 清空现有卡片
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # 过滤数据
        filtered_groups = self.groups
        if filter_text:
            filtered_groups = [
                g for g in self.groups
                if filter_text.lower() in g.get('group_name', '').lower()
            ]
        
        # 渲染卡片
        if not filtered_groups:
            empty_label = BodyLabel("暂无账号组，点击「新建账号组」创建", self)
            empty_hint_color = "#AAAAAA" if isDarkTheme() else "#888888"
            empty_label.setStyleSheet(f"color: {empty_hint_color};")
            self.cards_layout.addWidget(empty_label, 0, 0)
            return
        
        # 每行3个卡片
        columns = 3
        for i, group in enumerate(filtered_groups):
            card = AccountGroupCard(group, self)
            card.edit_clicked.connect(self._on_edit_group)
            card.delete_clicked.connect(self._on_delete_group)
            card.add_account_clicked.connect(self._on_add_account_to_group)
            card.remove_account_clicked.connect(self._on_remove_account_from_group)
            
            row = i // columns
            col = i % columns
            self.cards_layout.addWidget(card, row, col)
    
    def _on_search(self, text: str):
        """搜索账号组"""
        self._render_cards(text)
    
    def _on_create_group(self):
        """创建账号组（约定：未登录不可创建；受 max_account_groups 限制）"""
        from src.services.auth import CurrentUserService
        curr = CurrentUserService()
        if not curr.is_logged_in():
            InfoBar.warning(
                title="请先登录",
                content="创建账号组需要先登录软件",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return
        from .dialogs.create_group_dialog import CreateGroupDialog
        dialog = CreateGroupDialog(self)
        if dialog.exec():
            group_name = dialog.get_group_name()
            description = dialog.get_description()
            asyncio.ensure_future(self._async_create_group(group_name, description))
    
    async def _async_create_group(self, group_name: str, description: str):
        """异步创建账号组"""
        try:
            from src.services.auth import CurrentUserService
            curr = CurrentUserService()
            user_id = curr.get_user_id_or_default(1)
            max_groups = curr.get_max_account_groups()
            if max_groups is not None:
                groups = await self.group_service.get_groups(user_id=user_id)
                if len(groups) >= max_groups:
                    InfoBar.warning(
                        title="已达上限",
                        content=f"账号组数量已达上限（{max_groups}），请升级会员或联系客服。",
                        parent=self,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                    )
                    return
            await self.group_service.create_group(user_id, group_name, description)
            InfoBar.success(
                title="创建成功",
                content=f"账号组 '{group_name}' 已创建",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000
            )
            self._load_data()
        except ValueError as e:
            InfoBar.warning(
                title="创建失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )
        except Exception as e:
            logger.error(f"创建账号组失败: {e}")
            InfoBar.error(
                title="创建失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )
    
    def _on_edit_group(self, group_data: Dict):
        """编辑账号组"""
        from .dialogs.create_group_dialog import CreateGroupDialog
        dialog = CreateGroupDialog(self, group_data)
        if dialog.exec():
            group_name = dialog.get_group_name()
            description = dialog.get_description()
            asyncio.ensure_future(self._async_update_group(
                group_data['group_id'], group_name, description
            ))
    
    async def _async_update_group(self, group_id: int, group_name: str, description: str):
        """异步更新账号组"""
        try:
            await self.group_service.update_group(group_id, group_name, description)
            InfoBar.success(
                title="更新成功",
                content=f"账号组 '{group_name}' 已更新",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000
            )
            self._load_data()
        except Exception as e:
            logger.error(f"更新账号组失败: {e}")
            InfoBar.error(
                title="更新失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )
    
    def _on_delete_group(self, group_data: Dict):
        """删除账号组"""
        group_name = group_data.get('group_name', '未命名')
        from src.ui.utils.fluent_dialogs import show_confirm
        if show_confirm(
            self, "确认删除",
            f"确定要删除账号组 '{group_name}' 吗？\n组内账号不会被删除，只会解除分组关联。"
        ):
            asyncio.ensure_future(self._async_delete_group(group_data['group_id']))
    
    async def _async_delete_group(self, group_id: int):
        """异步删除账号组"""
        try:
            await self.group_service.delete_group(group_id)
            InfoBar.success(
                title="删除成功",
                content="账号组已删除",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000
            )
            self._load_data()
        except Exception as e:
            logger.error(f"删除账号组失败: {e}")
            InfoBar.error(
                title="删除失败",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )

    def _on_add_account_to_group(self, group_data: Dict):
        """添加到账号组"""
        asyncio.ensure_future(self._async_add_account_to_group(group_data))

    async def _async_add_account_to_group(self, group_data: Dict):
        """异步处理添加账号到组（单用户模式：加载本地全部账号）"""
        try:
            # 1. 获取所有账号
            accounts = await self.group_service.get_all_accounts(user_id=None)
            
            if not accounts:
                InfoBar.warning(title="无账号", content="当前没有任何账号可添加", parent=self)
                return

            # 2. 过滤：一个组内同一平台只能有一个账号
            # group_data['platforms'] 包含了当前组已有的平台
            current_platforms = set(group_data.get('platforms', []))
            
            # 可选账号：平台不在当前组中，且账号本身不在当前组中（虽然后者被前者包含，但为了保险）
            # 注意：如果允许“抢”别人的账号，则不对此限制。只要平台不冲突即可。
            available_accounts = [
                acc for acc in accounts
                if acc.get('platform') not in current_platforms
                and acc.get('group_id') != group_data['id']
            ]
            
            if not available_accounts:
                InfoBar.warning(title="无可用账号", content="没有可添加的账号（组内已包含对应平台或无更多账号）", parent=self)
                return

            # 3. 弹出选择对话框（支持多选，可一次添加多个账号）
            from src.ui.dialogs.account_selection_dialog import AccountSelectionDialog
            dialog = AccountSelectionDialog(self.window() or self)
            dialog.titleLabel.setText(f"添加到账号组: {group_data.get('group_name')}")
            dialog.set_data(available_accounts, self.groups, show_group_nav=False, multi_select=True)
            
            # 使用异步非阻塞等待弹窗，避免 dialog.exec() 导致 qasync 的重入报错 (Cannot enter into task)
            dialog.open()
            future = asyncio.get_event_loop().create_future()
            dialog.finished.connect(lambda res: future.set_result(res) if not future.done() else None)
            res = await future
            
            if res:
                selected_list = dialog.get_selected_accounts()
                if selected_list:
                    # 4. 逐个添加
                    added = 0
                    for acc in selected_list:
                        try:
                            await self.group_service.add_account_to_group(group_data['id'], acc['id'])
                            added += 1  # type: ignore
                        except ValueError as e:
                            InfoBar.warning(title="跳过", content=str(e), parent=self)
                    if added > 0:
                        InfoBar.success(
                            title="添加成功",
                            content=f"已将 {added} 个账号添加到组" if added > 1 else f"已将 {selected_list[0].get('platform_username')} 添加到组",
                            parent=self
                        )
                        self._load_data()
                    
        except Exception as e:
            logger.error(f"添加账号到组失败: {e}", exc_info=True)
            InfoBar.error(title="添加失败", content=str(e), parent=self)

    def _on_remove_account_from_group(self, account_id: int):
        """从组中移除账号"""
        from src.ui.utils.fluent_dialogs import show_confirm
        if show_confirm(self, "确认移除", "确定要将该账号从当前组中移除吗？\n账号本身不会被删除。"):
             asyncio.ensure_future(self._async_remove_account(account_id))

    async def _async_remove_account(self, account_id: int):
        try:
            await self.group_service.remove_account_from_group(account_id)
            InfoBar.success(title="移除成功", content="账号已移出分组", parent=self)
            self._load_data()
        except Exception as e:
            logger.error(f"移除账号失败: {e}")
            InfoBar.error(title="移除失败", content=str(e), parent=self)
