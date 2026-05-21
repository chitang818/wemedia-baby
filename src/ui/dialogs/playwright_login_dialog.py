"""
Playwright 登录对话框
文件路径：src/ui/dialogs/playwright_login_dialog.py
功能：使用 Playwright 在外部浏览器窗口中进行登录，并自动保存凭证
"""

from typing import Optional, Callable
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import QTimer, Qt, Signal
import logging
import asyncio

from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.ui.components.base_dialog import install_escape_reject_shortcut, resolve_top_level_window_parent

try:
    from qfluentwidgets import PrimaryPushButton, PushButton, BodyLabel, ProgressRing
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False

logger = logging.getLogger(__name__)


class PlaywrightLoginDialog(QDialog):
    """Playwright 登录对话框 - 使用外部浏览器窗口进行登录
    
    特点:
    1. 启动独立的 Chrome/Edge 浏览器窗口
    2. 自动加载已保存的凭证（如有）
    3. 登录成功后写入 cookies.json（关闭浏览器时可另存 storage_state 快照）
    4. 支持指纹持久化
    """
    
    # 登录成功信号 (account_id, nickname)
    login_success = Signal(str, str)
    # 登录失败信号 (error_message)
    login_failed = Signal(str)
    
    def __init__(
        self,
        parent,
        platform_username: str,
        platform: str,
        platform_name: str = "",
        account_manager=None,
        on_login_success: Optional[Callable] = None,
        on_login_failed: Optional[Callable] = None
    ):
        """初始化 Playwright 登录对话框
        
        Args:
            parent: 父窗口
            platform_username: 账号名称（用作 account_id）
            platform: 平台ID
            platform_name: 平台显示名称
            account_manager: 账号管理器实例
            on_login_success: 登录成功回调
            on_login_failed: 登录失败回调
        """
        super().__init__(resolve_top_level_window_parent(parent))
        install_escape_reject_shortcut(self)
        self.platform_username = platform_username
        self.platform = platform
        self.platform_name = platform_name or platform
        self.account_manager = account_manager
        self.on_login_success_callback = on_login_success
        self.on_login_failed_callback = on_login_failed
        
        self._login_service = None
        self._check_timer = None
        self._is_closed = False
        self._login_tasks = set()
        self._accept_timer = QTimer(self)
        self._accept_timer.setSingleShot(True)
        self._accept_timer.timeout.connect(self.accept)
        
        self.setWindowTitle(f"登录 {self.platform_name}")
        self.setMinimumSize(400, 250)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        
        self._setup_ui()
        self._start_login()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # 标题
        title_text = f"正在启动浏览器..."
        if FLUENT_WIDGETS_AVAILABLE:
            self.title_label = BodyLabel(title_text, self)
        else:
            self.title_label = QLabel(title_text, self)
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.title_label)
        
        # 提示文本
        tip_text = (
            f"请在新打开的浏览器窗口中完成登录。\n\n"
            f"• 平台：{self.platform_name}\n"
            f"• 账号：{self.platform_username}\n\n"
            f"登录成功后系统将自动检测并保存凭证。"
        )
        if FLUENT_WIDGETS_AVAILABLE:
            self.tip_label = BodyLabel(tip_text, self)
        else:
            self.tip_label = QLabel(tip_text, self)
        self.tip_label.setWordWrap(True)
        layout.addWidget(self.tip_label)
        
        # 状态标签
        if FLUENT_WIDGETS_AVAILABLE:
            self.status_label = BodyLabel("正在启动浏览器...", self)
        else:
            self.status_label = QLabel("正在启动浏览器...", self)
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        if FLUENT_WIDGETS_AVAILABLE:
            self.btn_done = PrimaryPushButton("我已完成登录", self)
            self.btn_cancel = PushButton("取消", self)
        else:
            self.btn_done = QPushButton("我已完成登录", self)
            self.btn_cancel = QPushButton("取消", self)
        
        self.btn_done.setEnabled(False)
        self.btn_done.clicked.connect(self._on_done_clicked)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        
        btn_layout.addWidget(self.btn_done)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)
    
    def _start_login(self):
        """启动登录流程"""
        # 在事件循环中启动异步任务
        self._track_login_task(self._start_login_async(), name="start")

    def _track_login_task(self, coro, *, name: str):
        task = get_async_task_registry().create_task(
            coro,
            name=f"ui.playwright_login.{name}",
            group="ui",
        )
        self._login_tasks.add(task)
        task.add_done_callback(self._login_tasks.discard)
        return task
    
    async def _start_login_async(self):
        """异步启动登录"""
        try:
            from src.services.account.login_service import LoginService
            
            self._login_service = LoginService(
                account_id=self.platform_username,
                platform=self.platform,
                account_manager=self.account_manager,
                on_login_success=self._handle_login_success,
                on_login_failed=self._handle_login_failed
            )
            
            # 启动浏览器
            success = await self._login_service.start_login(headless=False)
            
            if success:
                self.title_label.setText("请在浏览器中完成登录")
                self.status_label.setText("等待登录...")
                self.btn_done.setEnabled(True)
                
                # 启动登录状态检测定时器
                self._check_timer = QTimer(self)
                self._check_timer.timeout.connect(self._check_login_status)
                self._check_timer.start(3000)  # 每3秒检测一次
            else:
                self.status_label.setText("浏览器启动失败")
                
        except Exception as e:
            logger.error(f"启动登录失败: {e}", exc_info=True)
            self.status_label.setText(f"启动失败: {str(e)}")
    
    def _check_login_status(self):
        """检测登录状态（Qt定时器回调）"""
        if self._is_closed or not self._login_service:
            return
        
        self._track_login_task(self._check_login_status_async(), name="check_status")
    
    async def _check_login_status_async(self):
        """异步检测登录状态"""
        try:
            if await self._login_service.check_login_status():
                self.status_label.setText("✓ 检测到登录成功！正在保存...")
                
                # 停止检测
                if self._check_timer:
                    self._check_timer.stop()
                
                # 执行登录完成流程
                await self._login_service.on_login_complete()
                
                # 关闭对话框
                self._on_login_complete_ui()
                
        except Exception as e:
            logger.debug(f"检测登录状态时出错: {e}")
    
    def _on_done_clicked(self):
        """用户点击"我已完成登录"按钮"""
        self.status_label.setText("正在验证登录状态...")
        self._track_login_task(self._verify_and_save(), name="verify_and_save")
    
    async def _verify_and_save(self):
        """验证登录并保存"""
        try:
            if self._login_service:
                is_logged_in = await self._login_service.check_login_status()
                
                if is_logged_in:
                    self.status_label.setText("✓ 登录验证成功，正在保存...")
                    await self._login_service.on_login_complete()
                    self._on_login_complete_ui()
                else:
                    self.status_label.setText("⚠ 未检测到有效登录，请确认已完成登录")
                    
        except Exception as e:
            logger.error(f"验证登录失败: {e}")
            self.status_label.setText(f"验证失败: {str(e)}")
    
    def _on_cancel_clicked(self):
        """取消登录"""
        self._cleanup()
        self.reject()
    
    def _on_login_complete_ui(self):
        """登录完成后的UI处理"""
        self.status_label.setText("✓ 登录成功！")
        
        # 发射信号
        nickname = ""
        if self._login_service and hasattr(self._login_service, '_last_user_info'):
            nickname = self._login_service._last_user_info.get('nickname', '')
        
        self.login_success.emit(self.platform_username, nickname)
        
        # 触发回调
        if self.on_login_success_callback:
            self.on_login_success_callback(self.platform_username, {'nickname': nickname})
        
        # 延迟关闭
        self._accept_timer.start(1000)
    
    def _handle_login_success(self, account_id: str, user_info: dict):
        """LoginService 登录成功回调"""
        logger.info(f"登录成功: {account_id}, {user_info}")
    
    def _handle_login_failed(self, error_message: str):
        """LoginService 登录失败回调"""
        logger.error(f"登录失败: {error_message}")
        self.status_label.setText(f"登录失败: {error_message}")
        self.login_failed.emit(error_message)
        
        if self.on_login_failed_callback:
            self.on_login_failed_callback(error_message)
    
    def _cleanup(self):
        """清理资源"""
        self._is_closed = True
        
        if self._check_timer:
            self._check_timer.stop()
            self._check_timer = None
        self._accept_timer.stop()

        for task in list(self._login_tasks):
            if not task.done():
                task.cancel()
        self._login_tasks.clear()
        
        if self._login_service:
            get_async_task_registry().create_task(
                self._login_service.close(),
                name="ui.playwright_login.close_service",
                group="ui",
            )
            self._login_service = None
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        """对话框关闭事件"""
        self._cleanup()
        super().closeEvent(event)
    
    def reject(self):
        """覆盖 reject 以确保清理"""
        self._cleanup()
        super().reject()
