"""
个人中心页面（闭源实现）
原路径：src/ui/pages/subscription_page.py
"""

import os
from typing import Optional
from datetime import datetime
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtGui import QPixmap
import logging

from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, PrimaryPushButton, PushButton,
    MessageBox, InfoBar, InfoBarPosition, FluentIcon, IconWidget, TitleLabel,
    CaptionLabel, isDarkTheme, InfoBadge, FlowLayout
)
FLUENT_WIDGETS_AVAILABLE = True

from src.ui.pages.base_page import BasePage

logger = logging.getLogger(__name__)


class PersonalCenterPage(BasePage):
    """个人中心页面"""

    _lazy_content = True

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__("个人中心", parent)
        self.subscription_manager = None
        self.payment_handler = None
        self._active_workers = []

    def _init_data(self):
        self._update_account_status()
        self._update_benefits_card()

    def _init_services(self):
        try:
            from src.infrastructure.common.di.service_locator import ServiceLocator
            from src.services.subscription.subscription_manager_async import SubscriptionManagerAsync
            from src.infrastructure.common.event.event_bus import EventBus
            from src.services.auth import CurrentUserService

            service_locator = ServiceLocator()
            event_bus = service_locator.get(EventBus) if service_locator.is_registered(EventBus) else None
            if event_bus:
                event_bus.subscribe("SessionEvictedEvent", self._on_session_evicted)
            user_id = CurrentUserService().get_user_id_or_default(1)

            self.subscription_manager = SubscriptionManagerAsync(user_id=user_id, event_bus=event_bus)
            self.payment_handler = None

            logger.info("个人中心服务初始化成功")
        except Exception as e:
            logger.error(f"初始化个人中心服务失败: {e}", exc_info=True)

    def _setup_content(self):
        self._init_services()

        top_section = QHBoxLayout()
        top_section.setSpacing(20)
        top_section.setAlignment(Qt.AlignTop)

        self.account_card = self._create_account_card()
        self.status_card = self._create_status_card()
        top_section.addWidget(self.account_card, 1)
        top_section.addWidget(self.status_card, 1)

        self.content_layout.addLayout(top_section)

        self.feedback_card = self._create_feedback_card()
        self.content_layout.addWidget(self.feedback_card)

        self.content_layout.addStretch()

        self._schedule_base_page_timer("personal_center.init_data", 50, self._init_data)

    def _on_session_evicted(self, event):
        self._schedule_base_page_timer(
            "personal_center.update_account_status",
            0,
            self._update_account_status,
        )

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        if self._content_initialized:
            self._update_account_status()
            from src.ui.utils.async_helper import run_async_from_ui
            run_async_from_ui(lambda: self._sync_permissions_from_cloud())

    def _create_account_card(self) -> QWidget:
        card = CardWidget(self)
        # 账号信息较少，采用紧凑高度
        card.setMinimumHeight(220)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 18, 22, 18)
        card_layout.setSpacing(10)

        header = QHBoxLayout()
        icon = IconWidget(FluentIcon.CERTIFICATE, card)
        icon.setFixedSize(18, 18)
        title = BodyLabel("我的账户", card)
        _header_color = "#BBB" if isDarkTheme() else "#666"
        title.setStyleSheet(f"font-weight: bold; color: {_header_color};")
        header.addWidget(icon)
        header.addWidget(title)
        header.addStretch()
        card_layout.addLayout(header)

        info_layout = QHBoxLayout()
        info_layout.setSpacing(16)

        self.avatar_widget = IconWidget(FluentIcon.CERTIFICATE, card)
        self.avatar_widget.setFixedSize(60, 60)
        self.avatar_widget.setStyleSheet(
            """
            background-color: rgba(0, 120, 212, 0.1);
            color: #0078D4;
            border-radius: 30px;
            padding: 13px;
        """
        )

        text_info = QVBoxLayout()
        text_info.setSpacing(4)
        text_info.setAlignment(Qt.AlignVCenter)
        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        self.account_status_label = TitleLabel("未登录", card)
        self.account_status_label.setStyleSheet("font-size: 20px; font-weight: 650;")
        self.account_badge = InfoBadge.info("未登录")
        self.account_badge.setFixedHeight(20)
        name_row.addWidget(self.account_status_label)
        name_row.addWidget(self.account_badge, 0, Qt.AlignVCenter)
        name_row.addStretch()

        self.account_desc_label = CaptionLabel("登录解锁更多高级权益", card)
        self.account_desc_label.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        self.account_expire_label = CaptionLabel("", card)
        self.account_expire_label.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)

        text_info.addLayout(name_row)
        text_info.addWidget(self.account_desc_label)
        text_info.addWidget(self.account_expire_label)

        info_layout.addWidget(self.avatar_widget)
        info_layout.addLayout(text_info)
        info_layout.addStretch()
        card_layout.addLayout(info_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_login = PrimaryPushButton("登录/注册", card)
        self.btn_login.clicked.connect(self._on_login)
        self.btn_login.setFixedHeight(32)

        self.btn_logout = PushButton("退出登录", card)
        self.btn_logout.clicked.connect(self._on_logout)
        self.btn_logout.setVisible(False)
        self.btn_logout.setFixedHeight(32)

        btn_layout.addWidget(self.btn_login)
        btn_layout.addWidget(self.btn_logout)
        card_layout.addLayout(btn_layout)

        # 当前额度（应属于“我的账户”心智）
        _desc_color = "#AAA" if isDarkTheme() else "#555"
        _section_style = f"font-size: 13px; font-weight: 600; color: {_desc_color};"
        card_layout.addSpacing(6)
        self.account_quota_title = BodyLabel("当前额度", card)
        self.account_quota_title.setStyleSheet(_section_style)
        card_layout.addWidget(self.account_quota_title)

        self.quota_stats_container = QWidget(card)
        stats_row = QHBoxLayout(self.quota_stats_container)
        stats_row.setContentsMargins(0, 0, 0, 0)
        stats_row.setSpacing(10)
        _icon_user = getattr(FluentIcon, "PEOPLE", FluentIcon.CERTIFICATE)
        _icon_group = getattr(FluentIcon, "GROUP", FluentIcon.CERTIFICATE)
        _icon_send = getattr(FluentIcon, "SEND", FluentIcon.CERTIFICATE)
        self._stat_login_accounts = self._build_stat_item(
            "账号数量上限", "—", icon=_icon_user, accent="#0078D4", parent=self.quota_stats_container
        )
        self._stat_account_groups = self._build_stat_item(
            "账号组上限", "—", icon=_icon_group, accent="#6B61D6", parent=self.quota_stats_container
        )
        self._stat_daily_publish = self._build_stat_item(
            "每日最大发布次数", "—", icon=_icon_send, accent="#0F7B6C", parent=self.quota_stats_container
        )
        stats_row.addWidget(self._stat_login_accounts, 1)
        stats_row.addWidget(self._stat_account_groups, 1)
        stats_row.addWidget(self._stat_daily_publish, 1)
        card_layout.addWidget(self.quota_stats_container)
        self.quota_stats_container.setVisible(False)

        # 可用平台（也属于账号当前权益摘要）
        card_layout.addSpacing(6)
        self.status_platform_title = BodyLabel("可用平台", card)
        self.status_platform_title.setStyleSheet(_section_style)
        card_layout.addWidget(self.status_platform_title)

        self.platform_container = QWidget(card)
        pc = QVBoxLayout(self.platform_container)
        pc.setContentsMargins(0, 0, 0, 0)
        pc.setSpacing(6)
        self.platform_flow = FlowLayout()
        self.platform_flow.setContentsMargins(0, 0, 0, 0)
        self.platform_flow.setHorizontalSpacing(6)
        self.platform_flow.setVerticalSpacing(6)
        pc.addLayout(self.platform_flow)
        card_layout.addWidget(self.platform_container)
        self.platform_container.setVisible(False)

        return card

    def _create_status_card(self) -> QWidget:
        card = CardWidget(self)
        # 右侧改为“订阅中心”（电商订阅页风格）
        card.setMinimumHeight(220)
        _desc_color = "#AAA" if isDarkTheme() else "#555"
        _label_style = f"font-size: 13px; color: {_desc_color};"
        _section_style = f"font-size: 13px; font-weight: 600; color: {_desc_color};"
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 18, 22, 18)
        card_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)
        _sub_icon = getattr(FluentIcon, "SHOPPING_CART", FluentIcon.CERTIFICATE)
        icon = IconWidget(_sub_icon, card)
        icon.setFixedSize(18, 18)
        title = BodyLabel("订阅中心", card)
        _title_color = "#DDD" if isDarkTheme() else "#333"
        title.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {_title_color};")
        header.addWidget(icon)
        header.addWidget(title)
        header.addStretch()
        card_layout.addLayout(header)

        # 顶部说明：与「关注公众号领 Pro」路径一致
        self.sub_hint = BodyLabel(
            "免费版为开源基础能力；Pro 关注公众号并发送用户名即可开通（见下方二维码）。",
            card,
        )
        self.sub_hint.setStyleSheet(_label_style)
        self.sub_hint.setWordWrap(True)
        card_layout.addWidget(self.sub_hint)

        # 套餐对比（电商订阅页风格）
        self.plan_title = BodyLabel("套餐对比", card)
        self.plan_title.setStyleSheet(_section_style)
        card_layout.addWidget(self.plan_title)

        self.plans_container = QWidget(card)
        plans_row = QHBoxLayout(self.plans_container)
        plans_row.setContentsMargins(0, 0, 0, 0)
        plans_row.setSpacing(10)

        self._plan_cards = []
        for card_idx in range(2):
            c = QFrame(self.plans_container)
            c.setObjectName("PlanCard")
            c._card_index = card_idx  # type: ignore[attr-defined]
            c.setStyleSheet(
                """
                QFrame#PlanCard {
                    background: rgba(0, 0, 0, 0.02);
                    border: 1px solid rgba(0, 0, 0, 0.08);
                    border-radius: 12px;
                }
                """
            )
            cl = QVBoxLayout(c)
            cl.setContentsMargins(14, 12, 14, 12)
            cl.setSpacing(8)

            title_row = QHBoxLayout()
            title_row.setSpacing(8)
            name = SubtitleLabel("—", c)
            name.setStyleSheet("font-weight: 700; font-size: 15px;")
            title_row.addWidget(name)
            title_row.addStretch()
            rec = InfoBadge.success("推荐")
            rec.setVisible(False)
            rec.setFixedHeight(20)
            title_row.addWidget(rec, 0, Qt.AlignVCenter)
            cl.addLayout(title_row)

            price = TitleLabel("—", c)
            price.setStyleSheet("font-size: 22px; font-weight: 800; color: #0078D4; letter-spacing: -0.5px;")
            price_hint = CaptionLabel("", c)
            price_hint.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
            price_hint.setStyleSheet("font-size: 12px; margin-top: -2px;")
            price_hint.setWordWrap(True)
            # Pro 权益条：用 success 色系，比 warning 更符合「正向领取」
            badge = InfoBadge.success("")
            badge.setVisible(False)
            badge.setFixedHeight(22)
            feats = BodyLabel("", c)
            feats.setWordWrap(True)
            feats.setStyleSheet(_label_style + " line-height: 1.45;")
            cl.addWidget(price)
            cl.addWidget(price_hint)
            cl.addWidget(badge, 0, Qt.AlignLeft)
            cl.addWidget(feats)
            c._name = name  # type: ignore[attr-defined]
            c._rec_badge = rec  # type: ignore[attr-defined]
            c._price = price  # type: ignore[attr-defined]
            c._price_hint = price_hint  # type: ignore[attr-defined]
            c._badge = badge  # type: ignore[attr-defined]
            c._feats = feats  # type: ignore[attr-defined]
            self._plan_cards.append(c)
            plans_row.addWidget(c, 1)

        card_layout.addWidget(self.plans_container)
        self._render_subscription_plan_cards_sync()

        # CTA
        self.btn_get_pro = PrimaryPushButton("关注公众号 · 免费开通 Pro", card)
        self.btn_get_pro.setFixedHeight(34)
        self.btn_get_pro.clicked.connect(self._on_get_pro_clicked)
        card_layout.addWidget(self.btn_get_pro, 0, Qt.AlignRight)

        card_layout.addStretch()
        return card

    def _render_subscription_plan_cards_sync(self) -> None:
        """套餐对比为静态文案，构建 UI 时同步写入，不再走异步/数据库。"""
        plans: list = []
        try:
            mgr = self.subscription_manager
            if mgr is not None:
                plans = mgr.get_subscription_plans() or []
            else:
                from src.services.subscription.subscription_manager_async import SubscriptionManagerAsync

                plans = SubscriptionManagerAsync(user_id=1, event_bus=None).get_subscription_plans() or []
        except Exception:
            plans = []

        if not plans or not hasattr(self, "_plan_cards"):
            return

        try:
            for idx, plan in enumerate(plans[: len(self._plan_cards)]):
                c = self._plan_cards[idx]
                name = plan.get("name") or plan.get("plan_type") or "套餐"
                price = plan.get("price")
                feats = plan.get("features") or []
                badge_text = plan.get("badge") or ""
                price_hint = plan.get("price_hint") or ""
                recommended = bool(plan.get("recommended"))
                plan_type = str(plan.get("plan_type") or "")

                c._name.setText(str(name))
                c._price.setText("免费" if (price in (0, 0.0, None)) else f"¥{price}")
                if hasattr(c, "_price_hint") and c._price_hint is not None:
                    c._price_hint.setText(str(price_hint))
                    c._price_hint.setVisible(bool(price_hint))
                if hasattr(c, "_badge") and c._badge is not None:
                    c._badge.setText(str(badge_text))
                    c._badge.setVisible(bool(badge_text))
                if hasattr(c, "_rec_badge") and c._rec_badge is not None:
                    c._rec_badge.setVisible(recommended)
                c._feats.setText("\n".join([f"· {x}" for x in feats]) if feats else "")

                if plan_type == "pro":
                    c.setStyleSheet(
                        """
                        QFrame#PlanCard {
                            background: rgba(0, 120, 212, 0.06);
                            border: 1px solid rgba(0, 120, 212, 0.35);
                            border-radius: 12px;
                        }
                        """
                    )
                else:
                    c.setStyleSheet(
                        """
                        QFrame#PlanCard {
                            background: rgba(0, 0, 0, 0.02);
                            border: 1px solid rgba(0, 0, 0, 0.08);
                            border-radius: 12px;
                        }
                        """
                    )
        except Exception:
            pass

    def _create_feedback_card(self) -> QWidget:
        card = CardWidget(self)
        card_layout = QVBoxLayout(card)
        # 反馈区更轻量，避免占用过多空间
        card_layout.setContentsMargins(22, 16, 22, 16)
        card_layout.setSpacing(12)

        header = QHBoxLayout()
        icon = IconWidget(FluentIcon.FEEDBACK, card)
        icon.setFixedSize(18, 18)
        title = BodyLabel("用户反馈", card)
        _fb_title_color = "#DDD" if isDarkTheme() else "#333"
        title.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {_fb_title_color};")
        header.addWidget(icon)
        header.addWidget(title)
        header.addStretch()
        card_layout.addLayout(header)

        content = QHBoxLayout()
        content.setSpacing(18)
        text_col = QVBoxLayout()
        text_col.setSpacing(6)
        hint = BodyLabel("如有问题，可扫码添加公众号反馈。", card)
        _hint_color = "#AAA" if isDarkTheme() else "#666"
        hint.setStyleSheet(f"color: {_hint_color}; font-size: 13px;")
        hint.setWordWrap(True)
        text_col.addWidget(hint)
        pro_tip = BodyLabel("注册账号后发送用户名到公众号，免费获取 Pro 权限，解锁全部功能。", card)
        pro_tip.setStyleSheet("color: #E6162D; font-size: 14px; font-weight: 650;")
        pro_tip.setWordWrap(True)
        text_col.addWidget(pro_tip)
        content.addLayout(text_col, 1)

        qr_label = QLabel(card)
        qr_label.setAlignment(Qt.AlignCenter)
        qr_label.setFixedSize(140, 140)
        from src.infrastructure.common.path_manager import PathManager
        qr_path = str(PathManager.get_resource_path("resources/feedback_qrcode.png"))
        if os.path.isfile(qr_path):
            pixmap = QPixmap(qr_path)
            if not pixmap.isNull():
                qr_label.setPixmap(pixmap.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        content.addWidget(qr_label, 0)
        card_layout.addLayout(content)

        return card

    def _on_login(self):
        try:
            from src.ui.dialogs.login_dialog import LoginDialog
            dialog = LoginDialog(self)
            dialog.login_success.connect(self._on_login_success)
            dialog.exec()
        except Exception as e:
            logger.error(f"登录失败: {e}", exc_info=True)

    def _on_login_success(self, user_info: dict):
        self._update_account_status()
        self.show_success("登录成功", f"欢迎回来，{user_info.get('username', '用户')}！")

    def _on_get_pro_clicked(self):
        self._show_get_pro_guide_dialog()

    def _show_get_pro_guide_dialog(self) -> None:
        """关注公众号领取 Pro：分步说明 + 二维码，符合项目弹窗规范。"""
        from src.infrastructure.common.path_manager import PathManager
        from src.ui.components.base_dialog import StandardBaseDialog, FLUENT_WIDGETS_AVAILABLE
        from src.services.auth import CurrentUserService

        if not FLUENT_WIDGETS_AVAILABLE:
            MessageBox(
                "免费开通 Pro",
                "请使用微信扫描「用户反馈」中的公众号二维码，关注后发送你的登录用户名即可开通。",
                self,
            ).exec()
            return

        dlg = StandardBaseDialog(self, title="免费开通 Pro 会员")
        try:
            dlg.widget.setMinimumWidth(540)
        except Exception:
            pass
        dlg.set_yes_button_text("我知道了")
        if hasattr(dlg, "cancelButton") and dlg.cancelButton is not None:
            dlg.cancelButton.hide()

        _muted = "#8A8A8A" if not isDarkTheme() else "#B0B0B0"
        _body = "#333333" if not isDarkTheme() else "#E6E6E6"

        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(20)

        left = QVBoxLayout()
        left.setSpacing(8)
        sub = SubtitleLabel("操作步骤", root)
        sub.setStyleSheet("font-weight: 600;")
        left.addWidget(sub)

        user = CurrentUserService().get_user()
        if user and user.get("username"):
            tip = BodyLabel(f"当前登录用户：{user.get('username')}", root)
            tip.setStyleSheet(f"color: {_muted}; font-size: 12px;")
            tip.setWordWrap(True)
            left.addWidget(tip)

        steps = [
            "1. 使用微信扫描右侧二维码，关注官方公众号。",
            "2. 在公众号内发送你的媒小宝登录用户名（须与上方面板或「我的账户」中显示一致）。",
            "3. 开通成功后，若界面未更新，请尝试重新登录。",
        ]
        for line in steps:
            lab = BodyLabel(line, root)
            lab.setWordWrap(True)
            lab.setStyleSheet(f"color: {_body}; font-size: 13px; line-height: 1.5;")
            left.addWidget(lab)

        note = BodyLabel(
            "若已关注仍未生效，请核对用户名是否拼写正确；也可在公众号内留言说明问题。",
            root,
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {_muted}; font-size: 12px;")
        left.addWidget(note)
        left.addStretch()

        right = CardWidget(root)
        right.setFixedWidth(200)
        rv = QVBoxLayout(right)
        rv.setContentsMargins(12, 12, 12, 12)
        rv.setSpacing(8)
        cap = CaptionLabel("微信扫码关注", right)
        cap.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        rv.addWidget(cap, 0, Qt.AlignHCenter)
        qr_label = QLabel(right)
        qr_label.setAlignment(Qt.AlignCenter)
        qr_label.setFixedSize(160, 160)
        qr_path = str(PathManager.get_resource_path("resources/feedback_qrcode.png"))
        if os.path.isfile(qr_path):
            pm = QPixmap(qr_path)
            if not pm.isNull():
                qr_label.setPixmap(pm.scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            qr_label.setText("二维码未找到")
            qr_label.setStyleSheet(f"color: {_muted};")
        rv.addWidget(qr_label, 0, Qt.AlignHCenter)

        h.addLayout(left, 3)
        h.addWidget(right, 0, Qt.AlignTop)

        dlg.add_widget(root)
        dlg.exec()

    def _on_logout(self):
        from src.ui.utils.fluent_dialogs import show_confirm
        from src.services.auth import CurrentUserService
        if not show_confirm(self, "确认退出", "确定要退出登录吗？"):
            return
        CurrentUserService().clear_user()
        self._update_account_status()
        self.show_success("已退出", "您已成功退出登录")

    async def _sync_permissions_from_cloud(self):
        try:
            from src.services.auth import CurrentUserService
            from src.services.auth.auth_api_client import refresh_user_info
            from src.services.auth.auth_config import is_cloud_auth_enabled
            curr = CurrentUserService()
            if not curr.is_logged_in() or not is_cloud_auth_enabled():
                return
            token = curr.get_token()
            if not token:
                return
            result = await refresh_user_info(token)
            if not result.get("success") or not result.get("data"):
                logger.debug("个人中心刷新云端权限失败（可忽略）: %s", result.get("msg", ""))
                return
            curr.sync_from_cloud_data(result["data"])
            self._update_account_status()
        except Exception as e:
            logger.debug("个人中心同步云端权限失败（可忽略）: %s", e)

    def _finish_status_loading(self):
        # 订阅中心不再使用加载占位；保留函数以兼容历史调用
        if hasattr(self, "_status_spinner") and getattr(self, "_status_spinner", None) is not None:
            try:
                self._status_spinner.setVisible(False)
            except Exception:
                pass

    def _build_stat_item(
        self,
        title: str,
        value_text: str = "—",
        icon: Optional[FluentIcon] = None,
        accent: str = "#0078D4",
        parent: Optional[QWidget] = None,
    ) -> QWidget:
        """构建三列额度统计块：图标 + 标题 + 大数字（更像主流仪表盘卡片）"""
        w = QFrame(parent or self)
        w.setObjectName("QuotaStatItem")
        # 轻边框 + 悬浮态，暗色/亮色都能接受（不用强依赖主题色 API）
        w.setStyleSheet(
            f"""
            QFrame#QuotaStatItem {{
                background: rgba(0, 0, 0, 0.02);
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 10px;
            }}
            QFrame#QuotaStatItem:hover {{
                border: 1px solid rgba(0, 120, 212, 0.35);
                background: rgba(0, 120, 212, 0.06);
            }}
            """
        )

        lay = QVBoxLayout(w)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        if icon is not None:
            iw = IconWidget(icon, w)
            iw.setFixedSize(16, 16)
            iw.setStyleSheet(f"color: {accent};")
            top.addWidget(iw, 0, Qt.AlignVCenter)
        lab = CaptionLabel(title, w)
        lab.setTextColor(Qt.GlobalColor.gray, Qt.GlobalColor.gray)
        lab.setStyleSheet("font-size: 12px;")
        top.addWidget(lab, 0, Qt.AlignVCenter)
        top.addStretch()

        val = TitleLabel(value_text, w)
        val.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {accent};")

        lay.addLayout(top)
        lay.addWidget(val, 0, Qt.AlignLeft)
        w._value_label = val  # type: ignore[attr-defined]
        return w

    def _set_stat_values(self, user: Optional[dict]):
        """更新额度统计块（未登录时隐藏）"""
        if not hasattr(self, "quota_stats_container") or self.quota_stats_container is None:
            return
        if not user:
            self.quota_stats_container.setVisible(False)
            return

        def _set(item: QWidget, text: str):
            val = getattr(item, "_value_label", None)
            if val is not None:
                val.setText(text)

        _set(self._stat_login_accounts, self._format_quota(user.get("max_login_accounts")))
        _set(self._stat_account_groups, self._format_quota(user.get("max_account_groups")))
        _set(self._stat_daily_publish, self._format_quota(user.get("daily_max_publish_count")))
        self.quota_stats_container.setVisible(True)

    def _set_platforms_view(self, platform_names: list[str], badge_style: str = "info"):
        """用标签流式布局展示平台列表（避免长句挤在一行）"""
        if not hasattr(self, "platform_flow") or self.platform_flow is None:
            return

        while self.platform_flow.count():
            item = self.platform_flow.takeAt(0)
            # 兼容：有的 FlowLayout.takeAt() 返回 QLayoutItem，有的直接返回 QWidget
            w = None
            if hasattr(item, "widget"):
                try:
                    w = item.widget()
                except Exception:
                    w = None
            if w is None and isinstance(item, QWidget):
                w = item
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        for name in platform_names:
            if badge_style == "success":
                badge = InfoBadge.success(name)
            elif badge_style == "warning":
                badge = InfoBadge.warning(name)
            else:
                badge = InfoBadge.info(name)
            badge.setFixedHeight(20)
            self.platform_flow.addWidget(badge)

        if hasattr(self, "platform_container") and self.platform_container is not None:
            self.platform_container.setVisible(bool(platform_names))

    @staticmethod
    def _format_expire_time(expire_time) -> str:
        """把云端/本地的 expire_time 转成可读文案（支持秒/毫秒时间戳）"""
        if not expire_time:
            return "未知"
        try:
            ts = int(expire_time)
            if ts > 10**12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "未知"

    @staticmethod
    def _format_quota(value) -> str:
        if value is None:
            return "不限"
        try:
            return str(int(value))
        except Exception:
            return str(value)

    def _update_benefits_card(self):
        """更新“我的账户”里的当前权益摘要（额度 + 平台）。"""
        from src.services.auth import CurrentUserService
        from src.utils.pro_platforms import PRO_PLATFORM_IDS
        from src.utils.platform_names import get_platform_display_name

        curr = CurrentUserService()
        user = curr.get_user()

        # 未登录：隐藏额度与平台
        if not user:
            self._set_stat_values(None)
            self._set_platforms_view([], badge_style="info")
            if hasattr(self, "account_quota_title") and self.account_quota_title is not None:
                self.account_quota_title.setVisible(False)
            if hasattr(self, "status_platform_title") and self.status_platform_title is not None:
                self.status_platform_title.setVisible(False)
            return

        level = user.get("level", "vip0")
        is_expired = user.get("is_expired", True)
        has_pro = level == "vip1" and not is_expired

        if hasattr(self, "account_quota_title") and self.account_quota_title is not None:
            self.account_quota_title.setVisible(True)
        self._set_stat_values(user)

        community_names = [get_platform_display_name(pid) for pid in ("douyin", "kuaishou")]
        pro_names = sorted([get_platform_display_name(pid) for pid in PRO_PLATFORM_IDS])
        if hasattr(self, "status_platform_title") and self.status_platform_title is not None:
            self.status_platform_title.setVisible(True)
        if has_pro:
            self._set_platforms_view(community_names + pro_names, badge_style="success")
        else:
            self._set_platforms_view(community_names, badge_style="info")

    def _update_account_status(self):
        from src.services.auth import CurrentUserService
        curr = CurrentUserService()
        user = curr.get_user()
        if self.subscription_manager and user:
            self.subscription_manager.user_id = user.get("id", 1)
        if user:
            username = user.get("username", "用户")
            level = user.get("level", "vip0")
            is_expired = user.get("is_expired", True)
            level_text = "Pro 会员" if (level == "vip1" and not is_expired) else "免费版"
            self.account_status_label.setText(username)
            self.account_desc_label.setText(level_text)
            if hasattr(self, "account_badge") and self.account_badge is not None:
                self.account_badge.setText(level_text)
            expire_time = user.get("expire_time") or user.get("member_expire_at") or user.get("member_expire_time")
            if level == "vip1":
                if is_expired:
                    self.account_expire_label.setText("账号到期时间：已过期")
                else:
                    self.account_expire_label.setText(
                        f"账号到期时间：{self._format_expire_time(expire_time)}" if expire_time else "账号到期时间：未同步"
                    )
                self.account_expire_label.setVisible(True)
            else:
                self.account_expire_label.setText("")
                self.account_expire_label.setVisible(False)
            self.btn_login.setVisible(False)
            self.btn_logout.setVisible(True)
        else:
            self.account_status_label.setText("未登录")
            self.account_desc_label.setText("登录解锁更多高级权益")
            if hasattr(self, "account_badge") and self.account_badge is not None:
                self.account_badge.setText("未登录")
            self.btn_login.setVisible(True)
            self.btn_logout.setVisible(False)
            self.account_expire_label.setText("")
            self.account_expire_label.setVisible(False)
        self._update_benefits_card()

    def _remove_worker(self, worker):
        if worker in self._active_workers:
            self._active_workers.remove(worker)

    def closeEvent(self, event):
        for worker in self._active_workers[:]:
            if worker.isRunning():
                worker.terminate()
        super().closeEvent(event)

