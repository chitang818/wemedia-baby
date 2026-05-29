"""
发布设置弹窗（原列表设置）
文件路径：src/ui/pages/publish/list_settings_dialog.py
功能：发布列表显示模式 + 发布速度 + 任务间隔 + 显示浏览器 + 发布后关机（仅一次，不写配置）
+ 按平台时排在第一的平台 + 发布后文件处理；除「发布后关机」外持久化到 app_config.json（ConfigCenter）
"""

import logging
import json
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

from PySide6.QtWidgets import (
    QWidget,
    QButtonGroup,
    QHBoxLayout,
    QVBoxLayout,
    QFormLayout,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from qfluentwidgets import (
    BodyLabel,
    RadioButton,
    ComboBox,
    CheckBox,
    CardWidget,
    SubtitleLabel,
    CaptionLabel,
    LineEdit,
    InfoBar,
)

from src.ui.components.base_dialog import AppMessageBoxBase
from src.ui.utils.fluent_tooltips import apply_instructional_tooltip
from src.infrastructure.common.config.config_center import get_registered_config_center
from src.infrastructure.common.config.app_config_keys import (
    KEY_PUBLISH_LIST,
    PUBLISH_LIST_DISPLAY_MODE,
    PUBLISH_LIST_SPEED_INDEX,
    PUBLISH_LIST_FIRST_PLATFORM,
    PUBLISH_LIST_INTERVAL_SECONDS,
    PUBLISH_LIST_POST_PUBLISH_FILE_ACTION,
    PUBLISH_LIST_SHOW_BROWSER,
)
PUBLISH_LIST_QUEUE_RETRY_COUNT = "queue_retry_count"
PUBLISH_LIST_PRECHECK_ACCOUNT_ONLINE = "precheck_account_online"
from src.infrastructure.common.config.app_config_merge import (
    _deep_merge_inplace,
    merge_app_config,
    read_app_config_from_disk_sync,
)
from src.infrastructure.common.publish_material_path_policy import (
    pending_records_any_material_library_tree,
    pending_records_any_public_pool,
    sanitize_post_publish_action_for_save,
)
from src.infrastructure.browser.browser_launch_policy import (
    should_force_visible_publish_browser,
    should_respect_platform_publish_interval,
)
from src.infrastructure.common.path_manager import PathManager

# 兼容旧代码引用的「逻辑键名」常量（已映射到 app_config.publish_list 下的 snake_case）
DISPLAY_MODE_KEY = "publish_list/display_mode"
MODE_ORDER = "order"
MODE_PLATFORM = "platform"
MODE_ACCOUNT = "account"
SPEED_INDEX_KEY = "speed_index"
FIRST_PLATFORM_KEY = "publish_list/first_platform"
PUBLISH_INTERVAL_SEC_KEY = "publish_list/interval_seconds"
DEFAULT_PUBLISH_INTERVAL_SEC = 20
MIN_PUBLISH_INTERVAL_SEC = 0
MAX_PUBLISH_INTERVAL_SEC = 600
POST_PUBLISH_ACTION_KEY = "publish_list/post_publish_file_action"
POST_PUBLISH_ACTION_NONE = "none"
POST_PUBLISH_ACTION_MOVE = "move"
POST_PUBLISH_ACTION_DELETE = "delete"

SPEED_OPTIONS = [
    ("正常", 1.0),
    ("快速", 0.5),
    ("慢速", 2.0),
]

# 「发布后关机」仅内存一次有效：确认发布设置时写入，队列结束后清除；不写入 app_config。
_publish_after_shutdown_one_shot_armed: bool = False


def is_publish_after_shutdown_one_shot_armed() -> bool:
    """是否已为「下一次发布队列」勾选发布后关机（未持久化）。"""
    return _publish_after_shutdown_one_shot_armed


def set_publish_after_shutdown_one_shot_armed(armed: bool) -> None:
    global _publish_after_shutdown_one_shot_armed
    _publish_after_shutdown_one_shot_armed = bool(armed)


def clear_publish_after_shutdown_one_shot() -> None:
    """清除一次性发布后关机标记（队列已结束）。"""
    global _publish_after_shutdown_one_shot_armed
    _publish_after_shutdown_one_shot_armed = False


def _publish_list_dict() -> Dict[str, Any]:
    cc = get_registered_config_center()
    if cc is not None:
        pl = cc.get_app_config().get(KEY_PUBLISH_LIST)
        if isinstance(pl, dict):
            return pl
        return {}
    root = read_app_config_from_disk_sync()
    pl = root.get(KEY_PUBLISH_LIST)
    return pl if isinstance(pl, dict) else {}


def _coerce_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _apply_publish_list_partial_to_memory_sync(partial: Dict[str, Any]) -> None:
    """先把 publish_list 局部键合并进 ConfigCenter 内存，便于紧接着的 get_* / UI refresh 读到新值。

    异步 merge_app_config 可能晚一拍才写完内存+磁盘；仅依赖异步时会出现「弹窗已提示已改为移动，卡片仍显示不处理」。
    """
    if not partial:
        return
    cc = get_registered_config_center()
    if cc is None:
        return
    app_cfg = cc.get_app_config()
    if not isinstance(app_cfg, dict):
        return
    pl = app_cfg.get(KEY_PUBLISH_LIST)
    if not isinstance(pl, dict):
        pl = {}
        app_cfg[KEY_PUBLISH_LIST] = pl
    _deep_merge_inplace(pl, partial)


def _schedule_publish_list_patch(partial: Dict[str, Any]) -> None:
    _apply_publish_list_partial_to_memory_sync(partial)
    from src.ui.utils.async_helper import run_async_from_ui

    async def _save() -> None:
        await merge_app_config(get_registered_config_center(), {KEY_PUBLISH_LIST: partial})

    run_async_from_ui(_save)


def get_display_mode() -> str:
    pl = _publish_list_dict()
    v = pl.get(PUBLISH_LIST_DISPLAY_MODE, MODE_ORDER)
    return str(v) if v is not None else MODE_ORDER


def set_display_mode(mode: str) -> None:
    _schedule_publish_list_patch({PUBLISH_LIST_DISPLAY_MODE: mode})


def get_speed_index() -> int:
    pl = _publish_list_dict()
    idx = _coerce_int(pl.get(PUBLISH_LIST_SPEED_INDEX, 0), 0)
    return max(0, min(idx, len(SPEED_OPTIONS) - 1))


def get_speed_rate() -> float:
    return SPEED_OPTIONS[get_speed_index()][1]


def get_publish_interval_seconds() -> int:
    pl = _publish_list_dict()
    v = _coerce_int(pl.get(PUBLISH_LIST_INTERVAL_SECONDS, DEFAULT_PUBLISH_INTERVAL_SEC), DEFAULT_PUBLISH_INTERVAL_SEC)
    return max(MIN_PUBLISH_INTERVAL_SEC, min(v, MAX_PUBLISH_INTERVAL_SEC))


def _platform_publish_interval_min_seconds(platform: str) -> int:
    platform_id = str(platform or "").strip()
    if not platform_id:
        return 0
    try:
        p = Path(PathManager.get_resource_path(f"config/platforms/{platform_id}.json"))
        if not p.is_file():
            return 0
        data = json.loads(p.read_text(encoding="utf-8"))
        interval = data.get("publish_interval") if isinstance(data, dict) else None
        if not isinstance(interval, dict):
            return 0
        return max(0, int(interval.get("min", 0) or 0))
    except Exception:
        return 0


def get_effective_publish_interval_seconds(platform: str = "") -> int:
    base = get_publish_interval_seconds()
    if not should_respect_platform_publish_interval():
        return base
    return max(base, _platform_publish_interval_min_seconds(platform))


def sample_publish_interval_delay_seconds(base: int) -> float:
    """在 [max(0, base-3), base+3] 上均匀随机；调用方应在「下一任务与当前同平台」时才使用。"""
    b = max(MIN_PUBLISH_INTERVAL_SEC, min(int(base), MAX_PUBLISH_INTERVAL_SEC))
    if b <= 0:
        return 0.0
    lo = max(0.0, float(b) - 3.0)
    hi = float(b) + 3.0
    return random.uniform(lo, hi)


def get_first_platform() -> str:
    pl = _publish_list_dict()
    v = pl.get(PUBLISH_LIST_FIRST_PLATFORM, "") or ""
    return str(v).strip()


def set_first_platform(platform_id: str) -> None:
    val = str(platform_id).strip() if platform_id else ""
    _schedule_publish_list_patch({PUBLISH_LIST_FIRST_PLATFORM: val})


def get_post_publish_action() -> str:
    """读取发布后文件处理方式；未配置时默认为「移动至已发布目录」。"""
    pl = _publish_list_dict()
    raw = pl.get(PUBLISH_LIST_POST_PUBLISH_FILE_ACTION)
    if raw is None:
        return POST_PUBLISH_ACTION_MOVE
    v = str(raw).strip()
    if not v:
        return POST_PUBLISH_ACTION_MOVE
    if v not in (POST_PUBLISH_ACTION_NONE, POST_PUBLISH_ACTION_MOVE, POST_PUBLISH_ACTION_DELETE):
        return POST_PUBLISH_ACTION_NONE
    return v


def set_post_publish_action(action: str) -> None:
    _schedule_publish_list_patch({PUBLISH_LIST_POST_PUBLISH_FILE_ACTION: action})


def get_publish_show_browser() -> bool:
    """True：有头模式（显示浏览器窗口）；发布流程默认强制显示本机 Chrome。"""
    if should_force_visible_publish_browser():
        return True
    pl = _publish_list_dict()
    v = pl.get(PUBLISH_LIST_SHOW_BROWSER)
    if v is None:
        return True
    return bool(v)

def get_publish_queue_retry_count() -> int:
    """获取发布队列重试次数（0~3）。"""
    pl = _publish_list_dict()
    v = _coerce_int(pl.get(PUBLISH_LIST_QUEUE_RETRY_COUNT, 0), 0)
    return max(0, min(v, 3))


def get_auto_shutdown_after_complete() -> bool:
    """是否与「发布后关机」相关：当前是否为一次性勾选生效中（不写配置文件）。"""
    return is_publish_after_shutdown_one_shot_armed()


def get_precheck_account_online_enabled() -> bool:
    """发布前是否先批量检测账号在线状态。默认开启。"""
    pl = _publish_list_dict()
    v = pl.get(PUBLISH_LIST_PRECHECK_ACCOUNT_ONLINE)
    if v is None:
        return True
    return bool(v)


def format_publish_settings_summary() -> str:
    """格式化为多行纯文本，供发布列表「任务统计」卡片展示当前发布设置。"""
    mode = get_display_mode()
    if mode == MODE_PLATFORM:
        mode_zh = "按平台显示"
    elif mode == MODE_ACCOUNT:
        mode_zh = "按账号显示"
    else:
        mode_zh = "顺序显示"
    lines = [f"列表：{mode_zh}"]
    if mode == MODE_PLATFORM:
        first = get_first_platform()
        if first:
            try:
                from src.utils.platform_names import get_platform_display_name
                lines.append(f"首平台：{get_platform_display_name(first)}")
            except Exception:
                lines.append(f"首平台：{first}")
        else:
            lines.append("首平台：不指定")
    idx = get_speed_index()
    lines.append(f"速度：{SPEED_OPTIONS[idx][0]}")
    sec = get_publish_interval_seconds()
    lines.append(f"任务间隔：{sec} 秒（同平台连续时）")
    
    retry_ct = get_publish_queue_retry_count()
    lines.append(f"失败重试：{'关闭' if retry_ct == 0 else f'{retry_ct}次'}")

    lines.append(f"浏览器：{'显示本机 Chrome' if get_publish_show_browser() else '后台运行'}")
    lines.append(f"发布前检测账号在线：{'开启' if get_precheck_account_online_enabled() else '关闭'}")
    action = get_post_publish_action()
    if action == POST_PUBLISH_ACTION_MOVE:
        lines.append("发布后文件：移动至媒体库已发布目录")
    elif action == POST_PUBLISH_ACTION_DELETE:
        lines.append("发布后文件：删除原文件")
    else:
        lines.append("发布后文件：不处理")
    lines.append(
        f"完成后：{'关机' if is_publish_after_shutdown_one_shot_armed() else '不关机'}"
    )
    return "\n".join(lines)


class ListSettingsDialog(AppMessageBoxBase):
    """发布设置弹窗 — 与 AccountSelectionDialog 同级，使用 exec() 显示。"""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_saved: Optional[Callable[[], None]] = None,
        *,
        pending_policy_records: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(parent, header_title="发布设置")
        self.on_saved = on_saved
        self._pending_policy_records: List[Dict[str, Any]] = list(pending_policy_records or [])
        self._setup_ui()
        self._load_mode()
        self._load_speed()
        self._load_interval()
        self._load_retry_count()
        self._load_browser_and_shutdown()
        self._load_post_publish_action()
        self._apply_post_publish_policy_constraints()

    def _setup_ui(self):
        root = self.widget
        self.viewLayout.addSpacing(8)

        label_w = 116

        def _form_label(text: str, parent_w: QWidget) -> BodyLabel:
            lb = BodyLabel(text, parent_w)
            lb.setMinimumWidth(label_w)
            lb.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            return lb

        def _radio_row_with_hint(
            parent_w: QWidget, radio: RadioButton, tip: str
        ) -> QWidget:
            wrap = QWidget(parent_w)
            h = QHBoxLayout(wrap)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            h.addWidget(radio, 0, Qt.AlignmentFlag.AlignVCenter)
            h.addStretch(1)
            apply_instructional_tooltip(tip, radio)
            return wrap

        # ---------- 上排：左「列表与排序」+ 右「调度」 ----------
        row_top = QWidget(root)
        h_top = QHBoxLayout(row_top)
        h_top.setContentsMargins(0, 0, 0, 0)
        h_top.setSpacing(12)

        card_list = CardWidget(row_top)
        card_list.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        lay_l = QVBoxLayout(card_list)
        lay_l.setContentsMargins(14, 12, 14, 12)
        lay_l.setSpacing(8)
        lay_l.addWidget(SubtitleLabel("列表与排序", card_list))

        self.radio_order = RadioButton("顺序显示", card_list)
        self.radio_platform = RadioButton("按平台分组", card_list)
        self.radio_account = RadioButton("按账号分组", card_list)
        self._mode_group = QButtonGroup(self)
        self._mode_group.addButton(self.radio_order)
        self._mode_group.addButton(self.radio_platform)
        self._mode_group.addButton(self.radio_account)
        lay_l.addWidget(
            _radio_row_with_hint(card_list, self.radio_order, "按任务添加顺序显示")
        )
        lay_l.addWidget(
            _radio_row_with_hint(card_list, self.radio_platform, "同一平台的任务排在一起")
        )
        lay_l.addWidget(
            _radio_row_with_hint(card_list, self.radio_account, "同一账号的任务排在一起")
        )

        form_fp = QFormLayout()
        form_fp.setContentsMargins(0, 6, 0, 0)
        form_fp.setHorizontalSpacing(10)
        form_fp.setVerticalSpacing(8)
        lab_first_platform = _form_label("排在第一的平台", card_list)
        self.combo_first_platform = ComboBox(card_list)
        self._fill_first_platform_combo()
        self.combo_first_platform.setMinimumWidth(160)
        _tip_first_platform = (
            "仅在「按平台分组」时生效：所选平台任务排在列表最前。"
        )
        lab_fp_row = QWidget(card_list)
        _lfp = QHBoxLayout(lab_fp_row)
        _lfp.setContentsMargins(0, 0, 0, 0)
        _lfp.setSpacing(4)
        _lfp.addWidget(lab_first_platform)
        _lfp.addStretch(1)
        apply_instructional_tooltip(
            _tip_first_platform, lab_first_platform, self.combo_first_platform
        )
        form_fp.addRow(lab_fp_row, self.combo_first_platform)
        lay_l.addLayout(form_fp)

        card_sched = CardWidget(row_top)
        card_sched.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        lay_s = QVBoxLayout(card_sched)
        lay_s.setContentsMargins(14, 12, 14, 12)
        lay_s.setSpacing(8)
        sub_sched = SubtitleLabel("调度", card_sched)
        _sched_title_row = QWidget(card_sched)
        _str = QHBoxLayout(_sched_title_row)
        _str.setContentsMargins(0, 0, 0, 0)
        _str.setSpacing(4)
        _str.addWidget(sub_sched)
        _str.addStretch(1)
        apply_instructional_tooltip(
            "发布速度与任务间隔", sub_sched
        )
        lay_s.addWidget(_sched_title_row)

        form_sched = QFormLayout()
        form_sched.setContentsMargins(0, 0, 0, 0)
        form_sched.setHorizontalSpacing(10)
        form_sched.setVerticalSpacing(10)
        lab_speed = _form_label("发布速度", card_sched)
        self.combo_speed = ComboBox(card_sched)
        for i, (text, rate) in enumerate(SPEED_OPTIONS):
            self.combo_speed.addItem(text)
            self.combo_speed.setItemData(i, rate)
        self.combo_speed.setMinimumWidth(160)
        _tip_speed = (
            "正常：推荐默认设置；"
            "快速：操作节奏加倍，等待时间缩短一半；"
            "慢速：等待时间延长一倍，更为保守，适合需要稳定发布节奏的账号。"
        )
        lab_speed_row = QWidget(card_sched)
        _lsr = QHBoxLayout(lab_speed_row)
        _lsr.setContentsMargins(0, 0, 0, 0)
        _lsr.setSpacing(4)
        _lsr.addWidget(lab_speed)
        _lsr.addStretch(1)
        apply_instructional_tooltip(
            _tip_speed, lab_speed, self.combo_speed
        )
        form_sched.addRow(lab_speed_row, self.combo_speed)

        lab_interval = _form_label("任务间隔（秒）", card_sched)
        self.edit_interval = LineEdit(card_sched)
        self.edit_interval.setText(str(DEFAULT_PUBLISH_INTERVAL_SEC))
        self.edit_interval.setMinimumWidth(120)
        self.edit_interval.setMaxLength(4)
        self.edit_interval.setPlaceholderText(
            f"{MIN_PUBLISH_INTERVAL_SEC}～{MAX_PUBLISH_INTERVAL_SEC}"
        )
        _tip_interval = (
            "仅当下一待发布任务与当前任务为同一平台时生效：实际等待为设定值±3秒随机（如 20 秒约 17～23 秒）。"
            "下一项为其他平台时不等待该间隔，仅短暂衔接，以便尽快切换平台。"
            "设为 0 表示同平台连续任务之间也不按秒数等待（仍保留极短衔接）。"
            f"可填整数秒，范围 {MIN_PUBLISH_INTERVAL_SEC}～{MAX_PUBLISH_INTERVAL_SEC}。"
        )
        lab_iv_row = QWidget(card_sched)
        _lir = QHBoxLayout(lab_iv_row)
        _lir.setContentsMargins(0, 0, 0, 0)
        _lir.setSpacing(4)
        _lir.addWidget(lab_interval)
        _lir.addStretch(1)
        apply_instructional_tooltip(
            _tip_interval, lab_interval, self.edit_interval
        )
        form_sched.addRow(lab_iv_row, self.edit_interval)
        
        lab_retry = _form_label("发布队列重试", card_sched)
        self.combo_retry = ComboBox(card_sched)
        self.combo_retry.addItems(["关闭", "1次", "2次", "3次"])
        self.combo_retry.setMinimumWidth(120)
        _tip_retry = (
            "当队列正常执行完毕后，对于发布状态仍为失败的任务将作复位处理并自动开启下一轮重试。"
        )
        lab_retry_row = QWidget(card_sched)
        _lrr = QHBoxLayout(lab_retry_row)
        _lrr.setContentsMargins(0, 0, 0, 0)
        _lrr.setSpacing(4)
        _lrr.addWidget(lab_retry)
        _lrr.addStretch(1)
        apply_instructional_tooltip(
            _tip_retry, lab_retry, self.combo_retry
        )
        form_sched.addRow(lab_retry_row, self.combo_retry)

        lay_s.addLayout(form_sched)
        lay_s.addStretch(1)

        h_top.addWidget(card_list, 1)
        h_top.addWidget(card_sched, 1)
        self.viewLayout.addWidget(row_top)

        self._first_platform_row = (lab_first_platform, self.combo_first_platform)
        self.radio_platform.toggled.connect(self._on_platform_mode_toggled)

        # ---------- 通栏：发布行为 ----------
        self.viewLayout.addSpacing(10)
        card_run = CardWidget(root)
        lay_run = QVBoxLayout(card_run)
        lay_run.setContentsMargins(14, 12, 14, 12)
        lay_run.setSpacing(8)
        lay_run.addWidget(SubtitleLabel("发布行为", card_run))
        self.check_show_browser = CheckBox("显示本机 Chrome", card_run)
        _row_br = QWidget(card_run)
        _rbr = QHBoxLayout(_row_br)
        _rbr.setContentsMargins(0, 0, 0, 0)
        _rbr.setSpacing(4)
        _rbr.addWidget(self.check_show_browser)
        _rbr.addStretch(1)
        apply_instructional_tooltip(
            "发布流程默认显示本机 Chrome，以保持更接近正常使用的浏览器环境。",
            self.check_show_browser,
        )
        lay_run.addWidget(_row_br)
        self.check_auto_shutdown = CheckBox("发布后关机（仅下一次队列有效）", card_run)
        _row_sd = QWidget(card_run)
        _rsd = QHBoxLayout(_row_sd)
        _rsd.setContentsMargins(0, 0, 0, 0)
        _rsd.setSpacing(4)
        _rsd.addWidget(self.check_auto_shutdown)
        _rsd.addStretch(1)
        apply_instructional_tooltip(
            "只生效一次，不保存到配置。仅在队列全部正常发完后弹窗，约 3 分钟后关机；"
            "弹窗里可点「取消关闭」中止。未跑完全程则本次勾选作废。",
            self.check_auto_shutdown,
        )
        lay_run.addWidget(_row_sd)
        self.check_precheck_online = CheckBox("发布前检测账号在线状态", card_run)
        _row_pc = QWidget(card_run)
        _rpc = QHBoxLayout(_row_pc)
        _rpc.setContentsMargins(0, 0, 0, 0)
        _rpc.setSpacing(4)
        _rpc.addWidget(self.check_precheck_online)
        _rpc.addStretch(1)
        apply_instructional_tooltip(
            "勾选后点击发布会先检测本轮任务所涉账号是否在线，再决定是否继续发布。",
            self.check_precheck_online,
        )
        lay_run.addWidget(_row_pc)
        self.viewLayout.addWidget(card_run)

        # ---------- 通栏：发布后文件 ----------
        self.viewLayout.addSpacing(10)
        card_post = CardWidget(root)
        lay_p = QVBoxLayout(card_post)
        lay_p.setContentsMargins(14, 12, 14, 12)
        lay_p.setSpacing(8)
        sub_post = SubtitleLabel("发布后文件处理", card_post)
        _post_title_row = QWidget(card_post)
        _ptr = QHBoxLayout(_post_title_row)
        _ptr.setContentsMargins(0, 0, 0, 0)
        _ptr.setSpacing(4)
        _ptr.addWidget(sub_post)
        _ptr.addStretch(1)
        apply_instructional_tooltip(
            "发布成功后的本地文件处理方式", sub_post
        )
        lay_p.addWidget(_post_title_row)

        self.radio_post_none = RadioButton("不处理", card_post)
        self.radio_post_move = RadioButton("移动至已发布目录（默认）", card_post)
        self.radio_post_delete = RadioButton("删除原文件", card_post)
        self._post_action_group = QButtonGroup(self)
        self._post_action_group.addButton(self.radio_post_none)
        self._post_action_group.addButton(self.radio_post_move)
        self._post_action_group.addButton(self.radio_post_delete)

        _row_none = QWidget(card_post)
        _rn = QHBoxLayout(_row_none)
        _rn.setContentsMargins(0, 0, 0, 0)
        _rn.setSpacing(4)
        _rn.addWidget(self.radio_post_none)
        _rn.addStretch(1)
        lay_p.addWidget(_row_none)

        _tip_move = (
            "需在「设置」中配置媒体库路径。"
            "规则：在对应账号或账号组的「已发布」目录下按发布日期建子文件夹并移入文件；"
            "同一账号组内多账号共用同一视频时，等该组全部成功后再移动一次。"
        )
        _row_mv = QWidget(card_post)
        _rmv = QHBoxLayout(_row_mv)
        _rmv.setContentsMargins(0, 0, 0, 0)
        _rmv.setSpacing(4)
        _rmv.addWidget(self.radio_post_move)
        _rmv.addStretch(1)
        apply_instructional_tooltip(_tip_move, self.radio_post_move)
        lay_p.addWidget(_row_mv)

        _row_del = QWidget(card_post)
        _rdl = QHBoxLayout(_row_del)
        _rdl.setContentsMargins(0, 0, 0, 0)
        _rdl.setSpacing(4)
        _rdl.addWidget(self.radio_post_delete)
        _rdl.addStretch(1)
        apply_instructional_tooltip(
            "发布成功后永久删除本地原文件，不可恢复。",
            self.radio_post_delete,
        )
        lay_p.addWidget(_row_del)

        cap_move = CaptionLabel(
            "移动：按账号/账号组「已发布」目录与日期归档；组内多账号共用素材时，待组内全部成功后再移动。",
            card_post,
        )
        cap_move.setWordWrap(True)
        lay_p.addWidget(cap_move)

        self._hint_post_publish_policy = CaptionLabel("", card_post)
        self._hint_post_publish_policy.setWordWrap(True)
        self._hint_post_publish_policy.hide()
        lay_p.addWidget(self._hint_post_publish_policy)

        self.viewLayout.addWidget(card_post)

        self.yesButton.setText("确认")
        self.cancelButton.setText("取消")
        self.widget.setMinimumWidth(680)
        self._reorder_buttons()

    def _reorder_buttons(self):
        button_layout = getattr(self, "buttonLayout", None)
        if button_layout is None:
            button_layout = self.buttonGroup.layout()
        if button_layout:
            button_layout.removeWidget(self.yesButton)
            button_layout.removeWidget(self.cancelButton)
            button_layout.addWidget(self.cancelButton)
            button_layout.addWidget(self.yesButton)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def _fill_first_platform_combo(self):
        from src.utils.platform_names import PLATFORM_ID_TO_NAME
        self.combo_first_platform.clear()
        self.combo_first_platform.addItem("不指定")
        self.combo_first_platform.setItemData(0, "")
        for i, (pid, name) in enumerate(PLATFORM_ID_TO_NAME.items(), start=1):
            self.combo_first_platform.addItem(name)
            self.combo_first_platform.setItemData(i, pid)

    def _on_platform_mode_toggled(self, checked: bool):
        for w in self._first_platform_row:
            w.setEnabled(checked)

    def _load_mode(self):
        mode = get_display_mode()
        if mode == MODE_PLATFORM:
            self.radio_platform.setChecked(True)
        elif mode == MODE_ACCOUNT:
            self.radio_account.setChecked(True)
        else:
            self.radio_order.setChecked(True)
        first = get_first_platform()
        idx = 0
        first_str = str(first) if first else ""
        for i in range(self.combo_first_platform.count()):
            data = self.combo_first_platform.itemData(i)
            data_str = str(data) if data is not None else ""
            if data_str == first_str:
                idx = i
                break
        self.combo_first_platform.setCurrentIndex(idx)
        for w in self._first_platform_row:
            w.setEnabled(self.radio_platform.isChecked())

    def _load_speed(self):
        pl = _publish_list_dict()
        idx = _coerce_int(pl.get(PUBLISH_LIST_SPEED_INDEX, 0), 0)
        idx = max(0, min(idx, len(SPEED_OPTIONS) - 1))
        self.combo_speed.setCurrentIndex(idx)

    def _load_interval(self):
        sec = get_publish_interval_seconds()
        self.edit_interval.setText(str(sec))

    def _load_retry_count(self):
        count = get_publish_queue_retry_count()
        self.combo_retry.setCurrentIndex(count)

    def _parse_interval_seconds_for_save(self) -> Optional[int]:
        """从输入框解析任务间隔；无效时返回 None（调用方提示用户）。"""
        raw = self.edit_interval.text().strip()
        if raw == "":
            InfoBar.warning(
                "提示",
                "请填写任务间隔（秒）。",
                parent=self.window() or self,
                duration=2500,
            )
            return None
        try:
            v = int(raw, 10)
        except ValueError:
            InfoBar.warning(
                "提示",
                "任务间隔须为整数（秒），例如 20。",
                parent=self.window() or self,
                duration=3000,
            )
            return None
        if v < MIN_PUBLISH_INTERVAL_SEC or v > MAX_PUBLISH_INTERVAL_SEC:
            InfoBar.warning(
                "提示",
                f"任务间隔须在 {MIN_PUBLISH_INTERVAL_SEC}～{MAX_PUBLISH_INTERVAL_SEC} 秒之间。",
                parent=self.window() or self,
                duration=3500,
            )
            return None
        return v

    def _load_browser_and_shutdown(self) -> None:
        self.check_show_browser.setChecked(get_publish_show_browser())
        if should_force_visible_publish_browser():
            self.check_show_browser.setEnabled(False)
        self.check_auto_shutdown.setChecked(is_publish_after_shutdown_one_shot_armed())
        self.check_precheck_online.setChecked(get_precheck_account_online_enabled())

    def _load_post_publish_action(self):
        action = get_post_publish_action()
        if action == POST_PUBLISH_ACTION_MOVE:
            self.radio_post_move.setChecked(True)
        elif action == POST_PUBLISH_ACTION_DELETE:
            self.radio_post_delete.setChecked(True)
        else:
            self.radio_post_none.setChecked(True)

    def _apply_post_publish_policy_constraints(self) -> None:
        """待发布列表含素材库路径时限制「不处理」；含视频库/图片库任务时仅允许「移动」。"""
        recs = self._pending_policy_records
        any_pub = pending_records_any_public_pool(recs) if recs else False
        any_ml = pending_records_any_material_library_tree(recs) if recs else False

        allow_none = not any_ml
        allow_delete = not any_pub
        tip_lines: List[str] = []
        if any_pub:
            tip_lines.append(
                "当前待发布列表中含有来自「视频库」或「图片库」的任务，发布后文件处理固定为「移动至已发布目录」。"
            )
        elif any_ml:
            tip_lines.append(
                "当前待发布列表中含有媒体库内素材，不允许选择「不处理」，请选择移动或删除。"
            )

        self.radio_post_none.setEnabled(allow_none)
        self.radio_post_delete.setEnabled(allow_delete)
        none_tip = (
            ""
            if allow_none
            else "待发布任务来自媒体库时不可选「不处理」"
        )
        del_tip = (
            ""
            if allow_delete
            else "待发布任务来自视频库/图片库时仅可移动至已发布目录"
        )
        apply_instructional_tooltip(
            none_tip, self.radio_post_none,
        )
        _del_tip_final = del_tip or "发布成功后永久删除本地原文件，不可恢复。"
        apply_instructional_tooltip(
            _del_tip_final, self.radio_post_delete,
        )

        if any_pub and self.radio_post_delete.isChecked():
            self.radio_post_move.setChecked(True)
        elif not allow_none and self.radio_post_none.isChecked():
            self.radio_post_move.setChecked(True)

        if tip_lines:
            self._hint_post_publish_policy.setText(" ".join(tip_lines))
            self._hint_post_publish_policy.show()
            # 策略限制提示：在浅色/深色下保持可读
            self._hint_post_publish_policy.setStyleSheet(
                "color: #c62828; font-weight: 600;"
            )
        else:
            self._hint_post_publish_policy.hide()
            self._hint_post_publish_policy.setStyleSheet("")

    def _current_post_publish_action(self) -> str:
        if self.radio_post_move.isChecked():
            return POST_PUBLISH_ACTION_MOVE
        if self.radio_post_delete.isChecked():
            return POST_PUBLISH_ACTION_DELETE
        return POST_PUBLISH_ACTION_NONE

    def _current_mode(self) -> str:
        if self.radio_platform.isChecked():
            return MODE_PLATFORM
        if self.radio_account.isChecked():
            return MODE_ACCOUNT
        return MODE_ORDER

    def accept(self):
        if getattr(self, "_publish_list_save_in_progress", False):
            return
        interval_sec = self._parse_interval_seconds_for_save()
        if interval_sec is None:
            return

        self._publish_list_save_in_progress = True
        self.yesButton.setEnabled(False)

        raw = self.combo_first_platform.currentData()
        first_platform = str(raw).strip() if raw else ""
        post_action = sanitize_post_publish_action_for_save(
            self._current_post_publish_action(),
            self._pending_policy_records,
        )
        pl_save = {
            PUBLISH_LIST_DISPLAY_MODE: self._current_mode(),
            PUBLISH_LIST_SPEED_INDEX: self.combo_speed.currentIndex(),
            PUBLISH_LIST_INTERVAL_SECONDS: interval_sec,
            PUBLISH_LIST_FIRST_PLATFORM: first_platform,
            PUBLISH_LIST_POST_PUBLISH_FILE_ACTION: post_action,
            PUBLISH_LIST_QUEUE_RETRY_COUNT: self.combo_retry.currentIndex(),
            PUBLISH_LIST_SHOW_BROWSER: True if should_force_visible_publish_browser() else self.check_show_browser.isChecked(),
            PUBLISH_LIST_PRECHECK_ACCOUNT_ONLINE: self.check_precheck_online.isChecked(),
        }

        async def _save() -> None:
            await merge_app_config(get_registered_config_center(), {KEY_PUBLISH_LIST: pl_save})

        def _finish() -> None:
            self._publish_list_save_in_progress = False
            self.yesButton.setEnabled(True)
            # 发布后关机仅内存一次有效，与 pl_save 一并随「确认」生效
            set_publish_after_shutdown_one_shot_armed(self.check_auto_shutdown.isChecked())
            if self.on_saved:
                self.on_saved()
            super(ListSettingsDialog, self).accept()

        from src.ui.utils.async_helper import run_async_from_ui_with_finally

        try:
            run_async_from_ui_with_finally(_save, _finish)
        except Exception:
            logger.exception("发布设置保存调度失败")
            self._publish_list_save_in_progress = False
            self.yesButton.setEnabled(True)
            _finish()
