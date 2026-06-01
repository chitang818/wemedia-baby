# -*- coding: utf-8 -*-
"""更多发布设置：落库字段组装与编辑回填（从单条页迁出）。"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from src.domain.publish.location_settings import (
    LOCATION_MODE_CHECKIN,
    LOCATION_MODE_CHOICES,
    format_poi_info_storage,
    parse_location_short_name_from_storage,
    parse_poi_info_storage,
)
from src.domain.publish.work_declaration import strip_privacy_declaration_keys_for_platform

from .constants import LOCATION_MODE_TAG_KEY

if TYPE_CHECKING:
    from .more_publish_settings_card import MorePublishSettingsCard

logger = logging.getLogger(__name__)

CART_PROMOTION_TITLE_MAX_LEN = 10


@dataclass
class PublishExtensionPayload:
    poi_info: str = ""
    wechat_empty_location_open_picker: Optional[bool] = None
    micro_app_info: str = ""
    cart_info: str = ""
    anchor_info: str = ""
    privacy_settings: str = "{}"
    music_info: Optional[str] = None


def _parse_cart_info_storage(raw: str) -> Tuple[str, str]:
    s = (raw or "").strip()
    if not s:
        return "", ""
    if s.startswith("{"):
        try:
            d = json.loads(s)
            if isinstance(d, dict):
                link = d.get("cart") or d.get("link") or d.get("url") or ""
                if not isinstance(link, str):
                    link = str(link) if link is not None else ""
                st = (
                    d.get("promotion_title")
                    or d.get("short_title")
                    or d.get("goods_short_title")
                    or ""
                )
                if not isinstance(st, str):
                    st = str(st) if st is not None else ""
                st = st.strip()[:CART_PROMOTION_TITLE_MAX_LEN]
                return link.strip(), st
        except (json.JSONDecodeError, TypeError):
            pass
    return s, ""


def _format_cart_info_storage(link: str, promotion_title: str) -> str:
    link = (link or "").strip()
    promotion_title = (promotion_title or "").strip()[:CART_PROMOTION_TITLE_MAX_LEN]
    if not promotion_title:
        return link
    return json.dumps(
        {"cart": link, "promotion_title": promotion_title},
        ensure_ascii=False,
    )


def _parse_anchor_info_storage(raw: str) -> Tuple[str, str]:
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
                st = st.strip()[:CART_PROMOTION_TITLE_MAX_LEN]
                return main.strip(), st
        except (json.JSONDecodeError, TypeError):
            pass
    return s, ""


def _format_anchor_info_storage(main: str, promotion_title: str) -> str:
    main = (main or "").strip()
    promotion_title = (promotion_title or "").strip()[:CART_PROMOTION_TITLE_MAX_LEN]
    if not promotion_title:
        return main
    return json.dumps(
        {"tuan": main, "promotion_title": promotion_title},
        ensure_ascii=False,
    )


def _resolve_cart_anchor_exclusive(
    cart_info: str,
    anchor_info: str,
    *,
    promo_type_text: str,
    yellow_cart_payload: Optional[Dict[str, Any]],
) -> Tuple[str, str]:
    g = (cart_info or "").strip()
    a = (anchor_info or "").strip()
    if not g or not a:
        return cart_info or "", anchor_info or ""
    if promo_type_text == "购物车推广" and yellow_cart_payload:
        return (cart_info or "").strip(), ""
    if promo_type_text == "团购推广":
        return "", (anchor_info or "").strip()
    return (cart_info or "").strip(), ""


def _privacy_text_to_code(text: str) -> str:
    p_text = (text or "").strip()
    if "好友" in p_text:
        return "friend"
    if "私密" in p_text:
        return "private"
    if "粉丝" in p_text:
        return "fans"
    return "public"


def _privacy_code_to_combo_index(privacy: str) -> int:
    if privacy == "friend":
        return 1
    if privacy == "private":
        return 2
    return 0


def build_publish_extension_payload(
    card: "MorePublishSettingsCard",
    *,
    account_platform: str,
    preserve_micro_app_info: str = "",
) -> PublishExtensionPayload:
    """从更多发布设置卡片控件组装落库扩展字段。"""
    tv = dict(card._tag_values)
    loc_mode = (tv.get(LOCATION_MODE_TAG_KEY) or "").strip()
    if loc_mode not in LOCATION_MODE_CHOICES:
        loc_mode = ""

    loc_short = card._location_selector.get_selected_short_name() or (
        tv.get("位置", "") or ""
    ).strip()

    wx_loc_pick: Optional[bool] = None
    if loc_short:
        lm = loc_mode or LOCATION_MODE_CHECKIN
        poi_info = card._location_selector.build_poi_info_storage(lm)
        wx_loc_pick = False
    else:
        poi_info = ""
        wx_loc_pick = card._wx_empty_loc.value_for_persist(
            tag_is_location=True,
            effective_location_empty=True,
        )

    promo_type_text = card._promotion_type_combo.currentText()
    cart_info = ""
    anchor_info = ""
    yc_payload: Optional[Dict[str, Any]] = None
    if promo_type_text == "购物车推广":
        yc_payload = card._yellow_cart_selector.build_cart_info_dict()
        if yc_payload:
            cart_info = json.dumps(yc_payload, ensure_ascii=False)
    cart_info, anchor_info = _resolve_cart_anchor_exclusive(
        cart_info,
        anchor_info,
        promo_type_text=promo_type_text,
        yellow_cart_payload=yc_payload,
    )

    decl = card.collect_extension_fields().get("declaration_privacy") or {}
    privacy_code = _privacy_text_to_code(card._privacy_combo.currentText())
    full_ps: Dict[str, Any] = {
        "privacy": privacy_code,
        "allow_download": card._allow_download_check.isChecked(),
        **decl,
    }
    privacy_settings = strip_privacy_declaration_keys_for_platform(
        json.dumps(full_ps, ensure_ascii=False),
        (account_platform or "").strip(),
    )

    music_info: Optional[str] = None
    if card._is_image_mode:
        mt = card._music_type_combo.currentText()
        if mt == "随机音乐":
            music_info = json.dumps({"music_type": "random"}, ensure_ascii=False)
        elif mt == "指定音乐":
            mn = card._music_name_edit.text().strip()
            if mn:
                music_info = json.dumps(
                    {"music_type": "specific", "music_name": mn},
                    ensure_ascii=False,
                )

    return PublishExtensionPayload(
        poi_info=poi_info,
        wechat_empty_location_open_picker=wx_loc_pick,
        micro_app_info=(preserve_micro_app_info or "").strip(),
        cart_info=cart_info,
        anchor_info=anchor_info,
        privacy_settings=privacy_settings,
        music_info=music_info,
    )


def apply_from_publish_record(
    card: "MorePublishSettingsCard",
    record: dict,
    *,
    parent: Optional[QWidget] = None,
) -> None:
    """编辑回填：位置、带货、权限、音乐、申明。"""
    from qfluentwidgets import InfoBar, InfoBarPosition

    p_raw = (record.get("poi_info") or "").strip()
    loc_short = parse_location_short_name_from_storage(p_raw)
    loc_text, loc_mode = parse_poi_info_storage(p_raw)

    card._tag_values = {
        "位置": "",
        LOCATION_MODE_TAG_KEY: (
            loc_mode if loc_mode in LOCATION_MODE_CHOICES else LOCATION_MODE_CHECKIN
        ),
    }

    if loc_short:
        card._tag_values["位置"] = loc_short
        card._location_selector.apply_record(loc_short)
    elif loc_text and not loc_short:
        card._location_selector.apply_record("")
        if parent is not None:
            InfoBar.warning(
                title="位置需重新选择",
                content="该任务的位置为旧版手填数据，请先在「位置推广」中配置位置后重新选择。",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                duration=6000,
                position=InfoBarPosition.TOP,
                parent=parent,
            )
    else:
        card._location_selector.apply_record("")

    raw_wx = record.get("wechat_empty_location_open_picker")
    card._wx_empty_loc.apply_from_db(None if raw_wx is None else bool(raw_wx))

    card._sync_location_mode_from_tag_values()

    g_raw = (record.get("cart_info") or "").strip()
    yc_short = ""
    if g_raw.startswith("{"):
        try:
            d = json.loads(g_raw)
            if isinstance(d, dict):
                yc_short = (
                    d.get("cart_short_name") or d.get("yellow_cart_short_name") or ""
                ).strip()
        except Exception:
            pass
    if yc_short:
        card._promotion_type_combo.blockSignals(True)
        card._promotion_type_combo.setCurrentText("购物车推广")
        card._promotion_type_combo.blockSignals(False)
        card._yellow_cart_selector.apply_record(yc_short)
        card._sync_promotion_subcontrols("购物车推广")
    else:
        card._promotion_type_combo.blockSignals(True)
        card._promotion_type_combo.setCurrentIndex(0)
        card._promotion_type_combo.blockSignals(False)
        card._yellow_cart_selector.apply_record("")
        card._sync_promotion_subcontrols("无")

    privacy_settings_str = record.get("privacy_settings", "{}")
    if privacy_settings_str:
        try:
            ps = json.loads(privacy_settings_str)
            if isinstance(ps, dict):
                card._privacy_combo.blockSignals(True)
                card._privacy_combo.setCurrentIndex(
                    _privacy_code_to_combo_index(ps.get("privacy", "public"))
                )
                card._privacy_combo.blockSignals(False)
                card._allow_download_check.blockSignals(True)
                card._allow_download_check.setChecked(bool(ps.get("allow_download", True)))
                card._allow_download_check.blockSignals(False)
                card.apply_declaration_from_privacy_dict(ps)
        except Exception as e:
            logger.error("解析 privacy_settings 失败: %s", e)

    if card._is_image_mode:
        music_raw = (record.get("music_info") or "").strip()
        if music_raw:
            try:
                md = json.loads(music_raw)
                mt = (md.get("music_type") or "").strip()
                mn = (md.get("music_name") or "").strip()
                card._music_type_combo.blockSignals(True)
                if mt == "random":
                    card._music_type_combo.setCurrentText("随机音乐")
                    card._music_name_edit.hide()
                elif mt == "specific":
                    card._music_type_combo.setCurrentText("指定音乐")
                    card._music_name_edit.setText(mn)
                    card._music_name_edit.setVisible(bool(mn))
                else:
                    card._music_type_combo.setCurrentIndex(0)
                    card._music_name_edit.hide()
                card._music_type_combo.blockSignals(False)
            except Exception:
                pass
        else:
            card._music_type_combo.blockSignals(True)
            card._music_type_combo.setCurrentText("随机音乐")
            card._music_type_combo.blockSignals(False)
            card._music_name_edit.hide()

    card._apply_douyin_location_promotion_mutex()


def reset_music_controls_to_default(card: "MorePublishSettingsCard") -> None:
    if not card._is_image_mode:
        return
    card._music_type_combo.blockSignals(True)
    card._music_type_combo.setCurrentText("随机音乐")
    card._music_type_combo.blockSignals(False)
    card._music_name_edit.clear()
    card._music_name_edit.hide()
