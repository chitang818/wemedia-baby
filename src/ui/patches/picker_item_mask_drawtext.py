"""
qfluentwidgets ItemMaskWidget：第二行 item 可能为 None 时仍调用 _drawText，
会触发 AttributeError，并导致 QPainter 未正确结束、递归重绘等连锁问题。

在应用启动时对 ItemMaskWidget._drawText 做包装，不修改 site-packages。
"""


def apply_picker_item_mask_drawtext_safe():
    try:
        from qfluentwidgets.components.date_time.picker_base import ItemMaskWidget
    except ImportError:
        return
    if getattr(ItemMaskWidget, "_wemedia_drawtext_safe", False):
        return
    _orig = ItemMaskWidget._drawText

    def _drawText(self, item, painter, y):
        if item is None:
            return
        return _orig(self, item, painter, y)

    ItemMaskWidget._drawText = _drawText  # type: ignore[assignment]
    ItemMaskWidget._wemedia_drawtext_safe = True
