"""
购物车推广 Repository（异步版本）
文件路径：src/infrastructure/storage/repositories/cart_promotion_repository.py
功能：封装 cart_promotion_items 表的常用数据访问操作，
      包括全量查询、按商品简称创建或更新、批量导入和删除等。
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from tortoise.transactions import in_transaction

from src.domain.publish.promotion_limits import CART_SHORT_TITLE_MAX_LEN
from src.infrastructure.storage.orm_models.cart_promotion_item import CartPromotionItem
from src.infrastructure.storage.retry import retry_on_locked

logger = logging.getLogger(__name__)


class CartPromotionRepository:
    """购物车推广 Repository（异步）。"""

    @staticmethod
    async def list_all() -> List[Dict[str, Any]]:
        """获取全部商品配置，按商品简称升序。"""
        rows = await CartPromotionItem.all().order_by("short_name")
        return [CartPromotionRepository._to_dict(r) for r in rows]

    @staticmethod
    async def get_by_id(item_id: int) -> Optional[Dict[str, Any]]:
        """根据主键获取单条记录。"""
        item = await CartPromotionItem.get_or_none(id=item_id)
        return CartPromotionRepository._to_dict(item) if item else None

    @staticmethod
    async def create_or_update_by_short_name(data: Dict[str, Any]) -> Dict[str, Any]:
        """按商品简称创建或更新一条记录。

        data 字段期望包含：
            short_name, short_title, douyin_link, kuaishou_product_name,
            channels_id_or_link, xiaohongshu_link
        """
        short_name = (data.get("short_name") or "").strip()
        if not short_name:
            raise ValueError("商品简称不能为空")

        # 未带 short_title 键时（如旧版 Excel）更新已有行不覆盖库内短标题
        defaults = {
            "douyin_link": data.get("douyin_link") or "",
            "kuaishou_product_name": data.get("kuaishou_product_name") or "",
            "channels_id_or_link": data.get("channels_id_or_link") or "",
            "xiaohongshu_link": data.get("xiaohongshu_link") or "",
        }
        if "short_title" in data:
            defaults["short_title"] = (data.get("short_title") or "").strip()[
                :CART_SHORT_TITLE_MAX_LEN
            ]

        now = datetime.now()
        item = await CartPromotionItem.get_or_none(short_name=short_name)
        if item:
            for k, v in defaults.items():
                setattr(item, k, v)
            item.updated_at = now
            await item.save()
        else:
            create_kw = dict(defaults)
            if "short_title" not in create_kw:
                create_kw["short_title"] = ""
            item = await CartPromotionItem.create(
                short_name=short_name,
                created_at=now,
                **create_kw,
            )

        return CartPromotionRepository._to_dict(item)

    @staticmethod
    async def delete_by_ids(ids: List[int]) -> int:
        """批量删除指定 ID 的记录，返回删除数量。"""
        if not ids:
            return 0
        deleted = await CartPromotionItem.filter(id__in=ids).delete()
        return deleted or 0

    @staticmethod
    @retry_on_locked()
    async def bulk_import(
        items: List[Dict[str, Any]],
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        """批量导入商品配置记录。

        Args:
            items: 待导入数据列表，每项须含 short_name 字段。
            overwrite: 为 True 时按 short_name 存在则覆盖，否则仅插入不存在的行。

        Returns:
            统计信息字典：{total, success, failed, errors: [str]}
        """
        if not items:
            return {"total": 0, "success": 0, "failed": 0, "errors": []}

        total = len(items)
        success = 0
        errors: List[str] = []

        async with in_transaction("default"):
            for idx, data in enumerate(items, start=1):
                short_name = (data.get("short_name") or "").strip()
                if not short_name:
                    errors.append(f"第 {idx} 行：商品简称为空，已跳过。")
                    continue
                try:
                    if overwrite:
                        await CartPromotionRepository.create_or_update_by_short_name(data)
                    else:
                        existing = await CartPromotionItem.get_or_none(short_name=short_name)
                        if existing:
                            continue
                        await CartPromotionRepository.create_or_update_by_short_name(data)
                    success += 1
                except Exception as e:
                    logger.warning(
                        "导入购物车商品失败 (short_name=%s): %s", short_name, e, exc_info=True
                    )
                    errors.append(f"第 {idx} 行：导入失败，原因：{e}")

        failed = total - success
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "errors": errors,
        }

    # ---------- 内部工具 ----------

    @staticmethod
    def _to_dict(item: CartPromotionItem) -> Dict[str, Any]:
        """将 ORM 模型转换为字典。"""
        return {
            "id": item.id,
            "short_name": item.short_name,
            "short_title": item.short_title or "",
            "douyin_link": item.douyin_link or "",
            "kuaishou_product_name": item.kuaishou_product_name or "",
            "channels_id_or_link": item.channels_id_or_link or "",
            "xiaohongshu_link": item.xiaohongshu_link or "",
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
