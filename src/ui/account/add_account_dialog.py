# pyre-ignore-all-errors
"""
添加账号对话框
文件路径：src/ui/account/add_account_dialog.py
功能：添加平台账号的对话框，包含平台选择和账号名称输入
"""

from typing import Optional, Dict, Any, List
import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, 
    QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon, QColor, QPainter, QPainterPath, QPixmap, QImage
import logging
import re

try:
    from qfluentwidgets import (
        SubtitleLabel, BodyLabel, LineEdit,
        PrimaryPushButton, PushButton, TitleLabel,
        CardWidget, FluentIcon
    )
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False
    from PySide6.QtWidgets import QDialog

from src.ui.components.base_dialog import AppMessageBoxBase

logger = logging.getLogger(__name__)


# 平台配置（icon 为 emoji 回退；icon_file 为 resources/icons/platform/ 下的文件名，可选）
PLATFORM_CONFIG = {
    "douyin": {
        "name": "抖音",
        "url": "https://creator.douyin.com/",
        "icon": "🎵",
        "icon_file": "douyin.png",
        "color": "#000000",
        "category": "popular"
    },
    "kuaishou": {
        "name": "快手",
        "url": "https://cp.kuaishou.com/",
        "icon": "⚡",
        "icon_file": "kuaishou.png",
        "color": "#FF6600",
        "category": "popular"
    },
    "wechat_video": {
        "name": "视频号",
        "url": "https://channels.weixin.qq.com/login.html",
        "icon": "📹",
        "icon_file": "wechat_video.png",
        "color": "#07C160",
        "category": "popular"
    },
    "xiaohongshu": {
        "name": "小红书",
        "url": "https://creator.xiaohongshu.com/",
        "icon": "📕",
        "icon_file": "xiaohongshu.png",
        "color": "#FF2442",
        "category": "popular"
    },
    "bilibili": {
        "name": "哔哩哔哩",
        "url": "https://member.bilibili.com/",
        "icon": "📺",
        "icon_file": "bilibili.png",
        "color": "#00A1D6",
        "category": "popular"
    },
    "toutiao": {
        "name": "今日头条",
        "url": "https://mp.toutiao.com/",
        "icon": "📰",
        "icon_file": "toutiao.png",
        "color": "#ED1C24",
        "category": "popular",
        "precolored": True
    },
    "baijiahao": {
        "name": "百家号",
        "url": "https://baijiahao.baidu.com/",
        "icon": "📝",
        "icon_file": "baijiahao.png",
        "color": "#2932E1",
        "category": "popular"
    },
    "weibo": {
        "name": "新浪微博",
        "url": "https://weibo.com/",
        "icon": "🔴",
        "icon_file": "weibo.png",
        "color": "#E6162D",
        "category": "popular"
    },
    "duoduoshipin": {
        "name": "多多视频",
        "url": "https://live.pinduoduo.com/",
        "icon": "🟠",
        "icon_file": "duoduoshipin.png",
        "color": "#E02E24",
        "category": "popular",
        "precolored": True
    },
    "qiehao": {
        "name": "企鹅号",
        "url": "https://om.qq.com/",
        "icon": "🐧",
        "icon_file": "qiehao.png",
        "color": "#FAAD14",
        "category": "popular",
        "precolored": True
    }
}

# 平台图标显示尺寸（与横向卡片、工作台快捷卡片视觉协调）
PLATFORM_ICON_SIZE = 40


def _emoji_font() -> QFont:
    """用于平台卡片 emoji 回退的字体"""
    f = QFont()
    f.setPointSize(30)
    return f


def _colorize_pixmap(pixmap: QPixmap, hex_color: str) -> QPixmap:
    """将图标着为指定品牌色（非透明像素改为 hex_color），用于彩色显示"""
    if pixmap.isNull():
        return pixmap
    try:
        color = QColor(hex_color)
        if not color.isValid():
            return pixmap
        img = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
        r, g, b = color.red(), color.green(), color.blue()
        for y in range(img.height()):
            for x in range(img.width()):
                p = img.pixelColor(x, y)
                if p.alpha() > 0:
                    img.setPixelColor(x, y, QColor(r, g, b, p.alpha()))
        return QPixmap.fromImage(img)
    except Exception:
        return pixmap


def _get_platform_icon_path(platform_id: str) -> Optional[str]:
    """获取平台图标文件路径，若文件存在则返回路径，否则返回 None"""
    icon_file = PLATFORM_CONFIG.get(platform_id, {}).get("icon_file")
    if not icon_file:
        return None
    try:
        # 使用 PathManager 统一路径，兼容打包环境
        from src.infrastructure.common.path_manager import PathManager
        path = str(PathManager.get_resource_path(
            os.path.join("resources", "icons", "platform", str(icon_file))
        ))
        return path if os.path.isfile(path) else None
    except Exception:
        return None


class PlatformCard(QPushButton):
    """平台卡片按钮"""
    
    def __init__(self, platform_id: str, config: Dict[str, Any], parent=None):
        """初始化平台卡片"""
        super().__init__(parent)  # type: ignore
        self.platform_id = platform_id
        self.config = config
        self._setup_ui()

    def set_disabled_style(self, disabled: bool):
        """禁用平台：置灰且不可点击"""
        if disabled:
            self.setEnabled(False)
            self.setCursor(Qt.ForbiddenCursor)
            self.setStyleSheet("""
                QPushButton {
                    border: 1px solid #EDEDED;
                    border-radius: 10px;
                    background-color: #F7F7F7;
                    text-align: center;
                    padding: 10px;
                    color: #999999;
                }
            """)
        else:
            self.setEnabled(True)
            self.setCursor(Qt.PointingHandCursor)
            # 重新设置默认样式
            self._setup_ui()
    
    def _setup_ui(self):
        """设置UI：优先使用 resources/icons/platform 下的真实图标，否则用 emoji"""
        # 横向比例接近工作台 QuickActionCard（固定高度约 100），便于一行 5 个、共 2 行排布
        self.setFixedSize(150, 100)
        self.setCursor(Qt.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)
        
        # 图标区域：固定高度容器内居中，使平台图片始终居中显示
        icon_container = QWidget(self)
        icon_container.setFixedHeight(PLATFORM_ICON_SIZE + 8)
        icon_layout = QVBoxLayout(icon_container)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setSpacing(0)
        icon_layout.setAlignment(Qt.AlignCenter)
        icon_label = QLabel(icon_container)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_path = _get_platform_icon_path(self.platform_id)
        if icon_path:
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    PLATFORM_ICON_SIZE, PLATFORM_ICON_SIZE,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                if not self.config.get("precolored"):
                    brand_color = self.config.get("color")
                    if brand_color:
                        pixmap = _colorize_pixmap(pixmap, brand_color)
                icon_label.setPixmap(pixmap)
                icon_label.setFixedSize(PLATFORM_ICON_SIZE + 4, PLATFORM_ICON_SIZE + 4)
            else:
                icon_label.setText(self.config.get("icon", "📱"))
                icon_label.setFont(_emoji_font())
        else:
            icon_label.setText(self.config.get("icon", "📱"))
            icon_label.setFont(_emoji_font())
        icon_layout.addWidget(icon_label)
        layout.addWidget(icon_container)
        
        name_label = BodyLabel(self.config.get("name", ""), self)
        name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_label)
        
        # Pro 平台在右下角显示小号 Pro 字样
        try:
            from src.utils.pro_platforms import is_pro_platform
            if is_pro_platform(self.platform_id):
                pro_row = QHBoxLayout()
                pro_row.addStretch()
                pro_label = QLabel("Pro", self)
                pro_label.setStyleSheet(
                    "font-size: 8px; font-weight: bold; color: #0078D4; "
                    "background-color: rgba(0, 120, 212, 0.1); padding: 1px 4px; border-radius: 2px;"
                )
                pro_label.setFixedHeight(14)
                pro_row.addWidget(pro_label)
                layout.addLayout(pro_row)
        except Exception:
            pass
        
        # 设置样式 - 更加美观的卡片样式
        self.setStyleSheet(f"""
            QPushButton {{
                border: 1px solid #EDEDED;
                border-radius: 10px;
                background-color: #FFFFFF;
                text-align: center;
                padding: 10px;
            }}
            QPushButton:hover {{
                border: 1px solid {self.config.get("color", "#0078D4")};
                background-color: #FAFAFA;
            }}
            QPushButton:pressed {{
                background-color: #F5F5F5;
                border: 1px solid {self.config.get("color", "#0078D4")};
            }}
        """)
        
        # 添加阴影效果 (通过 QGraphicsDropShadowEffect 可能更好，这里先用简单的边框样式)



class PlatformSelectMessageBox(AppMessageBoxBase):
    """平台选择对话框（Fluent UI）"""
    
    def __init__(self, parent=None):
        # 标题置于卡片顶栏，与关闭按钮同一行（主流弹窗习惯）
        super().__init__(parent, header_title="选择平台")  # type: ignore
        self.selected_platform: Optional[str] = None
        self.platform_cards: List[PlatformCard] = []
        
        # 5 列 × 150px 卡片 + 间距 + 与 viewLayout 一致的左右边距
        self.widget.setMinimumWidth(848)
        # 顶栏已占标题区，正文区略收紧上边距
        self.viewLayout.setContentsMargins(24, 8, 24, 20)
        
        self._setup_content()
        
        # 隐藏确定按钮，因为点击卡片即确认
        self.yesButton.hide()
        self.cancelButton.setText("取消")
        
        # 增加内容内边距
        self.widget.setContentsMargins(0, 0, 0, 0)
        
        # 统一底部背景颜色
        self.buttonGroup.setStyleSheet("background-color: transparent; border-top: 1px solid #EDEDED;")
        self.cancelButton.setStyleSheet("""
            QPushButton {
                border: 1px solid #EDEDED;
                border-radius: 5px;
                background-color: #FFFFFF;
                padding: 6px 12px;
                font-size: 14px;
                color: #333333;
            }
            QPushButton:hover {
                background-color: #F5F5F5;
            }
            QPushButton:pressed {
                background-color: #EEEEEE;
            }
        """)

        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _setup_content(self):
        """设置内容区域"""
        # 平台展示区域（每行 5 个，10 个平台共 2 行）
        cards_layout = QGridLayout()
        cards_layout.setHorizontalSpacing(12)
        cards_layout.setVerticalSpacing(12)
        cards_layout.setAlignment(Qt.AlignCenter)
        
        platforms = list(PLATFORM_CONFIG.items())
        cols = 5

        # 当前启用的平台列表（默认仅 community）
        try:
            from src.utils.plugin_settings import get_enabled_platform_ids
            enabled_ids = set(get_enabled_platform_ids())
        except Exception:
            enabled_ids = {"douyin", "kuaishou", "wechat_video"}
        
        for idx, (platform_id, config) in enumerate(platforms):
            card = PlatformCard(platform_id, config, self.widget)
            card.clicked.connect(lambda checked=False, pid=platform_id: self._on_platform_clicked(pid))
            if platform_id not in enabled_ids:  # type: ignore
                card.set_disabled_style(True)
            cards_layout.addWidget(card, idx // cols, idx % cols)
            self.platform_cards.append(card)
        
        row_wrap = QHBoxLayout()
        row_wrap.addStretch(1)
        row_wrap.addLayout(cards_layout)
        row_wrap.addStretch(1)
        self.viewLayout.addLayout(row_wrap)
        
        self.viewLayout.addSpacing(8)

                
    def _on_platform_clicked(self, platform_id: str):
        """平台点击回调；Pro 平台需已登录且具备 Pro 权限才可选择，否则提示升级"""
        # 插件禁用：直接提示
        try:
            from src.utils.plugin_settings import is_platform_enabled
            if not is_platform_enabled(platform_id):
                parent = self.parent() or self.window()
                from qfluentwidgets import InfoBar
                InfoBar.warning("已禁用", "请在 设置-插件配置 中启用该平台后再添加账号。", parent=parent)
                return
        except Exception:
            pass
        from src.utils.pro_platforms import is_pro_platform
        from src.services.auth.current_user_service import CurrentUserService
        if is_pro_platform(platform_id):
            curr = CurrentUserService()
            if not curr.is_logged_in():
                parent = self.parent() or self.window()
                from src.ui.utils.fluent_dialogs import show_confirm
                if not show_confirm(parent, "提示", "Pro 插件需要登录软件后使用，是否登录？"):
                    return
                from src.ui.dialogs.login_dialog import LoginDialog
                dialog = LoginDialog(parent)

                def on_login_ok():
                    # 登录后再次校验 Pro 权限，免费版仍不可选 Pro 平台
                    if not curr.has_pro_permission():
                        from src.ui.utils.fluent_dialogs import show_warning
                        show_warning(parent, "权限不足", "当前为免费版，无法添加 Pro 平台账号。请升级 Pro 会员后使用。")
                        return
                    self.selected_platform = platform_id
                    self.accept()

                dialog.login_success.connect(on_login_ok)
                dialog.exec()
                return
            if not curr.has_pro_permission():
                parent = self.parent() or self.window()
                from src.ui.utils.fluent_dialogs import show_warning
                show_warning(parent, "权限不足", "当前为免费版，无法添加 Pro 平台账号。请升级 Pro 会员后使用。")
                return
        self.selected_platform = platform_id
        self.accept()


class AccountNameMessageBox(AppMessageBoxBase):
    """账号名称输入对话框（Fluent UI）"""
    
    def __init__(self, platform_id: str, platform_config: Dict, parent=None):
        super().__init__(parent, header_title="完善账号信息")  # type: ignore
        self.platform_id = platform_id
        self.platform_config = platform_config
        self.result_data: Optional[Dict[str, Any]] = None
        
        # 调整大小
        self.widget.setMinimumWidth(450)
        
        self._setup_content()
        
        self.yesButton.setText("确定")
        self.cancelButton.setText("上一步")
        
        self.yesButton.clicked.connect(self._on_confirm)
        self.cancelButton.clicked.disconnect()
        self.cancelButton.clicked.connect(self.reject)

        # 统一底部背景颜色
        self.buttonGroup.setStyleSheet("background-color: transparent; border-top: 1px solid #EDEDED;")
        
        # 调整按钮顺序：上一步(cancel)在左，确定(yes)在右
        # 获取 buttonGroup 的布局（通常是 QHBoxLayout）
        button_layout = self.buttonGroup.layout()
        if button_layout:
             button_layout.removeWidget(self.yesButton)
             button_layout.removeWidget(self.cancelButton)
             button_layout.addWidget(self.cancelButton)
             button_layout.addWidget(self.yesButton)

        self.yesButton.setStyleSheet("""
            QPushButton {
                border-radius: 5px;
                padding: 6px 12px;
                font-size: 14px;
            }
        """)
        self.cancelButton.setStyleSheet("""
            QPushButton {
                border: 1px solid #EDEDED;
                border-radius: 5px;
                background-color: #FFFFFF;
                padding: 6px 12px;
                font-size: 14px;
                color: #333333;
            }
            QPushButton:hover {
                background-color: #F5F5F5;
            }
            QPushButton:pressed {
                background-color: #EEEEEE;
            }
        """)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _setup_content(self):
        """设置内容"""
        # 平台信息展示
        info_layout = QHBoxLayout()
        icon_label = QLabel(self.platform_config.get("icon", "📱"), self.widget)
        font = QFont()
        font.setPointSize(24)
        icon_label.setFont(font)
        
        name_label = SubtitleLabel(self.platform_config.get("name", ""), self.widget)
        
        info_layout.addWidget(icon_label)
        info_layout.addWidget(name_label)
        info_layout.addStretch()
        
        self.viewLayout.addLayout(info_layout)
        self.viewLayout.addSpacing(20)
        
        # 账号名称输入
        self.viewLayout.addWidget(BodyLabel("账号名称（可选）", self.widget))
        self.name_edit = LineEdit(self.widget)
        default_name = f"{self.platform_config['name']}账号"
        self.name_edit.setPlaceholderText(f"留空则默认：{default_name}")
        self.name_edit.setMaxLength(20)
        self.name_edit.returnPressed.connect(self._on_confirm)
        
        self.viewLayout.addWidget(self.name_edit)
        self.viewLayout.addSpacing(10)
        
        # 提示信息
        tip_label = BodyLabel("提示：名称仅用于本地区分，不影响实际发布。", self.widget)
        tip_label.setTextColor('#999999', '#999999') # 设置灰度
        self.viewLayout.addWidget(tip_label)

    def _on_confirm(self):
        """确定按钮回调"""
        account_name = self.name_edit.text().strip()
        default_name = f"{self.platform_config['name']}账号"
        
        if not account_name:
            account_name = default_name
            
        # 简单验证
        if len(account_name) > 20:
             # 这里无法直接弹窗，只能通过 InfoBar 提示，但 MessageBoxBase 也是通过遮罩显示的
             # 简单起见，我们重置焦点并return，或者抖动窗口
             self.name_edit.setFocus()
             return
            
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]+$', account_name):
             # 同样，简单处理
             self.name_edit.setFocus()
             self.name_edit.selectAll()
             return

        self.result_data = {
            "platform_username": account_name,
            "platform": self.platform_id,
            "platform_name": self.platform_config["name"],
            "platform_url": self.platform_config["url"]
        }
        self.accept()


class AddAccountDialog:
    """添加账号流程控制器"""
    
    def __init__(self, parent=None):
        self.parent = parent
        
    def show(self) -> Optional[Dict[str, Any]]:
        """显示添加账号流程"""
        if not FLUENT_WIDGETS_AVAILABLE:
            return None # 降级处理略,假设环境已就绪
            
        # 第一步：选择平台
        step1 = PlatformSelectMessageBox(self.parent)
        if not step1.exec():
            return None  # 用户取消
        
        platform_id = step1.selected_platform
        if not platform_id:
            return None
        config = PLATFORM_CONFIG.get(platform_id)
        if not config:
            return None
        
        # 第二步：配置指纹
        from .fingerprint_config_dialog import FingerprintConfigMessageBox
        step2 = FingerprintConfigMessageBox(self.parent)
        if not step2.exec():
            # 用户点击"上一步",返回第一步
            return self.show()  # 递归调用重新开始
        
        fingerprint_config = step2.get_fingerprint_config()
        
        # 返回结果
        return {
            "platform_username": f"{config['name']}账号",
            "platform": platform_id,
            "platform_name": config["name"],
            "platform_url": config["url"],
            "fingerprint_config": fingerprint_config  # 新增字段
        }

