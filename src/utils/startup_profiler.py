"""
启动耗时埋点工具
通过环境变量 ENABLE_STARTUP_PROFILER=1 开启，输出各阶段耗时汇总到日志。
"""
import os
import time
import logging

_marks: list[tuple[str, float]] = []
_enabled: bool | None = None


def is_enabled() -> bool:
    global _enabled
    if _enabled is None:
        _enabled = os.environ.get("ENABLE_STARTUP_PROFILER", "").strip() in ("1", "true", "yes")
    return _enabled


def mark(stage: str) -> None:
    """记录当前时间点，stage 为阶段名称。"""
    if not is_enabled():
        return
    _marks.append((stage, time.perf_counter()))


def summary() -> str:
    """根据已记录的 mark 计算各阶段耗时，返回可打印的字符串。"""
    if not is_enabled() or len(_marks) < 2:
        return ""
    lines = ["[启动耗时]"]
    for i in range(1, len(_marks)):
        name_prev, t_prev = _marks[i - 1]
        name_curr, t_curr = _marks[i]
        delta_ms = (t_curr - t_prev) * 1000
        lines.append(f"  {name_prev} -> {name_curr}: {delta_ms:.0f} ms")
    total_ms = (_marks[-1][1] - _marks[0][1]) * 1000
    lines.append(f"  总计: {total_ms:.0f} ms")
    return "\n".join(lines)


def log_summary() -> None:
    """将 summary() 输出到 main logger。"""
    if not is_enabled():
        return
    s = summary()
    if s:
        logging.getLogger("main").info("\n%s", s)


# ---------------------------------------------------------------------------
# 页面首次加载耗时（与启动埋点独立，避免污染启动汇总）
# 环境变量 ENABLE_PAGE_LOAD_PROFILER=1 开启
# ---------------------------------------------------------------------------

_page_load_enabled: bool | None = None


def is_page_load_profiler_enabled() -> bool:
    global _page_load_enabled
    if _page_load_enabled is None:
        _page_load_enabled = os.environ.get("ENABLE_PAGE_LOAD_PROFILER", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
    return _page_load_enabled


def log_page_create_timing(page_name: str, elapsed_s: float) -> None:
    """记录 PageFactory 创建并加入堆栈的耗时（不含懒加载 _setup_content）。"""
    if not is_page_load_profiler_enabled():
        return
    logging.getLogger("ui.perf").info(
        "[页面耗时] create_page+addWidget %s: %.0f ms",
        page_name,
        elapsed_s * 1000,
    )


def log_page_setup_content_timing(label: str, elapsed_s: float) -> None:
    """记录 BasePage 首次 _setup_content 耗时。"""
    if not is_page_load_profiler_enabled():
        return
    logging.getLogger("ui.perf").info(
        "[页面耗时] _setup_content %s: %.0f ms",
        label,
        elapsed_s * 1000,
    )
