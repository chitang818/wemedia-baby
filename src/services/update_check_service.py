"""
更新检查服务
文件路径：src/services/update_check_service.py
功能：从 Gitee 拉取 version.json，与本地版本比较，返回是否有更新及下载链接。
下载链接以 Gitee 仓库 version.json 中的 download_url / download_url_feishu 为准；未配置时使用下方默认飞书说明页。
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Gitee 仓库 version.json 的 raw 地址（版本与下载链接均由此获取，修改库中 version.json 即可生效）
VERSION_JSON_URL_BASE = "https://gitee.com/chitangsuper/wemedia-baby/raw/main/version.json"

# version.json 未提供下载地址时的兜底（与发版默认一致）
DEFAULT_UPDATE_DOWNLOAD_URL = "https://my.feishu.cn/docx/DpotdqxU8owf15xD54oc6P9KnWf"

# 连接超时（秒）：连不上尽快失败
CONNECT_TIMEOUT = 5
# 总超时（秒）：覆盖 Gitee raw 在国内约 7–11s 的响应
TOTAL_TIMEOUT = 12
# 向后兼容旧引用
CHECK_TIMEOUT = TOTAL_TIMEOUT

# 成功结果内存缓存 TTL（秒）
CACHE_TTL_SECONDS = 300
# 错误结果短缓存 TTL（秒），抑制弱网抖动时连续打满 Gitee
ERROR_CACHE_TTL_SECONDS = 45

# 是否启用并发单飞（测试或排障时可关）
ENABLE_INFLIGHT_DEDUP = True

_session: Optional[aiohttp.ClientSession] = None
_session_lock: Optional[asyncio.Lock] = None
_cache_result: Optional["UpdateCheckResult"] = None
_cache_time: float = 0.0
_fetch_lock: Optional[asyncio.Lock] = None
_inflight_task: Optional[asyncio.Task] = None


@dataclass
class UpdateCheckResult:
    """更新检查结果"""

    has_update: bool
    current_version: str
    remote_version: Optional[str] = None
    notes: str = ""
    download_url: str = ""
    error: Optional[str] = None


def _parse_version(version_str: str) -> Optional[tuple]:
    """将版本字符串解析为 (major, minor, patch)，兼容 '1.0.0' 与 'v1.0.0'。"""
    if not version_str:
        return None
    s = version_str.strip().lstrip("vV")
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", s)
    if not m:
        return None
    try:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _compare_versions(current: str, remote: str) -> int:
    """
    比较版本号。返回正数表示 remote > current，0 表示相等，负数表示 remote < current。
    无法解析的版本不参与比较，避免误报有更新。
    """
    a = _parse_version(current)
    b = _parse_version(remote)
    if a is None:
        logger.warning("本地版本无法解析，跳过更新比较: %s", current)
        return 0
    if b is None:
        logger.warning("远程版本无法解析，跳过更新比较: %s", remote)
        return 0
    if a < b:
        return 1
    if a > b:
        return -1
    return 0


def _get_current_version() -> str:
    try:
        from src.version import __version__ as current_version

        return current_version
    except Exception as e:
        logger.warning("解析当前版本失败: %s", e)
        return "0.0.0"


def _request_headers() -> dict[str, str]:
    try:
        from src.version import __version__ as ver
    except Exception:
        ver = "unknown"
    return {
        "Accept": "application/json",
        "Cache-Control": "no-cache",
        "User-Agent": f"WeMediaBaby/{ver}",
    }


async def _get_session() -> aiohttp.ClientSession:
    """进程内复用 HTTP 会话，减少重复 DNS/TCP/TLS。"""
    global _session, _session_lock
    if _session_lock is None:
        _session_lock = asyncio.Lock()
    async with _session_lock:
        if _session is None or _session.closed:
            timeout = aiohttp.ClientTimeout(total=TOTAL_TIMEOUT, connect=CONNECT_TIMEOUT)
            connector = aiohttp.TCPConnector(ttl_dns_cache=300, limit=4)
            _session = aiohttp.ClientSession(timeout=timeout, connector=connector)
    return _session


async def close_update_check_session() -> None:
    """关闭共享会话（应用退出或测试 teardown 时调用）。

    退出阶段事件循环可能正在取消任务，aiohttp 的 close 可能抛出 asyncio.CancelledError
    （不继承 Exception）；此处吞掉并清空引用，避免打断 main.py 后续清理与日志。
    """
    global _session
    sess = _session
    _session = None
    if sess is None or getattr(sess, "closed", True):
        return
    try:
        await sess.close()
    except asyncio.CancelledError:
        logger.debug("更新检查会话关闭被取消（应用退出中，可忽略）")
    except Exception as e:
        logger.warning("关闭更新检查 HTTP 会话异常: %s", e)


def clear_update_check_cache() -> None:
    """清空内存缓存与进行中的单飞任务（测试或排障时调用）。"""
    global _cache_result, _cache_time, _inflight_task
    _cache_result = None
    _cache_time = 0.0
    if _inflight_task is not None and not _inflight_task.done():
        _inflight_task.cancel()
    _inflight_task = None


def _cache_ttl_for(result: UpdateCheckResult) -> float:
    return ERROR_CACHE_TTL_SECONDS if result.error else CACHE_TTL_SECONDS


def _get_cached_result() -> Optional[UpdateCheckResult]:
    global _cache_result, _cache_time
    if _cache_result is None:
        return None
    if time.monotonic() - _cache_time > _cache_ttl_for(_cache_result):
        return None
    return _cache_result


def _set_cached_result(result: UpdateCheckResult) -> None:
    global _cache_result, _cache_time
    _cache_result = result
    _cache_time = time.monotonic()


def _build_result_from_json(data: dict, current_version: str) -> UpdateCheckResult:
    remote_version = (data.get("version") or "").strip()
    if not remote_version:
        return UpdateCheckResult(
            has_update=False,
            current_version=current_version,
            error="版本信息无效",
        )
    logger.debug("更新检查: 当前=%s 远程=%s", current_version, remote_version)

    notes = data.get("notes") or ""
    download_url = (data.get("download_url") or "").strip()
    download_url_feishu = (data.get("download_url_feishu") or "").strip()
    url_to_use = download_url or download_url_feishu
    if not url_to_use:
        url_to_use = DEFAULT_UPDATE_DOWNLOAD_URL

    if _compare_versions(current_version, remote_version) > 0:
        return UpdateCheckResult(
            has_update=True,
            current_version=current_version,
            remote_version=remote_version,
            notes=notes,
            download_url=url_to_use,
        )
    return UpdateCheckResult(
        has_update=False,
        current_version=current_version,
        remote_version=remote_version,
        notes=notes,
        download_url=url_to_use,
    )


async def _fetch_version_json_from_network() -> UpdateCheckResult:
    """从 Gitee 拉取 version.json 并解析（不走缓存）。"""
    current_version = _get_current_version()

    try:
        session = await _get_session()
        async with session.get(
            VERSION_JSON_URL_BASE,
            headers=_request_headers(),
        ) as resp:
            if resp.status != 200:
                return UpdateCheckResult(
                    has_update=False,
                    current_version=current_version,
                    error=f"请求失败: HTTP {resp.status}",
                )
            text = await resp.text()
    except asyncio.TimeoutError:
        return UpdateCheckResult(
            has_update=False,
            current_version=current_version,
            error="检查更新超时，请稍后重试或检查网络",
        )
    except aiohttp.ClientError as e:
        logger.warning("更新检查网络错误: %s", e)
        return UpdateCheckResult(
            has_update=False,
            current_version=current_version,
            error="网络错误，请稍后重试或检查网络",
        )
    except Exception:
        logger.exception("更新检查异常")
        return UpdateCheckResult(
            has_update=False,
            current_version=current_version,
            error="检查更新失败，请稍后重试",
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return UpdateCheckResult(
            has_update=False,
            current_version=current_version,
            error="版本信息解析失败",
        )

    return _build_result_from_json(data, current_version)


async def _fetch_and_cache() -> UpdateCheckResult:
    """拉取网络并写入缓存。"""
    result = await _fetch_version_json_from_network()
    _set_cached_result(result)
    return result


def _ensure_fetch_lock() -> asyncio.Lock:
    global _fetch_lock
    if _fetch_lock is None:
        _fetch_lock = asyncio.Lock()
    return _fetch_lock


async def _fetch_with_inflight_dedup() -> UpdateCheckResult:
    """并发单飞：多路调用共享同一次网络请求。"""
    global _inflight_task

    if not ENABLE_INFLIGHT_DEDUP:
        return await _fetch_and_cache()

    lock = _ensure_fetch_lock()
    async with lock:
        if _inflight_task is not None and not _inflight_task.done():
            task = _inflight_task
        else:
            _inflight_task = asyncio.create_task(_fetch_and_cache())
            task = _inflight_task

    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("更新检查单飞任务异常")
        current_version = _get_current_version()
        return UpdateCheckResult(
            has_update=False,
            current_version=current_version,
            error="检查更新失败，请稍后重试",
        )


async def check_for_updates(force_refresh: bool = False) -> UpdateCheckResult:
    """
    请求 Gitee 上的 version.json，与本地 __version__ 比较，返回更新检查结果。

    Args:
        force_refresh: True 时跳过缓存强制联网（设置页手动检查）；False 时复用缓存。

    可在 qasync 事件循环中直接 await，不阻塞 UI。
    """
    t0 = time.perf_counter()

    if not force_refresh:
        cached = _get_cached_result()
        if cached is not None:
            elapsed = time.perf_counter() - t0
            cache_kind = "error" if cached.error else "ok"
            logger.info(
                "更新检查完成: 耗时=%.2fs 来源=cache 缓存=hit kind=%s",
                elapsed,
                cache_kind,
            )
            return cached

    result = await _fetch_with_inflight_dedup()

    elapsed = time.perf_counter() - t0
    read_cache = "skipped" if force_refresh else "miss"
    logger.info(
        "更新检查完成: 耗时=%.2fs 来源=network read_cache=%s force_refresh=%s error=%s",
        elapsed,
        read_cache,
        force_refresh,
        bool(result.error),
    )
    return result
