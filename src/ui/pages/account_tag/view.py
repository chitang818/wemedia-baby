# -*- coding: utf-8 -*-
"""
账号标签管理页面
文件路径：src/ui/pages/account_tag/view.py
"""

import logging
from typing import List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QApplication
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from qfluentwidgets import (
    CardWidget, PrimaryPushButton, FluentIcon, FlowLayout,
    TitleLabel, BodyLabel, TransparentToolButton, InfoBadge,
    InfoBar, InfoBarPosition, FlowLayout, SubtitleLabel, CaptionLabel, IconWidget,
    isDarkTheme
)

from src.ui.pages.base_page import BasePage
from src.services.account.account_tag_service import AccountTagService
from src.ui.pages.account_tag.dialogs.create_tag_dialog import CreateTagDialog
from src.ui.dialogs.account_selection_dialog import AccountSelectionDialog
import asyncio

logger = logging.getLogger(__name__)


class TagCard(CardWidget):
    """标签卡片组件"""
    
    # 信号定义
    edit_requested = Signal(dict)
    delete_requested = Signal(dict)
    add_target_requested = Signal(dict) # dict 包含 tag_id
    remove_account_requested = Signal(int, int) # tag_id, account_id
    remove_group_requested = Signal(int, int) # tag_id, group_id

    def __init__(self, tag_data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.tag_data = tag_data
        self._setup_ui()
        
    def _setup_ui(self):
        # 标签类型：account / group（兼容旧数据：按已关联对象推断）
        tag_type = (self.tag_data or {}).get("tag_type")
        if tag_type not in ("account", "group"):
            has_groups = bool((self.tag_data or {}).get("groups"))
            has_accounts = bool((self.tag_data or {}).get("accounts"))
            tag_type = "group" if (has_groups and not has_accounts) else "account"

        is_group_tag = bool(tag_type == "group")

        # 容器基础配置
        self.setMinimumSize(320, 200)
        self.setMaximumWidth(400)

        # 视觉策略：整体保持“轻”，类型用小色条+小胶囊区分（避免大面积底色/粗边框显得廉价）
        header_bg = "transparent"
        accent = "#6B61D6" if is_group_tag else "#0078D4"
        self.setStyleSheet(f"""
            CardWidget {{
                border: 1px solid rgba(0, 0, 0, 0.10);
                border-radius: 12px;
                background-color: rgba(255, 255, 255, 0.92);
            }}
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        
        # 1. 顶部 Header (标签名 + 操作按钮)
        header_wrap = QWidget(self)
        header_wrap.setStyleSheet(f"""
            QWidget {{
                background-color: {header_bg};
            }}
        """)
        header_layout = QHBoxLayout(header_wrap)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        # 左侧类型色条（小而明显）
        accent_bar = QWidget(header_wrap)
        accent_bar.setFixedSize(4, 18)
        accent_bar.setStyleSheet(f"background-color: {accent}; border-radius: 2px;")
        header_layout.addWidget(accent_bar)
        
        # 标签图标和名称
        title_icon = IconWidget(FluentIcon.LIBRARY if is_group_tag else FluentIcon.PEOPLE, header_wrap)
        title_icon.setFixedSize(16, 16)
        header_layout.addWidget(title_icon)
        
        title_label = SubtitleLabel(self.tag_data.get('name', ''), header_wrap)
        font = title_label.font()
        font.setPointSize(12)
        font.setBold(True)
        title_label.setFont(font)
        header_layout.addWidget(title_label)

        # 类型胶囊：实色浅底（不透明），文字用默认颜色，只用底色做区分
        type_pill = CaptionLabel("账号组标签" if is_group_tag else "账号标签", header_wrap)
        # 轻量实色（避免半透明“脏”感）
        # 加深一档：更明显但仍保持柔和
        chip_bg = "#E1D9FF" if is_group_tag else "#D6ECFF"
        type_pill.setStyleSheet(
            f"""
            QLabel {{
                background: {chip_bg};
                color: inherit;
                border: none;
                border-radius: 11px;
                padding: 2px 10px;
                font-weight: 650;
                letter-spacing: 0.2px;
            }}
            """
        )
        header_layout.addWidget(type_pill)
        header_layout.addStretch()
        
        # 操作按钮
        btn_add = TransparentToolButton(FluentIcon.ADD, header_wrap)
        btn_add.setToolTip("关联对象")
        btn_add.clicked.connect(lambda: self.add_target_requested.emit(self.tag_data))
        
        btn_edit = TransparentToolButton(FluentIcon.EDIT, header_wrap)
        btn_edit.setToolTip("编辑标签名")
        btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.tag_data))
        
        btn_delete = TransparentToolButton(FluentIcon.DELETE, header_wrap)
        btn_delete.setToolTip("删除标签")
        btn_delete.clicked.connect(lambda: self.delete_requested.emit(self.tag_data))
        
        header_layout.addWidget(btn_add)
        header_layout.addWidget(btn_edit)
        header_layout.addWidget(btn_delete)
        
        main_layout.addWidget(header_wrap)
        
        # 2. 数据统计
        acc_cnt = self.tag_data.get('account_count', 0)
        grp_cnt = self.tag_data.get('group_count', 0)
        if is_group_tag:
            stats_label = CaptionLabel(f"已关联 {grp_cnt} 个账号组", self)
            stats_label.setStyleSheet("color: rgba(0,0,0,0.55);")
        else:
            stats_label = CaptionLabel(f"已关联 {acc_cnt} 个账号", self)
            stats_label.setStyleSheet("color: rgba(0,0,0,0.55);")
        main_layout.addWidget(stats_label)
        
        # 3. 关联对象流式展示区
        targets_widget = QWidget(self)
        targets_layout = FlowLayout(targets_widget)
        targets_layout.setContentsMargins(0, 0, 0, 0)
        targets_layout.setSpacing(6)
        
        # 渲染关联的账号组
        for grp in self.tag_data.get('groups', []):
            badge = self._create_target_badge(
                text=grp.get('group_name', ''), 
                icon=FluentIcon.LIBRARY, 
                target_id=grp.get('id'),
                target_type='group'
            )
            targets_layout.addWidget(badge)
            
        # 渲染关联的个人账号
        for acc in self.tag_data.get('accounts', []):
            badge = self._create_target_badge(
                text=acc.get('platform_username', ''), 
                icon=FluentIcon.PEOPLE, 
                target_id=acc.get('id'),
                target_type='account'
            )
            targets_layout.addWidget(badge)
            
        if not self.tag_data.get('groups') and not self.tag_data.get('accounts'):
            empty_lbl = BodyLabel("暂无关联对象", self)
            empty_lbl.setStyleSheet("color: #999; font-style: italic;")
            targets_layout.addWidget(empty_lbl)
            
        main_layout.addWidget(targets_widget, 1) # stretch=1 填充底部
        
    def _create_target_badge(self, text: str, icon: FluentIcon, target_id: int, target_type: str) -> QWidget:
        """创建可移除的胶囊组件"""
        badge = QWidget(self)
        badge.setStyleSheet("""
            QWidget {
                background-color: #EEF1F4;
                border: 1px solid #E2E6EA;
                border-radius: 12px;
            }
            QWidget:hover {
                background-color: #E7EBEF;
            }
        """)
        h_layout = QHBoxLayout(badge)
        h_layout.setContentsMargins(8, 2, 4, 2)
        h_layout.setSpacing(4)
        
        # 类型图标
        ic = IconWidget(icon, badge)
        ic.setFixedSize(12, 12)
        h_layout.addWidget(ic)
        
        # 文本
        lbl = BodyLabel(text, badge)
        font = lbl.font()
        font.setPointSize(10)
        lbl.setFont(font)
        # 关联对象文案保持“默认颜色”，避免与标签类型（蓝/紫）抢色冲突
        lbl.setStyleSheet("color: inherit; border: none; background: transparent;")
        h_layout.addWidget(lbl)
        
        # 移除按钮
        btn_remove = TransparentToolButton(FluentIcon.CLOSE, badge)
        btn_remove.setFixedSize(20, 20)
        btn_remove.setIconSize(btn_remove.iconSize() * 0.6)
        btn_remove.setStyleSheet("border: none; background: transparent; padding: 2px;")
        
        tag_id = self.tag_data.get('id')
        if target_type == 'group':
            btn_remove.clicked.connect(lambda: self.remove_group_requested.emit(tag_id, target_id))
        else:
            btn_remove.clicked.connect(lambda: self.remove_account_requested.emit(tag_id, target_id))
            
        h_layout.addWidget(btn_remove)
        return badge


class AccountTagPage(BasePage):
    """账号标签管理页面"""
    
    _lazy_content = False

    def __init__(self, parent=None):
        super().__init__("账号标签管理", parent, enable_scroll=True)
        self.setObjectName("account_tag_page")
        self.tag_service = AccountTagService()
        
        from src.services.auth import CurrentUserService
        self.user_id = CurrentUserService().get_user_id_or_default(1)
        self._bg_tasks = set()
        
        self._setup_page_ui()
        
    def _run_bg_task(self, coro):
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task
        
    def _setup_page_ui(self):
        """设置UI布局"""
        # 1. 顶部操作栏
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 12)
        
        self.btn_add_tag = PrimaryPushButton(FluentIcon.ADD, "新建标签", self)
        self.btn_add_tag.clicked.connect(self._on_add_tag)
        
        self.btn_refresh = TransparentToolButton(FluentIcon.SYNC, self)
        self.btn_refresh.setToolTip("刷新列表")
        self.btn_refresh.clicked.connect(self._load_tags)
        
        action_layout.addWidget(self.btn_add_tag)
        action_layout.addWidget(self.btn_refresh)
        action_layout.addStretch()
        
        self.content_layout.addLayout(action_layout)
        
        # 2. 功能说明卡片
        info_card = CardWidget(self)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 12, 16, 12)
        
        info_title = SubtitleLabel("什么是账号标签？", self)
        info_layout.addWidget(info_title)
        
        info_text = BodyLabel(
            "账号标签是用于灵活归类账号和账号组的标记。"
            "一个标签可以同时关联多个账号或账号组，同一对象也可以拥有多个标签。"
            "发布内容时，可以通过标签快速筛选目标，方便按主题、用途等维度管理与一键发布。",
            self
        )
        info_text.setWordWrap(True)
        info_desc_color = "#AAAAAA" if isDarkTheme() else "#888888"
        info_text.setStyleSheet(f"color: {info_desc_color};")
        info_layout.addWidget(info_text)
        
        self.content_layout.addWidget(info_card)
        
        # 3. 流式布局容器
        self.flow_widget = QWidget(self)
        self.flow_layout = FlowLayout(self.flow_widget)
        self.flow_layout.setContentsMargins(0, 0, 0, 0)
        self.flow_layout.setHorizontalSpacing(16)
        self.flow_layout.setVerticalSpacing(16)
        
        self.content_layout.addWidget(self.flow_widget)
        self.content_layout.addStretch(1)
        
        # 加载数据
        self._load_tags()
        
    def _load_tags(self):
        """加载所有标签并渲染"""
        async def fetch_tags():
            try:
                tags = await self.tag_service.get_tags()
                self._render_tags(tags)
            except Exception as e:
                logger.error(f"加载账号标签失败: {e}", exc_info=True)
                InfoBar.error("加载失败", str(e), parent=self, position=InfoBarPosition.TOP)
                
        self._run_bg_task(fetch_tags())

    def _render_tags(self, tags: List[Dict[str, Any]]):
        """渲染卡片列表"""
        # 清空旧卡片
        while self.flow_layout.count():
            item = self.flow_layout.takeAt(0)
            if hasattr(item, 'widget'):
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            elif hasattr(item, 'deleteLater'):
                item.deleteLater()
                
        # 添加新卡片
        for tag in tags:
            card = TagCard(tag, self)
            card.edit_requested.connect(self._on_edit_tag)
            card.delete_requested.connect(self._on_delete_tag)
            card.add_target_requested.connect(self._on_add_target)
            card.remove_account_requested.connect(self._on_remove_account)
            card.remove_group_requested.connect(self._on_remove_group)
            self.flow_layout.addWidget(card)

    def _on_add_tag(self):
        """新建标签弹窗"""
        dialog = CreateTagDialog(self.window())
        if dialog.exec():
            name = dialog.get_tag_name()
            tag_type = dialog.get_tag_type()
            
            async def create_task():
                try:
                    await self.tag_service.create_tag(self.user_id, name, tag_type=tag_type)
                    type_cn = "账号组标签" if tag_type == "group" else "账号标签"
                    InfoBar.success("成功", f"{type_cn} '{name}' 已创建", parent=self, position=InfoBarPosition.TOP)
                    self._load_tags()
                except Exception as e:
                    InfoBar.error("失败", f"创建标签失败: {e}", parent=self, position=InfoBarPosition.TOP)
                
            self._run_bg_task(create_task())

    def _on_edit_tag(self, tag_data: Dict[str, Any]):
        """编辑标签名称"""
        dialog = CreateTagDialog(self.window(), tag_data=tag_data)
        if dialog.exec():
            name = dialog.get_tag_name()
            tag_id = tag_data['id']
            
            async def update_task():
                try:
                    await self.tag_service.update_tag(tag_id, name)
                    InfoBar.success("成功", f"标签已更新为 '{name}'", parent=self, position=InfoBarPosition.TOP)
                    self._load_tags()
                except Exception as e:
                    InfoBar.error("失败", f"更新标签失败: {e}", parent=self, position=InfoBarPosition.TOP)
                
            self._run_bg_task(update_task())

    def _on_delete_tag(self, tag_data: Dict[str, Any]):
        """删除标签"""
        from src.ui.components.base_dialog import AppMessageBoxBase
        
        dialog = AppMessageBoxBase(self.window(), header_title="删除标签")
        lbl = BodyLabel(f"确定要删除标签 '{tag_data.get('name')}' 吗？\n删除标签不会影响已关联的账号或账号组。", dialog)
        dialog.viewLayout.addWidget(lbl)
        
        dialog.yesButton.setText("删除")
        dialog.cancelButton.setText("取消")
        
        # 调换按钮位置
        lay = getattr(dialog, "buttonLayout", None)
        if lay is None:
            lay = dialog.buttonGroup.layout()
        if lay:
            lay.removeWidget(dialog.yesButton)
            lay.removeWidget(dialog.cancelButton)
            lay.addWidget(dialog.cancelButton)
            lay.addWidget(dialog.yesButton)
            
            if dialog.exec():
                tag_id = tag_data['id']
                
                async def delete_task():
                    try:
                        await self.tag_service.delete_tag(tag_id)
                        InfoBar.success("成功", "标签已删除", parent=self, position=InfoBarPosition.TOP)
                        self._load_tags()
                    except Exception as e:
                        InfoBar.error("失败", f"删除标签失败: {e}", parent=self, position=InfoBarPosition.TOP)
                    
                self._run_bg_task(delete_task())

    def _on_add_target(self, tag_data: Dict[str, Any]):
        """关联账号/组"""
        # 加载所有账号和组
        async def fetch_all_data():
            try:
                from src.services.account.account_manager_async import AccountManagerAsync
                from src.services.account.account_group_service import AccountGroupService
                from src.infrastructure.common.event.event_bus import EventBus
                from src.infrastructure.common.di.service_locator import ServiceLocator
                
                bus = ServiceLocator().get(EventBus)
                acc_mgr = AccountManagerAsync(user_id=self.user_id, event_bus=bus)
                grp_svc = AccountGroupService(event_bus=bus)
                
                import inspect
                accounts_ret = acc_mgr.get_accounts()
                if inspect.iscoroutine(accounts_ret):
                    accounts = await accounts_ret
                else:
                    accounts = accounts_ret
                    
                groups = await grp_svc.get_groups(self.user_id)
                
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._show_selection_dialog(tag_data, accounts, groups))
            except Exception as e:
                InfoBar.error("错误", f"加载账号数据失败: {e}", parent=self, position=InfoBarPosition.TOP)
                
        self._run_bg_task(fetch_all_data())

    def _show_selection_dialog(self, tag_data: Dict[str, Any], accounts: List[Dict], groups: List[Dict]):
        """显示对象选择弹窗"""
        dialog = AccountSelectionDialog(self.window(), header_title="选择要关联的对象")

        # 根据标签类型限制可关联对象
        tag_type = (tag_data or {}).get("tag_type")
        # 兼容老数据：按已绑定对象推断
        if not tag_type:
            has_groups = bool((tag_data or {}).get("groups"))
            has_accounts = bool((tag_data or {}).get("accounts"))
            if has_groups and not has_accounts:
                tag_type = "group"
            else:
                tag_type = "account"
        
        # 预先选出已经关联的 ID
        linked_account_ids = [a.get('id') for a in tag_data.get('accounts', [])]
        linked_group_ids = [g.get('id') for g in tag_data.get('groups', [])]
        
        # account 标签：只允许选账号；group 标签：只允许选账号组
        show_groups = bool(tag_type == "group")
        dialog.set_data(
            accounts=[] if show_groups else accounts,
            groups=groups if show_groups else [],
            show_group_nav=show_groups,
            multi_select=True,  # 允许多选
            initial_account_ids=linked_account_ids,
            initial_group_ids=linked_group_ids
        )
        
        if dialog.exec():
            # 拿到结果
            result = dialog.get_selected_result()
            if not result:
                return
                
            r_type = result.get('type')
            r_data = result.get('data', [])
            tag_id = tag_data['id']
            
            async def link_targets():
                try:
                    for acc_id in linked_account_ids:
                        await self.tag_service.remove_account_from_tag(tag_id, acc_id)
                    for grp_id in linked_group_ids:
                        await self.tag_service.remove_group_from_tag(tag_id, grp_id)
                        
                    if r_type == 'group':
                        for g in r_data:
                            await self.tag_service.add_group_to_tag(tag_id, g.get('id'))
                    else:
                        for a in r_data:
                            await self.tag_service.add_account_to_tag(tag_id, a.get('id'))
                            
                    InfoBar.success("成功", "关联对象已更新", parent=self, position=InfoBarPosition.TOP)
                    self._load_tags()
                except Exception as e:
                    InfoBar.error("失败", f"更新关联对象失败: {e}", parent=self, position=InfoBarPosition.TOP)
                    
            self._run_bg_task(link_targets())

    def _on_remove_account(self, tag_id: int, account_id: int):
        """从标签移除账号"""
        async def remove_task():
            try:
                await self.tag_service.remove_account_from_tag(tag_id, account_id)
                self._load_tags()
            except Exception as e:
                InfoBar.error("移除失败", str(e), parent=self, position=InfoBarPosition.TOP)
                
        self._run_bg_task(remove_task())

    def _on_remove_group(self, tag_id: int, group_id: int):
        """从标签移除组"""
        async def remove_task():
            try:
                await self.tag_service.remove_group_from_tag(tag_id, group_id)
                self._load_tags()
            except Exception as e:
                InfoBar.error("移除失败", str(e), parent=self, position=InfoBarPosition.TOP)
                
        self._run_bg_task(remove_task())
