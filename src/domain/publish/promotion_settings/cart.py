# -*- coding: utf-8 -*-
"""
购物车推广领域模型
文件路径：src/domain/publish/promotion_settings/cart.py

职责：
  - 定义各平台商品字段的映射关系。
  - 提供 CartPublishFields dataclass：按商品简称 + 平台查询商品库，
    返回该平台对应的值（链接或商品名称），并注入到发布管道 metadata。
  - 纯领域逻辑，不依赖 Qt。

平台映射规则：
  - douyin       → douyin_link（链接）→ metadata["cart_info"]
  - kuaishou     → kuaishou_product_name（商品名称）→ metadata["kuaishou_goods_name"]
  - wechat_video → channels_id_or_link（ID或链接）→ metadata["cart_info"]
  - xiaohongshu  → xiaohongshu_link（链接）→ metadata["cart_info"]
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.domain.publish.promotion_limits import CART_SHORT_TITLE_MAX_LEN

logger = logging.getLogger(__name__)

# 平台 ID → CartPromotionItem 字段名
PLATFORM_FIELD_MAP: Dict[str, str] = {
    "douyin": "douyin_link",
    "kuaishou": "kuaishou_product_name",
    "wechat_video": "channels_id_or_link",
    "xiaohongshu": "xiaohongshu_link",
}

# 使用商品名称搜索的平台（而非链接）
_NAME_BASED_PLATFORMS = {"kuaishou"}


@dataclass
class CartPublishFields:
    """购物车推广发布字段。

    Attributes:
        short_name:     商品简称（选中的商品，对应 CartPromotionItem.short_name）
        platform_value: 按平台取到的具体值（链接字符串或商品名称）
        is_name_based:  True=用商品名称搜索（如快手）；False=用链接
        short_title:    商品短标题（对应 CartPromotionItem.short_title，发布时填入弹窗）
    """

    short_name: str = ""
    platform_value: str = ""
    is_name_based: bool = False
    short_title: str = ""

    @staticmethod
    async def from_short_name_and_platform(
        short_name: str, platform: str
    ) -> "CartPublishFields":
        """从购物车商品库按简称查询，按平台取对应字段。

        Args:
            short_name: 商品简称（对应 CartPromotionItem.short_name）
            platform:   平台 ID（如 "douyin"、"kuaishou"）

        Returns:
            CartPublishFields；若未查到商品则 platform_value 为空字符串。
        """
        short_name = (short_name or "").strip()
        platform = (platform or "").strip()
        if not short_name:
            return CartPublishFields()

        try:
            from src.infrastructure.storage.repositories.cart_promotion_repository import (
                CartPromotionRepository,
            )

            rows = await CartPromotionRepository.list_all()
            matched = next((r for r in rows if r.get("short_name") == short_name), None)
            if matched is None:
                logger.warning("购物车商品库未找到简称：%s", short_name)
                return CartPublishFields(short_name=short_name)

            db_field = PLATFORM_FIELD_MAP.get(platform, "")
            platform_value = (matched.get(db_field) or "").strip() if db_field else ""
            is_name_based = platform in _NAME_BASED_PLATFORMS

            if not platform_value:
                logger.info(
                    "购物车商品「%s」在平台「%s」无对应值（字段=%s）",
                    short_name,
                    platform,
                    db_field,
                )

            short_title = (matched.get("short_title") or "").strip()

            return CartPublishFields(
                short_name=short_name,
                platform_value=platform_value,
                is_name_based=is_name_based,
                short_title=short_title,
            )
        except Exception as e:
            logger.error("查询购物车商品失败（short_name=%s）: %s", short_name, e, exc_info=True)
            return CartPublishFields(short_name=short_name)

    @classmethod
    def from_platform_value(cls, platform_value: str, platform: str) -> "CartPublishFields":
        """直接从已知 platform_value 构建（供 publish_executor 写入 cart_info 使用）。"""
        return cls(
            short_name="",
            platform_value=(platform_value or "").strip(),
            is_name_based=(platform or "") in _NAME_BASED_PLATFORMS,
        )

    def apply_to_plugin_metadata(self, metadata: Dict[str, Any]) -> None:
        """将商品信息写入发布管道的 metadata。

        - 链接类平台（抖音、视频号、小红书）→ metadata["cart_info"]（含 short_title 时序列化为 JSON）
        - 名称类平台（快手）→ metadata["kuaishou_goods_name"]
        """
        val = (self.platform_value or "").strip()
        if not val:
            return
        if self.is_name_based:
            metadata["kuaishou_goods_name"] = val
        else:
            st = (self.short_title or "").strip()
            if st:
                # 步骤6 _parse_goods_storage 识别 cart/short_title 键
                metadata["cart_info"] = json.dumps(
                    {"cart": val, "short_title": st}, ensure_ascii=False
                )
            else:
                metadata["cart_info"] = val

    def is_empty(self) -> bool:
        """是否无有效商品信息。"""
        return not (self.platform_value or "").strip()


def cart_preview_display(cart_info_raw: Optional[str]) -> str:
    """从 ``cart_info`` 解析购物车侧展示文案（商品短标题优先，无则简称）。

    用于界面「已选商品」摘要等，**不是**发布任务里的「作品简介」字段；
    作品简介与 ``cart_short_title`` 相互独立。

    仅当 JSON 内含 ``cart_short_name`` 时视为购物车推广记录。其它格式返回空串，
    由调用方按原逻辑显示（如 ✅ 或手填链接）。
    兼容旧键 ``yellow_cart_short_name`` / ``yellow_cart_short_title``。"""
    s = (cart_info_raw or "").strip()
    if not s.startswith("{"):
        return ""
    try:
        d = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(d, dict):
        return ""
    # 新键优先，兼容旧键
    sn = (d.get("cart_short_name") or d.get("yellow_cart_short_name") or "").strip()
    if not sn:
        return ""
    st = (d.get("cart_short_title") or d.get("yellow_cart_short_title") or "").strip()[
        :CART_SHORT_TITLE_MAX_LEN
    ]
    return st if st else sn
