"""
密码重置对话框（开源包装层）

闭源版真实实现：`src/proprietary/ui/password_reset_dialog.py`
开源版：若缺失闭源目录，则提供提示性弹窗/占位，不影响主程序运行。
"""

from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import QWidget


try:
    from config.feature_flags import FeatureFlags
    if not FeatureFlags.is_pro_build():
        raise Exception("Force open source mode")

    from src.proprietary.ui.password_reset_dialog import PasswordResetDialog as _ImplPasswordResetDialog
    PasswordResetDialog = _ImplPasswordResetDialog
except Exception:
    class PasswordResetDialog(QWidget):  # type: ignore[no-redef]
        """密码重置对话框开源占位 —— 开源版不提供媒小宝账号密码重置功能。"""

        def __init__(self, parent: Optional[QWidget] = None):
            super().__init__(parent)

        def exec(self) -> int:
            try:
                from src.ui.utils.fluent_dialogs import show_warning
                show_warning(None, "功能不可用", "当前为开源版：不包含媒小宝账号密码重置功能。")
            except Exception:
                pass
            return 0
