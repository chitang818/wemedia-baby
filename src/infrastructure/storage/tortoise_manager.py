"""
Tortoise ORM 生命周期管理器
功能：管理 Tortoise ORM 的初始化、配置和关闭
"""

import logging
from pathlib import Path
from typing import Optional

from tortoise import Tortoise

from src.infrastructure.common.path_manager import PathManager

logger = logging.getLogger(__name__)

# Tortoise ORM 配置模板
# 注意：connections.default.credentials.file_path 在运行时动态设置
TORTOISE_ORM_CONFIG = {
    "connections": {
        "default": {
            "engine": "tortoise.backends.sqlite",
            "credentials": {
                "file_path": "",  # 运行时动态设置
            },
        }
    },
    "apps": {
        "models": {
            "models": [
                "src.infrastructure.storage.orm_models",
            ] + (["aerich.models"] if not getattr(__import__("sys"), "frozen", False) else []),
            "default_connection": "default",
        }
    },
    # 数据库性能优化参数（通过 PRAGMA 设置）
    "use_tz": False,
    "timezone": "Asia/Shanghai",
}


def get_tortoise_config(db_path: Optional[str] = None) -> dict:
    """获取 Tortoise ORM 配置（填入实际的数据库路径）

    Args:
        db_path: 数据库文件路径（如果为 None，则使用 PathManager 默认路径）

    Returns:
        完整的 Tortoise 配置字典
    """
    if db_path is None:
        db_path = str(PathManager.get_db_path())

    config = TORTOISE_ORM_CONFIG.copy()
    # 深拷贝内层字典以防止修改全局模板
    config["connections"] = {
        "default": {
            "engine": "tortoise.backends.sqlite",
            "credentials": {
                "file_path": db_path,
            },
        }
    }
    return config


async def init_tortoise(db_path: Optional[str] = None) -> None:
    """初始化 Tortoise ORM 连接

    在应用启动时调用此函数。将自动加载所有 ORM 模型并建立连接。

    Args:
        db_path: 数据库文件路径（如果为 None，则使用默认路径）
    """
    if db_path is None:
        db_path = str(PathManager.get_db_path())

    # 确保数据库目录存在
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    config = get_tortoise_config(db_path)
    await Tortoise.init(config=config)

    # 对 SQLite 连接应用性能优化 PRAGMA
    conn = Tortoise.get_connection("default")
    try:
        # 启用 WAL 模式，提升并发读取能力
        await conn.execute_query("PRAGMA journal_mode=WAL")
        # 同步模式设为 NORMAL，平衡性能和安全性
        await conn.execute_query("PRAGMA synchronous=NORMAL")
        # 增加缓存大小到 10MB
        await conn.execute_query("PRAGMA cache_size=-10000")
        # 临时数据存储在内存中
        await conn.execute_query("PRAGMA temp_store=MEMORY")
        # 并发写入等待超时：10 秒内自动重试，批量发布场景下减少 database is locked 错误
        await conn.execute_query("PRAGMA busy_timeout=10000")
        # 增大 WAL 自动检查点间隔，减少写入争用
        await conn.execute_query("PRAGMA wal_autocheckpoint=2000")
        # 关闭外键约束（当前业务不依赖严格外键关联，避免旧数据引起的约束错误）
        await conn.execute_query("PRAGMA foreign_keys=OFF")
        
        # 通过底层 aiosqlite 连接强制禁用外键（防止 Tortoise ORM 覆盖）
        try:
            if hasattr(conn, '_connection') and conn._connection:
                await conn._connection.execute("PRAGMA foreign_keys=OFF")
                logger.debug("已通过底层连接禁用 SQLite 外键约束")
        except Exception as fk_e:
            logger.warning(f"底层禁用外键约束失败（不影响正常使用）: {fk_e}")
        
        logger.debug("Tortoise ORM SQLite 性能优化 PRAGMA 已设置")
    except Exception as e:
        logger.warning(f"设置 SQLite PRAGMA 失败（不影响正常使用）: {e}")

    try:
        # 核心优化：使用 Tortoise 自带构建数据库表（替代老版本的 SQLite 同步阻断脚本建表）
        await Tortoise.generate_schemas(safe=True)
        # 确保默认用户存在（解决 publish_records 等表的外键约束问题）
        try:
            await conn.execute_query(
                "INSERT OR IGNORE INTO users (id, username, password_hash, email, role, trial_count) "
                "VALUES (1, 'default', '', '', 'user', 999)"
            )
        except Exception as user_e:
            logger.debug(f"确保默认用户存在时出错（可忽略）: {user_e}")
        
        # ===== 自动列迁移：给已有表补充新增字段 =====
        # generate_schemas(safe=True) 只建表不加列，需要手动补全旧表缺失的列
        new_columns = {
            "account_tags": [
                # 标签类型：account=账号标签，group=账号组标签
                ("tag_type", "VARCHAR(20) DEFAULT 'account'"),
            ],
            "cart_promotion_items": [
                ("short_title", "TEXT"),
            ],
            "publish_records": [
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
                # group_id：任务来源为账号组时直接存储组ID，避免通过账号表多跳查询
                ("group_id", "INTEGER"),
            ],
            "platform_accounts": [
                # 账号数据目录名（如 profile_xxx），必填才能打开浏览器与 Cookie 路径解析
                ("profile_folder_name", "VARCHAR(200)"),
            ],
        }
        for table_name, columns in new_columns.items():
            try:
                # 获取当前表的列信息
                existing_cols_result = await conn.execute_query(f"PRAGMA table_info({table_name})")
                existing_col_names = {row[1] for row in existing_cols_result[1]}
                for col_name, col_type in columns:
                    if col_name not in existing_col_names:
                        await conn.execute_query(
                            f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                        )
                        logger.info(f"✅ 自动迁移：已向 {table_name} 添加新列 {col_name}")
            except Exception as migrate_e:
                logger.warning(f"列迁移 {table_name} 时遇到问题（可忽略）: {migrate_e}")
        # ===== 自动列迁移结束 =====

        # ===== 性能索引：加速发布记录的状态+时间排序查询 =====
        _indexes = [
            (
                "idx_publish_records_status_created",
                "CREATE INDEX IF NOT EXISTS idx_publish_records_status_created "
                "ON publish_records (status, created_at DESC)",
            ),
            (
                "idx_publish_records_platform_status",
                "CREATE INDEX IF NOT EXISTS idx_publish_records_platform_status "
                "ON publish_records (platform, status)",
            ),
        ]
        for idx_name, idx_sql in _indexes:
            try:
                await conn.execute_query(idx_sql)
                logger.debug("确保索引存在: %s", idx_name)
            except Exception as idx_e:
                logger.debug("创建索引 %s 时跳过: %s", idx_name, idx_e)
        # ===== 性能索引结束 =====

    except Exception as e:
         logger.warning(f"Tortoise ORM 生成表结构失败或报错（可能因表已存在且有变动而安全跳过）: {e}")

    logger.debug(f"Tortoise ORM 初始化完成，数据库路径: {db_path}")


async def close_tortoise() -> None:
    """关闭 Tortoise ORM 连接

    在应用退出时调用此函数，确保所有数据库连接被正确释放。
    """
    await Tortoise.close_connections()
    logger.info("Tortoise ORM 连接已关闭")


async def generate_schemas() -> None:
    """生成数据库表结构（仅用于首次初始化或开发阶段）

    注意：在生产环境中应使用 Aerich 迁移工具来管理表结构变更，
    而非直接调用此方法。此方法仅在以下场景使用：
    1. 全新安装时，数据库文件不存在
    2. 开发/测试环境快速重建数据库
    """
    await Tortoise.generate_schemas()
    logger.info("数据库表结构已生成")
