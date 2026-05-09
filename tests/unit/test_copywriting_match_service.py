from __future__ import annotations

import pytest

from src.services.copywriting.copywriting_match_service import (
    CopywritingMatchMode,
    CopywritingMatchService,
)


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_match_passes_assign_strategy_to_batch_match(monkeypatch):
    captured: dict = {}

    async def fake_batch_match(**kwargs):
        captured.update(kwargs)
        return [{"title": "t", "description": "d"}]

    monkeypatch.setattr(CopywritingMatchService, "batch_match", fake_batch_match)

    result = await CopywritingMatchService.match(
        mode=CopywritingMatchMode.RANDOM_ALL,
        file_path="/tmp/a.mp4",
        assign_strategy="random",
    )

    assert result == {"title": "t", "description": "d"}
    assert captured["assign_strategy"] == "random"
    assert captured["mode"] == CopywritingMatchMode.RANDOM_ALL


@pytest.mark.asyncio
async def test_batch_match_random_category_without_category_id_returns_none_list():
    tasks = [{"file_path": "/tmp/a.mp4"}, {"file_path": "/tmp/b.mp4"}]
    result = await CopywritingMatchService.batch_match(
        tasks=tasks,
        mode=CopywritingMatchMode.RANDOM_CATEGORY,
        category_id=None,
    )
    assert result == [None, None]
