"""
批量任务调度器
文件路径：src/pro_features/batch/services/task_scheduler.py

用途：
- 通过 APScheduler 在指定时间/cron/间隔触发 BatchTaskExecutor.execute_task
- 为了避免依赖缺失导致导入失败，本模块内部做了可选导入与降级处理
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(self):
        self._scheduler = None
        self._apscheduler_available = False

        # APScheduler 不是本项目必需依赖：可用则启用，否则提供降级实现
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            self._scheduler = BackgroundScheduler()
            self._scheduler.start()
            self._apscheduler_available = True
        except Exception as e:
            logger.warning("APScheduler 不可用，TaskScheduler 将降级为无调度器：%s", e)

    def add_job(
        self,
        func: Callable,
        trigger_type: str = "date",
        run_date: Optional[datetime] = None,
        interval_seconds: Optional[int] = None,
        cron_expression: Optional[str] = None,
        job_id: Optional[str] = None,
        **kwargs,
    ) -> Optional[str]:
        if not self._apscheduler_available or self._scheduler is None:
            logger.warning("调度器不可用，add_job 被忽略")
            return None

        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger
        from apscheduler.triggers.interval import IntervalTrigger

        if trigger_type == "date":
            if not run_date:
                raise ValueError("trigger_type='date' 时必须提供 run_date")
            trigger = DateTrigger(run_date=run_date)
        elif trigger_type == "interval":
            if interval_seconds is None:
                raise ValueError("trigger_type='interval' 时必须提供 interval_seconds")
            trigger = IntervalTrigger(seconds=interval_seconds)
        elif trigger_type == "cron":
            if not cron_expression:
                raise ValueError("trigger_type='cron' 时必须提供 cron_expression")
            trigger = CronTrigger.from_crontab(cron_expression)
        else:
            raise ValueError(f"未知 trigger_type: {trigger_type}")

        job = self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            kwargs=kwargs,
        )
        return job.id

    def remove_job(self, job_id: str) -> bool:
        if not self._apscheduler_available or self._scheduler is None:
            return False
        try:
            self._scheduler.remove_job(job_id)
            return True
        except Exception:
            return False

    def get_job(self, job_id: str) -> Optional[Any]:
        if not self._apscheduler_available or self._scheduler is None:
            return None
        try:
            return self._scheduler.get_job(job_id)
        except Exception:
            return None

    def get_jobs(self) -> list[Any]:
        if not self._apscheduler_available or self._scheduler is None:
            return []
        try:
            return self._scheduler.get_jobs()
        except Exception:
            return []

    def pause_job(self, job_id: str) -> bool:
        if not self._apscheduler_available or self._scheduler is None:
            return False
        try:
            self._scheduler.pause_job(job_id)
            return True
        except Exception:
            return False

    def resume_job(self, job_id: str) -> bool:
        if not self._apscheduler_available or self._scheduler is None:
            return False
        try:
            self._scheduler.resume_job(job_id)
            return True
        except Exception:
            return False

    def schedule_batch_task(
        self,
        task_id: int,
        task_executor: Any,
        run_date: Optional[datetime] = None,
        cron_expression: Optional[str] = None,
    ) -> Optional[str]:
        """
        约定：触发时调用 task_executor.execute_task(task_id)
        """
        if run_date is not None:
            job_id = f"batch_task_{task_id}_{run_date.timestamp()}"
            return self.add_job(
                func=task_executor.execute_task,
                trigger_type="date",
                run_date=run_date,
                job_id=job_id,
                task_id=task_id,
            )

        if cron_expression is not None:
            job_id = f"batch_task_{task_id}_cron"
            return self.add_job(
                func=task_executor.execute_task,
                trigger_type="cron",
                cron_expression=cron_expression,
                job_id=job_id,
                task_id=task_id,
            )

        logger.warning("schedule_batch_task 缺少 run_date/cron_expression，忽略")
        return None

    def cancel_scheduled_task(self, task_id: int) -> bool:
        if not self._apscheduler_available or self._scheduler is None:
            return False
        try:
            jobs = self._scheduler.get_jobs()
            for job in jobs:
                if str(job.id).startswith(f"batch_task_{task_id}_"):
                    self._scheduler.remove_job(job.id)
            return True
        except Exception:
            return False

    def shutdown(self) -> None:
        if not self._apscheduler_available or self._scheduler is None:
            return
        try:
            self._scheduler.shutdown()
        except Exception:
            pass

