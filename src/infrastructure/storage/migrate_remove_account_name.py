"""
数据库迁移脚本：删除 account_name 字段
文件路径：src/infrastructure/storage/migrate_remove_account_name.py
功能：将现有数据库中的 account_name 字段删除，仅保留 platform_username
"""

import sqlite3
import os
import logging
from pathlib import Path

from src.infrastructure.common.path_manager import PathManager

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
logger = logging.getLogger(__name__)


def migrate_database(db_path: str = None) -> None:
    """迁移数据库，删除 account_name 字段
    
    Args:
        db_path: 数据库文件路径 (如果为None，则使用PathManager默认路径)
    """
    if db_path is None:
        db_path = str(PathManager.get_db_path())
    
    # 备份数据库
    backup_path = f"{db_path}.backup"
    if os.path.exists(db_path):
        import shutil
        shutil.copy2(db_path, backup_path)
        logger.info(f"数据库已备份到: {backup_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 1. 迁移 platform_accounts 表
        logger.info("开始迁移 platform_accounts 表...")
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='platform_accounts'")
        if cursor.fetchone():
            # 检查 account_name 列是否存在
            cursor.execute("PRAGMA table_info(platform_accounts)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'account_name' in column_names:
                # 如果 platform_username 为空，用 account_name 填充
                cursor.execute("""
                    UPDATE platform_accounts 
                    SET platform_username = account_name 
                    WHERE platform_username IS NULL OR platform_username = ''
                """)
                logger.info(f"已将空的 platform_username 填充为 account_name")
                
                # 创建新表（不包含 account_name）
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS platform_accounts_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        platform TEXT NOT NULL,
                        cookie_path TEXT NOT NULL,
                        platform_username TEXT NOT NULL,
                        login_status TEXT DEFAULT 'offline',
                        last_login_at TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """)
                
                # 复制数据到新表
                cursor.execute("""
                    INSERT INTO platform_accounts_new 
                    (id, user_id, platform, cookie_path, platform_username, login_status, last_login_at, created_at)
                    SELECT id, user_id, platform, cookie_path, platform_username, login_status, last_login_at, created_at
                    FROM platform_accounts
                """)
                
                # 删除旧表
                cursor.execute("DROP TABLE platform_accounts")
                
                # 重命名新表
                cursor.execute("ALTER TABLE platform_accounts_new RENAME TO platform_accounts")
                
                logger.info("platform_accounts 表迁移成功")
            else:
                logger.info("platform_accounts 表已经没有 account_name 字段，跳过迁移")
        
        # 2. 迁移 publish_records 表
        logger.info("开始迁移 publish_records 表...")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='publish_records'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(publish_records)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'account_name' in column_names:
                # 将 account_name 重命名为 platform_username
                # SQLite 不支持直接重命名列，需要重建表
                
                # 创建新表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS publish_records_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        platform_username TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        file_path TEXT NOT NULL,
                        file_type TEXT NOT NULL,
                        title TEXT,
                        description TEXT,
                        tags TEXT,
                        cover_path TEXT,
                        poi_info TEXT,
                        micro_app_info TEXT,
                        cart_info TEXT,
                        anchor_info TEXT,
                        privacy_settings TEXT,
                        scheduled_publish_time TEXT,
                        status TEXT NOT NULL,
                        error_message TEXT,
                        publish_url TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """)
                
                # 复制数据（account_name -> platform_username）
                cursor.execute("""
                    INSERT INTO publish_records_new 
                    (id, user_id, platform_username, platform, file_path, file_type, 
                     title, description, tags, cover_path, poi_info, 
                     micro_app_info, cart_info, anchor_info, privacy_settings, 
                     scheduled_publish_time, status, error_message, publish_url, 
                     created_at, updated_at)
                    SELECT id, user_id, account_name, platform, file_path, file_type, 
                           title, description, tags, cover_path, poi_info, 
                           micro_app_info, goods_info, anchor_info, privacy_settings, 
                           scheduled_publish_time, status, error_message, publish_url, 
                           created_at, updated_at
                    FROM publish_records
                """)
                
                # 删除旧表
                cursor.execute("DROP TABLE publish_records")
                
                # 重命名新表
                cursor.execute("ALTER TABLE publish_records_new RENAME TO publish_records")
                
                logger.info("publish_records 表迁移成功")
            else:
                logger.info("publish_records 表已经使用 platform_username 字段，跳过迁移")
        
        # 3. 迁移 batch_tasks 表
        logger.info("开始迁移 batch_tasks 表...")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='batch_tasks'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(batch_tasks)")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'account_name' in column_names:
                # 重建表
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS batch_tasks_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        task_name TEXT NOT NULL,
                        task_description TEXT,
                        platform_username TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        task_type TEXT NOT NULL,
                        script_config TEXT NOT NULL,
                        video_count INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        completed_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        start_time TEXT,
                        end_time TEXT,
                        priority INTEGER DEFAULT 0,
                        retry_count INTEGER DEFAULT 3,
                        delay_seconds INTEGER DEFAULT 5,
                        max_concurrent INTEGER DEFAULT 1,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT,
                        FOREIGN KEY (user_id) REFERENCES users(id)
                    )
                """)
                
                # 复制数据
                cursor.execute("""
                    INSERT INTO batch_tasks_new 
                    (id, user_id, task_name, task_description, platform_username, platform, 
                     task_type, script_config, video_count, status, completed_count, 
                     failed_count, start_time, end_time, priority, retry_count, 
                     delay_seconds, max_concurrent, created_at, updated_at)
                    SELECT id, user_id, task_name, task_description, account_name, platform, 
                           task_type, script_config, video_count, status, completed_count, 
                           failed_count, start_time, end_time, priority, retry_count, 
                           delay_seconds, max_concurrent, created_at, updated_at
                    FROM batch_tasks
                """)
                
                # 删除旧表
                cursor.execute("DROP TABLE batch_tasks")
                
                # 重命名新表
                cursor.execute("ALTER TABLE batch_tasks_new RENAME TO batch_tasks")
                
                logger.info("batch_tasks 表迁移成功")
            else:
                logger.info("batch_tasks 表已经使用 platform_username 字段，跳过迁移")

        # 4. 重建索引
        logger.info("重建索引...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform_accounts_user_id ON platform_accounts(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform_accounts_platform ON platform_accounts(platform)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform_accounts_login_status ON platform_accounts(login_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_records_user_id ON publish_records(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_records_platform_username ON publish_records(platform_username)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_records_platform ON publish_records(platform)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_records_status ON publish_records(status)")
        
        conn.commit()
        logger.info("数据库迁移成功！")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"数据库迁移失败: {e}", exc_info=True)
        # 恢复备份
        if os.path.exists(backup_path):
            import shutil
            shutil.copy2(backup_path, db_path)
            logger.info(f"已从备份恢复数据库: {backup_path}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_database()
    print("数据库迁移完成！")
