# -*- coding: utf-8 -*-
"""
带货推广领域模块
文件路径：src/domain/publish/promotion_settings/__init__.py

子模块：
  - cart      — 购物车推广：按商品简称 + 平台查询商品库，注入 cart_info / kuaishou_goods_name
  - group_buy — 团购推广（占位）：注入 anchor_info
"""
from .cart import CartPublishFields, PLATFORM_FIELD_MAP
from .group_buy import GroupBuyPublishFields

__all__ = [
    "CartPublishFields",
    "PLATFORM_FIELD_MAP",
    "GroupBuyPublishFields",
]
