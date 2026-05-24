"""Versioned SQLite schema migrations for the desktop database.

The ORM creates new tables, but existing SQLite databases still need
idempotent schema fixes for newly added columns and indexes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Sequence

logger = logging.getLogger(__name__)

MigrationConn = object
MigrationFunc = Callable[[MigrationConn], Awaitable[None]]


@dataclass(frozen=True)
class MigrationStep:
    version: str
    description: str
    run: MigrationFunc


async def table_exists(conn: MigrationConn, table_name: str) -> bool:
    result = await conn.execute_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        [table_name],
    )
    return bool(result[1])


async def column_exists(conn: MigrationConn, table_name: str, column_name: str) -> bool:
    if not await table_exists(conn, table_name):
        return False

    result = await conn.execute_query(f'PRAGMA table_info("{table_name}")')
    return any(row[1] == column_name for row in result[1])


async def index_exists(conn: MigrationConn, index_name: str) -> bool:
    result = await conn.execute_query(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        [index_name],
    )
    return bool(result[1])


async def ensure_migration_table(conn: MigrationConn) -> None:
    await conn.execute_query(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


async def get_applied_versions(conn: MigrationConn) -> set[str]:
    await ensure_migration_table(conn)
    result = await conn.execute_query("SELECT version FROM schema_migrations")
    return {row[0] for row in result[1]}


async def _record_applied(conn: MigrationConn, step: MigrationStep) -> None:
    await conn.execute_query(
        "INSERT OR IGNORE INTO schema_migrations (version, description, applied_at) "
        "VALUES (?, ?, ?)",
        [step.version, step.description, datetime.now().isoformat(timespec="seconds")],
    )


async def _add_column_if_missing(
    conn: MigrationConn,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    if not await table_exists(conn, table_name):
        logger.debug("Skip migration column %s.%s: table missing", table_name, column_name)
        return

    if await column_exists(conn, table_name, column_name):
        return

    await conn.execute_query(
        f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}'
    )
    logger.info("Schema migration added column %s.%s", table_name, column_name)


async def _create_index_if_missing(conn: MigrationConn, index_name: str, sql: str) -> None:
    if await index_exists(conn, index_name):
        return

    await conn.execute_query(sql)
    logger.debug("Schema migration ensured index %s", index_name)


async def _migrate_account_tag_type(conn: MigrationConn) -> None:
    await _add_column_if_missing(
        conn,
        "account_tags",
        "tag_type",
        "VARCHAR(20) DEFAULT 'account'",
    )


async def _migrate_cart_promotion_short_title(conn: MigrationConn) -> None:
    await _add_column_if_missing(conn, "cart_promotion_items", "short_title", "TEXT")


async def _migrate_publish_record_extension_columns(conn: MigrationConn) -> None:
    columns = [
        ("privacy_settings", "TEXT"),
        ("cover_path", "TEXT"),
        ("poi_info", "TEXT"),
        ("micro_app_info", "TEXT"),
        ("cart_info", "TEXT"),
        ("anchor_info", "TEXT"),
        ("music_info", "TEXT"),
        ("scheduled_publish_time", "DATETIME"),
        ("platform_account_id", "INTEGER"),
        ("wechat_empty_location_open_picker", "INTEGER"),
        ("task_source", "VARCHAR(20)"),
        ("group_id", "INTEGER"),
    ]
    for column_name, column_type in columns:
        await _add_column_if_missing(
            conn,
            "publish_records",
            column_name,
            column_type,
        )


async def _migrate_platform_account_profile_folder_name(conn: MigrationConn) -> None:
    await _add_column_if_missing(
        conn,
        "platform_accounts",
        "profile_folder_name",
        "VARCHAR(200)",
    )


async def _migrate_publish_record_indexes(conn: MigrationConn) -> None:
    if not await table_exists(conn, "publish_records"):
        logger.debug("Skip publish record indexes: table missing")
        return

    await _create_index_if_missing(
        conn,
        "idx_publish_records_status_created",
        "CREATE INDEX IF NOT EXISTS idx_publish_records_status_created "
        "ON publish_records (status, created_at DESC)",
    )
    await _create_index_if_missing(
        conn,
        "idx_publish_records_platform_status",
        "CREATE INDEX IF NOT EXISTS idx_publish_records_platform_status "
        "ON publish_records (platform, status)",
    )
    await _create_index_if_missing(
        conn,
        "idx_publish_records_account_status_updated",
        "CREATE INDEX IF NOT EXISTS idx_publish_records_account_status_updated "
        "ON publish_records (platform_account_id, status, updated_at DESC)",
    )
    await _create_index_if_missing(
        conn,
        "idx_publish_records_account_status_scheduled",
        "CREATE INDEX IF NOT EXISTS idx_publish_records_account_status_scheduled "
        "ON publish_records (platform_account_id, status, scheduled_publish_time DESC)",
    )


MIGRATION_STEPS: tuple[MigrationStep, ...] = (
    MigrationStep(
        "20260522_001_account_tags_tag_type",
        "Add account_tags.tag_type",
        _migrate_account_tag_type,
    ),
    MigrationStep(
        "20260522_002_cart_promotion_short_title",
        "Add cart_promotion_items.short_title",
        _migrate_cart_promotion_short_title,
    ),
    MigrationStep(
        "20260522_003_publish_record_extension_columns",
        "Add publish_records extension columns",
        _migrate_publish_record_extension_columns,
    ),
    MigrationStep(
        "20260522_004_platform_accounts_profile_folder_name",
        "Add platform_accounts.profile_folder_name",
        _migrate_platform_account_profile_folder_name,
    ),
    MigrationStep(
        "20260522_005_publish_record_indexes",
        "Add publish_records query indexes",
        _migrate_publish_record_indexes,
    ),
)


async def run_pending_migrations(
    conn: MigrationConn,
    steps: Sequence[MigrationStep] = MIGRATION_STEPS,
) -> None:
    """Run unapplied schema migrations.

    Individual migration failures are logged and left unapplied so a later
    startup can retry after the underlying issue is fixed.
    """

    await ensure_migration_table(conn)
    applied_versions = await get_applied_versions(conn)
    pending_steps = [step for step in steps if step.version not in applied_versions]
    if not pending_steps:
        logger.debug("No pending schema migrations")
        return

    total_started = time.perf_counter()
    applied_count = 0
    for step in pending_steps:
        started = time.perf_counter()
        try:
            await step.run(conn)
            await _record_applied(conn, step)
            applied_count += 1
            logger.info(
                "Schema migration applied: %s (%s) in %.1fms",
                step.version,
                step.description,
                (time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            logger.warning(
                "Schema migration failed and will be retried later: %s (%s): %s",
                step.version,
                step.description,
                exc,
            )

    logger.info(
        "Schema migration runner finished: applied=%s pending=%s elapsed=%.1fms",
        applied_count,
        len(pending_steps) - applied_count,
        (time.perf_counter() - total_started) * 1000,
    )
