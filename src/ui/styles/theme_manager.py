"""
主题管理器
文件路径：src/ui/styles/theme_manager.py
功能：统一管理应用的主题和样式配置
"""

from typing import Optional
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPalette
import logging

# 导入 PySide6-Fluent-Widgets 主题相关
from qfluentwidgets import (
    setTheme, Theme, setThemeColor, isDarkTheme,
    qconfig, ConfigItem, OptionsConfigItem, OptionsValidator
)
FLUENT_WIDGETS_AVAILABLE = True

logger = logging.getLogger(__name__)


class ThemeMode:
    """主题模式枚举"""
    AUTO = "auto"
    LIGHT = "light"
    DARK = "dark"


class ThemeManager:
    """主题管理器 - 统一管理应用的主题和样式
    
    使用 PySide6-Fluent-Widgets 的主题系统，提供：
    - 主题模式切换（跟随系统/浅色/深色）
    - 主题色配置
    - 全局样式管理
    """
    
    # 默认主题色（蓝色）
    DEFAULT_THEME_COLOR = "#0078D4"

    # 预设主题色
    PRESET_COLORS = {
        "蓝色": "#0078D4",
        "绿色": "#107C10",
        "紫色": "#8764B8",
        "红色": "#E81123",
        "橙色": "#F7630C",
        "青色": "#00B7C3",
        "粉色": "#E3008C",
        "灰色": "#5D5A58"
    }
    
    # --- 调色板定义 (Semantic Colors) ---
    # 浅色模式调色板
    LIGHT_PALETTE = {
        "BG_MAIN": "#F3F3F3",       # 主背景 (Mica Alt)
        "BG_CARD": "#FFFFFF",       # 卡片背景
        "TEXT_PRIMARY": "#1A1A1A",  # 主要文字
        "TEXT_SECONDARY": "#666666",# 次要文字
        "BORDER_DEFAULT": "#E5E5E5",# 默认边框
        "SCROLL_HANDLE": "#C1C1C1", # 滚动条滑块
        "BG_HOVER": "rgba(0, 0, 0, 10)", # 悬停背景
        "BG_SELECTED": "rgba(0, 120, 212, 30)", # 选中背景 (基于主题色，后续动态生成)
        "BG_SELECTED_HOVER": "rgba(0, 120, 212, 40)", # 选中+悬停
        "INPUT_BG": "#FFFFFF",      # 输入框背景 (Standard) or #E8EAED for contrast
        "THEME_BLUE": "#0078D4",    # 主题蓝
    }

    # 深色模式调色板
    DARK_PALETTE = {
        "BG_MAIN": "#202020",       # 主背景 (Mica Alt Dark)
        "BG_CARD": "#2D2D2D",       # 卡片背景
        "TEXT_PRIMARY": "#FFFFFF",  # 主要文字
        "TEXT_SECONDARY": "#D0D0D0",# 次要文字
        "BORDER_DEFAULT": "#3E3E3E",# 默认边框
        "SCROLL_HANDLE": "#606060", # 滚动条滑块
        "BG_HOVER": "rgba(255, 255, 255, 10)", # 悬停背景
        "BG_SELECTED": "rgba(0, 120, 212, 40)", # 选中背景
        "BG_SELECTED_HOVER": "rgba(0, 120, 212, 50)", # 选中+悬停
        "INPUT_BG": "#333333",      # 输入框背景
        "THEME_BLUE": "#4CC2FF",    # 主题蓝 (Light Blue for Dark Mode)
    }

    _instance = None
    
    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化主题管理器"""
        if self._initialized:
            return
        
        self._current_mode = self._load_persisted_theme_mode()
        self._current_color = self.DEFAULT_THEME_COLOR
        self._qss_content = ""
        self._initialized = True
        
        # 加载 QSS 模板
        self._load_qss_template()
        
        # 应用初始主题
        self._apply_theme()
        
    def get_theme_color(self) -> str:
        """获取当前主题颜色（十六进制）"""
        return self._current_color
    
    def get_theme_mode(self) -> str:
        """获取当前主题模式"""
        return self._current_mode

    def set_theme_mode(self, mode: str):
        """设置主题模式并立即应用"""
        mode = (mode or "").strip().lower()
        if mode not in (ThemeMode.AUTO, ThemeMode.LIGHT, ThemeMode.DARK):
            mode = ThemeMode.AUTO
        self._current_mode = mode
        self._persist_theme_mode(self._current_mode)
        self._apply_theme()

    @staticmethod
    def _persist_theme_mode(mode: str) -> None:
        """持久化主题模式到 app_config.ui.theme_mode。"""
        try:
            from src.ui.utils.async_helper import run_async_from_ui
            from src.infrastructure.common.config.config_center import get_registered_config_center
            from src.infrastructure.common.config.app_config_keys import KEY_UI, UI_THEME_MODE
            from src.infrastructure.common.config.app_config_merge import merge_app_config, read_app_config_from_disk_sync

            async def _save() -> None:
                cc = get_registered_config_center()
                if cc is not None:
                    ui = dict(cc.get_app_config().get(KEY_UI) or {})
                else:
                    root = read_app_config_from_disk_sync()
                    ui = dict(root.get(KEY_UI) or {})
                ui[UI_THEME_MODE] = mode
                await merge_app_config(cc, {KEY_UI: ui})

            run_async_from_ui(_save)
        except Exception:
            pass

    @staticmethod
    def _load_persisted_theme_mode() -> str:
        """从 app_config.json 同步读取主题模式（ConfigCenter 可能尚未初始化）。"""
        try:
            from src.infrastructure.common.config.app_config_merge import read_app_config_from_disk_sync
            from src.infrastructure.common.config.app_config_keys import KEY_UI, UI_THEME_MODE

            root = read_app_config_from_disk_sync()
            ui = root.get(KEY_UI)
            if isinstance(ui, dict):
                raw = ui.get(UI_THEME_MODE)
                if raw is not None:
                    mode = str(raw).strip().lower()
                    if mode in (ThemeMode.AUTO, ThemeMode.LIGHT, ThemeMode.DARK):
                        return mode
        except Exception:
            pass
        return ThemeMode.AUTO

    def _apply_theme(self):
        """应用当前主题配置（应用内 setTheme 的权威入口；主窗口请勿再覆盖）。"""
        # 设置 Fluent Widgets 主题
        if self._current_mode == ThemeMode.AUTO:
            setTheme(Theme.AUTO)
        elif self._current_mode == ThemeMode.DARK:
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.LIGHT)
            
        # 更新自定义 QSS
        self._update_qss()
        
    def _load_qss_template(self):
        """加载 QSS 模板文件"""
        import os
        try:
            # 使用 PathManager 统一路径，兼容打包环境
            from src.infrastructure.common.path_manager import PathManager
            qss_path = str(PathManager.get_resource_path("src/ui/styles/style.qss"))
            # 回退方案：如果 PathManager 路径不存在，尝试 __file__ 相对路径
            if not os.path.exists(qss_path):
                current_dir = os.path.dirname(os.path.abspath(__file__))
                qss_path = os.path.join(current_dir, "style.qss")
            if os.path.exists(qss_path):
                with open(qss_path, "r", encoding="utf-8") as f:
                    self._qss_content = f.read()
                logger.debug(f"加载 QSS 模板成功: {qss_path}")
            else:
                logger.warning(f"QSS 文件不存在: {qss_path}")
        except Exception as e:
            logger.error(f"加载 QSS 模板失败: {e}")

    def _get_current_palette(self) -> dict:
        """获取当前模式下的调色板"""
        is_dark = False
        
        if self._current_mode == ThemeMode.AUTO:
            is_dark = isDarkTheme()
        elif self._current_mode == ThemeMode.DARK:
            is_dark = True
            
        return self.DARK_PALETTE.copy() if is_dark else self.LIGHT_PALETTE.copy()

    def _update_qss(self):
        """更新全局 QSS"""
        if not self._qss_content:
            return
            
        try:
            # 1. 获取基础调色板
            palette = self._get_current_palette()
            
            # 2. 动态生成基于主题色的变量
            c = QColor(self._current_color)
            
            # 选中背景色 (RGBA)
            # 浅色模式: alpha 30, 深色模式: alpha 40
            alpha = 40 if palette == self.DARK_PALETTE else 30
            palette['BG_SELECTED'] = f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"
            palette['BG_SELECTED_HOVER'] = f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha + 10})"
            
            # 3. 模板替换
            final_qss = self._qss_content
            for key, value in palette.items():
                placeholder = f"{{{{{key}}}}}"  # e.g., {{BG_CARD}}
                final_qss = final_qss.replace(placeholder, value)
            
            # 替换旧的占位符 (兼容性)
            final_qss = final_qss.replace("rgba(0, 120, 212, 30)", palette['BG_SELECTED'])
            
            # 4. 应用到 QApplication
            app = QApplication.instance()
            if app:
                # Appending our stylesheet to global stylesheet
                # Note: We need to be careful not to overwrite FluentWidget's internal styles completely
                # but usually qfluentwidgets manages its own styles on widgets directly.
                app.setStyleSheet(final_qss)
                # Windows 上原生 QToolTip 常按调色板绘制背景，QSS 的 background 可能不生效；
                # 全局 QWidget { color } 仍会作用到提示文字，易出现深底深字「黑块」。与主题对齐 ToolTip 角色即可。
                pal = app.palette()
                pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(palette["BG_CARD"]))
                pal.setColor(QPalette.ColorRole.ToolTipText, QColor(palette["TEXT_PRIMARY"]))
                app.setPalette(pal)
                logger.debug(f"全局 QSS 已更新 (Mode: {self._current_mode})")
                
        except Exception as e:
            logger.error(f"更新 QSS 失败: {e}", exc_info=True)
    
    @staticmethod
    def get_preset_colors() -> dict:
        """获取预设主题色"""
        return ThemeManager.PRESET_COLORS.copy()


# 全局主题管理器实例
theme_manager = ThemeManager()


def get_theme_manager() -> ThemeManager:
    """获取主题管理器实例"""
    return theme_manager

