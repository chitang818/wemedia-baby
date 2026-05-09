"""
更新检查服务
文件路径：src/services/update_check_service.py
功能：从 Gitee 拉取 version.json，与本地版本比较，返回是否有更新及下载链接。
下载链接始终从 Gitee 仓库的 version.json 中获取，便于在库中修改下载地址（如改为飞书文档）而无需发版。
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

# 请求超时（秒）
CHECK_TIMEOUT = 10


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
    """
    a = _parse_version(current)
    b = _parse_version(remote)
    if a is None:
        return 1 if b else 0
    if b is None:
        return 0
    if a < b:
        return 1
    if a > b:
        return -1
    return 0


async def check_for_updates() -> UpdateCheckResult:
    """
    请求 Gitee 上的 version.json，与本地 __version__ 比较，返回更新检查结果。
    下载链接从 version.json 的 download_url / download_url_feishu 读取，可在 Gitee 库中随时修改地址。
    可在 qasync 事件循环中直接 await，不阻塞 UI。
    """
    try:
        from src.version import __version__ as current_version
    except Exception as e:
        logger.warning("解析当前版本失败: %s", e)
        current_version = "0.0.0"

    try:
        # 加时间戳避免 Gitee/CDN 缓存导致拿到旧 version.json
        url = f"{VERSION_JSON_URL_BASE}?t={int(time.time())}"
        timeout = aiohttp.ClientTimeout(total=CHECK_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
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
    except Exception as e:
        logger.exception("更新检查异常")
        return UpdateCheckResult(
            has_update=False,
            current_version=current_version,
            error=str(e) or "检查更新失败",
        )

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return UpdateCheckResult(
            has_update=False,
            current_version=current_version,
            error="版本信息解析失败",
        )

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
    # 下载链接始终从 Gitee 的 version.json 获取：优先 download_url（可填飞书文档等），其次 download_url_feishu，未配置时回退到 Gitee releases 页
    url_to_use = download_url or download_url_feishu
    if not url_to_use:
        url_to_use = VERSION_JSON_URL_BASE.replace("/raw/main/version.json", "/releases")

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
