"""
飞书授权配置
文件路径：src/proprietary/services/feishu/feishu_config.py
功能：飞书应用配置（app_id / app_secret）与同步配置的加载与保存
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class FeishuCopywritingSyncConfig:
    """飞书文案库同步配置"""
    spreadsheet_token: str = ""
    spreadsheet_name: str = ""
    sheet_id: str = ""
    sheet_name: str = ""
    field_mapping: Dict[str, str] = None  # 飞书列名 -> 文案库字段名
    last_sync_time: str = ""  # ISO 格式时间
    auto_sync_on_startup: bool = False

    def __post_init__(self):
        if self.field_mapping is None:
            self.field_mapping = {}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "FeishuCopywritingSyncConfig":
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            spreadsheet_token=data.get("spreadsheet_token", "") or "",
            spreadsheet_name=data.get("spreadsheet_name", "") or "",
            sheet_id=data.get("sheet_id", "") or "",
            sheet_name=data.get("sheet_name", "") or "",
            field_mapping=data.get("field_mapping") or {},
            last_sync_time=data.get("last_sync_time", "") or "",
            auto_sync_on_startup=bool(data.get("auto_sync_on_startup", False)),
        )


class FeishuConfig:
    """飞书应用配置管理

    配置来源优先级：
    1. 环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET
    2. config/feishu_config.json 文件
    3. 设置页面用户输入（暂未实现，预留）
    """

    _cache: Optional["FeishuConfig"] = None
    _cache_mtime: float = 0.0

    def __init__(self):
        self.app_id: str = ""
        self.app_secret: str = ""
        self._config_path: Optional[Path] = None

    @property
    def is_app_configured(self) -> bool:
        """应用凭证是否已配置"""
        return bool(self.app_id and self.app_secret)

    @classmethod
    def load(cls) -> "FeishuConfig":
        """加载飞书应用配置"""
        cfg = cls()

        import os
        env_app_id = os.environ.get("FEISHU_APP_ID", "").strip()
        env_app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()

        if env_app_id and env_app_secret:
            cfg.app_id = env_app_id
            cfg.app_secret = env_app_secret
            return cfg

        candidates = [
            Path(__file__).resolve().parents[4] / "config" / "feishu_config.json",
        ]
        for p in candidates:
            if p.is_file():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    cfg.app_id = str(data.get("app_id", "") or "").strip()
                    cfg.app_secret = str(data.get("app_secret", "") or "").strip()
                    cfg._config_path = p
                    if cfg.app_id and cfg.app_secret:
                        return cfg
                except Exception as e:
                    logger.warning("读取 feishu_config.json 失败: %s", e)

        return cfg

    @classmethod
    def get_sync_config(cls) -> FeishuCopywritingSyncConfig:
        """从 app_config 读取文案库同步配置"""
        try:
            from src.infrastructure.common.config.config_center import (
                get_registered_config_center,
            )

            center = get_registered_config_center()
            if center:
                app_cfg = center.get_app_config()
                feishu_cfg = app_cfg.get("feishu_copywriting")
                return FeishuCopywritingSyncConfig.from_dict(feishu_cfg)
        except Exception as e:
            logger.debug("读取飞书同步配置失败: %s", e)

        return FeishuCopywritingSyncConfig()

    @classmethod
    async def save_sync_config(cls, config: FeishuCopywritingSyncConfig) -> bool:
        """保存文案库同步配置到 app_config"""
        try:
            from src.infrastructure.common.config.config_center import (
                get_registered_config_center,
            )
            import copy

            center = get_registered_config_center()
            if not center:
                return False

            app_cfg = center.get_app_config()
            new_cfg = copy.deepcopy(app_cfg)
            new_cfg["feishu_copywriting"] = config.to_dict()
            await center.update("app_config", new_cfg)
            return True
        except Exception as e:
            logger.error("保存飞书同步配置失败: %s", e, exc_info=True)
            return False
