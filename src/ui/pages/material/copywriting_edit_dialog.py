"""
文案新建/编辑弹窗（开源包装层）
闭源版实现：`src/proprietary/ui/pages/material/copywriting_edit_dialog.py`
"""

try:
    from src.proprietary.ui.pages.material.copywriting_edit_dialog import CopywritingEditDialog
except Exception as _import_err:
    import logging

    logging.getLogger(__name__).error(
        "无法加载 CopywritingEditDialog: %s", _import_err, exc_info=True
    )

    from src.ui.components.base_dialog import StandardBaseDialog

    class CopywritingEditDialog(StandardBaseDialog):  # type: ignore[no-redef]
        """占位弹窗（闭源模块加载失败时）"""

        def __init__(self, parent=None, item_data=None, strict_work_id: bool = True):
            super().__init__(parent, header_title="文案编辑不可用")

        def get_form_data(self):
            return {}

        def validate(self):
            return "文案编辑模块未加载，请检查安装包是否完整。"
