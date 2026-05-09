"""
结构化日志聚合模块
文件路径：src/core/monitoring/logger.py
功能：提供结构化日志记录，支持审计日志
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
import aiosqlite

from src.infrastructure.common.path_manager import PathManager

logger = logging.getLogger(__name__)


class StructuredLogger:
    """结构化日志聚合器
    
    提供结构化日志记录，支持审计日志（保留90天）。
    """
    
    def __init__(self, audit_log_path: str = None):
        """初始化结构化日志聚合器
        
        Args:
            audit_log_path: 审计日志数据库路径 (None则使用默认AppData路径)
        """
        if audit_log_path is None:
            self.audit_log_path = str(PathManager.get_app_data_dir() / "data" / "audit_log.sqlite")
        else:
            self.audit_log_path = audit_log_path
            
        self.logger = logging.getLogger(__name__)
        self._init_task = None
        
        # 确保审计日志目录存在
        Path(self.audit_log_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 延迟初始化审计日志数据库——在有事件循环时才调度
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            self._init_task = loop.create_task(self._init_audit_log())
        except RuntimeError:
            pass
    
    async def _init_audit_log(self) -> None:
        """初始化审计日志数据库（异步）"""
        try:
            async with aiosqlite.connect(self.audit_log_path) as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        action TEXT NOT NULL,
                        resource TEXT,
                        details TEXT,
                        timestamp TEXT NOT NULL,
                        ip_address TEXT,
                        user_agent TEXT
                    )
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_user_id ON audit_log(user_id)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_action ON audit_log(action)
                """)
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log(timestamp)
                """)
                await conn.commit()
        except Exception as e:
            self.logger.error(f"初始化审计日志数据库失败: {e}", exc_info=True)
    
    async def log_audit(
        self,
        user_id: int,
        action: str,
        resource: str,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> None:
        """记录审计日志（异步）
        
        Args:
            user_id: 用户ID
            action: 操作（如login、publish、config_modify）
            resource: 资源（如account、publish_record、config）
            details: 详细信息（可选）
            ip_address: IP地址（可选）
            user_agent: 用户代理（可选）
        """
        # 确保审计日志数据库已初始化
        if self._init_task is None:
            import asyncio
            self._init_task = asyncio.ensure_future(self._init_audit_log())
        if not self._init_task.done():
            await self._init_task
        
        try:
            details_json = json.dumps(details, ensure_ascii=False) if details else None
            
            async with aiosqlite.connect(self.audit_log_path) as conn:
                await conn.execute("""
                    INSERT INTO audit_log 
                    (user_id, action, resource, details, timestamp, ip_address, user_agent)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    action,
                    resource,
                    details_json,
                    datetime.now().isoformat(),
                    ip_address,
                    user_agent
                ))
                await conn.commit()
            
            # 清理90天前的日志
            await self._cleanup_old_logs()
        except Exception as e:
            self.logger.error(f"记录审计日志失败: {e}", exc_info=True)
    
    async def _cleanup_old_logs(self, days: int = 90) -> None:
        """清理旧日志（异步）
        
        Args:
            days: 保留天数（默认90天）
        """
        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            async with aiosqlite.connect(self.audit_log_path) as conn:
                await conn.execute("""
                    DELETE FROM audit_log WHERE timestamp < ?
                """, (cutoff_date,))
                await conn.commit()
        except Exception as e:
            self.logger.error(f"清理旧日志失败: {e}", exc_info=True)
    
    async def get_audit_logs(
        self,
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        limit: int = 100
    ) -> list[Dict[str, Any]]:
        """获取审计日志（异步）
        
        Args:
            user_id: 用户ID（可选，过滤）
            action: 操作（可选，过滤）
            limit: 返回数量限制
        
        Returns:
            审计日志列表
        """
        try:
            async with aiosqlite.connect(self.audit_log_path) as conn:
                conn.row_factory = aiosqlite.Row
                
                query = "SELECT * FROM audit_log WHERE 1=1"
                params = []
                
                if user_id:
                    query += " AND user_id = ?"
                    params.append(user_id)
                
                if action:
                    query += " AND action = ?"
                    params.append(action)
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                async with conn.execute(query, params) as cursor:
                    rows = await cursor.fetchall()
                    
                    result = []
                    for row in rows:
                        details = None
                        if row['details']:
                            try:
                                details = json.loads(row['details'])
                            except (json.JSONDecodeError, TypeError, ValueError):
                                pass
                        
                        result.append({
                            'id': row['id'],
                            'user_id': row['user_id'],
                            'action': row['action'],
                            'resource': row['resource'],
                            'details': details,
                            'timestamp': row['timestamp'],
                            'ip_address': row['ip_address'],
                            'user_agent': row['user_agent'],
                        })
                    
                    return result
        except Exception as e:
            self.logger.error(f"获取审计日志失败: {e}", exc_info=True)
            return []

