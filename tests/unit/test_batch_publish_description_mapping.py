from __future__ import annotations

import pytest

from src.pro_features.batch.publish_description_mapping import (
    combo_index_from_flags,
    flags_from_combo_index,
)

pytestmark = pytest.mark.unit


def test_flags_from_combo_index_all_modes():
    assert flags_from_combo_index(0) == (True, True)
    assert flags_from_combo_index(1) == (True, False)
    assert flags_from_combo_index(2) == (False, True)
    assert flags_from_combo_index(3) == (False, False)


def test_combo_index_from_flags_all_modes():
    assert combo_index_from_flags(True, True) == 0
    assert combo_index_from_flags(True, False) == 1
    assert combo_index_from_flags(False, True) == 2
    assert combo_index_from_flags(False, False) == 3


@pytest.mark.parametrize("index", [0, 1, 2, 3, 99, -1])
def test_combo_mapping_roundtrip_stable(index: int):
    flags = flags_from_combo_index(index)
    idx = combo_index_from_flags(*flags)
    assert idx in (0, 1, 2, 3)
    assert flags_from_combo_index(idx) == flags
