"""工作台发布统计聚合查询。"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.repositories.publish_record_repository_async import PublishRecordRepositoryAsync


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows
        self.queries: list[tuple[str, list | None]] = []

    async def execute_query(self, sql, params=None):
        self.queries.append((sql, params))
        return 1, self.rows


@pytest.mark.asyncio
async def test_aggregate_today_publish_counts_uses_single_query(monkeypatch):
    conn = _FakeConn(
        [
            {
                "today_count": 4,
                "today_success": 2,
                "today_failed": 1,
                "today_pending": 1,
                "today_running": 0,
            }
        ]
    )
    monkeypatch.setattr(
        "src.domain.repositories.publish_record_repository_async.Tortoise.get_connection",
        lambda _name: conn,
    )

    result = await PublishRecordRepositoryAsync().aggregate_today_publish_counts()

    assert result == {
        "today_count": 4,
        "today_success": 2,
        "today_failed": 1,
        "today_pending": 1,
        "today_running": 0,
    }
    assert len(conn.queries) == 1
    assert "SUM(CASE WHEN status = 'success'" in conn.queries[0][0]


@pytest.mark.asyncio
async def test_count_active_publish_by_status_uses_single_query(monkeypatch):
    conn = _FakeConn([{"total": 9, "success": 5, "failed": 2, "pending": 2}])
    monkeypatch.setattr(
        "src.domain.repositories.publish_record_repository_async.Tortoise.get_connection",
        lambda _name: conn,
    )

    result = await PublishRecordRepositoryAsync().count_active_publish_by_status()

    assert result == {"total": 9, "success": 5, "failed": 2, "pending": 2}
    assert len(conn.queries) == 1
    assert "COUNT(*) AS total" in conn.queries[0][0]


@pytest.mark.asyncio
async def test_count_finished_publish_since_uses_single_query(monkeypatch):
    conn = _FakeConn([{"finished_total": 6, "finished_success": 4}])
    monkeypatch.setattr(
        "src.domain.repositories.publish_record_repository_async.Tortoise.get_connection",
        lambda _name: conn,
    )

    result = await PublishRecordRepositoryAsync().count_finished_publish_since(
        datetime(2026, 5, 16)
    )

    assert result == {"finished_total": 6, "finished_success": 4}
    assert len(conn.queries) == 1
    assert "finished_success" in conn.queries[0][0]
