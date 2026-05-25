"""
工作台分阶段加载编排器
"""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QTimer

from src.infrastructure.common.async_task_registry import get_async_task_registry
from src.services.material.media_library_stats_cache import get_media_library_stats_cache
from src.services.material.media_library_stats_service import get_media_library_stats_service
from src.services.material.media_library_stats_types import MediaLibraryStats
from src.services.workspace.dashboard_snapshot import DashboardSnapshot

if TYPE_CHECKING:
    from src.ui.pages.workspace_page import WorkspacePage

logger = logging.getLogger(__name__)


class WorkspaceLoadOrchestrator:
    """按 fast / slow 分阶段加载；统计卡与媒体库并行。"""

    STARTUP_DELAY_MS = 50
    DEBOUNCE_MS = 300

    def __init__(self, page: "WorkspacePage") -> None:
        self._page = page
        self._generation = 0
        self._pipeline_task: Optional[asyncio.Task] = None
        self._debounce_timer: Optional[QTimer] = None
        self._accounts_cache: list = []
        self._pipeline_include_media = True
        self._startup_started = False
        self._cached_snapshot_applied = False
        self._latest_snapshot: Optional[DashboardSnapshot] = None

    def apply_cached_snapshot_if_any(self) -> bool:
        return self.apply_cached_first_paint()

    def get_latest_snapshot(self) -> Optional[DashboardSnapshot]:
        return self._latest_snapshot

    def apply_cached_first_paint(self) -> bool:
        svc = getattr(self._page, "dashboard_service", None)
        if svc is None:
            return False
        dashboard_snapshot = svc.get_cached_snapshot() or svc.get_persistent_snapshot()
        media_cache = get_media_library_stats_cache()
        media_stats = media_cache.get_memory() or media_cache.get_persistent()
        if dashboard_snapshot is None or media_stats is None:
            return False
        self._latest_snapshot = dashboard_snapshot
        self._page.apply_stats_batch(
            dashboard_snapshot,
            media_stats,
            animate_entry=False,
            reminders=True,
        )
        self._cached_snapshot_applied = True
        return True

    def schedule_startup_refresh(self) -> None:
        """show() 后延迟启动，避免与首帧绘制抢事件循环。"""
        if self._startup_started:
            return
        self._startup_started = True
        self._page._schedule_base_page_timer(
            "workspace_orchestrator_start",
            self.STARTUP_DELAY_MS,
            self.startup_load,
        )

    def startup_load(self) -> None:
        """首次加载专用路径：不经过常规刷新 debounce。"""
        if getattr(self._page, "dashboard_service", None) is None:
            return
        self._generation += 1
        gen = self._generation
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
        self._pipeline_task = get_async_task_registry().create_task(
            self._run_startup_pipeline(gen),
            name="ui.workspace.startup",
            group="ui",
        )

    def request_refresh(self, *, include_media: bool = False, reason: str = "full") -> None:
        """事件/定时器触发的刷新（debounce）。"""
        self._pipeline_include_media = include_media
        if self._debounce_timer is not None:
            try:
                self._debounce_timer.stop()
                self._debounce_timer.deleteLater()
            except Exception:
                pass
        self._debounce_timer = QTimer(self._page)
        self._debounce_timer.setSingleShot(True)

        def _fire() -> None:
            self._debounce_timer = None
            self._start_pipeline(include_media=self._pipeline_include_media, reason=reason)

        self._debounce_timer.timeout.connect(_fire)
        self._debounce_timer.start(self.DEBOUNCE_MS)

    def _start_pipeline_debounced(self) -> None:
        self._pipeline_include_media = True
        self.request_refresh(include_media=True)

    def _start_pipeline(self, *, include_media: bool, reason: str = "full") -> None:
        if getattr(self._page, "dashboard_service", None) is None:
            return
        self._generation += 1
        gen = self._generation
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
        self._pipeline_task = get_async_task_registry().create_task(
            self._run_pipeline(gen, include_media=include_media),
            name=f"ui.workspace.pipeline.{reason}",
            group="ui",
        )

    def cancel_pending(self) -> None:
        self._generation += 1
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
        self._page._cancel_chart_pending_reveals()
        self._page._cancel_stats_pending_reveals()
        self._page._cancel_base_page_timer("workspace_orchestrator_start")
        self._page._cancel_base_page_timer("workspace_account_platform_prewarm")
        if self._debounce_timer is not None:
            try:
                self._debounce_timer.stop()
                self._debounce_timer.deleteLater()
            except Exception:
                pass
            self._debounce_timer = None

    async def _refresh_media_stats(self):
        """与仪表盘查询并行刷新；UI 由 statsUpdated 信号更新。"""
        try:
            return await get_media_library_stats_service().refresh()
        except Exception as e:
            logger.debug("媒体库统计刷新失败（可忽略）: %s", e)
            return None

    async def _run_pipeline(self, generation: int, *, include_media: bool) -> None:
        svc = self._page.dashboard_service
        use_stats_animation = not getattr(self._page, "_stats_first_reveal_done", False)

        had_media_cache = self._apply_media_cache_first()

        try:
            need_media_loading = include_media and not had_media_cache
            if use_stats_animation:
                self._page.begin_stats_loading(top=True, media=need_media_loading)
            elif need_media_loading:
                self._page.begin_stats_loading(top=False, media=True)

            coros = [svc.load_fast(), svc.get_publish_statistics()]
            if include_media:
                coros.append(self._refresh_media_stats())

            gathered = await asyncio.gather(*coros)
            if generation != self._generation:
                return

            fast_result = gathered[0]
            publish_stats = gathered[1]

            fast, accounts = fast_result
            self._accounts_cache = accounts

            reminders = await svc.get_account_publish_reminders(accounts=accounts)
            if generation != self._generation:
                return

            full = DashboardSnapshot(
                account=fast.account,
                publish=publish_stats or {},
                task=fast.task,
                reminders=reminders,
                loaded_at=monotonic(),
                partial=False,
            )
            self._latest_snapshot = full
            svc.cache_snapshot(full)

            self._page._apply_snapshot(
                full,
                animate_entry=use_stats_animation,
                reminders=True,
            )

            self._page._stats_first_reveal_done = True
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("工作台数据管道失败: %s", e, exc_info=True)
            self._page._on_data_load_error(str(e))

    async def _run_startup_pipeline(self, generation: int) -> None:
        svc = self._page.dashboard_service
        had_stats_cache = self._cached_snapshot_applied
        media_cache_obj = get_media_library_stats_cache()
        media_cache = media_cache_obj.get() or media_cache_obj.get_persistent()
        had_media_cache = media_cache is not None
        use_stats_animation = not (had_stats_cache and had_media_cache)

        try:
            if not had_stats_cache or not had_media_cache:
                self._page.begin_stats_loading(top=True, media=True)

            self._page.set_media_stats_update_hold(True)
            media_coro = asyncio.sleep(0, result=media_cache or MediaLibraryStats())
            fast_result, publish_stats, media_stats = await asyncio.gather(
                svc.load_fast(),
                svc.get_publish_statistics(),
                media_coro,
            )
            if generation != self._generation:
                self._page.set_media_stats_update_hold(False)
                return
            fast, accounts = fast_result
            self._accounts_cache = accounts

            reminders = await svc.get_account_publish_reminders(accounts=accounts)
            if generation != self._generation:
                self._page.set_media_stats_update_hold(False)
                return

            full = DashboardSnapshot(
                account=fast.account,
                publish=publish_stats or {},
                task=fast.task,
                reminders=reminders,
                loaded_at=monotonic(),
                partial=False,
            )
            self._latest_snapshot = full
            svc.cache_snapshot(full)

            self._page._apply_snapshot(
                full,
                animate_entry=use_stats_animation,
                reminders=True,
            )

            held_media_stats = self._page.take_held_media_stats()
            self._page.set_media_stats_update_hold(False)
            self._page._on_media_stats_updated(
                held_media_stats or media_stats,
                animate_entry=use_stats_animation,
            )

            if fast.account:
                self._page.apply_account_platform_cache_if_available()

            self._cached_snapshot_applied = True
            self._page._stats_first_reveal_done = True

            get_async_task_registry().create_task(
                self._refresh_media_stats(),
                name="ui.workspace.media_refresh",
                group="ui",
            )
        except asyncio.CancelledError:
            self._page.set_media_stats_update_hold(False)
            raise
        except Exception as e:
            self._page.set_media_stats_update_hold(False)
            logger.error("工作台首次加载管道失败: %s", e, exc_info=True)
            self._page._on_data_load_error(str(e))

    def _apply_media_cache_first(self) -> bool:
        cache = get_media_library_stats_cache()
        stats = cache.get() or cache.get_persistent()
        if stats is not None:
            self._page._on_media_stats_updated(stats, animate_entry=False)
            return True
        return False
