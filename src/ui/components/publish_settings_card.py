"""
发布设置卡片
文件路径：src/ui/components/publish_settings_card.py
功能：发布列表底部，参考任务统计卡片样式，双列网格展示当前发布设置。
"""

from typing import Optional
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QWidget, QPushButton,
)
from PySide6.QtCore import Qt, Signal, QSize

from src.ui.utils.fluent_tooltips import ToolTipPosition, apply_instructional_tooltip

try:
    from qfluentwidgets import PrimaryToolButton, FluentIcon
    _FLUENT = True
except ImportError:
    _FLUENT = False


def _setting_block(
    key: str,
    default: str,
    color: str,
    bg: str,
    border: str,
    parent: QWidget,
    *,
    label_width: int = 80,
):
    """一个设置方块：单行「key：val」横排，返回 (容器, val_label)。"""
    block = QFrame(parent)
    block.setObjectName("SettingBlock")
    block.setStyleSheet(
        f"#SettingBlock {{ background:{bg}; border:1px solid {border}; border-radius:6px; }}"
    )
    h = QHBoxLayout(block)
    h.setContentsMargins(8, 6, 8, 6)
    h.setSpacing(4)

    k_lbl = QLabel(f"{key}：", block)
    k_lbl.setStyleSheet("font-size:12px; color:#888; border:none; background:transparent;")
    k_lbl.setFixedWidth(label_width)

    v_lbl = QLabel(default, block)
    v_lbl.setWordWrap(False)
    v_lbl.setStyleSheet(
        f"font-size:13px; font-weight:700; color:{color}; border:none; background:transparent;"
    )

    h.addWidget(k_lbl)
    h.addWidget(v_lbl, 1)
    return block, v_lbl


class PublishSettingsCard(QFrame):
    """发布设置摘要卡片：双列 3 行彩色方块，样式与任务统计卡片一致。"""

    open_settings_clicked = Signal()

    # 每项设置的颜色方案 (text_color, bg, border)
    _COLORS = [
        ("#444444", "#f5f5f5", "#ddd"),      # 列表  — 灰
        ("#6a1b9a", "#f3e5f5", "#ce93d8"),   # 速度  — 紫
        ("#e65100", "#fff3e0", "#ffcc80"),   # 间隔  — 橙
        ("#1565c0", "#e3f2fd", "#90caf9"),   # 浏览器 — 蓝
        ("#00695c", "#e0f2f1", "#80cbc4"),   # 完成后（文件）— 青
        ("#b71c1c", "#ffebee", "#ef9a9a"),   # 完成后（关机）— 红
    ]

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("PublishSettingsCard")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignTop)

        # ── 标题行 ──────────────────────────────────
        header = QWidget(self)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(0, 0, 0, 6)
        h_lay.setSpacing(0)

        title_lbl = QLabel("发布设置", header)
        title_lbl.setObjectName("UnifiedCardTitle")
        h_lay.addWidget(title_lbl)
        h_lay.addStretch(1)

        if _FLUENT:
            # 与发布列表顶栏「发布」PrimaryPushButton 同源主色，避免自绘色值与主题不一致
            self._btn = PrimaryToolButton(FluentIcon.SETTING, header)
            self._btn.setIconSize(QSize(18, 18))
        else:
            self._btn = QPushButton("⚙", header)
            self._btn.setStyleSheet("""
                QPushButton {
                    background: #00897b;
                    color: #fff;
                    border: none;
                    border-radius: 6px;
                    padding: 0 10px;
                    font-size: 16px;
                    font-weight: 600;
                }
                QPushButton:hover { background: #00acc1; }
                QPushButton:pressed { background: #00796b; }
            """)
        self._btn.setFixedSize(52, 32)
        self._btn.setCursor(Qt.PointingHandCursor)
        self._btn.clicked.connect(self.open_settings_clicked)
        apply_instructional_tooltip(
            "打开发布设置",
            self._btn,
            position=ToolTipPosition.BOTTOM,
        )
        h_lay.addWidget(self._btn)
        lay.addWidget(header)

        # ── 分隔线 ──────────────────────────────────
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("SettingsCardSep")
        lay.addWidget(sep)
        lay.addSpacing(6)

        # ── 双列 3 行方块（与任务统计 2×2 网格一致）────────────────
        # 两个「完成后」：前者为发布后文件处理，后者为是否关机（由取值区分）
        keys = ["列表", "速度", "间隔", "浏览器", "完成后", "完成后"]
        self._val_labels: list[QLabel] = []
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        for i, (key, (color, bg, border)) in enumerate(zip(keys, self._COLORS)):
            block, v_lbl = _setting_block(
                key, "—", color, bg, border, self, label_width=52
            )
            grid.addWidget(block, i // 2, i % 2)
            self._val_labels.append(v_lbl)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        lay.addStretch(1)
        self.refresh()

    def refresh(self):
        """从 app_config（ConfigCenter）读取最新设置并刷新显示。"""
        try:
            from src.ui.pages.publish.list_settings_dialog import (
                get_display_mode,
                get_publish_interval_seconds,
                get_post_publish_action,
                get_speed_index,
                get_publish_show_browser,
                get_auto_shutdown_after_complete,
                MODE_PLATFORM,
                MODE_ACCOUNT,
                SPEED_OPTIONS,
                POST_PUBLISH_ACTION_MOVE,
                POST_PUBLISH_ACTION_DELETE,
            )

            mode = get_display_mode()
            mode_text = {MODE_PLATFORM: "按平台", MODE_ACCOUNT: "按账号"}.get(mode, "顺序")

            idx = get_speed_index()
            speed_text = SPEED_OPTIONS[idx][0].split("(")[0].strip()

            interval_text = f"{get_publish_interval_seconds()}s"

            action = get_post_publish_action()
            action_text = {
                POST_PUBLISH_ACTION_MOVE: "移动",
                POST_PUBLISH_ACTION_DELETE: "删除",
            }.get(action, "不处理")

            browser_text = "显示" if get_publish_show_browser() else "后台"
            shutdown_text = (
                "关机"
                if get_auto_shutdown_after_complete()
                else "不关机"
            )

            for lbl, text in zip(
                self._val_labels,
                [
                    mode_text,
                    speed_text,
                    interval_text,
                    browser_text,
                    action_text,
                    shutdown_text,
                ],
            ):
                lbl.setText(text)
        except Exception:
            pass
