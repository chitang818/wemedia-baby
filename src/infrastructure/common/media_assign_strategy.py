"""
媒体文件分配算法模块

提供三种策略将文件列表分配到多个账号/账号组目标：
- 轮流分配（ROUND_ROBIN）：默认，files[i] → targets[i % len(targets)]
- 随机分配（RANDOM）：对目标列表随机打乱后再轮流分配
- 平均分配（AVERAGE）：尽量均分，相邻账号间文件数差值 ≤ 1

供视频库页面（文件移动）和批量视频页面（任务配对）共用。
两个场景使用独立的配置键，互不干扰；持久化在 app_config.batch_publish.media_assign。
"""

from __future__ import annotations

import logging
import random as _random
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, TypeVar

from src.infrastructure.common.config.config_center import get_registered_config_center
from src.infrastructure.common.config.app_config_keys import (
    KEY_BATCH_PUBLISH,
    BATCH_MEDIA_ASSIGN,
    MEDIA_ASSIGN_STRATEGY_LIBRARY,
    MEDIA_ASSIGN_STRATEGY_BATCH,
)
from src.infrastructure.common.config.app_config_merge import read_app_config_from_disk_sync

logger = logging.getLogger(__name__)

T = TypeVar("T")

StrategyScope = Literal["library", "batch"]


class AssignStrategy(Enum):
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    AVERAGE = "average"

    @classmethod
    def from_str(cls, value: str) -> "AssignStrategy":
        for member in cls:
            if member.value == value:
                return member
        return cls.ROUND_ROBIN

    def display_name(self) -> str:
        return {
            AssignStrategy.ROUND_ROBIN: "轮流分配（默认）",
            AssignStrategy.RANDOM: "随机分配",
            AssignStrategy.AVERAGE: "平均分配",
        }[self]


STRATEGY_DISPLAY_NAMES = [s.display_name() for s in AssignStrategy]


def strategy_from_display_name(name: str) -> AssignStrategy:
    for s in AssignStrategy:
        if s.display_name() == name:
            return s
    return AssignStrategy.ROUND_ROBIN


def _key_for_scope(scope: StrategyScope) -> str:
    return MEDIA_ASSIGN_STRATEGY_BATCH if scope == "batch" else MEDIA_ASSIGN_STRATEGY_LIBRARY


def _media_assign_dict() -> Dict[str, Any]:
    cc = get_registered_config_center()
    if cc is not None:
        bp = cc.get_app_config().get(KEY_BATCH_PUBLISH)
        if isinstance(bp, dict):
            ma = bp.get(BATCH_MEDIA_ASSIGN)
            if isinstance(ma, dict):
                return ma
        return {}
    root = read_app_config_from_disk_sync()
    bp = root.get(KEY_BATCH_PUBLISH)
    if not isinstance(bp, dict):
        return {}
    ma = bp.get(BATCH_MEDIA_ASSIGN)
    return ma if isinstance(ma, dict) else {}


def load_assign_strategy(scope: StrategyScope = "library") -> AssignStrategy:
    """从 app_config 读取指定场景的分配策略，默认轮流分配。

    Args:
        scope: "library" 视频库分配，"batch" 批量视频从媒体库选择。
    """
    try:
        ma = _media_assign_dict()
        val = ma.get(_key_for_scope(scope), AssignStrategy.ROUND_ROBIN.value)
        return AssignStrategy.from_str(str(val))
    except Exception as e:
        logger.warning("读取分配策略失败 (scope=%s): %s", scope, e)
        return AssignStrategy.ROUND_ROBIN


def save_assign_strategy(strategy: AssignStrategy, scope: StrategyScope = "library") -> None:
    """将指定场景的分配策略保存到 app_config。"""
    from src.ui.utils.async_helper import run_async_from_ui
    from src.infrastructure.common.config.app_config_merge import merge_app_config

    key = _key_for_scope(scope)

    async def _save() -> None:
        cc = get_registered_config_center()
        bp_existing: Dict[str, Any] = {}
        if cc is not None:
            raw = cc.get_app_config().get(KEY_BATCH_PUBLISH)
            if isinstance(raw, dict):
                bp_existing = dict(raw)
        ma = dict(bp_existing.get(BATCH_MEDIA_ASSIGN) or {})
        ma[key] = strategy.value
        bp_existing[BATCH_MEDIA_ASSIGN] = ma
        await merge_app_config(cc, {KEY_BATCH_PUBLISH: bp_existing})

    run_async_from_ui(_save)


def distribute_items_to_targets(
    items: List[T],
    targets: List[Any],
    strategy: AssignStrategy = AssignStrategy.ROUND_ROBIN,
) -> List[Tuple[T, Any]]:
    """将任意列表按策略分配到目标列表，返回 [(item, target)] 配对。

    当 targets 为空时返回空列表；item 数量可以多于 target 数量（循环分配）。

    Args:
        items:    待分配的元素列表（视频路径、文件信息 dict 等）。
        targets:  目标列表（账号 dict、AssignTarget 等）。
        strategy: 分配策略枚举。

    Returns:
        [(item, target)] 列表，保持 items 原始顺序（随机策略仅打乱目标顺序）。
    """
    if not items or not targets:
        return []

    ordered_targets = _apply_strategy(targets, strategy)
    n = len(ordered_targets)

    return [(item, ordered_targets[i % n]) for i, item in enumerate(items)]


def distribute_files_to_targets_grouped(
    files: List[Path],
    targets: List[Any],
    strategy: AssignStrategy = AssignStrategy.ROUND_ROBIN,
) -> Dict[Any, List[Path]]:
    """将文件列表按策略分配到目标，返回 {target: [文件列表]} 分组映射。

    用于视频库「分配到多账号」场景（后续逐组执行文件移动）。

    Args:
        files:    待分配文件路径列表。
        targets:  目标对象列表（AssignTarget 或任意可哈希对象）。
        strategy: 分配策略枚举。

    Returns:
        有序 dict，key 为 target，value 为该 target 分得的文件列表（保持原序）。
    """
    if not files or not targets:
        return {}

    ordered_targets = _apply_strategy(targets, strategy)
    n = len(ordered_targets)

    result: Dict[Any, List[Path]] = {t: [] for t in ordered_targets}
    for i, f in enumerate(files):
        result[ordered_targets[i % n]].append(f)

    return result


def _apply_strategy(targets: List[Any], strategy: AssignStrategy) -> List[Any]:
    """根据策略对目标列表进行排序/重排，返回新列表（不修改原列表）。"""
    if strategy == AssignStrategy.RANDOM:
        shuffled = list(targets)
        _random.shuffle(shuffled)
        return shuffled

    if strategy == AssignStrategy.AVERAGE:
        return _sort_for_average(targets)

    # 轮流分配：保持原顺序
    return list(targets)


def _sort_for_average(targets: List[Any]) -> List[Any]:
    """平均策略下返回目标列表（原顺序即可，分配时按均分块分配）。

    实际均分由调用侧通过 distribute_files_to_targets_grouped 保证：
    每 n 个文件为一轮，每个 target 每轮最多拿 1 个，自然均分。
    此处保持原顺序返回，与轮流分配效果相同但语义明确。
    """
    return list(targets)
