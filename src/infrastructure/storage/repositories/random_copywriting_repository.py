"""
随机文案库 Repository（异步版本）
文件路径：src/infrastructure/storage/repositories/random_copywriting_repository.py
功能：封装随机文案库分类及条目的数据访问操作。
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from tortoise.transactions import in_transaction

from src.infrastructure.storage.orm_models.random_copywriting import (
    RandomCopywritingCategory,
    RandomCopywritingItem,
)
from src.infrastructure.storage.retry import retry_on_locked

logger = logging.getLogger(__name__)


class RandomCopywritingRepository:
    """随机文案库 Repository（异步）。"""

    # ---------- 分类管理 ----------

    @staticmethod
    async def list_categories() -> List[Dict[str, Any]]:
        """获取所有分类列表。"""
        categories = await RandomCopywritingCategory.all().order_by("-created_at")
        return [
            {"id": cat.id, "name": cat.name, "created_at": cat.created_at.isoformat()}
            for cat in categories
        ]

    @staticmethod
    async def create_category(name: str) -> Dict[str, Any]:
        """创建一个新分类。"""
        name = name.strip()
        if not name:
            raise ValueError("分类名称不能为空")
        
        category = await RandomCopywritingCategory.create(name=name)
        return {"id": category.id, "name": category.name}

    @staticmethod
    async def update_category(category_id: int, name: str) -> bool:
        """更新分类名称。"""
        name = name.strip()
        if not name:
            raise ValueError("分类名称不能为空")
        updated = await RandomCopywritingCategory.filter(id=category_id).update(name=name)
        return bool(updated)

    @staticmethod
    async def delete_category(category_id: int) -> bool:
        """删除分类（级联删除关联文案）。"""
        # 显式删除分类下的条目，避免 SQLite 外键约束未开启导致产生孤儿记录
        await RandomCopywritingItem.filter(category_id=category_id).delete()
        deleted = await RandomCopywritingCategory.filter(id=category_id).delete()
        return bool(deleted)

    # ---------- 文案项管理 ----------

    @staticmethod
    async def list_items_by_category(category_id: int) -> List[Dict[str, Any]]:
        """根据分类 ID 获取文案列表。"""
        items = await RandomCopywritingItem.filter(category_id=category_id).order_by("id")
        return [RandomCopywritingRepository._to_dict(it) for it in items]

    @staticmethod
    async def create_or_update_item(category_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """在指定分类下创建或更新一条文案。"""
        work_id = (data.get("work_id") or "").strip()
        item_id = data.get("id")

        defaults = {
            "work_id": work_id,
            "short_title": data.get("short_title"),
            "description": data.get("description"),
            "topics": data.get("topics"),
            "content": data.get("content") or "",
        }

        if item_id:
            item = await RandomCopywritingItem.get_or_none(id=item_id, category_id=category_id)
            if item:
                for k, v in defaults.items():
                    setattr(item, k, v)
                await item.save()
            else:
                raise ValueError("未找到待更新的文案记录")
        else:
            item = await RandomCopywritingItem.create(
                category_id=category_id,
                **defaults
            )

        return RandomCopywritingRepository._to_dict(item)

    @staticmethod
    async def delete_items(ids: List[int]) -> int:
        """批量删除文案条目。"""
        if not ids:
            return 0
        deleted = await RandomCopywritingItem.filter(id__in=ids).delete()
        return deleted or 0

    @staticmethod
    async def clear_all() -> int:
        """清空随机文案库（分类及文案）。"""
        items_deleted = await RandomCopywritingItem.all().delete()
        cats_deleted = await RandomCopywritingCategory.all().delete()
        return (items_deleted or 0) + (cats_deleted or 0)

    @staticmethod
    @retry_on_locked()
    async def bulk_import(
        items: List[Dict[str, Any]],
        overwrite_by_work_id: bool = True,
        clear_first: bool = False,
    ) -> Dict[str, Any]:
        """批量导入随机文案库（支持多分类自动创建）。"""
        if clear_first:
            await RandomCopywritingRepository.clear_all()

        total = len(items)
        success = 0
        errors: List[str] = []

        if not items:
            return {"total": 0, "success": 0, "failed": 0, "errors": []}

        # 缓存分类名到 category_id 的映射
        cat_records = await RandomCopywritingCategory.all()
        cat_map = {c.name: c.id for c in cat_records}

        async with in_transaction("default"):
            for idx, data in enumerate(items, start=1):
                try:
                    cat_name = data.get("category") or "默认分类"
                    if cat_name not in cat_map:
                        new_cat = await RandomCopywritingCategory.create(name=cat_name)
                        cat_map[cat_name] = new_cat.id
                    
                    category_id = cat_map[cat_name]

                    work_id = (data.get("work_id") or "").strip()
                    if overwrite_by_work_id and work_id:
                        # 如果提供了 work_id 且开启了覆盖模式，尝试查找并更新
                        existing = await RandomCopywritingItem.get_or_none(
                            category_id=category_id, 
                            work_id=work_id
                        )
                        if existing:
                            data["id"] = existing.id
                    
                    await RandomCopywritingRepository.create_or_update_item(category_id, data)
                    success += 1
                except Exception as e:
                    logger.warning("导入随机文案失败: %s", e, exc_info=True)
                    errors.append(f"第 {idx} 行：导入失败，原因：{e}")

        failed = total - success
        return {
            "total": total,
            "success": success,
            "failed": failed,
            "errors": errors,
        }

    @staticmethod
    async def get_random_one(category_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """从库中随机抽取一条文案。"""
        items = await RandomCopywritingRepository.get_random_items(1, category_id)
        return items[0] if items else None

    @staticmethod
    async def get_random_items(count: int, category_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """从库中随机抽取指定数量的文案（支持批量分配）。"""
        if count <= 0:
            return []
            
        query = RandomCopywritingItem.all()
        if category_id is not None:
            query = query.filter(category_id=category_id)
        else:
            # 过滤掉由于历史原因遗留的孤儿记录
            from src.infrastructure.storage.orm_models.random_copywriting import RandomCopywritingCategory
            cat_ids = await RandomCopywritingCategory.all().values_list('id', flat=True)
            query = query.filter(category_id__in=cat_ids)
        
        total_count = await query.count()
        if total_count == 0:
            return []
        
        import random
        # 如果需求量很大，直接获取全部并在内存中随机
        if count >= total_count:
            all_items = await query.all()
            result = [RandomCopywritingRepository._to_dict(it) for it in all_items]
            random.shuffle(result)
            return result
        
        # 否则随机抽取 count 个不同的索引
        indices = random.sample(range(total_count), count)
        result = []
        for idx in indices:
            item = await query.offset(idx).first()
            if item:
                result.append(RandomCopywritingRepository._to_dict(item))
        return result

    @staticmethod
    async def count_items(category_id: Optional[int] = None) -> int:
        """获取指定分类（或全库）的随机文案总数。"""
        query = RandomCopywritingItem.all()
        if category_id is not None:
            query = query.filter(category_id=category_id)
        else:
            # 全库统计时，必须确保其分类依然存在（防止历史孤儿记录虚高了数量）
            from src.infrastructure.storage.orm_models.random_copywriting import RandomCopywritingCategory
            cat_ids = await RandomCopywritingCategory.all().values_list('id', flat=True)
            query = query.filter(category_id__in=cat_ids)
        return await query.count()

    # ---------- 兼容工具（供 UI 使用） ----------

    @staticmethod
    async def get_all_categories() -> List[str]:
        """获取所有分类的名称列表，与 CopywritingRepository 兼容。"""
        cats = await RandomCopywritingRepository.list_categories()
        return [c["name"] for c in cats]

    @staticmethod
    async def list_items(
        category: Optional[str] = None,
        paginate: bool = False,
        page: int = 1,
        page_size: int = 20
    ) -> List[Dict[str, Any]]:
        """与 CopywritingRepository 兼容的通用查询方法。"""
        from src.infrastructure.storage.orm_models.random_copywriting import RandomCopywritingCategory
        query = RandomCopywritingItem.all().order_by("id")
        
        if category and category != "全部":
            cat_obj = await RandomCopywritingCategory.get_or_none(name=category)
            if cat_obj:
                query = query.filter(category_id=cat_obj.id)
            else:
                return []
                
        if paginate:
            query = query.offset((page - 1) * page_size).limit(page_size)
            
        items = await query.all()
        return [RandomCopywritingRepository._to_dict(it) for it in items]

    # ---------- 内部工具 ----------

    @staticmethod
    def _to_dict(item: RandomCopywritingItem) -> Dict[str, Any]:
        """模型转字典。"""
        return {
            "id": item.id,
            "category_id": item.category_id,
            "work_id": item.work_id,
            "short_title": item.short_title,
            "description": item.description,
            "topics": item.topics,
            "content": item.content,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
