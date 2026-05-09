"""
作品描述配置弹窗
文件路径：src/ui/publish/work_description/publish_description_dialog.py
功能：提供“统一作品描述”的配置弹窗（单视频/批量视频等共用入口）。
"""
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
)
from PySide6.QtCore import Qt, QEventLoop
from qasync import asyncSlot
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    LineEdit,
    SubtitleLabel,
    TextEdit,
    CheckBox,
    SwitchButton,
    ComboBox,
    SegmentedWidget,
    InfoBar,
    InfoBarPosition,
    IconWidget,
    FluentIcon,
)

from src.ui.components.base_dialog import AppMessageBoxBase
from src.ui.utils.fluent_tooltips import apply_instructional_tooltip
from src.domain.publish.work_description.topics import normalize_topics_for_paste

from .work_description_edit_controller import WorkDescriptionEditController
from src.infrastructure.common.config.config_center import get_registered_config_center
from src.infrastructure.common.config.app_config_keys import (
    KEY_BATCH_PUBLISH,
    BATCH_DECLARE_ORIGINAL,
    BATCH_PUBLISH_DESCRIPTION,
)
from src.infrastructure.common.config.app_config_merge import merge_app_config, read_app_config_from_disk_sync
from src.services.copywriting.copywriting_match_service import CopywritingMatchMode
from src.infrastructure.common.media_assign_strategy import AssignStrategy

logger = logging.getLogger(__name__)

# 标题最大字数（与主页面保持一致）
TITLE_MAX_LENGTH = 30
# 作品描述字数上限（与单个任务页一致）
DESC_CHAR_LIMIT = 1000


_SESSION_STORAGE: dict[str, dict] = {}
_SESSION_KEY = "publish_description_dialog"

def _batch_publish_root() -> dict:
    cc = get_registered_config_center()
    if cc is not None:
        bp = cc.get_app_config().get(KEY_BATCH_PUBLISH)
        if isinstance(bp, dict):
            return bp
        return {}
    root = read_app_config_from_disk_sync()
    bp = root.get(KEY_BATCH_PUBLISH)
    return bp if isinstance(bp, dict) else {}


def _batch_publish_root_for_write() -> dict:
    return dict(_batch_publish_root())


def _read_pref_bool(raw: object, default: bool) -> bool:
    if raw is None:
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        return raw != 0
    if isinstance(raw, str):
        t = raw.strip().lower()
        if t in ("1", "true", "yes", "on"):
            return True
        if t in ("0", "false", "no", "off", ""):
            return False
    try:
        return bool(raw)
    except Exception:
        return default


def _persist_prefs_exist() -> bool:
    bp = _batch_publish_root()
    pd = bp.get(BATCH_PUBLISH_DESCRIPTION)
    if not isinstance(pd, dict) or not pd:
        return False
    if any(
        k in pd
        for k in (
            "apply_to_all_tasks",
            "use_library_title",
            "use_library_desc",
            "auto_match_enabled",
            "match_mode",
            "random_category_id",
            "copywriting_assign_strategy",
        )
    ):
        return True
    return bool(str(pd.get("title", "") or "").strip()) or bool(str(pd.get("desc", "") or "").strip())


def load_persisted_declare_original() -> bool:
    """读取批量页「声明原创」勾选；无记录时默认 True（与历史行为一致）。"""
    bp = _batch_publish_root()
    if BATCH_DECLARE_ORIGINAL not in bp:
        return True
    try:
        return _read_pref_bool(bp.get(BATCH_DECLARE_ORIGINAL), True)
    except Exception:
        logger.debug("读取声明原创持久化失败", exc_info=True)
        return True


def save_persisted_declare_original(checked: bool) -> None:
    """保存批量页「声明原创」勾选。"""
    from src.ui.utils.async_helper import run_async_from_ui

    async def _save() -> None:
        bp = _batch_publish_root_for_write()
        bp[BATCH_DECLARE_ORIGINAL] = bool(checked)
        ok = await merge_app_config(get_registered_config_center(), {KEY_BATCH_PUBLISH: bp})
        if not ok:
            logger.warning("保存声明原创勾选失败: ConfigCenter 不可用")

    try:
        run_async_from_ui(_save)
    except Exception as e:
        logger.warning("保存声明原创勾选失败: %s", e)


def load_persisted_publish_description_prefs() -> dict:
    """读取上次保存的作品描述弹窗状态（标题/简介/三个复选框及备份字段）。无记录时返回空 dict。"""
    if not _persist_prefs_exist():
        return {}
    try:
        bp = _batch_publish_root()
        pd = bp.get(BATCH_PUBLISH_DESCRIPTION)
        if not isinstance(pd, dict):
            return {}
        return {
            "title": str(pd.get("title", "") or ""),
            "desc": str(pd.get("desc", "") or ""),
            "apply_to_all_tasks": _read_pref_bool(pd.get("apply_to_all_tasks"), True),
            "use_library_title": _read_pref_bool(pd.get("use_library_title"), False),
            "use_library_desc": _read_pref_bool(pd.get("use_library_desc"), False),
            "manual_title_backup": str(pd.get("manual_title_backup", "") or ""),
            "manual_desc_backup": str(pd.get("manual_desc_backup", "") or ""),
            "auto_match_enabled": _read_pref_bool(pd.get("auto_match_enabled"), False),
            "match_mode": str(pd.get("match_mode", CopywritingMatchMode.STANDARD) or CopywritingMatchMode.STANDARD),
            "random_category_id": pd.get("random_category_id"),
            "copywriting_assign_strategy": str(pd.get("copywriting_assign_strategy", AssignStrategy.ROUND_ROBIN.value) or AssignStrategy.ROUND_ROBIN.value),
        }
    except Exception:
        logger.debug("读取作品描述持久化配置失败", exc_info=True)
        return {}


def save_persisted_publish_description_prefs(d: dict) -> bool:
    """写入作品描述弹窗状态到 app_config（异步合并写盘）。"""
    import copy

    from src.ui.utils.async_helper import run_async_from_ui

    payload = copy.deepcopy(d)

    async def _save() -> None:
        bp = _batch_publish_root_for_write()
        bp[BATCH_PUBLISH_DESCRIPTION] = payload
        ok = await merge_app_config(get_registered_config_center(), {KEY_BATCH_PUBLISH: bp})
        if not ok:
            logger.warning("作品描述配置写入失败: ConfigCenter 不可用")

    try:
        run_async_from_ui(_save)
        return True
    except Exception as e:
        logger.warning("保存作品描述持久化配置失败: %s", e)
        return False


class LibraryFetchCoordinator:
    def __init__(self):
        self._cache: Optional[dict] = None
        self._inflight = False
        self._pending_title = False
        self._pending_desc = False

    def update_pending(self, title: bool, desc: bool) -> bool:
        self._pending_title = bool(title)
        self._pending_desc = bool(desc)
        if self._cache is not None:
            return False
        if self._inflight:
            return False
        if not (self._pending_title or self._pending_desc):
            return False
        self._inflight = True
        return True

    def complete(self, item: Optional[dict]) -> tuple[Optional[dict], bool, bool]:
        self._cache = item
        self._inflight = False
        title, desc = self._pending_title, self._pending_desc
        self._pending_title = False
        self._pending_desc = False
        return self._cache, title, desc

    def cached(self) -> Optional[dict]:
        return self._cache

    def has_cache(self) -> bool:
        return self._cache is not None


class PublishDescriptionState:
    def __init__(
        self,
        title: str = "",
        desc: str = "",
        apply_to_all_tasks: bool = True,
        use_library_title: bool = False,
        use_library_desc: bool = False,
        manual_title_backup: str = "",
        manual_desc_backup: str = "",
        # 新增字段
        auto_match_enabled: bool = False,
        match_mode: str = "standard",
        random_category_id: Optional[int] = None,
        copywriting_assign_strategy: str = AssignStrategy.ROUND_ROBIN.value,
    ):
        self.title = title
        self.desc = desc
        self.apply_to_all_tasks = bool(apply_to_all_tasks)
        self.use_library_title = bool(use_library_title)
        self.use_library_desc = bool(use_library_desc)
        self.manual_title_backup = manual_title_backup
        self.manual_desc_backup = manual_desc_backup
        self.auto_match_enabled = bool(auto_match_enabled)
        self.match_mode = str(match_mode)
        self.random_category_id = random_category_id
        self.copywriting_assign_strategy = str(copywriting_assign_strategy)

    @staticmethod
    def from_dict(d: dict) -> "PublishDescriptionState":
        return PublishDescriptionState(
            title=d.get("title", "") or "",
            desc=d.get("desc", "") or "",
            apply_to_all_tasks=bool(d.get("apply_to_all_tasks", True)),
            use_library_title=bool(d.get("use_library_title", False)),
            use_library_desc=bool(d.get("use_library_desc", False)),
            manual_title_backup=d.get("manual_title_backup", "") or "",
            manual_desc_backup=d.get("manual_desc_backup", "") or "",
            auto_match_enabled=bool(d.get("auto_match_enabled", False)),
            match_mode=d.get("match_mode", CopywritingMatchMode.STANDARD),
            random_category_id=d.get("random_category_id"),
            copywriting_assign_strategy=d.get("copywriting_assign_strategy", AssignStrategy.ROUND_ROBIN.value),
        )

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "desc": self.desc,
            "apply_to_all_tasks": self.apply_to_all_tasks,
            "use_library_title": self.use_library_title,
            "use_library_desc": self.use_library_desc,
            "manual_title_backup": self.manual_title_backup,
            "manual_desc_backup": self.manual_desc_backup,
            "auto_match_enabled": self.auto_match_enabled,
            "match_mode": self.match_mode,
            "random_category_id": self.random_category_id,
            "copywriting_assign_strategy": self.copywriting_assign_strategy,
        }

    def on_title_edited(self, text: str) -> None:
        self.title = text
        if not self.use_library_title:
            self.manual_title_backup = text

    def on_desc_edited(self, text: str) -> None:
        self.desc = text
        if not self.use_library_desc:
            self.manual_desc_backup = text

    def toggle_use_library_title(self, checked: bool, lib_title: str) -> None:
        checked = bool(checked)
        if checked and not self.use_library_title:
            self.manual_title_backup = self.title
            self.title = lib_title
        if (not checked) and self.use_library_title:
            self.title = self.manual_title_backup
        self.use_library_title = checked

    def toggle_use_library_desc(self, checked: bool, lib_desc: str) -> None:
        checked = bool(checked)
        if checked and not self.use_library_desc:
            self.manual_desc_backup = self.desc
            self.desc = lib_desc
        if (not checked) and self.use_library_desc:
            self.desc = self.manual_desc_backup
        self.use_library_desc = checked


def reset_persisted_publish_description_prefs() -> None:
    """恢复为默认并清空会话缓存（清空设置 / 重置页面时使用）。"""
    save_persisted_publish_description_prefs(PublishDescriptionState().to_dict())
    _SESSION_STORAGE.pop(_SESSION_KEY, None)


def clear_publish_description_dialog_session() -> None:
    """仅清空内存会话，避免与磁盘已写入状态不一致（例如本页已清空描述）。"""
    _SESSION_STORAGE.pop(_SESSION_KEY, None)


def _merge_overlay_with_batch_desc_combo(overlay: dict, index: Optional[int]) -> dict:
    """与「批量发布设置 → 描述配置」下拉联动：打开弹窗时用当前下拉项对齐文案库勾选组合。

    顺序与页面 addItems 一致：0 自动（标题+描述）1 自动（标题）2 自动（描述）3 手动。
    """
    if index is None or index not in (0, 1, 2, 3):
        return overlay
    out = dict(overlay)
    if index == 0:
        out["use_library_title"] = True
        out["use_library_desc"] = True
    elif index == 1:
        out["use_library_title"] = True
        out["use_library_desc"] = False
    elif index == 2:
        out["use_library_title"] = False
        out["use_library_desc"] = True
    else:
        out["use_library_title"] = False
        out["use_library_desc"] = False
    return out


class PublishDescriptionDialog(AppMessageBoxBase):
    def __init__(
        self,
        initial_title: str = "",
        initial_desc: str = "",
        initial_apply_to_all_tasks: bool = True,
        batch_desc_combo_index: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent, header_title="配置描述")  # type: ignore
        persisted = load_persisted_publish_description_prefs()
        stored = _SESSION_STORAGE.get(_SESSION_KEY)
        # 磁盘优先于内存会话，避免曾写入失败时会话比持久化新、重启后勾选丢失
        overlay = {**(stored or {}), **persisted}
        overlay = _merge_overlay_with_batch_desc_combo(overlay, batch_desc_combo_index)
        self._suppress_async_persist = False
        self._state = PublishDescriptionState.from_dict({
            **overlay,
            "title": initial_title,
            "desc": initial_desc,
            "apply_to_all_tasks": bool(initial_apply_to_all_tasks),
        })
        self._restoring = False
        self._fetcher = LibraryFetchCoordinator()
        self._active_workers = [] # 跟踪运行中的 worker

        # ---- 弹窗基本设置 ----
        self.widget.setMinimumWidth(660)
        self.widget.setMinimumHeight(380)
        self.yesButton.setText("确定")
        self.cancelButton.setText("取消")
        self._reorder_buttons()
        try:
            self.yesButton.clicked.disconnect()
        except Exception:
            pass
        self.yesButton.clicked.connect(self._on_confirm)

        self.viewLayout.addSpacing(8)

        self._build_ui()
        self._restore_state()
        self._bind_events()
        self._maybe_trigger_library_fetch_on_restore()

    def _apply_pivot_style(self) -> None:
        """顶部 Tab 样式：与账号选择/排期弹窗保持一致。"""
        pivot = getattr(self, "_pivot", None)
        if pivot is None:
            return
        pivot.setObjectName("PublishDescriptionPivot")
        palette = self._palette_publish_dialog()
        bg_hover = palette.get("BG_HOVER", "rgba(0,0,0,0.06)")
        border = palette.get("BORDER_DEFAULT", "#E5E5E5")
        tp = palette.get("TEXT_PRIMARY", "#1A1A1A")
        ts = palette.get("TEXT_SECONDARY", "#666666")
        bg_card = palette.get("BG_CARD", "#FFFFFF")
        pivot.setStyleSheet(f"""
            #PublishDescriptionPivot {{
                background-color: {bg_hover}; border: 1px solid {border};
                border-radius: 8px; padding: 4px; min-height: 36px;
            }}
            #PublishDescriptionPivot SegmentedItem {{
                border: none; border-radius: 6px; padding: 5px 22px;
                min-width: 180px;
                font-size: 13px; color: {ts}; background: transparent;
            }}
            #PublishDescriptionPivot SegmentedItem:hover {{
                color: {tp}; background: rgba(128,128,128,0.15);
            }}
            #PublishDescriptionPivot SegmentedItem[isSelected="true"],
            #PublishDescriptionPivot SegmentedItem[isSelected="1"] {{
                color: {tp}; font-weight: 600; background-color: {bg_card};
            }}
        """)

    def _sync_pivot_selection(self) -> None:
        """同步 SegmentedItem 的 isSelected 属性，确保样式正确刷新。"""
        pivot = getattr(self, "_pivot", None)
        if pivot is None:
            return
        try:
            get_current = getattr(pivot, "currentRouteKey", None)
            current_key = get_current() if callable(get_current) else "auto"
        except Exception:
            current_key = "auto"
        for child in pivot.findChildren(QWidget):
            if type(child).__name__ == "SegmentedItem":
                key = child.property("routeKey") or ""
                child.setProperty("isSelected", key == current_key)
                try:
                    child.style().unpolish(child)
                    child.style().polish(child)
                except Exception:
                    pass

    def _palette_publish_dialog(self) -> dict:
        """与排期弹窗同源的配色读取，保证深色主题下也可读。"""
        try:
            from src.ui.styles.theme_manager import ThemeManager
            return ThemeManager()._get_current_palette()
        except Exception:
            return {
                "BG_MAIN": "#F3F3F3",
                "BG_HOVER": "rgba(0,0,0,0.06)",
                "BORDER_DEFAULT": "#E5E5E5",
                "TEXT_PRIMARY": "#1A1A1A",
                "TEXT_SECONDARY": "#666666",
                "BG_CARD": "#FFFFFF",
            }

    def _apply_dialog_style(self) -> None:
        """本弹窗局部样式：增加层次感，避免“大片空白”。"""
        self.widget.setStyleSheet("""
            QWidget#PublishDescriptionPage {
                background: rgba(0, 0, 0, 0.018);
                border-radius: 12px;
            }
            CardWidget#PublishDescriptionCard {
                background: rgba(255, 255, 255, 0.92);
                border: 1px solid rgba(0, 0, 0, 0.06);
                border-radius: 12px;
            }
        """)

    def _wrap_scroll(self, content: QWidget) -> QScrollArea:
        parent = getattr(self, "_stack", None) or self.widget
        scroll = QScrollArea(parent)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setWidget(content)
        return scroll

    def _set_current_page(self, page_index: int) -> None:
        if page_index not in (0, 1):
            page_index = 0
        if hasattr(self, "_stack") and isinstance(self._stack, QStackedWidget):
            self._stack.setCurrentIndex(page_index)
        try:
            if hasattr(self, "_pivot"):
                if page_index == 0:
                    self._pivot.setCurrentItem("auto")
                else:
                    self._pivot.setCurrentItem("manual")
        except Exception:
            pass

    def _set_pivot_item_enabled(self, route_key: str, enabled: bool) -> None:
        """兼容不同版本的 SegmentedWidget：尽量将某个 tab 置灰/禁用。"""
        pivot = getattr(self, "_pivot", None)
        if pivot is None:
            return

        # 1) 新版本可能提供 setItemEnabled(routeKey, bool)
        fn = getattr(pivot, "setItemEnabled", None)
        if callable(fn):
            try:
                fn(route_key, bool(enabled))
                return
            except Exception:
                pass

        # 2) 可能提供 item(routeKey) -> QWidget/Action
        item_fn = getattr(pivot, "item", None)
        if callable(item_fn):
            try:
                item = item_fn(route_key)
                if hasattr(item, "setEnabled"):
                    item.setEnabled(bool(enabled))
                    return
            except Exception:
                pass

        # 3) 兜底：在点击回调里拦截（无法真实置灰时至少防误触）
        # （不在此做任何事）

    def _sync_desc_after_programmatic_edit(self, plain: str) -> None:
        """粘贴规范化时曾 blockSignals，需补写状态（与 textChanged 路径一致）。"""
        if self._restoring:
            return
        self._state.on_desc_edited(plain)
        self._save_session()
        self._refresh_topics_preview_visibility()

    def _build_auto_page(self, parent: QWidget) -> QWidget:
        """自动匹配页：标签列对齐 + 视觉分组，控件与逻辑保持一致。"""
        page = QWidget(parent)
        page.setObjectName("PublishDescriptionPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        self._card_auto = CardWidget(page)
        card_auto = self._card_auto
        card_auto.setObjectName("PublishDescriptionCard")
        card_auto.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card_auto.setMaximumWidth(610)
        lay_auto = QVBoxLayout(card_auto)
        lay_auto.setContentsMargins(16, 12, 16, 12)
        lay_auto.setSpacing(8)

        # 顶部：标题 + 总开关；同行展示「库内文案」徽章作为状态提示
        auto_header_row = QWidget(card_auto)
        _ahr = QHBoxLayout(auto_header_row)
        _ahr.setContentsMargins(0, 0, 0, 0)
        _ahr.setSpacing(10)

        sub_auto = SubtitleLabel("自动匹配", card_auto)
        _ahr.addWidget(sub_auto)

        self.library_count_label = CaptionLabel("库内文案: --", card_auto)
        self.library_count_label.setStyleSheet(
            "color: rgba(0, 159, 170, 0.95); font-weight: 600; font-size: 12px;"
            "background-color: rgba(0, 159, 170, 0.10);"
            "padding: 2px 10px; border-radius: 10px;"
        )
        _ahr.addWidget(self.library_count_label)

        _ahr.addStretch(1)

        self.auto_match_switch = SwitchButton(card_auto)
        self.auto_match_switch.setOnText("开启")
        self.auto_match_switch.setOffText("关闭")
        _ahr.addWidget(self.auto_match_switch)
        lay_auto.addWidget(auto_header_row)

        _tip_auto_title = (
            "开启后，系统将根据所选模式自动匹配文案库中的标题与描述。\n"
            "开启自动匹配后，「手动填写」将不可用。"
        )
        apply_instructional_tooltip(_tip_auto_title, sub_auto)

        # 视觉分隔线，增加层次感
        sep = QFrame(card_auto)
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: rgba(0,0,0,0.06);")
        lay_auto.addWidget(sep)

        # 标签统一宽度，使各行右侧控件起点对齐
        _LABEL_W = 64
        _LABEL_QSS = "color: rgba(0,0,0,0.6); font-weight: 600; font-size: 13px;"

        # 匹配模式行
        mode_row = QWidget(card_auto)
        _mr = QHBoxLayout(mode_row)
        _mr.setContentsMargins(0, 0, 0, 0)
        _mr.setSpacing(10)
        label_mode = BodyLabel("匹配模式", mode_row)
        label_mode.setFixedWidth(_LABEL_W)
        label_mode.setStyleSheet(_LABEL_QSS)
        _mr.addWidget(label_mode)

        self.match_mode_combo = ComboBox(mode_row)
        self.match_mode_combo.addItem("标准文案库 (按作品编号)", userData=CopywritingMatchMode.STANDARD)
        self.match_mode_combo.addItem("随机文案库 (全库随机)", userData=CopywritingMatchMode.RANDOM_ALL)
        self.match_mode_combo.addItem("随机文案库 (指定分类)", userData=CopywritingMatchMode.RANDOM_CATEGORY)
        self.match_mode_combo.setFixedWidth(230)
        _mr.addWidget(self.match_mode_combo)

        self.random_category_combo = ComboBox(mode_row)
        self.random_category_combo.setPlaceholderText("选择分类...")
        self.random_category_combo.setFixedWidth(160)
        self.random_category_combo.setVisible(False)
        _mr.addWidget(self.random_category_combo)

        _mr.addStretch(1)
        lay_auto.addWidget(mode_row)

        # 应用字段：使用文案库的标题/描述（常用配置紧贴匹配模式）
        self.standard_options_widget = QWidget(card_auto)
        _sor = QHBoxLayout(self.standard_options_widget)
        _sor.setContentsMargins(0, 0, 0, 0)
        _sor.setSpacing(18)
        label_apply = BodyLabel("应用字段", self.standard_options_widget)
        label_apply.setFixedWidth(_LABEL_W)
        label_apply.setStyleSheet(_LABEL_QSS)
        _sor.addWidget(label_apply)
        self.use_library_title_checkbox = CheckBox("使用文案标题", self.standard_options_widget)
        self.use_library_desc_checkbox = CheckBox("使用文案描述", self.standard_options_widget)
        _sor.addWidget(self.use_library_title_checkbox)
        _sor.addWidget(self.use_library_desc_checkbox)
        _sor.addStretch(1)
        lay_auto.addWidget(self.standard_options_widget)

        # 高级设置子卡：仅随机模式下出现，承载「分配策略」等不常用配置
        self.advanced_settings_card = QFrame(card_auto)
        self.advanced_settings_card.setObjectName("AutoMatchAdvancedCard")
        self.advanced_settings_card.setStyleSheet(
            "QFrame#AutoMatchAdvancedCard {"
            " background-color: rgba(0, 0, 0, 0.025);"
            " border: 1px dashed rgba(0, 0, 0, 0.12);"
            " border-radius: 8px;"
            "}"
        )
        asc_lay = QVBoxLayout(self.advanced_settings_card)
        asc_lay.setContentsMargins(12, 8, 12, 10)
        asc_lay.setSpacing(6)

        adv_header = QHBoxLayout()
        adv_header.setContentsMargins(0, 0, 0, 0)
        adv_header.setSpacing(4)
        adv_icon = IconWidget(FluentIcon.SETTING, self.advanced_settings_card)
        adv_icon.setFixedSize(12, 12)
        adv_header.addWidget(adv_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        adv_label = CaptionLabel("高级设置 · 随机模式", self.advanced_settings_card)
        adv_label.setStyleSheet(
            "color: rgba(0,0,0,0.55); font-size: 11px; font-weight: 600;"
        )
        adv_header.addWidget(adv_label, 0, Qt.AlignmentFlag.AlignVCenter)
        adv_header.addStretch(1)
        asc_lay.addLayout(adv_header)

        self.assign_strategy_row = QWidget(self.advanced_settings_card)
        _asr = QHBoxLayout(self.assign_strategy_row)
        _asr.setContentsMargins(0, 0, 0, 0)
        _asr.setSpacing(10)
        label_as = BodyLabel("分配策略", self.assign_strategy_row)
        label_as.setFixedWidth(_LABEL_W)
        label_as.setStyleSheet(_LABEL_QSS)
        _asr.addWidget(label_as)

        self.assign_strategy_combo = ComboBox(self.assign_strategy_row)
        for s in AssignStrategy:
            self.assign_strategy_combo.addItem(s.display_name(), userData=s.value)
        self.assign_strategy_combo.setFixedWidth(230)
        _asr.addWidget(self.assign_strategy_combo)
        _asr.addStretch(1)
        asc_lay.addWidget(self.assign_strategy_row)

        apply_instructional_tooltip(
            "文案库分配策略：确定如何将随机文案分配到不同账号的任务中。\n"
            "· 轮流：按账号顺序循环分配\n"
            "· 随机：对文案池进行随机打乱后分配\n"
            "· 平均：尽量让每个账号分到的文案数量均等",
            self.assign_strategy_combo
        )

        lay_auto.addWidget(self.advanced_settings_card)

        # 匹配规则说明：根据当前模式给出详细说明，充分利用卡片底部空间
        self.rules_tip_card = QFrame(card_auto)
        self.rules_tip_card.setObjectName("AutoMatchRulesTip")
        self.rules_tip_card.setStyleSheet(
            "QFrame#AutoMatchRulesTip {"
            " background-color: rgba(0, 159, 170, 0.05);"
            " border: 1px solid rgba(0, 159, 170, 0.18);"
            " border-radius: 10px;"
            "}"
        )
        rt_lay = QVBoxLayout(self.rules_tip_card)
        rt_lay.setContentsMargins(14, 12, 14, 12)
        rt_lay.setSpacing(8)

        tip_header = QHBoxLayout()
        tip_header.setContentsMargins(0, 0, 0, 0)
        tip_header.setSpacing(6)
        tip_icon = IconWidget(FluentIcon.INFO, self.rules_tip_card)
        tip_icon.setFixedSize(14, 14)
        tip_header.addWidget(tip_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        tip_header_label = BodyLabel("当前匹配规则说明", self.rules_tip_card)
        tip_header_label.setStyleSheet(
            "color: rgba(0, 159, 170, 0.95); font-weight: 600; font-size: 13px;"
        )
        tip_header.addWidget(tip_header_label, 0, Qt.AlignmentFlag.AlignVCenter)
        tip_header.addStretch(1)
        rt_lay.addLayout(tip_header)

        self._rules_tip_text = CaptionLabel("", self.rules_tip_card)
        self._rules_tip_text.setWordWrap(True)
        self._rules_tip_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._rules_tip_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._rules_tip_text.setStyleSheet(
            "color: rgba(0,0,0,0.72); font-size: 12px;"
        )
        rt_lay.addWidget(self._rules_tip_text, 1)

        # stretch=1：让规则说明卡片占满主卡剩余的纵向空间
        lay_auto.addWidget(self.rules_tip_card, 1)

        # 主卡始终充满整页（Expanding+Expanding）；卡片内部用 rules_tip 的 stretch 占满底部
        layout.addWidget(card_auto, 1)
        return page

    def _refresh_rules_tip(self) -> None:
        """根据当前匹配模式刷新规则说明文案：力求精简，每条规则两行内说明完。"""
        if not hasattr(self, "_rules_tip_text"):
            return
        mode = self._current_match_mode()
        use_t = self.use_library_title_checkbox.isChecked() if hasattr(self, "use_library_title_checkbox") else False
        use_d = self.use_library_desc_checkbox.isChecked() if hasattr(self, "use_library_desc_checkbox") else False
        if use_t and use_d:
            apply_hint = "将同时写入文案的标题与描述。"
        elif use_t:
            apply_hint = "仅写入文案标题，描述保持原值。"
        elif use_d:
            apply_hint = "仅写入文案描述，标题保持原值。"
        else:
            apply_hint = "未勾选任何字段，匹配结果不会写入任务。"

        if mode == CopywritingMatchMode.STANDARD:
            rule = "按任务作品编号匹配「标准文案库」中同编号的条目，需保证条目数充足并与任务一一对应。"
        elif mode == CopywritingMatchMode.RANDOM_ALL:
            rule = "从「随机文案库」整库随机抽取；账号间分配方式见上方「分配策略」。"
        elif mode == CopywritingMatchMode.RANDOM_CATEGORY:
            cat_text = self.random_category_combo.currentText() if hasattr(self, "random_category_combo") else ""
            if cat_text and cat_text != "选择分类...":
                rule = f"在「随机文案库 → {cat_text}」中随机抽取；分配方式见上方「分配策略」。"
            else:
                rule = "请先在右侧选择分类，否则不会匹配到任何文案。"
        else:
            rule = "请在「匹配模式」下拉中选择一种自动匹配方式。"
        self._rules_tip_text.setText(f"{rule}\n{apply_hint}")

    def _build_manual_page(self, parent: QWidget) -> QWidget:
        """手动填写页：紧凑卡片，描述高度受限，话题/字符提示同行。"""
        page = QWidget(parent)
        page.setObjectName("PublishDescriptionPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        self.card_manual = CardWidget(page)
        self.card_manual.setObjectName("PublishDescriptionCard")
        self.card_manual.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.card_manual.setMaximumWidth(610)
        lay_manual = QVBoxLayout(self.card_manual)
        lay_manual.setContentsMargins(16, 12, 16, 12)
        lay_manual.setSpacing(8)

        # 标题行：左侧「手动填写」标签 + 右侧「应用到所有任务」复选框，节省一行垂直空间
        header_row = QWidget(self.card_manual)
        _hr = QHBoxLayout(header_row)
        _hr.setContentsMargins(0, 0, 0, 0)
        _hr.setSpacing(8)
        sub_manual = SubtitleLabel("手动填写", self.card_manual)
        _hr.addWidget(sub_manual)
        _hr.addStretch(1)
        self.apply_all_checkbox = CheckBox("应用到所有任务", self.card_manual)
        _hr.addWidget(self.apply_all_checkbox)
        lay_manual.addWidget(header_row)

        _tip_manual_block = (
            "勾选「应用到所有任务」后，下方填写的标题和描述将应用到任务列表中全部任务，适合多视频使用统一描述。"
        )
        apply_instructional_tooltip(_tip_manual_block, sub_manual)
        apply_instructional_tooltip(_tip_manual_block, self.apply_all_checkbox)

        # 标题行
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)
        title_label = BodyLabel("标题", self.card_manual)
        title_label.setFixedWidth(48)
        title_label.setStyleSheet("color: rgba(0,0,0,0.6); font-weight: 600; font-size: 13px;")
        self.same_title_edit = LineEdit(self.card_manual)
        self.same_title_edit.setPlaceholderText(f"作品标题（最多 {TITLE_MAX_LENGTH} 字）")
        self.same_title_edit.setMaxLength(TITLE_MAX_LENGTH)
        self.same_title_edit.setMinimumHeight(34)
        self.same_title_edit.returnPressed.connect(self._on_confirm)
        title_row.addWidget(title_label)
        title_row.addWidget(self.same_title_edit, 1)
        lay_manual.addLayout(title_row)

        # 描述：高度受限，约 4 行可视，溢出自动滚动
        desc_label = BodyLabel("描述", self.card_manual)
        desc_label.setStyleSheet("color: rgba(0,0,0,0.6); font-weight: 600; font-size: 13px;")
        lay_manual.addWidget(desc_label)

        self.same_desc_edit = TextEdit(self.card_manual)
        self.same_desc_edit.setPlaceholderText("作品描述，支持 #话题 格式")
        self.same_desc_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.same_desc_edit.setMinimumHeight(96)
        self.same_desc_edit.setMaximumHeight(108)
        self.same_desc_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lay_manual.addWidget(self.same_desc_edit)

        # 字符数 + 话题数同行（左：话题 / 右：字符），节省一行高度
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 2, 0, 0)
        meta_row.setSpacing(8)
        self.same_desc_topic_count_label = CaptionLabel("已识别 0 个话题", self.card_manual)
        self.same_desc_topic_count_label.setStyleSheet("color: rgba(0,0,0,0.55); font-size: 11px;")
        meta_row.addWidget(self.same_desc_topic_count_label)
        meta_row.addStretch(1)
        self.same_desc_char_count_label = CaptionLabel(f"0 / {DESC_CHAR_LIMIT}", self.card_manual)
        self.same_desc_char_count_label.setStyleSheet("color: rgba(0,0,0,0.45); font-size: 11px;")
        meta_row.addWidget(self.same_desc_char_count_label)
        lay_manual.addLayout(meta_row)

        # 话题预览：默认隐藏，识别到话题时由控制器显示
        self.same_desc_topics_preview = CaptionLabel("", self.card_manual)
        self.same_desc_topics_preview.setStyleSheet("color: rgba(0,0,0,0.45); font-size: 11px;")
        self.same_desc_topics_preview.setWordWrap(True)
        self.same_desc_topics_preview.setVisible(False)
        lay_manual.addWidget(self.same_desc_topics_preview)

        layout.addWidget(self.card_manual)
        layout.addStretch(1)

        self._work_desc_edit_controller = WorkDescriptionEditController(
            self,
            self.same_desc_edit,
            char_limit=DESC_CHAR_LIMIT,
            char_count_label=self.same_desc_char_count_label,
            topic_count_label=self.same_desc_topic_count_label,
            topic_count_format="已识别 {} 个话题",
            topic_list_label=self.same_desc_topics_preview,
            after_programmatic_text_change=self._sync_desc_after_programmatic_edit,
        )

        return page

    def _build_ui(self) -> None:
        self._apply_dialog_style()
        # 顶部分段 + 两页内容（每页独立滚动，顶部不随内容滚动）
        self._pivot = SegmentedWidget(self)
        self._apply_pivot_style()
        try:
            self._pivot.setMaximumWidth(610)
            self._pivot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        self._stack = QStackedWidget(self)
        self._stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")

        auto_page = self._build_auto_page(self._stack)
        manual_page = self._build_manual_page(self._stack)
        self._stack.addWidget(self._wrap_scroll(auto_page))
        self._stack.addWidget(self._wrap_scroll(manual_page))

        # 初始化顶部 Tab
        self._pivot.addItem(
            routeKey="auto",
            text="自动匹配",
            onClick=lambda: self._set_current_page(0),
        )
        self._pivot.addItem(
            routeKey="manual",
            text="手动填写",
            onClick=lambda: self._on_manual_tab_clicked(),
        )
        try:
            self._pivot.currentItemChanged.connect(self._sync_pivot_selection)
        except Exception:
            pass

        # 顶部与主体：Pivot 与下方卡片左右边距（16px）对齐，整体撑到 610px 宽
        self.viewLayout.setSpacing(10)
        pivot_bar = QWidget(self)
        pivot_bar_lay = QHBoxLayout(pivot_bar)
        pivot_bar_lay.setContentsMargins(16, 0, 16, 0)
        pivot_bar_lay.setSpacing(0)
        pivot_bar_lay.addWidget(self._pivot, 1)
        pivot_bar_lay.addStretch(0)

        self.viewLayout.addWidget(pivot_bar, 0)
        self.viewLayout.addWidget(self._stack, 1)
        self._set_current_page(0)
        self._sync_pivot_selection()

    def _on_manual_tab_clicked(self) -> None:
        """手动填写 Tab 点击：开启自动匹配时提示并阻止切页。"""
        if hasattr(self, "auto_match_switch") and self.auto_match_switch.isChecked():
            InfoBar.warning(
                "手动填写已禁用",
                "已开启自动匹配，请先关闭「自动匹配」后再使用手动填写。",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2500,
            )
            self._set_current_page(0)
            return
        self._set_current_page(1)

    def _restore_state(self) -> None:
        self._restoring = True
        try:
            self.auto_match_switch.setChecked(self._state.auto_match_enabled)
            
            idx = self.match_mode_combo.findData(self._state.match_mode)
            if idx >= 0:
                self.match_mode_combo.setCurrentIndex(idx)
            
            self.apply_all_checkbox.setChecked(self._state.apply_to_all_tasks)
            self.use_library_desc_checkbox.setChecked(self._state.use_library_desc)
            self.use_library_title_checkbox.setChecked(self._state.use_library_title)
            self.same_title_edit.setText(self._state.title)
            self.same_desc_edit.setPlainText(self._state.desc)
            
            as_idx = self.assign_strategy_combo.findData(self._state.copywriting_assign_strategy)
            if as_idx >= 0:
                self.assign_strategy_combo.setCurrentIndex(as_idx)
            
            self._update_ui_visibility()
            self._refresh_random_categories()
            self._refresh_library_count()
        finally:
            self._restoring = False
        self._refresh_topics_preview_visibility()

    def _bind_events(self) -> None:
        from src.ui.utils.async_helper import run_async_from_ui
        self.auto_match_switch.checkedChanged.connect(self._on_auto_match_toggled)
        self.match_mode_combo.currentIndexChanged.connect(self._on_match_mode_changed)
        self.random_category_combo.currentIndexChanged.connect(self._on_random_category_changed)
        self.assign_strategy_combo.currentIndexChanged.connect(self._on_assign_strategy_changed)
        
        self.apply_all_checkbox.stateChanged.connect(self._on_any_changed)
        self.use_library_desc_checkbox.stateChanged.connect(self._on_use_library_changed)
        self.use_library_title_checkbox.stateChanged.connect(self._on_use_library_changed)
        self.same_title_edit.textChanged.connect(self._on_title_changed)
        self.same_desc_edit.textChanged.connect(self._on_desc_changed)
        
        # 数量统计监听
        self.auto_match_switch.checkedChanged.connect(self._refresh_library_count)
        self.match_mode_combo.currentIndexChanged.connect(self._refresh_library_count)
        self.random_category_combo.currentIndexChanged.connect(self._refresh_library_count)

    def _update_ui_visibility(self) -> None:
        """根据开关状态和模式更新 UI 可见性和可用性。
        关闭自动匹配时所有配置项仍然显示，只是置灰禁用，便于用户预览将要使用的设置。"""
        auto_enabled = self.auto_match_switch.isChecked()
        self.match_mode_combo.setEnabled(auto_enabled)
        
        mode = self._current_match_mode()
        
        # 指定分类下拉：可见性看模式（仅指定分类模式才出现），可用性看开关
        self.random_category_combo.setVisible(mode == CopywritingMatchMode.RANDOM_CATEGORY)
        self.random_category_combo.setEnabled(auto_enabled)
        # 应用字段始终可见，关闭自动匹配时整体禁用
        self.standard_options_widget.setVisible(True)
        self.standard_options_widget.setEnabled(auto_enabled)

        # 分配策略归类到「高级设置」子卡：可见性仅看模式（随机库才出现），可用性看开关
        is_random = mode in (CopywritingMatchMode.RANDOM_ALL, CopywritingMatchMode.RANDOM_CATEGORY)
        if hasattr(self, "advanced_settings_card"):
            self.advanced_settings_card.setVisible(is_random)
            self.advanced_settings_card.setEnabled(auto_enabled)
        # 行本身保持可见（由父卡可见性控制），避免父卡显示时内部行被误隐藏
        self.assign_strategy_row.setVisible(True)

        # 规则说明卡：始终显示；关闭自动匹配时整体置灰
        if hasattr(self, "rules_tip_card"):
            self.rules_tip_card.setVisible(True)
            self.rules_tip_card.setEnabled(auto_enabled)
        self._refresh_rules_tip()
        # 同步刷新「确定」按钮可用性（指定分类模式未选分类时禁用）
        self._update_confirm_button_state()
        
        # 手动填写页：当开启自动匹配时禁用 + Tab 置灰
        self.card_manual.setEnabled(not auto_enabled)
        self._set_pivot_item_enabled("manual", enabled=(not auto_enabled))
        if auto_enabled:
            # 若用户此前停留在“手动填写”，开启后强制回到自动页，避免看到不可操作的表单
            try:
                if hasattr(self, "_stack") and int(self._stack.currentIndex()) == 1:
                    self._set_current_page(0)
            except Exception:
                self._set_current_page(0)

    def _current_match_mode(self) -> str:
        raw = self.match_mode_combo.currentData()
        if raw in (
            CopywritingMatchMode.STANDARD,
            CopywritingMatchMode.RANDOM_ALL,
            CopywritingMatchMode.RANDOM_CATEGORY,
        ):
            return str(raw)

        # 兜底：部分场景下 currentData 可能为空，改用索引和文本判定，确保“指定分类”能正确显示分类下拉。
        idx = int(self.match_mode_combo.currentIndex())
        if idx == 1:
            return CopywritingMatchMode.RANDOM_ALL
        if idx == 2:
            return CopywritingMatchMode.RANDOM_CATEGORY

        text = str(self.match_mode_combo.currentText() or "")
        if "指定分类" in text:
            return CopywritingMatchMode.RANDOM_CATEGORY
        if "全库随机" in text:
            return CopywritingMatchMode.RANDOM_ALL
        return CopywritingMatchMode.STANDARD

    def _on_auto_match_toggled(self, checked: bool) -> None:
        if self._restoring:
            return
        self._state.auto_match_enabled = checked
        self._update_ui_visibility()
        self._save_session()
        
        if self._state.match_mode == CopywritingMatchMode.STANDARD:
            self._maybe_trigger_library_fetch_on_restore()

    def _on_match_mode_changed(self, index: int) -> None:
        if self._restoring:
            return
        self._state.match_mode = self._current_match_mode()
        self._update_ui_visibility()
        self._save_session()

        # 模式切换后，若开启了自动匹配，尝试拉取预览以更新界面
        if self._state.auto_match_enabled:
            self._maybe_trigger_library_fetch_on_restore()

    def _on_random_category_changed(self, index: int) -> None:
        if self._restoring:
            return
        self._state.random_category_id = self.random_category_combo.currentData()
        self._save_session()
        self._refresh_rules_tip()
        self._update_confirm_button_state()

        # 切换分类后，若开启了自动匹配，尝试拉取预览
        if self._state.auto_match_enabled:
            self._maybe_trigger_library_fetch_on_restore()

    def _on_assign_strategy_changed(self, index: int) -> None:
        if self._restoring:
            return
        self._state.copywriting_assign_strategy = str(self.assign_strategy_combo.currentData())
        self._save_session()

    @asyncSlot()
    async def _refresh_random_categories(self) -> None:
        """异步加载随机分类。"""
        from src.infrastructure.storage.repositories.random_copywriting_repository import RandomCopywritingRepository
        
        try:
            cats = await RandomCopywritingRepository.list_categories()
            
            self.random_category_combo.blockSignals(True)
            self.random_category_combo.clear()
            self.random_category_combo.addItem("选择分类...", userData=None)
            target_idx = 0
            for i, cat in enumerate(cats, start=1):
                self.random_category_combo.addItem(cat["name"], userData=cat["id"])
                if cat["id"] == self._state.random_category_id:
                    target_idx = i
            self.random_category_combo.setCurrentIndex(target_idx)
            self.random_category_combo.blockSignals(False)
            
            # 加载完成后刷新一次数量显示与确定按钮状态
            await self._refresh_library_count()
            self._update_confirm_button_state()
        except Exception as e:
            logger.error("加载随机分类失败: %s", e, exc_info=True)

    @asyncSlot()
    async def _refresh_library_count(self) -> None:
        """异步刷新当前所选文案库的数量显示。"""
        if not self.auto_match_switch.isChecked():
            self.library_count_label.setVisible(False)
            return

        self.library_count_label.setVisible(True)

        from src.infrastructure.storage.repositories.copywriting_repository import CopywritingRepository
        from src.infrastructure.storage.repositories.random_copywriting_repository import RandomCopywritingRepository

        mode = self._current_match_mode()
        
        try:
            if mode == CopywritingMatchMode.STANDARD:
                count = await CopywritingRepository.count_valid_items()
            elif mode == CopywritingMatchMode.RANDOM_ALL:
                count = await RandomCopywritingRepository.count_items(None)
            elif mode == CopywritingMatchMode.RANDOM_CATEGORY:
                cat_id = self.random_category_combo.currentData()
                if cat_id is None:
                    count = 0
                else:
                    count = await RandomCopywritingRepository.count_items(cat_id)
            else:
                count = 0

            self.library_count_label.setText(f"库内文案: {count}")
        except Exception as e:
            logger.error("刷新文案数量失败: %s", e)
            self.library_count_label.setText("库内文案: 获取失败")

    def _save_session(self) -> None:
        if self._suppress_async_persist:
            return
        d = self._state.to_dict()
        save_persisted_publish_description_prefs(d)
        _SESSION_STORAGE[_SESSION_KEY] = d

    def _on_any_changed(self) -> None:
        if self._restoring:
            return
        self._state.apply_to_all_tasks = self.apply_all_checkbox.isChecked()
        self._save_session()

    def _on_title_changed(self) -> None:
        if self._restoring:
            return
        self._state.on_title_edited(self.same_title_edit.text())
        self._save_session()

    def _on_desc_changed(self) -> None:
        if self._restoring:
            return
        self._state.on_desc_edited(self.same_desc_edit.toPlainText())
        self._save_session()
        self._refresh_topics_preview_visibility()

    def _refresh_topics_preview_visibility(self) -> None:
        """识别到 #话题 时显示预览行，否则隐藏，避免空文案占据高度。"""
        try:
            ctrl = getattr(self, "_work_desc_edit_controller", None)
            tags = ctrl.get_topic_tags() if ctrl is not None else []
            preview = getattr(self, "same_desc_topics_preview", None)
            if preview is not None:
                preview.setVisible(bool(tags))
        except Exception:
            pass

    def _on_use_library_changed(self) -> None:
        if self._restoring:
            return
        self._state.use_library_desc = self.use_library_desc_checkbox.isChecked()
        self._state.use_library_title = self.use_library_title_checkbox.isChecked()
        self._save_session()
        self._refresh_rules_tip()

        need_title = self.use_library_title_checkbox.isChecked()
        need_desc = self.use_library_desc_checkbox.isChecked()

        cached = self._fetcher.cached()
        if cached is not None:
            self._apply_library_item(cached, need_title, need_desc)
            return

        should_start = self._fetcher.update_pending(title=need_title, desc=need_desc)
        if should_start:
            self._start_fetch_latest_copywriting()

    def _maybe_trigger_library_fetch_on_restore(self) -> None:
        need_title = self.use_library_title_checkbox.isChecked()
        need_desc = self.use_library_desc_checkbox.isChecked()
        if not (need_title or need_desc):
            return
        if self._fetcher.has_cache():
            cached = self._fetcher.cached()
            if cached is not None:
                self._apply_library_item(cached, need_title, need_desc)
            return
        should_start = self._fetcher.update_pending(title=need_title, desc=need_desc)
        if should_start:
            self._start_fetch_latest_copywriting()

    def _start_fetch_latest_copywriting(self) -> None:
        from src.ui.utils.async_helper import run_async_from_ui
        from src.infrastructure.storage.repositories.copywriting_repository import CopywritingRepository
        from src.infrastructure.storage.repositories.random_copywriting_repository import RandomCopywritingRepository

        async def _load():
            mode = self._current_match_mode()
            if mode == CopywritingMatchMode.STANDARD:
                items = await CopywritingRepository.list_items(page=1, page_size=1)
                return items[0] if items else None
            else:
                # 随机库模式
                cat_id = None
                if mode == CopywritingMatchMode.RANDOM_CATEGORY:
                    cat_id = self.random_category_combo.currentData()
                return await RandomCopywritingRepository.get_random_one(cat_id)

        async def _run() -> None:
            item: Optional[dict] = None
            try:
                item = await _load()
            except Exception:
                logger.debug("异步拉取文案库失败", exc_info=True)
            if self._suppress_async_persist:
                return
            cached, title, desc = self._fetcher.complete(item)
            # 即使 cached 为 None (库为空)，也需要调用 apply 以清空 UI 或状态
            self._apply_library_item(cached, title, desc)

        try:
            run_async_from_ui(_run)
        except Exception:
            logger.debug("调度异步拉取文案库失败", exc_info=True)
            self._fetcher.complete(None)
            self._save_session()

    def _apply_library_item(self, item: Optional[dict], apply_title: bool, apply_desc: bool) -> None:
        if item is None:
            lib_title = ""
            lib_desc = ""
        else:
            lib_title = (item.get("short_title") or "").strip()
            lib_desc_raw = (item.get("description") or "").strip()
            lib_desc = normalize_topics_for_paste(lib_desc_raw) if lib_desc_raw else lib_desc_raw
    
        self._restoring = True
        try:
            if apply_title:
                self._state.toggle_use_library_title(True, lib_title)
                self.same_title_edit.setText(self._state.title)
            else:
                self._state.toggle_use_library_title(False, lib_title)
                self.same_title_edit.setText(self._state.title)
    
            if apply_desc:
                self._state.toggle_use_library_desc(True, lib_desc)
                self.same_desc_edit.setPlainText(self._state.desc)
            else:
                self._state.toggle_use_library_desc(False, lib_desc)
                self.same_desc_edit.setPlainText(self._state.desc)
        finally:
            self._restoring = False
        self._save_session()
        self._refresh_topics_preview_visibility()

    def _ensure_library_filled_sync(self) -> None:
        """若已勾选使用文案库但标题/描述仍为空，则同步拉取文案库并填充，避免确定后页面拿到空内容。"""
        need_title = self.use_library_title_checkbox.isChecked()
        need_desc = self.use_library_desc_checkbox.isChecked()
        if not (need_title or need_desc):
            return
        title_empty = not (self.same_title_edit.text() or "").strip()
        desc_empty = not (self.same_desc_edit.toPlainText() or "").strip()
        if not (need_title and title_empty) and not (need_desc and desc_empty):
            return

        from src.infrastructure.storage.repositories.copywriting_repository import CopywritingRepository
        from src.infrastructure.storage.repositories.random_copywriting_repository import RandomCopywritingRepository
        import asyncio

        async def _load():
            mode = self._current_match_mode()
            if mode == CopywritingMatchMode.STANDARD:
                items = await CopywritingRepository.list_items(page=1, page_size=1)
                return items[0] if items else None
            else:
                cat_id = None
                if mode == CopywritingMatchMode.RANDOM_CATEGORY:
                    cat_id = self.random_category_combo.currentData()
                return await RandomCopywritingRepository.get_random_one(cat_id)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        ev = QEventLoop(self)
        future = asyncio.ensure_future(_load(), loop=loop)
        future.add_done_callback(lambda _: ev.quit())
        ev.exec()
        try:
            item = future.result()
        except Exception:
            logger.debug("同步拉取文案库失败", exc_info=True)
            return

        self._apply_library_item(item, need_title, need_desc)

    def _capture_state_from_widgets(self) -> None:
        self._state.apply_to_all_tasks = self.apply_all_checkbox.isChecked()
        self._state.use_library_title = self.use_library_title_checkbox.isChecked()
        self._state.use_library_desc = self.use_library_desc_checkbox.isChecked()
        t = self.same_title_edit.text()
        d = self.same_desc_edit.toPlainText()
        self._state.title = t
        self._state.desc = d
        if not self._state.use_library_title:
            self._state.manual_title_backup = t
        if not self._state.use_library_desc:
            self._state.manual_desc_backup = d

    def _on_confirm(self) -> None:
        if not self._validate_confirm():
            return
        self._ensure_library_filled_sync()
        self._capture_state_from_widgets()
        self._save_session()
        self.accept()

    def _validate_confirm(self) -> bool:
        """提交前校验：开启自动匹配且选了「指定分类」模式时，必须先选具体分类。"""
        if not hasattr(self, "auto_match_switch") or not self.auto_match_switch.isChecked():
            return True
        if self._current_match_mode() == CopywritingMatchMode.RANDOM_CATEGORY:
            cat_id = self.random_category_combo.currentData() if hasattr(self, "random_category_combo") else None
            if cat_id is None:
                InfoBar.warning(
                    "请先选择分类",
                    "已选择「随机文案库（指定分类）」模式，请在右侧选择一个分类后再确认。",
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=2500,
                )
                try:
                    self.random_category_combo.setFocus()
                except Exception:
                    pass
                return False
        return True

    def _update_confirm_button_state(self) -> None:
        """根据当前配置实时刷新「确定」按钮可用性：
        - 自动匹配开启 + 指定分类模式 + 未选分类 → 禁用，并附鼠标悬浮提示
        - 其他场景 → 启用
        """
        if not hasattr(self, "yesButton") or not hasattr(self, "auto_match_switch"):
            return
        if not self.auto_match_switch.isChecked():
            self.yesButton.setEnabled(True)
            self.yesButton.setToolTip("")
            return
        if self._current_match_mode() == CopywritingMatchMode.RANDOM_CATEGORY:
            cat_id = self.random_category_combo.currentData() if hasattr(self, "random_category_combo") else None
            if cat_id is None:
                self.yesButton.setEnabled(False)
                self.yesButton.setToolTip("请先选择一个分类后再确定")
                return
        self.yesButton.setEnabled(True)
        self.yesButton.setToolTip("")

    def _reorder_buttons(self):
        button_layout = getattr(self, "buttonLayout", None)
        if button_layout is None:
            button_layout = self.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(self.yesButton)
            button_layout.removeWidget(self.cancelButton)
            button_layout.addWidget(self.cancelButton)
            button_layout.addWidget(self.yesButton)

    def done(self, code: int) -> None:
        """关闭后禁止异步文案库回调再写配置，避免与已确认状态竞态。"""
        self._suppress_async_persist = True
        # 清理 worker
        for w in self._active_workers:
            try:
                w.disconnect()
            except:
                pass
        self._active_workers.clear()
        super().done(int(code))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def get_description_settings(self) -> dict:
        return {
            "mode": "same",
            "same_title": self.same_title_edit.text().strip(),
            "same_desc": self.same_desc_edit.toPlainText().strip(),
            "apply_to_all_tasks": self.apply_all_checkbox.isChecked(),
            "use_library_title": self.use_library_title_checkbox.isChecked(),
            "use_library_desc": self.use_library_desc_checkbox.isChecked(),
            # 新增字段
            "auto_match_enabled": self.auto_match_switch.isChecked(),
            "match_mode": self.match_mode_combo.currentData(),
            "random_category_id": self.random_category_combo.currentData(),
            "copywriting_assign_strategy": self.assign_strategy_combo.currentData(),
        }
