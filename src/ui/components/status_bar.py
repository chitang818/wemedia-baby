from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor
from datetime import datetime
from qfluentwidgets import parseColor, themeColor, isDarkTheme

class CustomStatusBar(QWidget):
    """自定义底部状态栏"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self._init_ui()
        self._init_timer()
        
    def _init_ui(self):
        """初始化UI"""
        self.h_layout = QHBoxLayout(self)
        self.h_layout.setContentsMargins(16, 0, 16, 0)
        self.h_layout.setSpacing(12)
        
        # 背景颜色设置（在 paintEvent 中或样式表中处理更佳，这里简单用样式表）
        self.setObjectName("CustomStatusBar")
        self._update_style()
        
        # 1. 状态标签 (左侧)
        self.status_label = QLabel("准备就绪", self)
        self.status_label.setObjectName("statusLabel")
        
        # 分隔符 1
        self.sep1 = self._create_separator()
        
        # 2. 任务进度标签 (中间)
        self.task_label = QLabel("暂无运行中的任务", self)
        self.task_label.setObjectName("taskLabel")
        
        # 3. 伸缩占位符
        self.h_layout.addWidget(self.status_label)
        self.h_layout.addWidget(self.sep1)
        self.h_layout.addWidget(self.task_label)
        self.h_layout.addStretch(1)
        
        # 分隔符 2
        self.sep2 = self._create_separator()
        
        # 4. 时间标签 (右侧)
        self.time_label = QLabel(self)
        self.time_label.setObjectName("timeLabel")
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._update_time()
        
        self.h_layout.addWidget(self.sep2)
        self.h_layout.addWidget(self.time_label)
        
    def _create_separator(self):
        """创建分隔符"""
        sep = QFrame(self)
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Sunken)
        sep.setFixedHeight(14)
        sep.setStyleSheet("color: #CCCCCC;")  # 浅灰色分隔线
        return sep
        
    def _init_timer(self):
        """初始化时间更新定时器"""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_time)
        self.timer.start(1000) # 每秒更新
        
    def _update_time(self):
        """更新时间显示"""
        now = datetime.now()
        self.time_label.setText(now.strftime("%Y-%m-%d %H:%M"))
        
    def set_status(self, text: str):
        """设置状态文本"""
        self.status_label.setText(text)
        
    def set_task_info(self, text: str):
        """设置任务信息"""
        self.task_label.setText(text)
        
    def _update_style(self):
        """更新样式"""
        bg_color = "#F3F3F3" if not isDarkTheme() else "#202020"
        text_color = "#333333" if not isDarkTheme() else "#CCCCCC"
        border_color = "#E5E5E5" if not isDarkTheme() else "#2B2B2B"
        
        self.setStyleSheet(f"""
            #CustomStatusBar {{
                background-color: {bg_color};
                border-top: 1px solid {border_color};
            }}
            QLabel {{
                color: {text_color};
                font-family: 'Microsoft YaHei', 'Segoe UI';
                font-size: 12px;
            }}
        """)
