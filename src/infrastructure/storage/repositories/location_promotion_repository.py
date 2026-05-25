"""
位置推广 Repository（异步版本）
功能：封装 location_promotion_items 表的常用数据访问操作。
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from tortoise.transactions import in_transaction

from src.infrastructure.storage.orm_models.location_promotion_item import (
    LocationPromotionItem,
)
from src.infrastructure.storage.retry import retry_on_locked

logger = logging.getLogger(__name__)


class LocationPromotionRepository:
    """位置推广 Repository（异步）。"""

    @staticmethod
    async def list_all() -> List[Dict[str, Any]]:
        """获取全部位置配置，按位置简称升序。"""
        rows = await LocationPromotionItem.all().order_by("short_name")
        return [LocationPromotionRepository._to_dict(r) for r in rows]

    @staticmethod
    async def get_by_id(item_id: int) -> Optional[Dict[str, Any]]:
        """根据主键获取单条记录。"""
        item = await LocationPromotionItem.get_or_none(id=item_id)
        return LocationPromotionRepository._to_dict(item) if item else None

    @staticmethod
    async def create_or_update_by_short_name(data: Dict[str, Any]) -> Dict[str, Any]:
        """按位置简称创建或更新一条记录。"""
        short_name = (data.get("short_name") or "").strip()
        if not short_name:
            raise ValueError("位置简称不能为空")

        defaults = {
            "douyin_location": data.get("douyin_location") or "",
            "kuaishou_location": data.get("kuaishou_location") or "",
            "channels_location": data.get("channels_location") or "",
            "xiaohongshu_location": data.get("xiaohongshu_location") or "",
        }

        now = datetime.now()
        item = await LocationPromotionItem.get_or_none(short_name=short_name)
        if item:
            for k, v in defaults.items():
                setattr(item, k, v)
            item.updated_at = now
            await item.save()
        else:
            item = await LocationPromotionItem.create(
                short_name=short_name,
                created_at=now,
                **defaults,
            )

        return LocationPromotionRepository._to_dict(item)

    @staticmethod
    async def delete_by_ids(ids: List[int]) -> int:
        """批量删除指定 ID 的记录，返回删除数量。"""
        if not ids:
            return 0
        deleted = await LocationPromotionItem.filter(id__in=ids).delete()
        return deleted or 0

    @staticmethod
    @retry_on_locked()
    async def bulk_import(
        items: List[Dict[str, Any]],
        overwrite: bool = True,
    ) -> Dict[str, Any]:
        """批量导入位置配置记录。"""
        if not items:
            return {"total": 0, "success": 0, "failed": 0, "errors": []}

        total = len(items)
        success = 0
        errors: List[str] = []

        async with in_transaction("default"):
            for idx, data in enumerate(items, start=1):
                short_name = (data.get("short_name") or "").strip()
                if not short_name:
                    errors.append(f"第 {idx} 行：位置简称为空，已跳过。")
                    continue
                try:
                    if overwrite:
                        await LocationPromotionRepository.create_or_update_by_short_name(
                            data
                        )
                    else:
                        existing = await LocationPromotionItem.get_or_none(
                            short_name=short_name
                        )
                        if existing:
                            continue
                        await LocationPromotionRepository.create_or_update_by_short_name(
                            data
                        )
                    success += 1
                except Exception as e:
                    logger.warning(
                        "导入位置配置失败 (short_name=%s): %s",
                        short_name,
                        e,
                        exc_info=True,
                    )
                    errors.append(f"第 {idx} 行：导入失败，原因：{e}")

        failed = total - success
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "errors": errors,
        }

    @staticmethod
    def _to_dict(item: LocationPromotionItem) -> Dict[str, Any]:
        """将 ORM 模型转换为字典。"""
        return {
            "id": item.id,
            "short_name": item.short_name,
            "douyin_location": item.douyin_location or "",
            "kuaishou_location": item.kuaishou_location or "",
            "channels_location": item.channels_location or "",
            "xiaohongshu_location": item.xiaohongshu_location or "",
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
