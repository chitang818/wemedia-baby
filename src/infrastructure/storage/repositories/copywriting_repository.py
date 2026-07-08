"""
文案库 Repository（异步版本）
文件路径：src/infrastructure/storage/repositories/copywriting_repository.py
功能：封装 copywriting_items 表的常用数据访问操作，
      包括分页查询、按作品编号创建或更新、批量导入和删除等。

作品编号仅承认新格式（1 个大写英文字母 + 4 位数字）。表中若存在旧格式数据，
列表与按编号/按 id 读取均不返回（不兼容旧格式）；需用户自行清理库或改编号后重新导入。
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from datetime import datetime
import logging

from tortoise.transactions import in_transaction

from src.infrastructure.common.copywriting_work_id import is_valid_copywriting_work_id
from src.infrastructure.storage.orm_models.copywriting_item import CopywritingItem
from src.infrastructure.storage.retry import retry_on_locked

logger = logging.getLogger(__name__)


class CopywritingRepository:
    """文案库 Repository（异步）。

    注意：为保持简单，本仓储未继承 BaseRepositoryAsync，仅围绕文案表提供专用方法。
    """

    @staticmethod
    async def list_items(
        page: int = 1,
        page_size: int = 50,
        category: Optional[str] = None,
        paginate: bool = True,
    ) -> List[Dict[str, Any]]:
        """分页获取文案列表（按作品编号升序，A0001 在前）。

        已优化为数据库层原生分页（offset/limit），极大地提升了大数据量下的加载速度。
        """
        if page < 1:
            page = 1
        if page_size <= 0:
            page_size = 50
        offset = (page - 1) * page_size
        query = CopywritingItem.all()
        if category:
            query = query.filter(category=category)
        
        # 数据库原生分页查询
        if paginate:
            page_slice = await query.order_by("work_id").offset(offset).limit(page_size)
        else:
            page_slice = await query.order_by("work_id")
        return [CopywritingRepository._to_dict(it) for it in page_slice if is_valid_copywriting_work_id(it.work_id)]

    @staticmethod
    async def get_by_id(item_id: int) -> Optional[Dict[str, Any]]:
        """根据主键获取单条文案。作品编号非新格式时不返回（与旧数据不兼容）。"""
        item = await CopywritingItem.get_or_none(id=item_id)
        if not item:
            return None
        if not is_valid_copywriting_work_id(item.work_id):
            return None
        return CopywritingRepository._to_dict(item)

    @staticmethod
    async def get_by_work_id(work_id: str) -> Optional[Dict[str, Any]]:
        """根据作品编号获取单条文案（用于导入视频时按文件名自动匹配）。

        查询参数须为新格式，否则直接视为不存在；库内旧格式编号亦无法通过本方法命中。
        """
        work_id = (work_id or "").strip()
        if not work_id:
            return None
        if not is_valid_copywriting_work_id(work_id):
            return None
        item = await CopywritingItem.get_or_none(work_id=work_id)
        return CopywritingRepository._to_dict(item) if item else None

    @staticmethod
    async def create_or_update_by_work_id(data: Dict[str, Any]) -> Dict[str, Any]:
        """按作品编号创建或更新一条文案记录。

        data 字段期望包含：
            work_id, short_title, description, topics, content
        """
        work_id = (data.get("work_id") or "").strip()
        if not work_id:
            raise ValueError("work_id 不能为空")
        if not is_valid_copywriting_work_id(work_id):
            raise ValueError(
                "作品编号须为 5 个字符：1 个大写英文字母 + 4 位数字（如 A0001），"
                f"当前为「{work_id}」。"
            )

        defaults = {
            "short_title": data.get("short_title"),
            "description": data.get("description"),
            "topics": data.get("topics"),
            "category": data.get("category") or "全部",
            "content": data.get("content") or "",
        }

        now = datetime.now()
        item = await CopywritingItem.get_or_none(work_id=work_id)
        if item:
            for k, v in defaults.items():
                setattr(item, k, v)
            item.updated_at = now
            await item.save()
        else:
            item = await CopywritingItem.create(
                work_id=work_id,
                created_at=now,
                **defaults,
            )

        return CopywritingRepository._to_dict(item)

    @staticmethod
    async def delete_items(ids: List[int]) -> int:
        """批量删除指定 ID 的文案记录，返回删除数量。"""
        if not ids:
            return 0
        deleted = await CopywritingItem.filter(id__in=ids).delete()
        return deleted or 0

    @staticmethod
    async def clear_all() -> int:
        """清空文案库，返回删除的记录数。"""
        deleted = await CopywritingItem.all().delete()
        return deleted or 0

    @staticmethod
    @retry_on_locked()
    async def bulk_import(
        items: List[Dict[str, Any]],
        overwrite_by_work_id: bool = True,
        clear_first: bool = False,
    ) -> Dict[str, Any]:
        """批量导入文案记录（高性能重构版）。

        Args:
            items: 待导入的数据列表，每项包含 work_id / content 等字段。
            overwrite_by_work_id: 为 True 时，按 work_id 存在则覆盖，否则新增。
            clear_first: 为 True 时，导入前清空现有本地库（全量镜像模式）。

        Returns:
            统计信息字典：{total, success, failed, errors: [str]}
        """
        if clear_first:
            await CopywritingRepository.clear_all()
        total = len(items)
        errors: List[str] = []

        if not items:
            return {"total": 0, "success": 0, "failed": 0, "errors": []}

        # 1. 过滤和预处理数据
        valid_items = []
        for idx, data in enumerate(items, start=1):
            work_id = (data.get("work_id") or "").strip()
            if not work_id or not (data.get("description") or "").strip():
                errors.append(f"第 {idx} 行：作品编号或作品描述为空，已跳过。")
                continue
            if not is_valid_copywriting_work_id(work_id):
                errors.append(
                    f"第 {idx} 行：作品编号「{work_id}」格式不正确（须为 1 个大写字母 + 4 位数字，共 5 字符），已跳过。"
                )
                continue
            data["work_id"] = work_id
            valid_items.append(data)

        if not valid_items:
            return {"total": total, "success": 0, "failed": total, "errors": errors}

        # 对本次导入的 valid_items 按 work_id 进行去重（保留同编号中最后一次出现的数据）
        dedup_map = {}
        for data in valid_items:
            dedup_map[data["work_id"]] = data
            
        dedup_diff = len(valid_items) - len(dedup_map)
        if dedup_diff > 0:
            total -= dedup_diff
            errors.append(f"发现本次导入中有 {dedup_diff} 条作品编号重复的数据，已自动合并保留最新项。")
            
        valid_items = list(dedup_map.values())

        # 2. 批量查出已存在的记录
        work_ids = [item["work_id"] for item in valid_items]
        
        async with in_transaction("default"):
            existing_records = await CopywritingItem.filter(work_id__in=work_ids)
            existing_map = {record.work_id: record for record in existing_records}
            
            to_create = []
            to_update = []
            now = datetime.now()
            
            for data in valid_items:
                work_id = data["work_id"]
                category = data.get("category") or "全部"
                
                if work_id in existing_map:
                    if overwrite_by_work_id:
                        record = existing_map[work_id]
                        record.short_title = data.get("short_title")
                        record.description = data.get("description")
                        record.topics = data.get("topics")
                        record.content = data.get("content") or ""
                        record.category = category
                        record.updated_at = now
                        to_update.append(record)
                else:
                    to_create.append(CopywritingItem(
                        work_id=work_id,
                        short_title=data.get("short_title"),
                        description=data.get("description"),
                        topics=data.get("topics"),
                        content=data.get("content") or "",
                        category=category,
                        created_at=now,
                        updated_at=now
                    ))
            
            # 3. 执行批量写入
            success = 0
            try:
                if to_create:
                    await CopywritingItem.bulk_create(to_create)
                if to_update:
                    await CopywritingItem.bulk_update(
                        to_update, 
                        fields=["short_title", "description", "topics", "content", "category", "updated_at"]
                    )
                success = len(to_create) + len(to_update)
            except Exception as e:
                logger.error("文案库 bulk_import 失败: %s", e, exc_info=True)
                errors.append(f"批量写入数据库时发生错误：{e}")
                
        return {"total": total, "success": success, "failed": total - success, "errors": errors}

    @staticmethod
    async def get_all_categories() -> List[str]:
        """获取所有存在的类别标签（去重并保持插入顺序）。"""
        rows = await CopywritingItem.all().order_by("id").values_list("category", flat=True)
        categories: list[str] = list(dict.fromkeys(str(r) for r in rows if r))
        if "全部" in categories:
            categories.remove("全部")
            categories.insert(0, "全部")
        return categories

    @staticmethod
    async def count_valid_items(category: Optional[str] = None) -> int:
        """获取文案总数。"""
        query = CopywritingItem.all()
        if category and category != "全部":
            query = query.filter(category=category)
        return await query.count()

    # ---------- 内部工具 ----------

    @staticmethod
    def _to_dict(item: CopywritingItem) -> Dict[str, Any]:
        """将 ORM 模型转换为字典。"""
        return {
            "id": item.id,
            "work_id": item.work_id,
            "short_title": item.short_title,
            "description": item.description,
            "topics": item.topics,
            "category": item.category,
            "content": item.content,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

