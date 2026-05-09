"""
日期/时间选择器弹窗：将确定（对号）置于右侧、取消（X）置于左侧
在应用启动时对 qfluentwidgets 的 PickerPanel 做猴子补丁，不修改 site-packages。
"""


def apply_picker_confirm_right():
    """对 PickerPanel 的 buttonLayout 重排：取消、重置、确定（确定在右）。"""
    try:
        from qfluentwidgets.components.date_time.picker_base import PickerPanel
    except ImportError:
        return
    # 类内部调用的是名称改写后的 _PickerPanel__initWidget，必须替换该属性才能生效
    _mangled = "_PickerPanel__initWidget"
    _orig = getattr(PickerPanel, _mangled, None)
    if _orig is None:
        return

    def _initWidget_swapped(self):
        _orig(self)
        lay = getattr(self, "buttonLayout", None)
        if lay is None:
            return
        # 原顺序: yesButton, resetButton, cancelButton -> 改为 cancel, reset, yes
        for w in (self.cancelButton, self.resetButton, self.yesButton):
            lay.removeWidget(w)
        lay.addWidget(self.cancelButton)
        lay.addWidget(self.resetButton)
        lay.addWidget(self.yesButton)

    setattr(PickerPanel, _mangled, _initWidget_swapped)
