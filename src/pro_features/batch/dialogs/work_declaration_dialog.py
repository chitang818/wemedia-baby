# -*- coding: utf-8 -*-
"""批量页「作品申明」弹窗：按平台分段切换配置（抖音 / 快手 / 视频号 / 小红书）。"""
from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget, QSizePolicy
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    ComboBox,
    SegmentedWidget,
)

from src.ui.components.base_dialog import AppMessageBoxBase
from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip
from src.domain.publish.work_declaration import (
    DOUYIN_CHOICES,
    KUAISHOU_CHOICES,
    XHS_CONTENT_ATTR_CHOICES,
    normalize_douyin_value,
    normalize_kuaishou_value,
    normalize_xhs_content_attr,
)


def _apply_work_declaration_pivot_style(pivot: SegmentedWidget) -> None:
    """与批量「定时发布」弹窗 SegmentedWidget 视觉对齐。"""
    try:
        from src.ui.styles.theme_manager import ThemeManager

        palette = ThemeManager()._get_current_palette()
    except Exception:
        palette = {
            "BG_HOVER": "rgba(0,0,0,0.06)",
            "BORDER_DEFAULT": "#E5E5E5",
            "TEXT_PRIMARY": "#1A1A1A",
            "TEXT_SECONDARY": "#666666",
            "BG_CARD": "#FFFFFF",
        }
    bg_hover = palette.get("BG_HOVER", "rgba(0,0,0,0.06)")
    border = palette.get("BORDER_DEFAULT", "#E5E5E5")
    tp = palette.get("TEXT_PRIMARY", "#1A1A1A")
    ts = palette.get("TEXT_SECONDARY", "#666666")
    bg_card = palette.get("BG_CARD", "#FFFFFF")
    pivot.setStyleSheet(f"""
        #WorkDeclarationPivot {{
            background-color: {bg_hover}; border: 1px solid {border};
            border-radius: 8px; padding: 4px; min-height: 36px;
        }}
        #WorkDeclarationPivot SegmentedItem {{
            border: none; border-radius: 6px; padding: 6px 16px;
            font-size: 13px; color: {ts}; background: transparent;
        }}
        #WorkDeclarationPivot SegmentedItem:hover {{
            color: {tp}; background: rgba(128,128,128,0.15);
        }}
        #WorkDeclarationPivot SegmentedItem[isSelected="true"],
        #WorkDeclarationPivot SegmentedItem[isSelected="1"] {{
            color: {tp}; font-weight: 600; background-color: {bg_card};
        }}
    """)


def show_work_declaration_dialog(
    *,
    douyin_value: str,
    kuaishou_value: str,
    douyin_auto: bool,
    kuaishou_auto: bool,
    wechat_is_original: bool,
    xhs_is_original: bool,
    xhs_content_attr: str,
    xhs_content_attr_auto: bool,
    parent: QWidget,
) -> Optional[Tuple[str, str, bool, bool, bool, bool, str, bool]]:
    """弹出作品申明设置。

    Returns:
        (douyin_enum, kuaishou_enum, wechat_is_original, douyin_auto, kuaishou_auto,
         xhs_is_original, xhs_content_attr, xhs_content_attr_auto)，取消则 None。
    """
    w = AppMessageBoxBase(parent, header_title="作品申明")
    w.widget.setMinimumWidth(460)

    root = QVBoxLayout()
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(10)

    hint = BodyLabel(
        "按平台分别配置；仅对对应平台的发布任务生效。",
        w,
    )
    hint.setWordWrap(True)
    root.addWidget(hint)

    pivot = SegmentedWidget(w)
    pivot.setObjectName("WorkDeclarationPivot")
    _apply_work_declaration_pivot_style(pivot)

    stacked = QStackedWidget(w)
    stacked.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)

    # ----- 抖音 -----
    card_dy = CardWidget(w)
    dy_l = QVBoxLayout(card_dy)
    dy_l.setContentsMargins(12, 12, 12, 12)
    dy_l.setSpacing(8)
    dy_l.addWidget(
        CaptionLabel("自主声明对应发布页「作品申明」中的选项。", card_dy),
    )
    chk_dy_auto = CheckBox("发布时自动设置", card_dy)
    chk_dy_auto.setChecked(bool(douyin_auto))
    apply_instructional_tooltip(
        "勾选：发布时在网页上按所选申明自动操作。\n"
        "不勾选：不启用自动设置；所选申明仍会保存。",
        chk_dy_auto,
        position=ToolTipPosition.BOTTOM,
    )
    combo_dy = ComboBox(card_dy)
    for val, label in DOUYIN_CHOICES:
        combo_dy.addItem(label, userData=val)
    dv = normalize_douyin_value(douyin_value)
    for i in range(combo_dy.count()):
        if combo_dy.itemData(i) == dv:
            combo_dy.setCurrentIndex(i)
            break
    combo_dy.setEnabled(chk_dy_auto.isChecked())
    chk_dy_auto.toggled.connect(combo_dy.setEnabled)
    row_dy = QHBoxLayout()
    row_dy.setContentsMargins(0, 0, 0, 0)
    row_dy.setSpacing(12)
    row_dy.addWidget(chk_dy_auto, 0, Qt.AlignmentFlag.AlignVCenter)
    row_dy.addWidget(combo_dy, 0, Qt.AlignmentFlag.AlignVCenter)
    row_dy.addStretch(1)
    dy_l.addLayout(row_dy)
    dy_l.addWidget(
        CaptionLabel("不勾选时不在发布页自动点击，下拉所选仍会保存。", card_dy),
    )
    stacked.addWidget(card_dy)

    # ----- 快手 -----
    card_ks = CardWidget(w)
    ks_l = QVBoxLayout(card_ks)
    ks_l.setContentsMargins(12, 12, 12, 12)
    ks_l.setSpacing(8)
    ks_l.addWidget(CaptionLabel("原创 / 来源类声明选项。", card_ks))
    chk_ks_auto = CheckBox("发布时自动设置", card_ks)
    chk_ks_auto.setChecked(bool(kuaishou_auto))
    apply_instructional_tooltip(
        "勾选：发布时在网页上按所选申明自动操作。\n"
        "不勾选：不启用自动设置；所选仍会保存。",
        chk_ks_auto,
        position=ToolTipPosition.BOTTOM,
    )
    combo_ks = ComboBox(card_ks)
    for val, label in KUAISHOU_CHOICES:
        combo_ks.addItem(label, userData=val)
    kv = normalize_kuaishou_value(kuaishou_value)
    for i in range(combo_ks.count()):
        if combo_ks.itemData(i) == kv:
            combo_ks.setCurrentIndex(i)
            break
    combo_ks.setEnabled(chk_ks_auto.isChecked())
    chk_ks_auto.toggled.connect(combo_ks.setEnabled)
    row_ks = QHBoxLayout()
    row_ks.setContentsMargins(0, 0, 0, 0)
    row_ks.setSpacing(12)
    row_ks.addWidget(chk_ks_auto, 0, Qt.AlignmentFlag.AlignVCenter)
    row_ks.addWidget(combo_ks, 0, Qt.AlignmentFlag.AlignVCenter)
    row_ks.addStretch(1)
    ks_l.addLayout(row_ks)
    ks_l.addWidget(
        CaptionLabel("不勾选时不在发布页自动点击，下拉所选仍会保存。", card_ks),
    )
    stacked.addWidget(card_ks)

    # ----- 视频号 -----
    card_wx = CardWidget(w)
    wx_l = QVBoxLayout(card_wx)
    wx_l.setContentsMargins(12, 12, 12, 12)
    wx_l.setSpacing(8)
    wx_l.addWidget(CaptionLabel("仅作用于视频号发布任务。", card_wx))
    chk_orig = CheckBox("申明原创（关闭则为不申明原创）", card_wx)
    chk_orig.setChecked(bool(wechat_is_original))
    wx_l.addWidget(chk_orig)
    wx_l.addStretch(1)
    stacked.addWidget(card_wx)

    # ----- 小红书 -----
    card_xhs = CardWidget(w)
    xhs_l = QVBoxLayout(card_xhs)
    xhs_l.setContentsMargins(12, 12, 12, 12)
    xhs_l.setSpacing(8)
    xhs_l.addWidget(
        CaptionLabel("原创声明与「内容属性」互不影响。", card_xhs),
    )
    chk_xhs_orig = CheckBox("申明原创（关闭则为不申明原创）", card_xhs)
    chk_xhs_orig.setChecked(bool(xhs_is_original))
    xhs_l.addWidget(chk_xhs_orig)

    chk_xhs_attr_auto = CheckBox("发布时自动设置内容属性", card_xhs)
    chk_xhs_attr_auto.setChecked(bool(xhs_content_attr_auto))
    apply_instructional_tooltip(
        "勾选：发布时在网页上按所选内容属性自动操作。\n"
        "不勾选：不启用自动设置；所选仍会保存。",
        chk_xhs_attr_auto,
        position=ToolTipPosition.BOTTOM,
    )
    combo_xhs = ComboBox(card_xhs)
    for val, label in XHS_CONTENT_ATTR_CHOICES:
        combo_xhs.addItem(label, userData=val)
    xv = normalize_xhs_content_attr(xhs_content_attr)
    for i in range(combo_xhs.count()):
        if combo_xhs.itemData(i) == xv:
            combo_xhs.setCurrentIndex(i)
            break
    combo_xhs.setEnabled(chk_xhs_attr_auto.isChecked())
    chk_xhs_attr_auto.toggled.connect(combo_xhs.setEnabled)
    row_xhs = QHBoxLayout()
    row_xhs.setContentsMargins(0, 0, 0, 0)
    row_xhs.setSpacing(12)
    row_xhs.addWidget(chk_xhs_attr_auto, 0, Qt.AlignmentFlag.AlignVCenter)
    row_xhs.addWidget(combo_xhs, 0, Qt.AlignmentFlag.AlignVCenter)
    row_xhs.addStretch(1)
    xhs_l.addLayout(row_xhs)
    xhs_l.addWidget(
        CaptionLabel("不勾选时不在发布页操作内容属性下拉，所选仍会保存。", card_xhs),
    )
    stacked.addWidget(card_xhs)

    pivot.addItem(
        routeKey="douyin",
        text="抖音",
        onClick=lambda: stacked.setCurrentIndex(0),
    )
    pivot.addItem(
        routeKey="kuaishou",
        text="快手",
        onClick=lambda: stacked.setCurrentIndex(1),
    )
    pivot.addItem(
        routeKey="wechat",
        text="视频号",
        onClick=lambda: stacked.setCurrentIndex(2),
    )
    pivot.addItem(
        routeKey="xiaohongshu",
        text="小红书",
        onClick=lambda: stacked.setCurrentIndex(3),
    )
    pivot.setCurrentItem("douyin")

    root.addWidget(pivot)
    root.addWidget(stacked, 1)

    host = QWidget(w)
    host.setLayout(root)
    w.viewLayout.addWidget(host)

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
        out_dy = str(combo_dy.currentData() or combo_dy.itemData(combo_dy.currentIndex()))
        out_ks = str(combo_ks.currentData() or combo_ks.itemData(combo_ks.currentIndex()))
        out_xhs = str(
            combo_xhs.currentData()
            if combo_xhs.currentData() is not None
            else combo_xhs.itemData(combo_xhs.currentIndex())
        )
        return (
            normalize_douyin_value(out_dy),
            normalize_kuaishou_value(out_ks),
            chk_orig.isChecked(),
            chk_dy_auto.isChecked(),
            chk_ks_auto.isChecked(),
            chk_xhs_orig.isChecked(),
            normalize_xhs_content_attr(out_xhs or None),
            chk_xhs_attr_auto.isChecked(),
        )
    return None
