"""
任务统计卡片
文件路径：src/ui/components/task_overview_card.py
功能：发布列表底部，以大数字 + 彩色标签展示四项统计，适配窄卡片 ≤160px。
"""

from typing import Optional, List, Any
from PySide6.QtWidgets import (
    QWidget, QLabel, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
)
from PySide6.QtCore import Qt


def _stat_block(label: str, color: str, bg: str, border: str, parent: QWidget):
    """一个小方块：大数字 + 彩色小标签，返回 (容器, 数值label)。"""
    block = QFrame(parent)
    block.setObjectName("StatBlock")
    block.setStyleSheet(
        f"#StatBlock {{ background:{bg}; border:1px solid {border}; border-radius:6px; }}"
    )
    v = QVBoxLayout(block)
    v.setContentsMargins(4, 6, 4, 6)
    v.setSpacing(2)
    v.setAlignment(Qt.AlignCenter)

    val = QLabel("0", block)
    val.setAlignment(Qt.AlignCenter)
    val.setStyleSheet(f"font-size:20px; font-weight:700; color:{color}; border:none; background:transparent;")

    lbl = QLabel(label, block)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet(f"font-size:11px; color:{color}; border:none; background:transparent;")

    v.addWidget(val)
    v.addWidget(lbl)
    return block, val


class TaskOverviewCard(QFrame):
    """任务统计卡片：2×2 方块，适配窄卡片。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("TaskOverviewCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignTop)

        # 标题行与「发布设置」卡片同结构：右侧留 52×32 占位，与齿轮按钮对齐，分隔线高度一致
        header = QWidget(self)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(0, 0, 0, 6)
        h_lay.setSpacing(0)

        title = QLabel("任务统计", header)
        title.setObjectName("UnifiedCardTitle")
        h_lay.addWidget(title)
        h_lay.addStretch(1)

        _header_placeholder = QWidget(header)
        _header_placeholder.setFixedSize(52, 32)
        _header_placeholder.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        h_lay.addWidget(_header_placeholder)

        lay.addWidget(header)

        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("SettingsCardSep")
        lay.addWidget(sep)
        lay.addSpacing(6)

        # 2×2 方块网格
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        self._b_total,     self._v_total     = _stat_block("总计", "#444444", "#f5f5f5", "#ddd",     self)
        self._b_remaining, self._v_remaining = _stat_block("剩余", "#1565c0", "#e3f2fd", "#90caf9",  self)
        self._b_success,   self._v_success   = _stat_block("成功", "#2e7d32", "#e8f5e9", "#a5d6a7",  self)
        self._b_failed,    self._v_failed    = _stat_block("失败", "#c62828", "#ffebee", "#ef9a9a",  self)

        grid.addWidget(self._b_total,     0, 0)
        grid.addWidget(self._b_remaining, 0, 1)
        grid.addWidget(self._b_success,   1, 0)
        grid.addWidget(self._b_failed,    1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        lay.addLayout(grid)
        lay.addStretch(1)

    def set_task_overview(
        self,
        total: int,
        remaining: int,
        current_index: int,
        task_items: Optional[List[Any]] = None,
    ):
        success_count = failed_count = 0
        if task_items:
            for item in task_items:
                s = item.get("status")
                if s == "success":
                    success_count += 1
                elif s == "failed":
                    failed_count += 1
        self._v_total.setText(str(total))
        self._v_remaining.setText(str(remaining))
        self._v_success.setText(str(success_count))
        self._v_failed.setText(str(failed_count))
