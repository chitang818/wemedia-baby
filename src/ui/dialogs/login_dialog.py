"""
登录对话框（开源包装层）

闭源版真实实现：`src/proprietary/ui/login_dialog.py`
开源版：若缺失闭源目录，则提供提示性弹窗/占位，不影响主程序运行。
"""

from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal


try:
    from config.feature_flags import FeatureFlags
    if not FeatureFlags.is_pro_build():
        raise Exception("Force open source mode")
        
    from src.proprietary.ui.login_dialog import LoginDialog as _ImplLoginDialog
    LoginDialog = _ImplLoginDialog
except Exception:
    class LoginDialog(QWidget):  # type: ignore[no-redef]
        login_success = Signal(dict)

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent)

        def exec(self) -> int:
            try:
                from src.ui.utils.fluent_dialogs import show_warning
                show_warning(None, "未提供登录", "当前为开源版：不包含媒小宝账号登录功能。")
            except Exception:
                pass
            return 0
