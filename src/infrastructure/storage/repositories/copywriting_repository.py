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
    ) -> List[Dict[str, Any]]:
        """分页获取文案列表（按作品编号升序，A0001 在前）。

        仅包含作品编号符合新格式的记录，旧格式行不出现在列表中。
        """
        if page < 1:
            page = 1
        if page_size <= 0:
            page_size = 50
        offset = (page - 1) * page_size
        query = CopywritingItem.all()
        if category:
            query = query.filter(category=category)
        all_rows = await query.order_by("work_id")
        valid = [it for it in all_rows if is_valid_copywriting_work_id(it.work_id)]
        page_slice = valid[offset : offset + page_size]
        return [CopywritingRepository._to_dict(it) for it in page_slice]

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
    @retry_on_locked()
    async def bulk_import(
        items: List[Dict[str, Any]],
        overwrite_by_work_id: bool = True,
    ) -> Dict[str, Any]:
        """批量导入文案记录。

        Args:
            items: 待导入的数据列表，每项包含 work_id / content 等字段。
            overwrite_by_work_id: 为 True 时，按 work_id 存在则覆盖，否则新增。

        Returns:
            统计信息字典：{total, success, failed, errors: [str]}
        """
        total = len(items)
        success = 0
        errors: List[str] = []

        if not items:
            return {"total": 0, "success": 0, "failed": 0, "errors": []}

        async with in_transaction("default"):
            for idx, data in enumerate(items, start=1):
                work_id = (data.get("work_id") or "").strip()
                if not work_id or not (data.get("content") or "").strip():
                    errors.append(f"第 {idx} 行：作品编号或文案内容为空，已跳过。")
                    continue
                if not is_valid_copywriting_work_id(work_id):
                    errors.append(
                        f"第 {idx} 行：作品编号「{work_id}」格式不正确（须为 1 个大写字母 + 4 位数字，共 5 字符），已跳过。"
                    )
                    continue
                try:
                    if overwrite_by_work_id:
                        await CopywritingRepository.create_or_update_by_work_id(data)
                    else:
                        # 追加模式：仅当不存在时插入
                        existing = await CopywritingItem.get_or_none(work_id=work_id)
                        if existing:
                            continue
                        await CopywritingRepository.create_or_update_by_work_id(data)
                    success += 1
                except Exception as e:
                    logger.warning(
                        "导入文案记录失败 (work_id=%s): %s", work_id, e, exc_info=True
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
    async def get_all_categories() -> List[str]:
        """获取所有存在的类别标签（去重）。"""
        rows = await CopywritingItem.all().values_list("category", flat=True)
        categories: list[str] = list(set(str(r) for r in rows if r))
        if "全部" in categories:
            categories.remove("全部")
            categories.insert(0, "全部")
        return categories

    @staticmethod
    async def count_valid_items(category: Optional[str] = None) -> int:
        """获取有效的文案总数（符合新格式作品编号）。"""
        query = CopywritingItem.all()
        if category:
            query = query.filter(category=category)
        all_wid = await query.values_list("work_id", flat=True)
        return sum(1 for wid in all_wid if wid and is_valid_copywriting_work_id(str(wid)))

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

