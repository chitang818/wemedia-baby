"""
媒体文件分配算法单元测试
测试 distribute_items_to_targets 和 distribute_files_to_targets_grouped 的三种策略。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.common.media_assign_strategy import (
    AssignStrategy,
    distribute_items_to_targets,
    distribute_files_to_targets_grouped,
    strategy_from_display_name,
    STRATEGY_DISPLAY_NAMES,
)

pytestmark = pytest.mark.unit


class TestAssignStrategy:

    def test_from_str_round_robin(self):
        assert AssignStrategy.from_str("round_robin") == AssignStrategy.ROUND_ROBIN

    def test_from_str_random(self):
        assert AssignStrategy.from_str("random") == AssignStrategy.RANDOM

    def test_from_str_average(self):
        assert AssignStrategy.from_str("average") == AssignStrategy.AVERAGE

    def test_from_str_unknown_defaults_to_round_robin(self):
        assert AssignStrategy.from_str("unknown") == AssignStrategy.ROUND_ROBIN

    def test_display_names_not_empty(self):
        for s in AssignStrategy:
            assert s.display_name()

    def test_strategy_from_display_name_roundtrip(self):
        for s in AssignStrategy:
            assert strategy_from_display_name(s.display_name()) == s

    def test_strategy_from_display_name_unknown_defaults_to_round_robin(self):
        assert strategy_from_display_name("不存在的策略") == AssignStrategy.ROUND_ROBIN

    def test_strategy_display_names_list(self):
        assert len(STRATEGY_DISPLAY_NAMES) == len(list(AssignStrategy))


class TestDistributeItemsToTargets:

    def test_round_robin_basic(self):
        items = [1, 2, 3, 4, 5, 6]
        targets = ["A", "B", "C"]
        pairs = distribute_items_to_targets(items, targets, AssignStrategy.ROUND_ROBIN)
        assert len(pairs) == 6
        assert pairs[0] == (1, "A")
        assert pairs[1] == (2, "B")
        assert pairs[2] == (3, "C")
        assert pairs[3] == (4, "A")

    def test_round_robin_more_items_than_targets(self):
        pairs = distribute_items_to_targets(list(range(7)), ["X", "Y"], AssignStrategy.ROUND_ROBIN)
        assert len(pairs) == 7
        # X 拿 0,2,4,6；Y 拿 1,3,5
        x_items = [item for item, t in pairs if t == "X"]
        y_items = [item for item, t in pairs if t == "Y"]
        assert len(x_items) == 4
        assert len(y_items) == 3

    def test_empty_items_returns_empty(self):
        assert distribute_items_to_targets([], ["A", "B"]) == []

    def test_empty_targets_returns_empty(self):
        assert distribute_items_to_targets([1, 2, 3], []) == []

    def test_single_target_all_to_same(self):
        pairs = distribute_items_to_targets([1, 2, 3], ["only"], AssignStrategy.ROUND_ROBIN)
        targets = [t for _, t in pairs]
        assert all(t == "only" for t in targets)

    def test_random_strategy_same_distribution_size(self):
        items = list(range(9))
        targets = ["A", "B", "C"]
        pairs = distribute_items_to_targets(items, targets, AssignStrategy.RANDOM)
        assert len(pairs) == 9

    def test_average_strategy_distributes_evenly(self):
        items = list(range(6))
        targets = ["A", "B", "C"]
        pairs = distribute_items_to_targets(items, targets, AssignStrategy.AVERAGE)
        counts = {t: sum(1 for _, tt in pairs if tt == t) for t in targets}
        assert max(counts.values()) - min(counts.values()) <= 1

    def test_preserves_item_order(self):
        items = ["first", "second", "third"]
        pairs = distribute_items_to_targets(items, ["A", "B"], AssignStrategy.ROUND_ROBIN)
        assigned_items = [item for item, _ in pairs]
        assert assigned_items == items


class TestDistributeFilesToTargetsGrouped:

    def test_round_robin_grouped(self):
        files = [Path(f"/v{i}.mp4") for i in range(6)]
        targets = ["A", "B", "C"]
        result = distribute_files_to_targets_grouped(files, targets, AssignStrategy.ROUND_ROBIN)
        assert len(result) == 3
        assert len(result["A"]) == 2
        assert len(result["B"]) == 2
        assert len(result["C"]) == 2

    def test_uneven_distribution(self):
        files = [Path(f"/v{i}.mp4") for i in range(5)]
        targets = ["A", "B"]
        result = distribute_files_to_targets_grouped(files, targets, AssignStrategy.ROUND_ROBIN)
        total = sum(len(v) for v in result.values())
        assert total == 5

    def test_empty_files_returns_empty(self):
        result = distribute_files_to_targets_grouped([], ["A", "B"])
        assert result == {}

    def test_empty_targets_returns_empty(self):
        files = [Path("/v1.mp4")]
        result = distribute_files_to_targets_grouped(files, [])
        assert result == {}

    def test_all_targets_present_in_result(self):
        files = [Path(f"/v{i}.mp4") for i in range(4)]
        targets = ["A", "B", "C"]
        result = distribute_files_to_targets_grouped(files, targets, AssignStrategy.ROUND_ROBIN)
        for t in targets:
            assert t in result
