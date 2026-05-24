"""
工作台仪表盘快照（内存缓存与分阶段加载共用）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Dict, List


@dataclass
class DashboardSnapshot:
    """工作台一次加载结果；partial=True 表示仅 fast 路径（发布/提醒可能为空）。"""

    account: Dict[str, Any] = field(default_factory=dict)
    publish: Dict[str, Any] = field(default_factory=dict)
    task: Dict[str, Any] = field(default_factory=dict)
    reminders: List[Dict[str, Any]] = field(default_factory=list)
    loaded_at: float = field(default_factory=monotonic)
    partial: bool = False

    def to_legacy_dict(self) -> Dict[str, Any]:
        return {
            "account": self.account,
            "publish": self.publish,
            "task": self.task,
            "account_publish_reminders": self.reminders,
        }

    def to_cache_dict(self) -> Dict[str, Any]:
        """Serialize the UI-facing snapshot shape for cold-start cache files."""
        return {
            "account": self.account,
            "publish": self.publish,
            "task": self.task,
            "reminders": self.reminders,
            "loaded_at": self.loaded_at,
            "partial": self.partial,
        }

    @classmethod
    def from_cache_dict(cls, data: Dict[str, Any]) -> "DashboardSnapshot":
        if not isinstance(data, dict):
            return cls()
        return cls(
            account=data.get("account") if isinstance(data.get("account"), dict) else {},
            publish=data.get("publish") if isinstance(data.get("publish"), dict) else {},
            task=data.get("task") if isinstance(data.get("task"), dict) else {},
            reminders=data.get("reminders") if isinstance(data.get("reminders"), list) else [],
            loaded_at=float(data.get("loaded_at") or monotonic()),
            partial=bool(data.get("partial", False)),
        )

    def merge(self, other: "DashboardSnapshot") -> "DashboardSnapshot":
        """将 slow 路径结果合并到当前快照（保留已加载的 account/task）。"""
        account = other.account if other.account else self.account
        task = other.task if other.task else self.task
        publish = other.publish if other.publish else self.publish
        reminders = other.reminders if other.reminders else self.reminders
        return DashboardSnapshot(
            account=account,
            publish=publish,
            task=task,
            reminders=reminders,
            loaded_at=other.loaded_at,
            partial=False,
        )
