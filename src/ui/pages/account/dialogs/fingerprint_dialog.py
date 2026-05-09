# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QHeaderView, QTableWidgetItem
from PySide6.QtCore import Qt

from src.ui.components.base_dialog import install_escape_reject_shortcut, resolve_top_level_window_parent

try:
    from qfluentwidgets import TableWidget, PrimaryPushButton, PushButton
    FLUENT_WIDGETS_AVAILABLE = True
except ImportError:
    from PySide6.QtWidgets import QTableWidget as TableWidget, QPushButton as PrimaryPushButton, QPushButton as PushButton
    FLUENT_WIDGETS_AVAILABLE = False

class FingerprintDialog(QDialog):
    """浏览器指纹查看对话框"""
    
    def __init__(self, account_name: str, platform: str, fingerprint_data: dict, parent=None):
        super().__init__(resolve_top_level_window_parent(parent))
        install_escape_reject_shortcut(self)
        self.account_name = account_name
        self.platform = platform
        self.fingerprint_data = fingerprint_data or {}
        
        self.setWindowTitle(f"浏览器指纹 - {platform} - {account_name}")
        self.resize(800, 600)
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 表格
        self.table = TableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["参数", "值"])
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        
        # 填充数据
        self._populate_table()
        
        layout.addWidget(self.table)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_close = PrimaryPushButton("关闭", self)
        self.btn_close.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
        
    def _populate_table(self):
        """填充表格数据"""
        # 定义要展示的字段和说明
        fields = [
            ("user_agent", "User Agent (用户代理)"),
            ("viewport", "Viewport (视口大小)"),
            ("os_platform", "OS Platform (操作系统)"),
            ("hardware_concurrency", "CPU Cores (CPU核心数)"),
            ("cpu_model", "CPU 型号"),
            ("device_memory", "Device Memory (设备内存/GB)"),
            ("pixel_ratio", "Pixel Ratio (像素比)"),
            ("locale", "Locale (语言环境)"),
            ("timezone_id", "Timezone (时区)"),
            ("webgl_vendor", "WebGL Vendor (显卡厂商)"),
            ("webgl_renderer", "WebGL Renderer (显卡渲染器)"),
            ("canvas_noise_seed", "Canvas Noise Seed (Canvas噪声种子)"),
            ("audio_context_seed", "Audio Context Seed (音频指纹种子)"),
            ("screen_width", "Screen Width (屏幕宽度)"),
            ("screen_height", "Screen Height (屏幕高度)"),
            ("connection_effective_type", "Network Type (网络类型)"),
            ("connection_downlink", "Downlink Speed (下行速度 Mbps)"),
        ]
        
        row = 0
        self.table.setRowCount(len(fields) + 5) # 预留一些额外行
        
        # 1. 优先展示定义好的字段
        for key, label in fields:
            value = self.fingerprint_data.get(key)
            if value is None and key == "viewport":
                 # 特殊处理 viewport 为 None 的情况
                 value = "Auto (自适应)"
            elif value is None:
                continue
                
            self._add_row(row, label, str(value))
            row += 1
            
        # 2. 展示其他未列出的字段 (如有)
        for key, value in self.fingerprint_data.items():
            if not any(f[0] == key for f in fields):
                # 过滤掉一些太长的或者不重要的内部字段
                if key in ["font_families", "plugins"]: 
                    continue
                self._add_row(row, key, str(value))
                row += 1
                
        self.table.setRowCount(row)

    def _add_row(self, row, label, value):
        ac = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        li = QTableWidgetItem(label)
        li.setTextAlignment(ac)
        vi = QTableWidgetItem(value)
        vi.setTextAlignment(ac)
        self.table.setItem(row, 0, li)
        self.table.setItem(row, 1, vi)
