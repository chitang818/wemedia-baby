"""Versioned SQLite schema migrations for the desktop database.

The ORM creates new tables, but existing SQLite databases still need
idempotent schema fixes for newly added columns and indexes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Sequence

logger = logging.getLogger(__name__)

MigrationConn = Any
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
        ("diagnostic_path", "TEXT"),
        ("updated_at", "DATETIME"),
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


async def _migrate_publish_record_diagnostic_path(conn: MigrationConn) -> None:
    await _add_column_if_missing(
        conn,
        "publish_records",
        "diagnostic_path",
        "TEXT",
    )


async def _migrate_publish_risk_observability(conn: MigrationConn) -> None:
    account_columns = [
        ("publish_risk_state", "VARCHAR(20) DEFAULT 'normal'"),
        ("publish_risk_reason", "TEXT"),
        ("publish_risk_at", "DATETIME"),
    ]
    for column_name, column_type in account_columns:
        await _add_column_if_missing(
            conn,
            "platform_accounts",
            column_name,
            column_type,
        )

    await _add_column_if_missing(
        conn,
        "publish_records",
        "failure_kind",
        "VARCHAR(40)",
    )

    if await table_exists(conn, "platform_accounts"):
        await _create_index_if_missing(
            conn,
            "idx_platform_accounts_publish_risk_state",
            "CREATE INDEX IF NOT EXISTS idx_platform_accounts_publish_risk_state "
            "ON platform_accounts (publish_risk_state)",
        )
    if await table_exists(conn, "publish_records"):
        await _create_index_if_missing(
            conn,
            "idx_publish_records_failure_kind_updated",
            "CREATE INDEX IF NOT EXISTS idx_publish_records_failure_kind_updated "
            "ON publish_records (failure_kind, updated_at DESC)",
        )


async def _migrate_location_promotion_items_table(conn: MigrationConn) -> None:
    if await table_exists(conn, "location_promotion_items"):
        return
    await conn.execute_query(
        """
        CREATE TABLE IF NOT EXISTS location_promotion_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            short_name VARCHAR(500) NOT NULL UNIQUE,
            douyin_location TEXT,
            kuaishou_location TEXT,
            channels_location TEXT,
            xiaohongshu_location TEXT,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP
        )
        """
    )
    await _create_index_if_missing(
        conn,
        "idx_location_promotion_items_short_name",
        "CREATE INDEX IF NOT EXISTS idx_location_promotion_items_short_name "
        "ON location_promotion_items (short_name)",
    )
    logger.info("Schema migration created table location_promotion_items")


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


async def _migrate_copywriting_items_category(conn: MigrationConn) -> None:
    await _add_column_if_missing(
        conn,
        "copywriting_items",
        "category",
        "VARCHAR(100) DEFAULT '全部'",
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
    MigrationStep(
        "20260525_001_publish_record_diagnostic_path",
        "Add publish_records.diagnostic_path",
        _migrate_publish_record_diagnostic_path,
    ),
    MigrationStep(
        "20260525_002_location_promotion_items_table",
        "Create location_promotion_items table",
        _migrate_location_promotion_items_table,
    ),
    MigrationStep(
        "20260610_001_publish_risk_observability",
        "Add account publish risk state and publish failure kind",
        _migrate_publish_risk_observability,
    ),
    MigrationStep(
        "20260627_001_copywriting_items_category",
        "Add copywriting_items.category",
        _migrate_copywriting_items_category,
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
