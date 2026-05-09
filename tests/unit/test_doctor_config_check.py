"""EnvironmentDoctor.check_config_files 与用户目录/内置路径解耦。"""

import pytest

from src.infrastructure.common import path_manager as path_manager_mod
from src.infrastructure.monitoring.doctor import CheckStatus, EnvironmentDoctor


@pytest.fixture(autouse=True)
def _reset_resource_dir():
    path_manager_mod.PathManager._resource_dir = None
    yield
    path_manager_mod.PathManager._resource_dir = None


@pytest.mark.asyncio
async def test_check_config_files_no_cwd_relative_paths(tmp_path, monkeypatch):
    user_cfg = tmp_path / "usercfg"
    user_cfg.mkdir(parents=True, exist_ok=True)

    def _get_config_dir():
        return user_cfg

    monkeypatch.setattr(
        path_manager_mod.PathManager,
        "get_config_dir",
        classmethod(lambda cls: _get_config_dir()),
    )

    res_root = tmp_path / "res"
    (res_root / "config" / "platforms").mkdir(parents=True)
    (res_root / "config" / "platforms" / "douyin.json").write_text("{}", encoding="utf-8")
    (res_root / "config" / "selectors_manifest.json").write_text("{}", encoding="utf-8")
    path_manager_mod.PathManager._resource_dir = res_root

    doctor = EnvironmentDoctor()
    results = await doctor.check_config_files()
    by_name = {r.name: r for r in results}

    assert by_name["用户配置目录"].status == CheckStatus.PASS
    assert by_name["用户应用配置"].status == CheckStatus.WARNING
    assert by_name["内置平台配置"].status == CheckStatus.PASS
    assert by_name["选择器清单"].status == CheckStatus.PASS
