"""
批量任务检查点管理器（断点续传）
文件路径：src/pro_features/batch/services/checkpoint_manager_async.py

说明：
该模块用于“记住批量任务执行进度”，以文件形式持久化到本地：
  {AppData}/WeMediaBaby/data/checkpoints/task_{task_id}.json

设计目标：
1) 可导入、可运行（不依赖数据库/外部存储）
2) 保存为原子写入（先写 tmp 再 replace），避免写入中断导致 JSON 损坏
3) 对 completed_indices 做类型兜底（list<->set），保证重启后可恢复
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any, Set, List

from src.infrastructure.common.path_manager import PathManager

logger = logging.getLogger(__name__)


class CheckpointManagerAsync:
    def __init__(self, checkpoint_dir: str | Path | None = None):
        if checkpoint_dir is None:
            self.checkpoint_dir = PathManager.get_app_data_dir() / "data" / "checkpoints"
        else:
            self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    def _get_checkpoint_path(self, task_id: int) -> Path:
        return self.checkpoint_dir / f"task_{task_id}.json"

    @staticmethod
    def _get_current_time() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    async def save_checkpoint(
        self,
        task_id: int,
        completed_indices: Set[int],
        current_index: int,
    ) -> bool:
        """
        Args:
            task_id: 批量任务 ID
            completed_indices: 已成功完成的视频序号集合
            current_index: 下一个需要处理的索引（resume 时作为 start_index）
        """
        try:
            checkpoint_data = {
                "task_id": int(task_id),
                "completed_indices": sorted(int(i) for i in set(completed_indices)),
                "current_index": int(current_index),
                "saved_at": self._get_current_time(),
            }

            checkpoint_path = self._get_checkpoint_path(task_id)
            tmp_path = checkpoint_path.with_suffix(".json.tmp")

            # 原子写入：先写 tmp 再替换
            tmp_path.write_text(
                json.dumps(checkpoint_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(checkpoint_path)
            return True
        except Exception as e:
            logger.warning("保存检查点失败: task_id=%s, err=%s", task_id, e)
            return False

    async def load_checkpoint(self, task_id: int) -> Optional[Dict[str, Any]]:
        checkpoint_path = self._get_checkpoint_path(task_id)
        if not checkpoint_path.exists():
            return None

        try:
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            completed_list = data.get("completed_indices", [])
            if not isinstance(completed_list, list):
                completed_list = []
            data["completed_indices"] = set(int(i) for i in completed_list)
            data["current_index"] = int(data.get("current_index", 0) or 0)
            return data
        except Exception as e:
            logger.warning("读取检查点失败: task_id=%s, err=%s", task_id, e)
            return None

    async def clear_checkpoint(self, task_id: int) -> bool:
        checkpoint_path = self._get_checkpoint_path(task_id)
        try:
            if checkpoint_path.exists():
                checkpoint_path.unlink()
            return True
        except Exception as e:
            logger.warning("清除检查点失败: task_id=%s, err=%s", task_id, e)
            return False

    async def has_checkpoint(self, task_id: int) -> bool:
        return self._get_checkpoint_path(task_id).exists()

    async def get_all_checkpoints(self) -> list[Dict[str, Any]]:
        checkpoints: list[Dict[str, Any]] = []
        try:
            for p in self.checkpoint_dir.glob("task_*.json"):
                try:
                    data = await self.load_checkpoint(int(p.stem.split("_")[-1]))
                    if data:
                        checkpoints.append(data)
                except Exception:
                    continue
        except Exception as e:
            logger.debug("遍历检查点失败: %s", e, exc_info=True)
        return checkpoints

    async def cleanup_old_checkpoints(self, max_age_hours: int = 72) -> int:
        """清理历史检查点文件（仅文件级别）。"""
        cleaned = 0
        max_age_seconds = max(0, int(max_age_hours)) * 3600
        now = time.time()
        try:
            for p in self.checkpoint_dir.glob("task_*.json"):
                try:
                    if now - p.stat().st_mtime > max_age_seconds:
                        p.unlink()
                        cleaned += 1
                except Exception:
                    continue
        except Exception as e:
            logger.debug("清理历史检查点失败: %s", e, exc_info=True)
        return cleaned

