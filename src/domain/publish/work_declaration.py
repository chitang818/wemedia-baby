# -*- coding: utf-8 -*-
"""
多平台作品申明：枚举、privacy_settings 键名、列表/预览展示与写库前按平台裁剪。

存储字段（扁平，写入 publish_record.privacy_settings JSON）：
- is_original: bool，仅视频号发布自动化使用
- douyin_work_declaration: str 枚举
- kuaishou_work_declaration: str 枚举
- douyin_work_declaration_auto: bool，为 True 时发布自动化尝试设置抖音申明（缺省视为关闭）
- kuaishou_work_declaration_auto: bool，为 True 时发布自动化尝试设置快手申明（缺省视为关闭）
- xiaohongshu_is_original: bool，小红书「原创声明」（与视频号 is_original 独立）
- xiaohongshu_content_attribute: str 枚举；历史空值在读入时规范化为默认项（虚构演绎）
- xiaohongshu_content_attribute_auto: bool，为 True 时尝试自动设置下方内容属性下拉（缺省视为关闭）
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

# JSON 键名（与任务 dict 中 privacy_settings 一致）
KEY_IS_ORIGINAL = "is_original"
KEY_DOUYIN = "douyin_work_declaration"
KEY_KUAISHOU = "kuaishou_work_declaration"
KEY_DOUYIN_AUTO = "douyin_work_declaration_auto"
KEY_KUAISHOU_AUTO = "kuaishou_work_declaration_auto"
KEY_XHS_ORIGINAL = "xiaohongshu_is_original"
KEY_XHS_CONTENT_ATTR = "xiaohongshu_content_attribute"
KEY_XHS_CONTENT_ATTR_AUTO = "xiaohongshu_content_attribute_auto"

# 抖音
DOUYIN_NONE = "none"
DOUYIN_AI_GENERATED = "ai_generated"
DOUYIN_OPINION = "opinion"
DOUYIN_REPOST = "repost"
DOUYIN_MARKETING = "marketing"
DOUYIN_FICTION = "fiction"

DOUYIN_CHOICES: Tuple[Tuple[str, str], ...] = (
    (DOUYIN_AI_GENERATED, "内容由AI生成"),
    (DOUYIN_OPINION, "内容为个人观点或见解"),
    (DOUYIN_REPOST, "内容为转载信息"),
    (DOUYIN_MARKETING, "内容含营销推广信息"),
    (DOUYIN_FICTION, "虚构演绎，仅供娱乐"),
    (DOUYIN_NONE, "无需添加自主声明"),
)

# 若抖音前台选项文案与 DOUYIN_CHOICES 不完全一致，可为枚举补充「等价展示文案」，
# 发布自动化点击下拉项时将按顺序尝试（仍需与页面完全一致才能命中）。
# 任务配置、批量 UI 仍以 DOUYIN_CHOICES 为准；此处仅服务运行时点击。
DOUYIN_UI_CLICK_ALTERNATES: Dict[str, Tuple[str, ...]] = {
    # 报告/DOM：radio 可访问名称常见为「内容由 AI 生成」（含空格），与配置枚举文案略有差异
    DOUYIN_AI_GENERATED: ("内容由 AI 生成",),
    # 个别版本/文案写作「申明」而非「声明」
    DOUYIN_NONE: ("无需添加自主申明",),
}


def douyin_declaration_trigger_label_hints() -> Tuple[str, ...]:
    """发布页识别自主声明入口按钮：各枚举已选态展示文案（与占位符并列用于匹配入口 button）。"""
    return tuple(dict.fromkeys(v for _, v in DOUYIN_CHOICES))

# 快手（界面文案以产品为准；部分为历史需求字面）
KUAISHOU_AI = "ai_generated"
KUAISHOU_FICTION = "fiction_disclaimer"
KUAISHOU_PERSONAL = "personal_opinion"
KUAISHOU_MATERIAL = "material_from_web"

KUAISHOU_CHOICES: Tuple[Tuple[str, str], ...] = (
    (KUAISHOU_AI, "内容为AI生成"),
    (KUAISHOU_FICTION, "演绎清洁仅供参考"),
    (KUAISHOU_PERSONAL, "个人观点经供参考"),
    (KUAISHOU_MATERIAL, "素材来源于网络"),
)

_DOUYIN_LABEL = {k: v for k, v in DOUYIN_CHOICES}
_KS_LABEL = {k: v for k, v in KUAISHOU_CHOICES}

# 小红书 — 内容属性（与「原创声明」开关无关）
XHS_ATTR_FICTION = "fiction_entertainment"
XHS_ATTR_AI = "ai_synthesis"
XHS_ATTR_MARKETING = "marketing"
XHS_ATTR_SOURCE = "content_source"

# UI 与自动化默认值（不再提供「不选择」项；空/无效存储读入时落在此项）
DEFAULT_XHS_CONTENT_ATTR = XHS_ATTR_FICTION

XHS_CONTENT_ATTR_CHOICES: Tuple[Tuple[str, str], ...] = (
    (XHS_ATTR_FICTION, "虚构演绎，仅供娱乐"),
    (XHS_ATTR_AI, "笔记含AI合成内容"),
    (XHS_ATTR_MARKETING, "内容包含营销广告"),
    (XHS_ATTR_SOURCE, "内容来源声明"),
)
_XHS_ATTR_LABEL = {k: v for k, v in XHS_CONTENT_ATTR_CHOICES}

# 配置持久化用默认值
DEFAULT_DOUYIN_VALUE = DOUYIN_NONE
DEFAULT_KUAISHOU_VALUE = KUAISHOU_MATERIAL


def _parse_privacy_dict(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            d = json.loads(raw)
            return dict(d) if isinstance(d, dict) else {}
        except Exception:
            return {}
    return {}


def parse_privacy_settings_dict(privacy_settings: Any) -> Dict[str, Any]:
    """将任务中的 privacy_settings 转为 dict（解析失败返回空 dict）。"""
    return _parse_privacy_dict(privacy_settings)


def label_for_douyin_value(value: Optional[str]) -> str:
    if not value or value not in _DOUYIN_LABEL:
        return _DOUYIN_LABEL.get(DEFAULT_DOUYIN_VALUE, "")
    return _DOUYIN_LABEL[value]


def douyin_declaration_click_texts(value: Optional[str]) -> Tuple[str, ...]:
    """抖音自主声明下拉：点击选项时依次尝试的文案（canonical + DOUYIN_UI_CLICK_ALTERNATES）。"""
    key = normalize_douyin_value(value)
    primary = label_for_douyin_value(value)
    if not primary:
        return ()
    extras = DOUYIN_UI_CLICK_ALTERNATES.get(key, ())
    ordered: List[str] = []
    seen = set()
    for t in (primary,) + tuple(extras):
        if t and t not in seen:
            seen.add(t)
            ordered.append(t)
    return tuple(ordered)


def label_for_kuaishou_value(value: Optional[str]) -> str:
    if not value or value not in _KS_LABEL:
        return _KS_LABEL.get(DEFAULT_KUAISHOU_VALUE, "")
    return _KS_LABEL[value]


def normalize_douyin_value(value: Optional[str]) -> str:
    if value and value in _DOUYIN_LABEL:
        return value
    return DEFAULT_DOUYIN_VALUE


def normalize_kuaishou_value(value: Optional[str]) -> str:
    if value and value in _KS_LABEL:
        return value
    return DEFAULT_KUAISHOU_VALUE


def normalize_xhs_content_attr(value: Optional[str]) -> str:
    """将存储值规范为合法枚举；空或未知值使用 DEFAULT_XHS_CONTENT_ATTR。"""
    if value and str(value) in _XHS_ATTR_LABEL:
        return str(value)
    return DEFAULT_XHS_CONTENT_ATTR


def label_for_xhs_content_attr(value: Optional[str]) -> str:
    v = normalize_xhs_content_attr(value)
    return _XHS_ATTR_LABEL.get(v, "")


def format_xiaohongshu_work_declaration_display(
    ps: Dict[str, Any],
    *,
    empty_display: str = "—",
) -> str:
    """小红书：原创声明文案 + 可选的内容属性（分号连接）。

    关闭「发布时自动设置内容属性」时，列表「作品申明」列与抖音/快手一致，不展示已保存选项（占位符）。
    """
    if not declaration_auto_apply(ps, KEY_XHS_CONTENT_ATTR_AUTO):
        return empty_display
    orig_part = "申明原创" if bool(ps.get(KEY_XHS_ORIGINAL, False)) else "不申明原创"
    attr = normalize_xhs_content_attr(str(ps.get(KEY_XHS_CONTENT_ATTR) or "") or None)
    al = label_for_xhs_content_attr(attr)
    return f"{orig_part}；{al}" if al else orig_part


def declaration_auto_apply(
    privacy_settings: Any,
    auto_key: str,
    *,
    default: bool = False,
) -> bool:
    """是否由发布自动化操作该平台作品申明（privacy_settings 可为 dict 或 JSON 字符串）。

    当 auto_key 在配置中不存在时，返回 default（应用默认配置为 False，即不自动操作）。
    """
    ps = parse_privacy_settings_dict(privacy_settings)
    v = ps.get(auto_key)
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("1", "true", "yes", "on"):
            return True
        if t in ("0", "false", "no", "off", ""):
            return False
    return bool(v)


def format_work_declaration_table_cell(
    platform: str,
    privacy_settings: Any,
    *,
    empty_display: str = "—",
) -> str:
    """待发布/已发布/回收站等表格「作品申明」列主文案（完整短句，用于展示与 Tooltip）。"""
    ps = parse_privacy_settings_dict(privacy_settings)
    p = (platform or "").strip()
    if p == "wechat_video":
        if bool(ps.get(KEY_IS_ORIGINAL, False)):
            return "申明原创"
        return empty_display
    if p == "douyin":
        if not declaration_auto_apply(ps, KEY_DOUYIN_AUTO):
            return empty_display
        return label_for_douyin_value(str(ps.get(KEY_DOUYIN) or "") or None)
    if p == "kuaishou":
        if not declaration_auto_apply(ps, KEY_KUAISHOU_AUTO):
            return empty_display
        return label_for_kuaishou_value(str(ps.get(KEY_KUAISHOU) or "") or None)
    if p == "xiaohongshu":
        return format_xiaohongshu_work_declaration_display(ps, empty_display=empty_display)
    return empty_display


def format_work_declaration_preview_cell(
    task_platform: str,
    privacy_dict: Dict[str, Any],
    *,
    account_group_includes_wechat: bool = False,
    account_group_includes_douyin: bool = False,
    account_group_includes_kuaishou: bool = False,
    account_group_includes_xiaohongshu: bool = False,
    empty_display: str = "—",
) -> str:
    """批量预览表：按任务行平台展示；账号组占位时仅当组内可能包含该平台时显示有效文案。"""
    p = (task_platform or "").strip()
    ps = privacy_dict or {}
    if p == "account_group":
        parts = []
        if account_group_includes_wechat and bool(ps.get(KEY_IS_ORIGINAL)):
            parts.append("视频号:申明原创")
        if account_group_includes_douyin:
            if declaration_auto_apply(ps, KEY_DOUYIN_AUTO):
                parts.append(
                    "抖音:"
                    + label_for_douyin_value(str(ps.get(KEY_DOUYIN) or "") or None)
                )
        if account_group_includes_kuaishou:
            if declaration_auto_apply(ps, KEY_KUAISHOU_AUTO):
                parts.append(
                    "快手:"
                    + label_for_kuaishou_value(str(ps.get(KEY_KUAISHOU) or "") or None)
                )
        if account_group_includes_xiaohongshu:
            xhs_t = format_xiaohongshu_work_declaration_display(
                ps, empty_display=empty_display,
            )
            if xhs_t != empty_display:
                parts.append("小红书:" + xhs_t)
        return "；".join(parts) if parts else empty_display
    return format_work_declaration_table_cell(p, ps, empty_display=empty_display)


def ellipsize(text: str, max_chars: int = 10) -> str:
    """表格单元格过长的省略显示（全文在 Tooltip）。"""
    t = (text or "").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def strip_privacy_declaration_keys_for_platform(
    privacy_settings_json: str,
    platform: str,
) -> str:
    """按任务平台裁剪申明相关字段，仅保留本平台需要的键 + 通用 privacy/allow_download。"""
    ps = _parse_privacy_dict(privacy_settings_json)
    plat = (platform or "").strip()

    if plat != "wechat_video" and KEY_IS_ORIGINAL in ps:
        ps.pop(KEY_IS_ORIGINAL, None)

    if plat != "douyin" and KEY_DOUYIN in ps:
        ps.pop(KEY_DOUYIN, None)

    if plat != "kuaishou" and KEY_KUAISHOU in ps:
        ps.pop(KEY_KUAISHOU, None)

    if plat != "douyin" and KEY_DOUYIN_AUTO in ps:
        ps.pop(KEY_DOUYIN_AUTO, None)

    if plat != "kuaishou" and KEY_KUAISHOU_AUTO in ps:
        ps.pop(KEY_KUAISHOU_AUTO, None)

    if plat != "xiaohongshu":
        ps.pop(KEY_XHS_ORIGINAL, None)
        ps.pop(KEY_XHS_CONTENT_ATTR, None)
        ps.pop(KEY_XHS_CONTENT_ATTR_AUTO, None)

    # 非视频号也曾写入 is_original=false，清理后不强制写回 false
    try:
        return json.dumps(ps, ensure_ascii=False)
    except Exception:
        return "{}"


def strip_tasks_privacy_declaration_by_platform(tasks: list) -> None:
    """就地处理任务列表：每条任务的 privacy_settings 按 platform 裁剪申明字段。"""
    for task in tasks:
        raw = task.get("privacy_settings")
        if raw is None:
            continue
        plat = str(task.get("platform") or "")
        if isinstance(raw, dict):
            raw = json.dumps(raw, ensure_ascii=False)
        if not isinstance(raw, str):
            continue
        task["privacy_settings"] = strip_privacy_declaration_keys_for_platform(raw, plat)


# 兼容旧函数名（批量构建仍调用）
def strip_non_wechat_original_declaration(tasks: list) -> None:
    """向后兼容入口：现为按平台裁剪全部申明字段。"""
    strip_tasks_privacy_declaration_by_platform(tasks)
