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
from src.services.workspace.dashboard_snapshot import DashboardSnapshot
from src.ui.workspace_chart_animation_prefs import CHART_STAGGER_MS

if TYPE_CHECKING:
    from src.ui.pages.workspace_page import WorkspacePage

logger = logging.getLogger(__name__)


class WorkspaceLoadOrchestrator:
    """按 fast / slow 分阶段加载；统计卡与媒体库并行；图表独立 loading → reveal。"""

    STARTUP_DELAY_MS = 50
    DEBOUNCE_MS = 300

    def __init__(self, page: "WorkspacePage") -> None:
        self._page = page
        self._generation = 0
        self._pipeline_task: Optional[asyncio.Task] = None
        self._debounce_timer: Optional[QTimer] = None
        self._accounts_cache: list = []
        self._pipeline_include_media = True

    def apply_cached_snapshot_if_any(self) -> bool:
        svc = getattr(self._page, "dashboard_service", None)
        if svc is None:
            return False
        cached = svc.get_cached_snapshot()
        if cached is None:
            return False
        has_charts = bool(cached.publish)
        self._page._apply_snapshot(cached, charts=False, animate_entry=False)
        if has_charts and cached.account:
            self._page.reveal_platform_chart(cached.account, animate_entry=False)
        if has_charts and cached.publish:
            self._page.reveal_trend_chart(cached.publish, animate_entry=False)
        return True

    def schedule_startup_refresh(self) -> None:
        """show() 后延迟启动，避免与首帧绘制抢事件循环。"""
        self._page._schedule_base_page_timer(
            "workspace_orchestrator_start",
            self.STARTUP_DELAY_MS,
            self._start_pipeline_debounced,
        )

    def request_refresh(self, *, include_media: bool = False) -> None:
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
            self._start_pipeline(include_media=self._pipeline_include_media)

        self._debounce_timer.timeout.connect(_fire)
        self._debounce_timer.start(self.DEBOUNCE_MS)

    def _start_pipeline_debounced(self) -> None:
        self._pipeline_include_media = True
        self.request_refresh(include_media=True)

    def _start_pipeline(self, *, include_media: bool) -> None:
        if getattr(self._page, "dashboard_service", None) is None:
            return
        self._generation += 1
        gen = self._generation
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
        self._pipeline_task = get_async_task_registry().create_task(
            self._run_pipeline(gen, include_media=include_media),
            name="ui.workspace.pipeline",
            group="ui",
        )

    def cancel_pending(self) -> None:
        self._generation += 1
        if self._pipeline_task and not self._pipeline_task.done():
            self._pipeline_task.cancel()
        self._page._cancel_chart_pending_reveals()
        self._page._cancel_stats_pending_reveals()
        self._page._cancel_base_page_timer("workspace_orchestrator_start")
        self._page._cancel_base_page_timer("workspace_trend_reveal")
        if self._debounce_timer is not None:
            try:
                self._debounce_timer.stop()
                self._debounce_timer.deleteLater()
            except Exception:
                pass
            self._debounce_timer = None

    async def _refresh_media_stats(self) -> None:
        """与仪表盘查询并行刷新；UI 由 statsUpdated 信号更新。"""
        try:
            await get_media_library_stats_service().refresh()
        except Exception as e:
            logger.debug("媒体库统计刷新失败（可忽略）: %s", e)

    async def _run_pipeline(self, generation: int, *, include_media: bool) -> None:
        svc = self._page.dashboard_service
        use_entry_animation = not getattr(self._page, "_chart_first_reveal_done", False)
        use_stats_animation = not getattr(self._page, "_stats_first_reveal_done", False)

        had_media_cache = self._apply_media_cache_first()

        try:
            if use_entry_animation:
                self._page.begin_charts_loading()

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
            self._page._apply_snapshot(
                fast,
                charts=False,
                animate_entry=use_stats_animation,
            )

            if fast.account:
                self._page.reveal_platform_chart(
                    fast.account,
                    animate_entry=use_entry_animation,
                )

            reminders = await svc.get_online_account_publish_reminders(accounts=accounts)
            if generation != self._generation:
                return

            full = DashboardSnapshot(
                account=fast.account,
                publish=publish_stats,
                task=fast.task,
                reminders=reminders,
                loaded_at=monotonic(),
                partial=False,
            )
            svc.cache_snapshot(full)

            if publish_stats:
                self._page._apply_publish_stats(
                    publish_stats,
                    animate_entry=use_stats_animation,
                )

                def _reveal_trend() -> None:
                    if generation != self._generation:
                        return
                    self._page.reveal_trend_chart(
                        publish_stats,
                        animate_entry=use_entry_animation,
                    )

                if use_entry_animation and CHART_STAGGER_MS > 0:
                    self._page._schedule_base_page_timer(
                        "workspace_trend_reveal",
                        CHART_STAGGER_MS,
                        _reveal_trend,
                    )
                else:
                    _reveal_trend()
            elif use_entry_animation:
                self._page.reveal_trend_chart({}, animate_entry=False)

            if reminders and hasattr(self._page, "recent_activity"):
                self._page.recent_activity.set_account_reminders(reminders)

            self._page._chart_first_reveal_done = True
            self._page._stats_first_reveal_done = True
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("工作台数据管道失败: %s", e, exc_info=True)
            self._page._on_data_load_error(str(e))

    def _apply_media_cache_first(self) -> bool:
        stats = get_media_library_stats_cache().get()
        if stats is not None:
            self._page._on_media_stats_updated(stats, animate_entry=False)
            return True
        return False
