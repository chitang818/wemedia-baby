"""声明原创设置弹窗（可复用于批量视频/图文页）。"""
from qfluentwidgets import CheckBox
from src.ui.components.base_dialog import AppMessageBoxBase
from PySide6.QtWidgets import QWidget


def show_declare_original_dialog(
    current_checked: bool,
    parent: QWidget,
) -> bool | None:
    """弹出声明原创设置弹窗。

    Returns:
        新的勾选状态（True/False），若用户取消则返回 None。
    """
    from qfluentwidgets import BodyLabel

    w = AppMessageBoxBase(parent, header_title="声明原创设置")
    hint = BodyLabel("是否对符合条件的系统账号声明原创？\n(仅对【视频号】平台生效)", w)
    w.viewLayout.addWidget(hint)

    check = CheckBox("声明原创", w)
    check.setChecked(current_checked)
    w.viewLayout.addWidget(check)
    w.widget.setMinimumWidth(320)

    w.yesButton.setText("确定")
    w.cancelButton.setText("取消")
    button_layout = getattr(w, "buttonLayout", None)
    if button_layout is None:
        button_layout = w.buttonGroup.layout()
    if button_layout:
        button_layout.removeWidget(w.yesButton)
        button_layout.removeWidget(w.cancelButton)
        button_layout.addWidget(w.cancelButton)
        button_layout.addWidget(w.yesButton)

    if w.exec():
        return check.isChecked()
    return None
