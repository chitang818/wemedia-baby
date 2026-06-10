from __future__ import annotations

import importlib
import sys
from pathlib import Path


MODULES_TO_IMPORT = [
    "src.ui.pages.workspace_page",
    "src.ui.pages.account",
    "src.ui.pages.account_group",
    "src.ui.pages.publish.publish_list_page",
    "src.ui.pages.publish",
    "src.ui.pages.publish.image_single_task_creation_page",
    "src.ui.pages.settings_page",
    "src.ui.pages.material.video_library_page",
    "src.ui.pages.material.image_library_page",
    "src.ui.pages.material.copywriting_library_page",
    "src.ui.pages.material.cart_promotion_page",
    "src.ui.pages.material.group_buy_promotion_page",
    "src.plugins.community.douyin.login_plugin",
    "src.plugins.community.douyin.publish_plugin",
    "src.plugins.community.kuaishou.login_plugin",
    "src.plugins.community.kuaishou.publish_plugin",
    "src.infrastructure.storage.tortoise_manager",
    "src.infrastructure.common.pipeline.publish_pipeline",
    "src.services.account.account_service",
    "src.services.publish.publish_service",
    "src.domain.publish.work_description",
    "src.ui.publish.work_description",
    "PySide6.QtWidgets",
    "qasync",
    "qfluentwidgets",
    "tortoise",
    "aiosqlite",
    "patchright",
    "src.infrastructure.browser.automation_api",
    "src.infrastructure.browser.browser_manager",
    "cryptography",
    "pydantic",
    "aiohttp",
]


def _resource_base() -> Path:
    try:
        from src.infrastructure.common.path_manager import PathManager

        PathManager._resource_dir = None
        return PathManager.get_resource_dir()
    except Exception:
        return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()


def run_smoke_test() -> int:
    print("=" * 60)
    print("  WeMediaBaby smoke test (--smoke-test)")
    print("=" * 60)

    try:
        from config.feature_flags import FeatureFlags

        if hasattr(FeatureFlags, "debug_dist_mode"):
            info = FeatureFlags.debug_dist_mode()
        else:
            info = {"dist_mode": FeatureFlags.get_dist_mode(), "source": ""}
        print(f"  [INFO] dist_mode = {info.get('dist_mode')}  source = {info.get('source')}")
    except Exception as e:
        print(f"  [WARN] dist_mode probe failed: {e}")

    failed: list[tuple[str, str]] = []
    for module_name in MODULES_TO_IMPORT:
        try:
            importlib.import_module(module_name)
            print(f"  [OK] {module_name}")
        except Exception as e:
            failed.append((module_name, str(e)))
            print(f"  [FAIL] {module_name}  ->  {e}")

    try:
        from src.infrastructure.browser.automation_api import ENGINE_NAME, async_playwright

        engine_module = getattr(async_playwright, "__module__", "")
        if ENGINE_NAME != "patchright" or not engine_module.startswith("patchright."):
            raise RuntimeError(
                f"unexpected browser engine: name={ENGINE_NAME}, module={engine_module}"
            )
        print(f"  [OK] browser engine: {ENGINE_NAME} ({engine_module})")
    except Exception as e:
        failed.append(("browser_engine", str(e)))
        print(f"  [FAIL] browser engine -> {e}")

    print()

    base = _resource_base()
    missing_resources: list[str] = []
    for relative in ("config", "resources"):
        path = base / relative
        if path.exists():
            print(f"  [OK] resource dir: {path}")
        else:
            missing_resources.append(str(path))
            print(f"  [MISSING] resource dir: {path}")

    print()
    print("=" * 60)
    total_issues = len(failed) + len(missing_resources)
    if total_issues == 0:
        print("  Smoke test passed. All modules and resources are available.")
        print("=" * 60)
        return 0

    print(f"  Smoke test found {total_issues} issue(s).")
    for module_name, error in failed:
        print(f"    module: {module_name} -> {error}")
    for resource in missing_resources:
        print(f"    missing: {resource}")
    print("=" * 60)
    return 1
