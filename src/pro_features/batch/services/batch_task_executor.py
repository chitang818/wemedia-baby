"""
批量任务执行器（带断点续传）
文件路径：src/pro_features/batch/services/batch_task_executor.py

说明：
- 主要用于“记住批量发布进度”（通过 CheckpointManagerAsync 持久化）。
- 本实现重点解决：原文件语法损坏导致无法导入的问题。
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple, List

from PySide6.QtCore import QObject, Signal

from src.infrastructure.common.pipeline.base_filter import PublishRequest
from src.services.publish.pipeline.pipeline_factory_async import PipelineFactoryAsync as PipelineFactory
from .checkpoint_manager_async import CheckpointManagerAsync
from .retry_strategy import RetryStrategy, is_retryable_error

logger = logging.getLogger(__name__)


@dataclass
class BatchTaskProgressEvent:
    task_id: int
    current: int
    total: int
    completed: int
    failed: int
    current_file: Optional[str] = None


class BatchTaskExecutor(QObject):
    # UI 层监听
    progress_updated = Signal(object)  # BatchTaskProgressEvent
    task_completed = Signal(int, int, int)  # (task_id, completed, failed)
    task_failed = Signal(int, str)  # (task_id, error_message)

    def __init__(
        self,
        task_manager: Any,
        pipeline_factory: Any = None,
        retry_count: int = 3,
        delay_seconds: int = 5,
        enable_random_delay: bool = True,
        random_delay_range: Tuple[int, int] = (3, 10),
        enable_checkpoint: bool = True,
    ):
        super().__init__()
        self.task_manager = task_manager
        self.pipeline_factory = pipeline_factory or PipelineFactory
        self.logger = logging.getLogger(__name__)

        self.retry_strategy = RetryStrategy(max_retries=retry_count)
        self.retry_count = int(retry_count)
        self.delay_seconds = int(delay_seconds)
        self.enable_random_delay = bool(enable_random_delay)
        self.random_delay_range = random_delay_range
        self.enable_checkpoint = bool(enable_checkpoint)

        self.checkpoint_manager = CheckpointManagerAsync() if enable_checkpoint else None

        # 运行控制：同一个 task_id 是否继续
        self._running_flags: Dict[int, bool] = {}
        self._flags_lock = threading.Lock()

    def _set_running(self, task_id: int, running: bool) -> None:
        with self._flags_lock:
            self._running_flags[int(task_id)] = bool(running)

    def _is_running(self, task_id: int) -> bool:
        with self._flags_lock:
            return bool(self._running_flags.get(int(task_id), False))

    def pause_task(self, task_id: int) -> bool:
        """请求暂停：标记 running=false，由执行线程在循环点位暂停并保存检查点。"""
        self._set_running(task_id, False)
        return True

    def resume_task(self, task_id: int) -> bool:
        """请求恢复：仅标记 running=true；实际执行通常需要再次 start_task。"""
        self._set_running(task_id, True)
        return True

    def cancel_task(self, task_id: int) -> bool:
        """取消等价于暂停并终止后续索引处理。"""
        self._set_running(task_id, False)
        return True

    def shutdown(self) -> None:
        """停止所有运行中的 task（仅影响暂停点）。"""
        with self._flags_lock:
            for tid in list(self._running_flags.keys()):
                self._running_flags[tid] = False

    def execute_task(self, task_id: int) -> None:
        """线程入口：同步方法包装异步执行。"""
        try:
            asyncio.run(self._execute_task_async(task_id))
        except Exception as e:
            self.logger.error("批量任务执行失败（task_id=%s）: %s", task_id, e, exc_info=True)
            try:
                self.task_failed.emit(int(task_id), str(e))
            except Exception:
                pass

    async def _maybe_await(self, obj: Any) -> Any:
        """兼容：允许 task_manager 的方法是 async 或 sync。"""
        if asyncio.iscoroutine(obj):
            return await obj
        return obj

    async def _update_task_status_safe(self, task_id: int, status: str, completed: int, failed: int) -> None:
        try:
            if hasattr(self.task_manager, "update_task_status"):
                res = self.task_manager.update_task_status(
                    task_id=task_id,
                    status=status,
                    completed_count=completed,
                    failed_count=failed,
                )
                await self._maybe_await(res)
        except Exception as e:
            self.logger.debug("更新任务状态失败（忽略）: %s", e)

    async def _execute_task_async(self, task_id: int) -> None:
        task_id = int(task_id)
        self._set_running(task_id, True)

        task = await self._maybe_await(self.task_manager.get_task_by_id(task_id))
        if not task:
            self.task_failed.emit(task_id, "任务不存在")
            return

        # 状态允许：pending / running / paused
        status = str(task.get("status", "pending"))
        if status not in ("pending", "running", "paused"):
            self.task_failed.emit(task_id, f"不允许的任务状态: {status}")
            return

        script_config = task.get("script_config") or {}
        if isinstance(script_config, str):
            try:
                script_config = json.loads(script_config)
            except Exception:
                script_config = {}
        if not isinstance(script_config, dict):
            script_config = {}

        videos = script_config.get("videos") or []
        if not isinstance(videos, list):
            videos = []

        total = len(videos)
        completed = 0
        failed = 0

        # resume
        completed_indices: Set[int] = set()
        start_index = 0
        if self.enable_checkpoint and self.checkpoint_manager:
            ck = await self.checkpoint_manager.load_checkpoint(task_id)
            if ck:
                completed_indices = ck.get("completed_indices") or set()
                if not isinstance(completed_indices, set):
                    completed_indices = set(completed_indices)
                start_index = int(ck.get("current_index", 0) or 0)

        # pipeline：一次构建，循环复用
        user_id = int(getattr(self.task_manager, "user_id", task.get("user_id", 1)) or 1)
        pipeline = await self.pipeline_factory.create_pipeline(user_id=user_id)

        account_name = str(task.get("account_name") or task.get("platform_username") or "")
        platform = str(task.get("platform") or "")
        task_type = str(task.get("task_type") or script_config.get("task_type") or "video")

        headless = bool(script_config.get("headless", True))
        speed_rate = float(script_config.get("speed_rate", 1.0) or 1.0)
        privacy_settings = script_config.get("privacy_settings")
        scheduled_publish_time = script_config.get("scheduled_publish_time")
        close_browser_after = bool(script_config.get("close_browser_after", True))

        # 每个视频的重试次数/间隔（尽力从任务字段读取）
        task_retry_count = int(task.get("retry_count", self.retry_count) or self.retry_count)
        retry_delay_seconds = int(task.get("delay_seconds", self.delay_seconds) or self.delay_seconds)

        for index in range(start_index, total):
            if not self._is_running(task_id):
                # 暂停：保留检查点
                await self._update_task_status_safe(task_id, "paused", completed, failed)
                self.task_completed.emit(task_id, completed, failed)
                return

            if index in completed_indices:
                # 已完成：刷新进度
                self.progress_updated.emit(
                    BatchTaskProgressEvent(
                        task_id=task_id,
                        current=index + 1,
                        total=total,
                        completed=completed,
                        failed=failed,
                        current_file=videos[index].get("file_path") if isinstance(videos[index], dict) else None,
                    )
                )
                continue

            video_config = videos[index] if isinstance(videos[index], dict) else {}
            file_path = video_config.get("file_path") or ""
            title = video_config.get("title")
            description = video_config.get("description")
            tags = video_config.get("tags")
            if isinstance(tags, list):
                tags = ",".join(str(x) for x in tags)
            elif tags is None:
                tags = None
            else:
                tags = str(tags)

            publish_type = task_type if task_type in ("video", "image") else "video"

            ok = False
            last_error: Optional[str] = None

            for attempt in range(task_retry_count + 1):
                try:
                    # PublishPipeline.execute 返回 List[PublishResult]
                    request = PublishRequest(
                        user_id=user_id,
                        account_name=account_name,
                        platform=platform,
                        file_path=file_path,
                        publish_type=publish_type,
                        title=title,
                        description=description,
                        tags=tags,
                        headless=headless,
                        speed_rate=speed_rate,
                        scheduled_publish_time=scheduled_publish_time,
                        privacy_settings=privacy_settings,
                        close_browser_after=close_browser_after,
                    )

                    results = await pipeline.execute(request)
                    ok = bool(results and results[0].success)
                    if ok:
                        last_error = None
                        break

                    # 管道返回失败（非异常）：记录错误并等待退避后重试
                    last_error = (results[0].error_message if results and results[0].error_message else "发布失败")
                    if attempt < task_retry_count:
                        delay = self.retry_strategy.get_retry_delay(attempt)
                        await asyncio.sleep(delay)
                except Exception as e:
                    last_error = str(e)
                    if attempt >= task_retry_count or not is_retryable_error(e):
                        break

                    delay = self.retry_strategy.get_retry_delay(attempt)
                    await asyncio.sleep(delay)

            if ok:
                completed += 1
                completed_indices.add(index)
            else:
                failed += 1

            # 保存检查点：成功时推进到下一条；失败时保留当前索引以便恢复时重试
            if self.enable_checkpoint and self.checkpoint_manager:
                next_index = index + 1 if ok else index
                await self.checkpoint_manager.save_checkpoint(task_id, completed_indices, next_index)

            # 通知 UI：进度 + 可选错误（UI 这里不展示 error，只写日志时可扩展）
            self.progress_updated.emit(
                BatchTaskProgressEvent(
                    task_id=task_id,
                    current=index + 1,
                    total=total,
                    completed=completed,
                    failed=failed,
                    current_file=file_path,
                )
            )

            # 非暂停情况下的节奏控制（简化）
            delay_seconds = retry_delay_seconds
            if self.enable_random_delay:
                delay_seconds = random.randint(self.random_delay_range[0], self.random_delay_range[1])
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)

        # 走到这里：处理完所有索引
        await self._update_task_status_safe(task_id, "completed", completed, failed)
        if self.enable_checkpoint and self.checkpoint_manager:
            await self.checkpoint_manager.clear_checkpoint(task_id)

        self.task_completed.emit(task_id, completed, failed)

