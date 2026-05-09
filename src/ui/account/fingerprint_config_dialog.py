"""
指纹配置对话框
文件路径:src/ui/account/fingerprint_config_dialog.py
功能:添加账号时配置浏览器指纹参数(中国专用版)
"""

from typing import Optional, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt
import logging

try:
    from qfluentwidgets import (
        BodyLabel,
        RadioButton, ComboBox
    )
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    FLUENT_WIDGETS_AVAILABLE = False

from src.ui.components.base_dialog import AppMessageBoxBase

logger = logging.getLogger(__name__)


# 固定参数(中国专用)
FIXED_CHINA_CONFIG = {
    "timezone_id": "Asia/Shanghai",
    "locale": "zh-CN",
    "languages": ["zh-CN", "zh", "en"],
}

# 可自定义的参数选项
CUSTOMIZABLE_OPTIONS = {
    "screen_resolution": [
        {"name": "1920x1080 (全高清)", "width": 1920, "height": 1080},
        {"name": "2560x1440 (2K)", "width": 2560, "height": 1440},
        {"name": "1366x768 (笔记本)", "width": 1366, "height": 768},
        {"name": "1536x864 (笔记本)", "width": 1536, "height": 864},
        {"name": "3840x2160 (4K)", "width": 3840, "height": 2160},
    ],
    "user_agent_platform": [
        {"name": "Windows 10", "value": "Win32"},
        {"name": "Windows 11", "value": "Win32"},
        {"name": "MacOS", "value": "MacIntel"},
    ],
    # 整机档位：同时决定 CPU/内存/显卡/型号，避免厂商与渲染器字符串不一致
    "hardware_tier": [
        {"name": "入门办公（核显 / 入门独显）", "value": "entry"},
        {"name": "主流性能（中端独显）", "value": "mainstream"},
        {"name": "高端配置（高端独显与大内存）", "value": "high"},
    ],
    "canvas_noise": [
        {"name": "低噪声", "value": 0.0001},
        {"name": "中噪声", "value": 0.0003},
        {"name": "高噪声", "value": 0.0005},
    ],
}


class FingerprintConfigMessageBox(AppMessageBoxBase):
    """指纹配置对话框(中国专用版)"""
    
    def __init__(self, parent=None):
        super().__init__(parent, header_title="配置浏览器指纹")
        self.mode = "random"  # random 或 custom
        self.custom_config = {}
        
        # 调整大小
        self.widget.setMinimumWidth(500)
        
        self._setup_content()
        
        # 设置按钮
        self.yesButton.setText("确定")
        self.cancelButton.setText("上一步")
        
        # 统一底部背景颜色
        self.buttonGroup.setStyleSheet("background-color: transparent; border-top: 1px solid #EDEDED;")
        
        # 调整按钮顺序
        button_layout = self.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(self.yesButton)
            button_layout.removeWidget(self.cancelButton)
            button_layout.addWidget(self.cancelButton)
            button_layout.addWidget(self.yesButton)
        
        # 按钮样式：确定为主按钮，上一步为次要按钮
        self.yesButton.setStyleSheet("""
            QPushButton {
                border: 1px solid #0078D4;
                border-radius: 5px;
                background-color: #0078D4;
                padding: 6px 12px;
                font-size: 14px;
                color: #FFFFFF;
            }
            QPushButton:hover {
                background-color: #106EBE;
                border-color: #106EBE;
            }
            QPushButton:pressed {
                background-color: #005A9E;
                border-color: #005A9E;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                border-color: #CCCCCC;
                color: #666666;
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
        """设置内容区域"""
        # 模式选择
        self.random_radio = RadioButton("随机生成 (推荐)", self.widget)
        self.random_radio.setChecked(True)
        self.random_radio.clicked.connect(self._on_mode_changed)  # 使用clicked信号
        
        self.viewLayout.addWidget(self.random_radio)
        self.viewLayout.addSpacing(5)
        
        # 随机生成提示
        tip_label = BodyLabel("自动生成随机指纹参数", self.widget)
        tip_label.setTextColor('#999999', '#999999')
        self.viewLayout.addWidget(tip_label)
        
        self.viewLayout.addSpacing(20)
        
        # 自定义配置选项
        self.custom_radio = RadioButton("自定义配置", self.widget)
        self.custom_radio.clicked.connect(self._on_mode_changed)  # 使用clicked信号
        self.viewLayout.addWidget(self.custom_radio)
        
        self.viewLayout.addSpacing(10)
        
        # 自定义配置区域
        self._create_custom_config_area()
        
        # 固定参数提示
        self.viewLayout.addSpacing(15)
        fixed_tip = BodyLabel(
            "提示: 时区和语言已固定为中国大陆；自定义模式下 CPU/内存/显卡由「整机档位」自动配套生成。",
            self.widget,
        )
        fixed_tip.setTextColor('#666666', '#666666')
        self.viewLayout.addWidget(fixed_tip)
        
        self.viewLayout.addSpacing(10)
    
    def _create_custom_config_area(self):
        """创建自定义配置区域"""
        self.custom_area = QWidget(self.widget)
        # 使用网格布局优化空间利用
        from PySide6.QtWidgets import QGridLayout, QPushButton
        custom_layout = QGridLayout(self.custom_area)
        custom_layout.setContentsMargins(20, 0, 0, 0)
        custom_layout.setVerticalSpacing(15)
        custom_layout.setHorizontalSpacing(20)
        
        # 存储选项数据
        self.options_data = {}
        
        # --- 第一列 ---
        
        # 1. 屏幕分辨率
        custom_layout.addWidget(BodyLabel("屏幕分辨率:", self.custom_area), 0, 0)
        self.resolution_combo = ComboBox(self.custom_area)
        self.options_data["resolution"] = CUSTOMIZABLE_OPTIONS["screen_resolution"]
        for res in self.options_data["resolution"]:
            self.resolution_combo.addItem(res["name"])
        self.resolution_combo.setCurrentIndex(0)
        custom_layout.addWidget(self.resolution_combo, 0, 1)

        # --- 第二列 ---

        # 2. 操作系统平台
        custom_layout.addWidget(BodyLabel("操作系统平台:", self.custom_area), 0, 2)
        self.platform_combo = ComboBox(self.custom_area)
        self.options_data["platform"] = CUSTOMIZABLE_OPTIONS["user_agent_platform"]
        for p in self.options_data["platform"]:
            self.platform_combo.addItem(p["name"])
        self.platform_combo.setCurrentIndex(0)
        custom_layout.addWidget(self.platform_combo, 0, 3)
        
        # 3. 整机硬件档位（CPU/内存/显卡/型号一致，随机取该档常见组合）
        custom_layout.addWidget(BodyLabel("整机档位:", self.custom_area), 1, 0)
        self.tier_combo = ComboBox(self.custom_area)
        self.options_data["tier"] = CUSTOMIZABLE_OPTIONS["hardware_tier"]
        for t in self.options_data["tier"]:
            self.tier_combo.addItem(t["name"])
        self.tier_combo.setCurrentIndex(1)
        custom_layout.addWidget(self.tier_combo, 1, 1)

        # 4. Canvas噪声
        custom_layout.addWidget(BodyLabel("Canvas噪声强度:", self.custom_area), 1, 2)
        self.canvas_combo = ComboBox(self.custom_area)
        self.options_data["canvas"] = CUSTOMIZABLE_OPTIONS["canvas_noise"]
        for c in self.options_data["canvas"]:
            self.canvas_combo.addItem(c["name"])
        self.canvas_combo.setCurrentIndex(1)
        custom_layout.addWidget(self.canvas_combo, 1, 3)
        
        # --- 底部操作栏 ---
        
        # 恢复默认按钮
        if FLUENT_WIDGETS_AVAILABLE:
            from qfluentwidgets import PushButton
            self.reset_btn = PushButton("恢复默认", self.custom_area)
        else:
            self.reset_btn = QPushButton("恢复默认", self.custom_area)
            
        self.reset_btn.setFixedWidth(100)
        self.reset_btn.clicked.connect(self._reset_to_default)
        custom_layout.addWidget(self.reset_btn, 2, 0)

        self.custom_area.setEnabled(False)  # 初始禁用
        self.viewLayout.addWidget(self.custom_area)
        
    def _reset_to_default(self):
        """恢复默认设置"""
        self.resolution_combo.setCurrentIndex(0)
        self.platform_combo.setCurrentIndex(0)
        self.tier_combo.setCurrentIndex(1)
        self.canvas_combo.setCurrentIndex(1)
        
        if FLUENT_WIDGETS_AVAILABLE:
            from qfluentwidgets import InfoBar
            InfoBar.success(
                title='已恢复默认',
                content="自定义配置已重置为默认推荐值",
                parent=self,
                duration=2000
            )
    
    def _on_mode_changed(self):
        """模式切换"""
        if self.random_radio.isChecked():
            self.mode = "random"
            self.custom_area.setEnabled(False)
            logger.info("切换到随机生成模式")
        else:
            self.mode = "custom"
            self.custom_area.setEnabled(True)
            logger.info("切换到自定义配置模式")
        
        # 强制刷新UI
        self.custom_area.update()
    
    def get_fingerprint_config(self) -> Optional[Dict[str, Any]]:
        """获取指纹配置"""
        if self.mode == "random":
            logger.info("用户选择随机生成指纹")
            return None
        
        # 获取当前选中的索引
        res_idx = self.resolution_combo.currentIndex()
        plat_idx = self.platform_combo.currentIndex()
        tier_idx = self.tier_combo.currentIndex()
        canvas_idx = self.canvas_combo.currentIndex()

        from src.infrastructure.browser.hardware_profiles import pick_hardware_bundle_for_tier

        # 从本地数据中检索
        resolution = self.options_data["resolution"][res_idx]
        platform = self.options_data["platform"][plat_idx]
        tier = self.options_data["tier"][tier_idx]
        canvas = self.options_data["canvas"][canvas_idx]

        hw = pick_hardware_bundle_for_tier(tier["value"])

        config = {
            "screen_width": resolution["width"],
            "screen_height": resolution["height"],
            "platform": platform["value"],
            # 统一字段：canvas_noise_strength（旧字段 canvas_noise 仍保留兼容 ProfileManager）
            "canvas_noise_strength": canvas["value"],
            "canvas_noise": canvas["value"],
            # 固定参数
            **FIXED_CHINA_CONFIG,
            **hw,
        }

        logger.info(
            "用户自定义指纹: %s, %s, %s核, %sGB, %s",
            resolution["name"],
            tier["name"],
            hw["hardware_concurrency"],
            hw["device_memory"],
            platform["name"],
        )
        return config
