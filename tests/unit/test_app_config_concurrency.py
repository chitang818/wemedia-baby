"""app_config 并发写入串行化（ConfigCenter 写锁）。"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from src.infrastructure.common.config.config_center import ConfigCenter
from src.infrastructure.common.config.app_config_merge import merge_app_config

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_app_config_update_merges_disk_when_value_is_partial():
    """磁盘上已有完整字段时，仅用内存中的部分键 update 不得冲掉磁盘其它键。"""
    with tempfile.TemporaryDirectory() as td:
        cfg_path = Path(td) / "app_config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "chrome_executable_path": "C:/Chrome/chrome.exe",
                    "material_library_root": "D:/media",
                    "enabled_platform_plugins": ["douyin"],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        cc = ConfigCenter(config_dir=td)
        await cc.initialize()
        partial = {"enabled_platform_plugins": ["douyin", "kuaishou", "wechat_video"]}
        await cc.update("app_config", partial)
        on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert on_disk["chrome_executable_path"] == "C:/Chrome/chrome.exe"
        assert on_disk["material_library_root"] == "D:/media"
        assert on_disk["enabled_platform_plugins"] == [
            "douyin",
            "kuaishou",
            "wechat_video",
        ]
        cc.close()


@pytest.mark.asyncio
async def test_concurrent_merge_app_config_preserves_both_patches():
    """两路同时 merge 不同顶层键时，不应出现 lost update。"""
    with tempfile.TemporaryDirectory() as td:
        cc = ConfigCenter(config_dir=td)
        await cc.initialize()
        await cc.update("app_config", {"con_a": 1, "con_b": 1})

        async def patch_a() -> None:
            await merge_app_config(cc, {"con_a": 100})

        async def patch_b() -> None:
            await merge_app_config(cc, {"con_b": 200})

        await asyncio.gather(patch_a(), patch_b())

        app = cc.get_app_config()
        assert app.get("con_a") == 100
        assert app.get("con_b") == 200
