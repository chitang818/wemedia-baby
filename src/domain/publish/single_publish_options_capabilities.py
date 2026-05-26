# -*- coding: utf-8 -*-
"""
单条发布页「发布设置」各平台 UI 能力（与插件 metadata 消费对齐）。

能力矩阵（视频默认可选图文音乐）：
- douyin：完整添加标签、带货推广、权限、作品申明；图文额外音乐
- kuaishou：仅作品申明
- xiaohongshu：位置设置、权限、作品申明
- wechat_video：位置设置 + 默认城市定位、作品申明（原创）
- 其他平台：无可编辑项（作品申明堆叠内另有「暂不支持」提示）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

ALL_TAG_TYPES: Tuple[str, ...] = ("团购", "购物车", "小程序")


@dataclass(frozen=True)
class PublishOptionsCapabilities:
    """单条发布页发布设置卡片各行是否展示。"""

    show_add_tags: bool = False
    tag_types: Tuple[str, ...] = ()
    show_location: bool = False
    show_location_mode: bool = False
    show_wechat_empty_location: bool = False
    show_promotion: bool = False
    show_music: bool = False
    show_privacy: bool = False
    show_allow_download: bool = False
    show_work_declaration: bool = False


def capabilities_for_platform(
    platform_id: str,
    *,
    is_image_mode: bool,
) -> PublishOptionsCapabilities:
    """按平台 id 返回发布设置 UI 能力（platform_id 已规范化小写）。"""
    p = (platform_id or "").strip().lower()

    if p == "douyin":
        return PublishOptionsCapabilities(
            show_add_tags=True,
            tag_types=ALL_TAG_TYPES,
            show_location=True,
            show_location_mode=True,
            show_promotion=True,
            show_music=is_image_mode,
            show_privacy=True,
            show_allow_download=True,
            show_work_declaration=True,
        )

    if p == "kuaishou":
        return PublishOptionsCapabilities(
            show_work_declaration=True,
        )

    if p == "xiaohongshu":
        return PublishOptionsCapabilities(
            show_location=True,
            show_privacy=True,
            show_allow_download=True,
            show_work_declaration=True,
        )

    if p == "wechat_video":
        return PublishOptionsCapabilities(
            show_location=True,
            show_wechat_empty_location=True,
            show_work_declaration=True,
        )

    return PublishOptionsCapabilities()
