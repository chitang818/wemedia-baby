# -*- coding: utf-8 -*-
"""批量视频任务页 — 购物车推广设置弹窗（StandardBaseDialog）。"""
from __future__ import annotations

import json

from qfluentwidgets import BodyLabel

from src.ui.components.base_dialog import StandardBaseDialog
from src.ui.publish.promotion.cart_selector_widget import CartSelectorWidget


class BatchCartDialog(StandardBaseDialog):
    """选择购物车推广商品库中的商品；确定后仅返回 cart_info JSON（含商品简称与商品短标题等）。

    商品短标题仅存于 JSON 的 ``cart_short_title``，与批量页「作品描述」字段无关；
    作品描述请在「④配置描述」中单独编辑。
    """

    def __init__(self, parent=None, *, initial_short_name: str = "") -> None:
        super().__init__(parent, title="购物车设置")
        self._out_goods_json = ""

        self._selector = CartSelectorWidget(
            self.widget, initial_short_name=initial_short_name
        )
        self.viewLayout.addWidget(self._selector)

        hint = BodyLabel(
            "若下拉列表为空，请先到左侧「购物车推广」页面添加商品。",
            self.widget,
        )
        hint.setTextColor("#888888", "#888888")
        self.viewLayout.addWidget(hint)

    def accept(self) -> None:
        payload = self._selector.build_cart_info_dict()
        if payload:
            self._out_goods_json = json.dumps(payload, ensure_ascii=False)
        else:
            self._out_goods_json = ""
        super().accept()

    def outcome(self) -> str:
        """``cart_info`` 存储串（JSON）；未选商品时为空串。"""
        return self._out_goods_json
