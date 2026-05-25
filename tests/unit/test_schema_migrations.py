from __future__ import annotations

import sqlite3

import pytest

from src.infrastructure.storage.schema_migrations import (
    MIGRATION_STEPS,
    MigrationStep,
    run_pending_migrations,
)


class SqliteConn:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(":memory:")

    async def execute_query(self, query: str, values: list[object] | None = None):
        cursor = self.conn.execute(query, values or [])
        self.conn.commit()
        return cursor.rowcount, cursor.fetchall()

    def close(self) -> None:
        self.conn.close()


def _column_names(conn: SqliteConn, table_name: str) -> set[str]:
    return {row[1] for row in conn.conn.execute(f'PRAGMA table_info("{table_name}")')}


def _migration_versions(conn: SqliteConn) -> list[str]:
    return [
        row[0]
        for row in conn.conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        )
    ]


@pytest.fixture
def old_schema_conn() -> SqliteConn:
    conn = SqliteConn()
    conn.conn.executescript(
        """
        CREATE TABLE account_tags (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE cart_promotion_items (
            id INTEGER PRIMARY KEY,
            title TEXT
        );
        CREATE TABLE publish_records (
            id INTEGER PRIMARY KEY,
            status TEXT,
            created_at DATETIME,
            platform TEXT
        );
        CREATE TABLE platform_accounts (
            id INTEGER PRIMARY KEY,
            platform TEXT
        );
        """
    )
    conn.conn.commit()
    try:
        yield conn
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_run_pending_migrations_adds_missing_columns_and_indexes(old_schema_conn):
    await run_pending_migrations(old_schema_conn)

    assert "tag_type" in _column_names(old_schema_conn, "account_tags")
    assert "short_title" in _column_names(old_schema_conn, "cart_promotion_items")
    assert "profile_folder_name" in _column_names(
        old_schema_conn,
        "platform_accounts",
    )

    publish_columns = _column_names(old_schema_conn, "publish_records")
    for column in [
        "privacy_settings",
        "cover_path",
        "poi_info",
        "micro_app_info",
        "cart_info",
        "anchor_info",
        "music_info",
        "scheduled_publish_time",
        "platform_account_id",
        "wechat_empty_location_open_picker",
        "task_source",
        "group_id",
        "diagnostic_path",
        "updated_at",
    ]:
        assert column in publish_columns

    indexes = {
        row[1]
        for row in old_schema_conn.conn.execute(
            'PRAGMA index_list("publish_records")'
        )
    }
    assert "idx_publish_records_status_created" in indexes
    assert "idx_publish_records_platform_status" in indexes

    assert _migration_versions(old_schema_conn) == [
        step.version for step in MIGRATION_STEPS
    ]


@pytest.mark.asyncio
async def test_run_pending_migrations_is_idempotent(old_schema_conn):
    await run_pending_migrations(old_schema_conn)
    versions_after_first_run = _migration_versions(old_schema_conn)

    await run_pending_migrations(old_schema_conn)

    assert _migration_versions(old_schema_conn) == versions_after_first_run
    assert (
        old_schema_conn.conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        == len(MIGRATION_STEPS)
    )


@pytest.mark.asyncio
async def test_location_promotion_items_table_migration(old_schema_conn):
    await run_pending_migrations(old_schema_conn)
    tables = {
        row[0]
        for row in old_schema_conn.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert "location_promotion_items" in tables
    cols = _column_names(old_schema_conn, "location_promotion_items")
    for col in [
        "short_name",
        "douyin_location",
        "kuaishou_location",
        "channels_location",
        "xiaohongshu_location",
    ]:
        assert col in cols


@pytest.mark.asyncio
async def test_missing_optional_tables_are_skipped_safely():
    conn = SqliteConn()
    try:
        conn.conn.execute(
            """
            CREATE TABLE publish_records (
                id INTEGER PRIMARY KEY,
                status TEXT,
                created_at DATETIME,
                platform TEXT
            )
            """
        )
        conn.conn.commit()

        await run_pending_migrations(conn)

        assert "privacy_settings" in _column_names(conn, "publish_records")
        assert _migration_versions(conn) == [step.version for step in MIGRATION_STEPS]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_failed_migration_is_not_recorded():
    conn = SqliteConn()

    async def fail(_conn):
        raise RuntimeError("boom")

    try:
        bad_step = MigrationStep("99999999_bad", "bad migration", fail)

        await run_pending_migrations(conn, steps=[bad_step])

        assert _migration_versions(conn) == []
    finally:
        conn.close()
