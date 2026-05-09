# -*- coding: utf-8 -*-
"""批量视频任务页 — 团购推广设置弹窗（StandardBaseDialog）。"""
from __future__ import annotations

import json
from typing import Tuple

from PySide6.QtWidgets import QVBoxLayout, QWidget

from qfluentwidgets import BodyLabel, LineEdit

from src.ui.components.base_dialog import StandardBaseDialog

_PROMO_TITLE_MAX = 10


def _parse_anchor_initial(raw: str) -> Tuple[str, str]:
    """与单条任务页 anchor_info JSON 格式对齐，解析出团购主内容、推广标题。"""
    s = (raw or "").strip()
    if not s:
        return "", ""
    if s.startswith("{"):
        try:
            d = json.loads(s)
            if isinstance(d, dict):
                main = (
                    d.get("tuan")
                    or d.get("link")
                    or d.get("url")
                    or d.get("anchor")
                    or ""
                )
                if not isinstance(main, str):
                    main = str(main) if main is not None else ""
                st = d.get("promotion_title") or d.get("short_title") or ""
                if not isinstance(st, str):
                    st = str(st) if st is not None else ""
                return main.strip(), st.strip()[:_PROMO_TITLE_MAX]
        except (json.JSONDecodeError, TypeError):
            pass
    return s, ""


class BatchGroupBuyDialog(StandardBaseDialog):
    """配置团购主内容与可选推广标题，写入 anchor_info（与发布列表、单条任务兼容）。"""

    def __init__(self, parent=None, *, anchor_info_initial: str = "") -> None:
        super().__init__(parent, title="团购设置")
        self.widget.setMinimumWidth(460)
        self._out_anchor = ""

        self.add_description(
            "填写团购挂载所需的主内容（如活动链接或口令）。可选填推广标题（最多 10 字），"
            "格式与单条发布任务中「团购」标签一致。"
        )

        main0, promo0 = _parse_anchor_initial(anchor_info_initial)

        box = QWidget(self.widget)
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        v.addWidget(BodyLabel("团购主内容", box))
        self._main_edit = LineEdit(box)
        self._main_edit.setPlaceholderText("链接、口令或说明文字")
        self._main_edit.setText(main0)
        v.addWidget(self._main_edit)
        v.addWidget(BodyLabel("推广标题（可选）", box))
        self._promo_edit = LineEdit(box)
        self._promo_edit.setPlaceholderText("最多 10 字")
        self._promo_edit.setMaxLength(_PROMO_TITLE_MAX)
        self._promo_edit.setText(promo0)
        v.addWidget(self._promo_edit)
        self.viewLayout.addWidget(box)

    def accept(self) -> None:
        main = self._main_edit.text().strip()
        promo = self._promo_edit.text().strip()[:_PROMO_TITLE_MAX]
        if not main:
            self._out_anchor = ""
        elif not promo:
            self._out_anchor = main
        else:
            self._out_anchor = json.dumps(
                {"tuan": main, "promotion_title": promo},
                ensure_ascii=False,
            )
        super().accept()

    def outcome(self) -> str:
        return self._out_anchor or ""
