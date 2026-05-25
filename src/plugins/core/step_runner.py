"""
通用步骤运行器基类（所有平台插件共用）
文件路径：src/plugins/core/step_runner.py
功能：提供 StepRunner 的核心执行循环、重试、NeedsAction 补救、诊断截图与 selector probe，
      各平台通过配置（MAIN_PHASES / STEP_DISPLAY_NAMES / screenshot_platform）和少量覆写使用。
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, Any, Iterable, List, Optional, Sequence, Set, Tuple

from playwright.async_api import Page

from src.infrastructure.common.path_manager import PathManager
from src.plugins.core.interfaces.publish_plugin import PublishResult
from src.plugins.core.steps_base import BasePublishStep, NeedsAction, StepOutcome

logger = logging.getLogger(__name__)
USER_LOG = logging.getLogger("publish.user_log")


@dataclass
class BaseRunnerConfig:
    """步骤链运行配置基类，各平台继承并设置 screenshot_platform 默认值即可。"""

    max_step_retries: int = 3
    step_retry_delay_seconds: float = 1.5
    max_submit_retries: int = 2
    screenshot_on_error: bool = True
    screenshot_platform: str = "unknown"
    log_selector_probe: bool = True
    diagnostics_on_error: bool = True
    diagnostics_capture_html: bool = True
    diagnostics_capture_dom_summary: bool = True
    diagnostics_max_html_bytes: int = 5_000_000
    diagnostics_retention_days: int = 14


def _build_phase_index(
    phases: List[Tuple[str, ...]],
) -> Dict[str, int]:
    index: Dict[str, int] = {}
    for idx, group in enumerate(phases, start=1):
        for step_cls in group:
            index.setdefault(step_cls, idx)
    return index


class GenericStepRunner:
    """通用步骤链运行器，包含完整的重试/补救/诊断逻辑。

    子类需提供：
    * ``MAIN_PHASES``：阶段列表（用于日志 ``[步骤X/N]``）
    * ``STEP_DISPLAY_NAMES``：步骤类名 → 中文显示名
    * ``RunnerConfig`` 中正确的 ``screenshot_platform``

    可选覆写钩子：
    * ``_should_skip_browse(step_name)``：是否跳过步骤前拟人浏览（抖音封面步需跳过）
    * ``_get_retry_delay(step_name, attempt, base_delay)``：自定义重试间隔（快手上传用指数退避）
    * ``_resolve_submit_index(step_list)``：定位 SubmitStep 索引
    """

    MAIN_PHASES: List[Tuple[str, ...]] = []
    STEP_DISPLAY_NAMES: Dict[str, str] = {}

    def __init__(
        self,
        page: Page,
        file_path: str,
        metadata: Dict[str, Any],
        config: Optional[BaseRunnerConfig] = None,
        action_handlers: Optional[Dict[str, Callable[[], Sequence[BasePublishStep]]]] = None,
    ):
        self.page = page
        self.file_path = file_path
        self.metadata = metadata
        self.config = config or BaseRunnerConfig()
        self.action_handlers = action_handlers or {}
        self._submit_retry_count = 0

        self._phase_index = _build_phase_index(self.MAIN_PHASES)
        self._total_phases = len(self.MAIN_PHASES)

    # ------ 可覆写钩子 ------

    def _should_skip_browse(self, step_name: str) -> bool:
        """返回 True 时跳过该步骤前的拟人浏览。默认不跳过。"""
        return False

    def _get_retry_delay(self, step_name: str, attempt: int, base_delay: float) -> float:
        """返回本次重试的延迟秒数。默认固定间隔。"""
        return base_delay

    def _resolve_submit_index(self, step_list: list) -> Optional[int]:
        """在步骤列表中定位 SubmitStep 的索引。默认按类名匹配。"""
        for i, s in enumerate(step_list):
            if s.__class__.__name__ == "SubmitStep":
                return i
        return None

    def _get_step_max_retries(self, step_name: str, default_max_retries: int) -> int:
        """返回指定步骤的最大重试次数。默认使用全局配置。"""
        return default_max_retries

    # ------ 日志辅助 ------

    def _step_display_name(self, step_name: str) -> str:
        return self.STEP_DISPLAY_NAMES.get(step_name, step_name)

    def _phase_prefix(self, step_name: str) -> str:
        display = self._step_display_name(step_name)
        idx = self._phase_index.get(step_name)
        if idx is None:
            return f"[步骤 {display}]"
        return f"[步骤{idx}/{self._total_phases} {display}]"

    # ------ 核心执行循环 ------

    async def _retry_sleep(self, delay: float) -> None:
        """重试等待：先 sleep，再检查暂停事件（若用户已暂停则挂起直到继续/停止）。
        停止信号（CancelledError）会直接打断 sleep，无需额外处理。"""
        if delay > 0:
            await asyncio.sleep(delay)
        pause_event = self.metadata.get("pause_event")
        if pause_event is not None and hasattr(pause_event, "wait"):
            await pause_event.wait()

    async def run(self, steps: Iterable[BasePublishStep]) -> PublishResult:
        """按顺序执行步骤链；支持重试、NeedsAction 补救、诊断截图。"""
        step_list = list(steps)
        submit_index = self._resolve_submit_index(step_list)
        max_retries = max(1, self.config.max_step_retries)
        base_delay = max(0.0, self.config.step_retry_delay_seconds)

        i = 0
        while i < len(step_list):
            step = step_list[i]
            step_name = step.__class__.__name__
            step_max_retries = max(1, self._get_step_max_retries(step_name, max_retries))
            last_failure: Optional[PublishResult] = None
            prefix = self._phase_prefix(step_name)
            # 将当前步骤序号、总步骤数和日志前缀注入 metadata，供步骤内部日志动态使用
            _step_idx = self._phase_index.get(step_name)
            self.metadata["_step_idx"] = _step_idx
            self.metadata["_total_steps"] = self._total_phases
            self.metadata["_step_prefix"] = prefix

            for attempt in range(1, step_max_retries + 1):
                retry_delay = self._get_retry_delay(step_name, attempt, base_delay)

                if attempt > 1:
                    logger.info(f"--- 重试步骤: {step_name} (第 {attempt}/{step_max_retries} 次) ---")
                    USER_LOG.info(f"{prefix} ▶ 重试第{attempt}次")
                else:
                    logger.info(f"--- 正在执行步骤: {step_name} ---")
                    USER_LOG.info(f"{prefix} ▶ 执行中")

                if not self._should_skip_browse(step_name):
                    try:
                        from src.infrastructure.anti_risk.human_like import optional_browse_before_action
                        await asyncio.wait_for(
                            optional_browse_before_action(
                                self.page, self.metadata, self.metadata.get("anti_risk_config")
                            ),
                            timeout=3.0,
                        )
                    except Exception:
                        pass

                try:
                    outcome: StepOutcome = await step.execute(self.page, self.file_path, self.metadata)
                except Exception as e:
                    last_failure = PublishResult(success=False, error_message=f"{step_name} 执行异常: {e}")
                    if attempt >= step_max_retries:
                        diagnostic_path = await self._diagnose(step_name, reason=f"exception_after_retries: {e}")
                        short = str(e)[:50] + ("..." if len(str(e)) > 50 else "")
                        USER_LOG.warning(f"{prefix} ✗ 失败: {short}")
                        return PublishResult(
                            success=False,
                            error_message=f"{step_name} 执行异常（已重试 {step_max_retries} 次）: {e}",
                            failed_step=step_name,
                            diagnostic_path=diagnostic_path,
                        )
                    logger.warning(f"{step_name} 第 {attempt} 次执行异常，剩余 {step_max_retries - attempt} 次重试: {e}")
                    await self._retry_sleep(retry_delay)
                    continue

                # None → 本步成功
                if outcome is None:
                    USER_LOG.info(f"{prefix} ✓ 完成")
                    try:
                        from src.infrastructure.anti_risk.delays import step_interval
                        await step_interval(self.page, self.metadata, self.metadata.get("anti_risk_config"))
                    except Exception:
                        pass
                    i += 1
                    break

                # NeedsAction → 补救
                if isinstance(outcome, NeedsAction):
                    handled = await self._handle_action(outcome)
                    if not handled:
                        diagnostic_path = await self._diagnose(step_name, reason=f"needs_action_unhandled: {outcome.action}")
                        USER_LOG.warning(f"{prefix} ✗ 失败: 需要补救但未实现")
                        return PublishResult(
                            success=False,
                            error_message=outcome.message or f"需要处理动作但未实现: {outcome.action}",
                            failed_step=step_name,
                            diagnostic_path=diagnostic_path,
                        )

                    USER_LOG.info(f"{prefix} ▶ 需补救({outcome.action})，执行补救后重试")
                    handler = self.action_handlers.get(outcome.action)
                    if handler:
                        for h_step in handler():
                            h_name = h_step.__class__.__name__
                            logger.info(f"--- 补救步骤: {h_name} (for {outcome.action}) ---")
                            try:
                                h_outcome = await h_step.execute(self.page, self.file_path, self.metadata)
                            except Exception as e:
                                diagnostic_path = await self._diagnose(h_name, reason=f"handler_exception: {e}")
                                USER_LOG.warning(f"{self._phase_prefix(h_name)} ✗ 失败: 补救步骤异常")
                                return PublishResult(
                                    success=False,
                                    error_message=f"{h_name} 执行异常: {e}",
                                    failed_step=h_name,
                                    diagnostic_path=diagnostic_path,
                                )

                            if isinstance(h_outcome, PublishResult):
                                if not h_outcome.success:
                                    diagnostic_path = await self._diagnose(h_name, reason=h_outcome.error_message or "failed")
                                    short = (h_outcome.error_message or "")[:50]
                                    USER_LOG.warning(f"{self._phase_prefix(h_name)} ✗ 失败: {short}")
                                    return PublishResult(success=False, error_message=h_outcome.error_message, failed_step=h_name, diagnostic_path=diagnostic_path)
                                return h_outcome
                            if isinstance(h_outcome, NeedsAction):
                                diagnostic_path = await self._diagnose(h_name, reason=f"nested_needs_action: {h_outcome.action}")
                                USER_LOG.warning(f"{self._phase_prefix(h_name)} ✗ 失败: 返回未处理动作")
                                return PublishResult(
                                    success=False,
                                    error_message=h_outcome.message or f"{h_name} 返回未处理动作: {h_outcome.action}",
                                    failed_step=h_name,
                                    diagnostic_path=diagnostic_path,
                                )

                    if submit_index is not None:
                        if self._submit_retry_count >= self.config.max_submit_retries:
                            diagnostic_path = await self._diagnose(step_name, reason="submit_retry_exceeded")
                            USER_LOG.warning(f"{prefix} ✗ 失败: 提交重试次数已达上限")
                            return PublishResult(
                                success=False,
                                error_message=outcome.message or "已触发补救，但提交重试次数已达上限",
                                failed_step=step_name,
                                diagnostic_path=diagnostic_path,
                            )
                        self._submit_retry_count += 1
                        logger.info(f"准备重试提交: {self._submit_retry_count}/{self.config.max_submit_retries}")
                        i = submit_index
                    else:
                        i += 1
                    break

                # PublishResult → 成功直接返回；失败重试
                if isinstance(outcome, PublishResult):
                    if outcome.success:
                        USER_LOG.info(f"{prefix} ✓ 完成")
                        return outcome
                    last_failure = outcome
                    if attempt >= step_max_retries:
                        diagnostic_path = await self._diagnose(step_name, reason=outcome.error_message or "failed")
                        short = (outcome.error_message or "未知原因")[:50]
                        USER_LOG.warning(f"{prefix} ✗ 失败: {short}")
                        return PublishResult(
                            success=False,
                            error_message=f"{step_name} 失败（已重试 {step_max_retries} 次）: {outcome.error_message or '未知原因'}",
                            failed_step=step_name,
                            diagnostic_path=diagnostic_path or getattr(outcome, "diagnostic_path", None),
                        )
                    logger.warning(f"{step_name} 第 {attempt} 次返回失败，剩余 {step_max_retries - attempt} 次重试: {outcome.error_message}")
                    await self._retry_sleep(retry_delay)
                    continue

                # 未知结果类型
                last_failure = PublishResult(success=False, error_message=f"{step_name} 返回未知结果类型，流程中断", failed_step=step_name)
                if attempt >= step_max_retries:
                    diagnostic_path = await self._diagnose(step_name, reason="unknown_outcome")
                    last_failure.diagnostic_path = diagnostic_path
                    USER_LOG.warning(f"{prefix} ✗ 失败: 未知结果类型")
                    return last_failure
                logger.warning(f"{step_name} 返回未知结果类型，剩余 {step_max_retries - attempt} 次重试")
                await self._retry_sleep(retry_delay)

        return PublishResult(success=False, error_message="发布流程异常中断：步骤链未返回明确结果")

    # ------ NeedsAction 补救 ------

    async def _handle_action(self, action: NeedsAction) -> bool:
        if action.action in ("need_cover", "need_supplement"):
            return True
        if action.action == "need_retry":
            return self._submit_retry_count < self.config.max_submit_retries
        return False

    # ------ 诊断 ------

    async def _diagnose(self, step_name: str, reason: str) -> Optional[str]:
        if self.config.log_selector_probe:
            try:
                probes = self.metadata.get("selector_probes") or {}
                if isinstance(probes, dict) and probes:
                    for k, sel in list(probes.items())[:20]:
                        try:
                            cnt = await self.page.locator(str(sel)).count()
                            logger.info(f"[probe] {k} -> {cnt} ({sel})")
                        except Exception:
                            continue
            except Exception:
                pass

        if self.config.diagnostics_on_error:
            try:
                from src.plugins.core.diagnostics import PageDiagnosticsConfig, PageDomDiagnosticPlugin

                diag_config = PageDiagnosticsConfig(
                    enabled=True,
                    capture_html=self.config.diagnostics_capture_html,
                    capture_dom_summary=self.config.diagnostics_capture_dom_summary,
                    max_html_bytes=self.config.diagnostics_max_html_bytes,
                    retention_days=self.config.diagnostics_retention_days,
                )
                result = await PageDomDiagnosticPlugin(diag_config).capture(
                    self.page,
                    platform=self.config.screenshot_platform,
                    step_name=step_name,
                    reason=reason,
                    metadata=self.metadata,
                    selector_probes=self.metadata.get("selector_probes") or {},
                )
                if result:
                    return result.path
            except Exception as e:
                logger.warning("page diagnostics capture failed: %s", e)

        if not self.config.screenshot_on_error:
            return None

        try:
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            url = ""
            try:
                url = self.page.url
            except Exception:
                pass

            out_dir = PathManager.get_debug_screenshots_dir(self.config.screenshot_platform)
            out_dir.mkdir(parents=True, exist_ok=True)
            safe_reason = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in reason])[:80]
            path = out_dir / f"{now}_{step_name}_{safe_reason}.png"
            await self.page.screenshot(path=str(path), full_page=True)
            diagnostic_path = str(path)
            logger.info(f"已保存诊断截图: {path} (url={url})")
            return diagnostic_path
        except Exception as e:
            logger.warning("诊断时页面不可用或已关闭: %s", e)
