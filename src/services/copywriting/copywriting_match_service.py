"""
文案自动匹配服务
文件路径：src/services/copywriting/copywriting_match_service.py
功能：统一标准文案库（精准匹配）与随机文案库（随机匹配）的获取逻辑。
"""

from typing import Optional, Dict, Any, List
import logging
import os

from src.infrastructure.storage.repositories.copywriting_repository import CopywritingRepository
from src.infrastructure.storage.repositories.random_copywriting_repository import RandomCopywritingRepository
from src.services.copywriting.helpers import (
    extract_work_id_from_filename,
    merge_title_desc_from_copywriting_item,
)

logger = logging.getLogger(__name__)


class CopywritingMatchMode:
    """文案匹配模式枚举"""
    NONE = "none"               # 不使用
    STANDARD = "standard"       # 标准库 (按作品编号匹配)
    RANDOM_ALL = "random_all"   # 随机库 (全库随机)
    RANDOM_CATEGORY = "random_category" # 随机库 (按分类随机)


class CopywritingMatchService:
    """文案自动匹配服务"""

    @staticmethod
    async def match(
        mode: str,
        file_path: Optional[str] = None,
        category_id: Optional[int] = None,
        assign_strategy: str = "round_robin",
        *,
        apply_all: bool = True,
        same_title: str = "",
        same_desc: str = "",
        use_lib_title: bool = True,
        use_lib_desc: bool = True,
    ) -> Optional[Dict[str, str]]:
        """执行单条匹配逻辑（保持原有 API 兼容性）。"""
        results = await CopywritingMatchService.batch_match(
            tasks=[{"file_path": file_path}],
            mode=mode,
            category_id=category_id,
            assign_strategy=assign_strategy,
            apply_all=apply_all,
            same_title=same_title,
            same_desc=same_desc,
            use_lib_title=use_lib_title,
            use_lib_desc=use_lib_desc,
        )
        return results[0] if results else None

    @staticmethod
    async def batch_match(
        tasks: List[Dict[str, Any]],
        mode: str,
        category_id: Optional[int] = None,
        assign_strategy: str = "round_robin",
        *,
        apply_all: bool = True,
        same_title: str = "",
        same_desc: str = "",
        use_lib_title: bool = True,
        use_lib_desc: bool = True,
    ) -> List[Optional[Dict[str, str]]]:
        """
        批量执行文案匹配逻辑，支持分配策略。
        
        Args:
            tasks: 任务列表，每个字典包含 'file_path'
            mode: 匹配模式
            category_id: 随机库分类 ID
            assign_strategy: 分配策略 (round_robin, random, average)
            
        Returns:
            与 tasks 长度一致的匹配结果列表。
        """
        if not tasks:
            return []
        
        if mode == CopywritingMatchMode.NONE:
            return [None] * len(tasks)

        if mode == CopywritingMatchMode.RANDOM_CATEGORY and category_id is None:
            logger.warning("随机分类匹配缺少 category_id，已阻断本次匹配")
            return [None] * len(tasks)

        from src.infrastructure.common.media_assign_strategy import AssignStrategy, distribute_items_to_targets
        strategy = AssignStrategy.from_str(assign_strategy)
        
        results: List[Optional[Dict[str, str]]] = [None] * len(tasks)

        # 1. 如果是标准模式：逐个匹配
        if mode == CopywritingMatchMode.STANDARD:
            for i, task in enumerate(tasks):
                fp = task.get("file_path")
                if not fp: continue
                work_id = extract_work_id_from_filename(fp) or extract_work_id_from_filename(os.path.basename(fp))
                if not work_id: continue
                
                item = await CopywritingRepository.get_by_work_id(work_id.strip())
                if item:
                    title, desc = merge_title_desc_from_copywriting_item(
                        apply_all=apply_all, same_title=same_title, same_desc=same_desc,
                        use_lib_title=use_lib_title, use_lib_desc=use_lib_desc, item=item
                    )
                    results[i] = {"title": title, "description": desc}

        # 2. 如果是随机模式：获取文案池并应用分配策略
        elif mode in (CopywritingMatchMode.RANDOM_ALL, CopywritingMatchMode.RANDOM_CATEGORY):
            cat_id = category_id if mode == CopywritingMatchMode.RANDOM_CATEGORY else None
            # 获取足够的随机文案
            items = await RandomCopywritingRepository.get_random_items(len(tasks), cat_id)
            if items:
                # 使用分配策略将文案分配给任务
                pairings = distribute_items_to_targets(items, list(range(len(tasks))), strategy)
                
                for item, task_idx in pairings:
                    title, desc = merge_title_desc_from_copywriting_item(
                        apply_all=apply_all, same_title=same_title, same_desc=same_desc,
                        use_lib_title=use_lib_title, use_lib_desc=use_lib_desc, item=item
                    )
                    results[task_idx] = {"title": title, "description": desc}
                    
        return results
